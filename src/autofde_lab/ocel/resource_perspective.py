# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Organizational / resource-perspective mining -- van der Aalst's who/what
performs which activity dimension, orthogonal to the control-flow discovery
in :mod:`autofde_lab.ocel.wasm4pm_bridge` and the performance mining in
:mod:`autofde_lab.ocel.enhancement`, and not previously present in this repo
in any form.

No new capture code, no schema change: :mod:`autofde_lab.ocel.queries`'s
``solver_timeout_rates`` already proves ``Solver`` objects are real, linked
``resource``-perspective objects on ``decision_solve`` events (via
``event_object_links``), not just case (``Domain``) or trace (``MCPSession``)
objects. This module treats ``Solver`` as the resource dimension -- the same
role ``solver_timeout_rates`` already gives it -- and mines *handover of
work*: how often, within one session's ordered trace, two consecutive
resource-linked events were handled by two *different* solvers.

Convention: only consecutive event pairs where both events resolve to a
``Solver`` object are counted (an event with no linked ``Solver``, e.g.
``decision_catalog``, contributes no handover edge on either side of it,
matching :mod:`autofde_lab.ocel.enhancement`'s treatment of activities with
no measurable "next step"). Per-session ordering reuses
:func:`autofde_lab.ocel.queries.session_event_order`, the same primitive
:mod:`autofde_lab.ocel.enhancement` and :mod:`autofde_lab.ocel.wasm4pm_bridge`
already share.

Like ``ocel/enhancement.py`` and ``ocel/wasm4pm_bridge.py``, this only
computes and reports -- no actuation, no admission, no receipt semantics.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from autofde_lab.ocel.queries import all_session_ids, session_event_order

__all__ = ["HandoverEdge", "handover_of_work"]


@dataclass(frozen=True)
class HandoverEdge:
    from_solver: str
    to_solver: str
    count: int


def _solver_for_event(conn: sqlite3.Connection, event_id: str) -> str | None:
    """The ``Solver`` object id linked to ``event_id``, or ``None`` if the
    event has no linked ``Solver`` (e.g. ``decision_catalog``/``decision_match``
    events, which link ``MCPSession``/``Domain`` objects but no ``Solver``).

    Same join ``solver_timeout_rates`` already runs (``event_object_links``
    joined against ``objects WHERE object_type = 'Solver'``), scoped to one
    event instead of aggregated across the corpus.
    """
    row = conn.execute(
        """
        SELECT o.id AS solver_id
        FROM event_object_links AS eol
        JOIN objects AS o ON o.id = eol.object_id
        WHERE eol.event_id = ? AND o.object_type = 'Solver'
        """,
        (event_id,),
    ).fetchone()
    return row["solver_id"] if row is not None else None


def handover_of_work(conn: sqlite3.Connection) -> list[HandoverEdge]:
    """Real solver-to-solver handover counts across the whole recorded corpus.

    For each session (:func:`all_session_ids`), each consecutive pair of
    events in timestamp order (:func:`session_event_order`) where both
    resolve to a ``Solver`` object and those solvers differ, count one
    handover from the earlier solver to the later one. Sorted by count
    descending, matching :func:`autofde_lab.ocel.enhancement.bottleneck_ranking`'s
    convention.
    """
    counts: dict[tuple[str, str], int] = {}
    for session_id in all_session_ids(conn):
        ordered = session_event_order(conn, session_id)
        for prev_row, next_row in zip(ordered, ordered[1:]):
            prev_solver = _solver_for_event(conn, prev_row["event_id"])
            next_solver = _solver_for_event(conn, next_row["event_id"])
            if prev_solver is None or next_solver is None:
                continue
            if prev_solver == next_solver:
                continue
            key = (prev_solver, next_solver)
            counts[key] = counts.get(key, 0) + 1

    edges = [
        HandoverEdge(from_solver=from_id, to_solver=to_id, count=count)
        for (from_id, to_id), count in counts.items()
    ]
    edges.sort(key=lambda edge: edge.count, reverse=True)
    return edges
