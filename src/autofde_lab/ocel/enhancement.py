# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Performance mining -- van der Aalst's third process-mining pillar
(discovery / conformance checking / **enhancement**), not previously present
in this repo in any form (hand-rolled or via ``wasm4pm``).

Every ``events`` row already carries a real ``timestamp_ns`` (written by
:mod:`autofde_lab.ocel.mcp_instrumentation` at the moment each MCP tool call
completed) -- this module adds no new capture code and no new schema. It
answers a real performance-mining question directly from data that has been
sitting unused in :mod:`autofde_lab.ocel.sqlite_store`'s schema since
:mod:`autofde_lab.ocel.queries` was written: *how long does the real system
wait between one MCP tool call finishing and the next one starting, per
activity, and which step is the bottleneck?*

Convention (van der Aalst, performance-mining chapter of *Process Mining:
Data Science in Action*): a "gap" is attributed to the activity that
*precedes* it -- the step that made the next one wait. Computed per session
(gaps are only meaningful within one ordered trace, never across sessions)
via :func:`autofde_lab.ocel.queries.session_event_order`, the same ordering
primitive :mod:`autofde_lab.ocel.wasm4pm_bridge` already reuses.

Like ``ocel/powl_replay.py`` and ``ocel/wasm4pm_bridge.py``, this only
computes and reports -- no actuation, no admission, no receipt semantics.
"""

from __future__ import annotations

import sqlite3
import statistics
from dataclasses import dataclass

from autofde_lab.ocel.queries import all_session_ids, session_event_order

__all__ = ["ActivityDuration", "activity_durations", "bottleneck_ranking"]


@dataclass(frozen=True)
class ActivityDuration:
    activity: str
    count: int
    mean_gap_ns: float
    p95_gap_ns: float


def _gaps_by_preceding_activity(conn: sqlite3.Connection) -> dict[str, list[int]]:
    gaps: dict[str, list[int]] = {}
    for session_id in all_session_ids(conn):
        ordered = session_event_order(conn, session_id)
        for prev_row, next_row in zip(ordered, ordered[1:]):
            gap_ns = next_row["timestamp_ns"] - prev_row["timestamp_ns"]
            gaps.setdefault(prev_row["activity"], []).append(gap_ns)
    return gaps


def activity_durations(conn: sqlite3.Connection) -> list[ActivityDuration]:
    """Real per-activity wait-before-next-step statistics.

    For each activity that was directly followed by another event within the
    same session, real ``count``/``mean_gap_ns``/``p95_gap_ns`` across every
    such occurrence in the whole recorded corpus. An activity that only ever
    appeared as the last event in its session (nothing followed it) is
    absent -- there is no "gap after" to measure.
    """
    gaps = _gaps_by_preceding_activity(conn)
    results = []
    for activity, values in gaps.items():
        sorted_values = sorted(values)
        p95_index = min(len(sorted_values) - 1, int(round(0.95 * (len(sorted_values) - 1))))
        results.append(
            ActivityDuration(
                activity=activity,
                count=len(values),
                mean_gap_ns=statistics.fmean(values),
                p95_gap_ns=float(sorted_values[p95_index]),
            )
        )
    results.sort(key=lambda row: row.activity)
    return results


def bottleneck_ranking(conn: sqlite3.Connection) -> list[ActivityDuration]:
    """:func:`activity_durations`, sorted slowest-mean-gap first.

    "Which step between two recorded MCP tool calls costs the most real
    wall-clock time" -- answered directly, not inferred.
    """
    return sorted(activity_durations(conn), key=lambda row: row.mean_gap_ns, reverse=True)
