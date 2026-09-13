# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""A real `laboratory.ProcessScienceProvider` implementation, backed by a
real `sqlite3.Connection` populated via `ocel.sqlite_store.to_sqlite`
against an already-materialized `OcelLog`.

Closes a real, previously-named gap
(`docs/2026-08-11-van-der-aalst-audit-gap-report.md`): `decision_mining.py`
/ `enhancement.py` / `resource_perspective.py` are real, tested, sqlite-
backed process-science functions with zero real callers -- only the
honest `UnsupportedProcessScienceProvider` default existed. This module is
the mechanical bridge: `OcelLog` (in-memory) -> `sqlite_store.to_sqlite`
(a real, already-proven pipeline -- see `tests/ocel/test_decision_mining.py`
and `tests/ocel/test_wasm4pm_bridge.py`) -> a real `sqlite3.Connection` ->
the three real mining functions -> a real `ProcessObservation`.

This provider is deliberately scoped to **one real, already-materialized
sqlite db path**, supplied at construction -- it never resolves an
arbitrary string ref out of `EnterpriseObservation` into a live connection
(no such resolution mechanism exists, and inventing one here would be a
fabricated capability, not a real one). It observes one real,
already-recorded process; the caller decides which one.

Never raises: a missing file or missing schema (the target sqlite db was
never populated by `to_sqlite`) is a real, honest `UNSUPPORTED`
`ProcessObservation`, matching `UnsupportedProcessScienceProvider`'s own
no-raise convention -- never a crash, per
`.claude/rules/absence-is-not-evidence.md`.
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from autofde_lab.ocel.decision_mining import compatible_solver_set_stability
from autofde_lab.ocel.enhancement import activity_durations, bottleneck_ranking
from autofde_lab.ocel.resource_perspective import handover_of_work
from autofde_lab.reasoning.laboratory import EnterpriseObservation, ProcessObservation

__all__ = ["SqliteProcessScienceProvider"]


def _digest(*parts: str) -> str:
    """Real, deterministic reference digest -- same stdlib-only approach
    `laboratory._digest` uses (not imported directly since it's a private
    name; duplicated rather than exposed across the module boundary)."""
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


class SqliteProcessScienceProvider:
    """Real `ProcessScienceProvider` backed by a real sqlite3.Connection.

    Constructed with `db_path` -- the real sqlite file `sqlite_store.to_sqlite`
    already wrote for some real, already-completed `OcelLog`. Every call to
    `request_process_observation` opens a fresh connection (sqlite
    connections are cheap and this keeps the provider itself immutable and
    thread-safe, matching the read-only, query-only real functions it
    wraps -- none of `decision_mining.py`/`enhancement.py`/
    `resource_perspective.py` ever writes).
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)

    def request_process_observation(self, observation: EnterpriseObservation) -> ProcessObservation:
        # `observation` is accepted for Protocol conformance but not
        # consulted -- this provider is scoped to one real, already-
        # materialized sqlite db path fixed at construction (see module
        # docstring), never resolved from an arbitrary caller-supplied ref.
        del observation
        try:
            conn = sqlite3.connect(str(self._db_path))
            conn.row_factory = sqlite3.Row
        except sqlite3.Error as exc:
            return ProcessObservation(
                evidence_standing="UNSUPPORTED",
                computation_receipt_ref=f"sqlite-connect-failed:{self._db_path}:{exc}",
            )

        try:
            try:
                durations = activity_durations(conn)
                bottlenecks = bottleneck_ranking(conn)
                handovers = handover_of_work(conn)
                stability = compatible_solver_set_stability(conn)
            except sqlite3.Error as exc:
                # A real connection to a file that isn't a real, to_sqlite-
                # written schema (missing tables) -- honest UNSUPPORTED,
                # never a crash and never a fabricated empty result passed
                # off as "observed nothing real".
                return ProcessObservation(
                    evidence_standing="UNSUPPORTED",
                    computation_receipt_ref=f"sqlite-query-failed:{self._db_path}:{exc}",
                )
        finally:
            conn.close()

        # ProcessObservation has no dedicated decision-stability field --
        # named honestly here, not silently dropped and not fabricated
        # into an existing, semantically-wrong bucket. It shares
        # performance_metric_refs with activity_durations, distinguished
        # by the `decision_stability:` prefix.
        performance_metric_refs = tuple(
            f"activity_duration:{d.activity}:count={d.count}:mean_gap_ns={d.mean_gap_ns:.1f}:p95_gap_ns={d.p95_gap_ns:.1f}"
            for d in durations
        ) + tuple(
            f"decision_stability:{s.domain_id}:distinct_solver_sets={s.distinct_solver_sets}:is_deterministic={s.is_deterministic}"
            for s in stability
        )
        bottleneck_refs = tuple(
            f"bottleneck:{b.activity}:mean_gap_ns={b.mean_gap_ns:.1f}:p95_gap_ns={b.p95_gap_ns:.1f}"
            for b in bottlenecks
        )
        object_centric_relation_refs = tuple(
            f"handover:{h.from_solver}->{h.to_solver}:count={h.count}" for h in handovers
        )

        real_signal_found = bool(durations or bottlenecks or handovers or stability)
        evidence_standing = "OBSERVED" if real_signal_found else "UNKNOWN"

        return ProcessObservation(
            performance_metric_refs=performance_metric_refs,
            bottleneck_refs=bottleneck_refs,
            object_centric_relation_refs=object_centric_relation_refs,
            evidence_standing=evidence_standing,
            computation_receipt_ref=_digest(
                str(self._db_path),
                str(len(durations)),
                str(len(bottlenecks)),
                str(len(handovers)),
                str(len(stability)),
            ),
        )
