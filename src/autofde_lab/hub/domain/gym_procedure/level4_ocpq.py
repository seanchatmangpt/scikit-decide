# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Query the Level 4 OCEL log with wasm4pm's real OCPQ query engine.

:func:`build_level4_ocel` (``level4_ocel.py``) builds a real, receipt-derived
OCEL 2.0 log over the chain vocabulary -- ``AuthorityAdmitted`` /
``ActuationOpened`` / ``ActuationClosed`` / ``PostconditionObserved`` /
``PostconditionVerified`` / ``ReceiptEmitted`` events, real O2O edges -- and
persists it. Nothing in this repo queried that log with a real
object-centric process query engine: it was read only by ad hoc Python
(label extraction, absence-reason bookkeeping).

This module wires a real query in. It calls ``wasm4pm``'s native OCPQ
engine (``wasm4pm-bindings-py``, PyO3 bindings over
``wasm4pm/src/ocpq_runtime.rs`` -- the engine reachable from
``evaluate_ocpq`` in the published Python binding surface, i.e. the
`ocpq_runtime`/`ocpq_parser` engine, not a re-implementation of it in
Python. The verdict returned is exactly what the Rust engine computed;
nothing here re-derives pass/fail from the OCEL log itself.

The query, and why it is scoped by ``Task`` and not by ``Actuation``
--------------------------------------------------------------------
The original intent was to scope this per ``Actuation`` object ("the same
actuation object"). Running the real query that way against a real executed
trial's log (see ``tests/test_level4_ocpq.py``) surfaced a real fact about
``build_level4_ocel``'s own E2O linking, not a bindings bug: an
``ActuationOpened``/``ActuationClosed`` event's relationships include the
``Actuation`` object, but a ``PostconditionObserved`` event's relationships
include the ``PostconditionObservation`` object and the *receipt that
carries the verification*, not the ``Actuation`` object -- the
actuation<->observation relation is recorded only as an **O2O** edge
(``observes_actuation``), which this engine's ``SAME OBJECT`` scope (an
E2O-relationship partition, per ``wasm4pm/src/ocpq_runtime.rs::evaluate``'s
``events_by_object`` construction) does not traverse. Scoping by
``Actuation`` therefore always denies, for every trial, regardless of
whether a postcondition was really observed -- not because the log is
wrong, but because that scope asks a question the log's E2O structure
cannot answer. Real, not fabricated: this is what the actual engine found
in the actual first run (see the module's history in this repo).

The query built here instead uses the object type every event in a single
Level 4 trial's log genuinely shares by E2O relationship -- ``Task`` (one
per built log; see ``build_level4_ocel``, which links ``(task_id, "task")``
onto every event it appends) -- so the constraint the real engine checks is:
**every** ``ActuationOpened`` in the trial must be followed, later in that
trial's real receipt-ordered event history, by **some** ``PostconditionObserved``:

    REQUIRE PostconditionObserved AFTER ActuationOpened ON SAME OBJECT OF TYPE "Task"

(``OcpqRelation::After`` -- see ``wasm4pm/src/ocpq_runtime.rs::check_relation``
-- means "for every occurrence of the right-hand activity, a subsequent
occurrence of the left-hand activity must exist"; ``SAME OBJECT OF TYPE``
partitions the log's events by shared object before checking.) The engine's
own violation strings name the exact object and event that broke the
constraint; this module does not re-word or re-classify them.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from autofde_lab.hub.domain.gym_procedure.level4_ocel import Level4Ocel, build_level4_ocel

__all__ = [
    "OCPQ_SCOPE_OBJECT_TYPE",
    "OCPQ_POSTCONDITION_FOLLOWS_ACTUATION_QUERY",
    "OcpqUnavailable",
    "ActuationPostconditionVerdict",
    "wasm4pm_ocpq_available",
    "run_actuation_postcondition_query",
    "query_level4_ocel_dir",
]

#: The OCEL 2.0 object type every event ``build_level4_ocel`` appends links
#: by E2O relationship (``(task_id, "task")`` is in every ``opened``/``base``
#: link list) -- see the module docstring above for why this, and not
#: ``"Actuation"``, is the scope the real query below uses.
OCPQ_SCOPE_OBJECT_TYPE = "Task"

#: Real wasm4pm OCPQ surface-syntax query (``wasm4pm/src/ocpq_parser.rs``
#: grammar): for every ``Task`` object (one per built Level 4 log), every
#: ``ActuationOpened`` event must be followed, later in that trial's real
#: event sequence, by a ``PostconditionObserved`` event.
OCPQ_POSTCONDITION_FOLLOWS_ACTUATION_QUERY = (
    'REQUIRE PostconditionObserved AFTER ActuationOpened '
    f'ON SAME OBJECT OF TYPE "{OCPQ_SCOPE_OBJECT_TYPE}"'
)


class OcpqUnavailable(RuntimeError):
    """Raised when the native ``wasm4pm`` OCPQ bindings are not importable.

    Never caught to fabricate a result: callers that need a real verdict let
    this propagate; callers that only want to skip (e.g. tests) catch it
    explicitly and skip, they do not substitute a Python re-implementation.
    """


def wasm4pm_ocpq_available() -> bool:
    """True iff the real native ``wasm4pm._native`` extension is importable."""
    try:
        import wasm4pm  # noqa: F401
    except ImportError:
        return False
    return True


@dataclass(frozen=True)
class ActuationPostconditionVerdict:
    """The real per-query verdict returned by wasm4pm's OCPQ engine.

    ``status`` and ``violations`` are copied verbatim from the engine's
    ``OcpqVerdict`` JSON (``wasm4pm::ocpq_runtime::OcpqVerdict``) --
    ``status`` is ``"Allow"`` (constraint holds everywhere in scope) or
    ``"Deny"`` (at least one violation), and each violation string names the
    exact object id and event id the engine found unsatisfied.
    """

    status: str
    violations: tuple[str, ...]
    query: str
    ocel_event_count: int
    ocel_object_count: int

    @property
    def passed(self) -> bool:
        return self.status == "Allow"

    def violated_scope_object_ids(self) -> tuple[str, ...]:
        """Object ids named in a ``"Object <id> - ..."`` violation string.

        Parses only the engine's own prefix convention
        (``wasm4pm::ocpq_runtime::evaluate``'s ``SameObject`` branch: every
        violation is reformatted as ``f"Object {obj_id} - {msg}"`` before
        being appended) -- this does not re-derive which objects failed by
        re-walking the OCEL log; it reads the engine's own labeling of its
        own result.
        """
        ids: list[str] = []
        for v in self.violations:
            if v.startswith("Object "):
                rest = v[len("Object "):]
                obj_id, _, _ = rest.partition(" - ")
                if obj_id and obj_id not in ids:
                    ids.append(obj_id)
        return tuple(ids)


def run_actuation_postcondition_query(
    level4: Level4Ocel,
    *,
    query: str = OCPQ_POSTCONDITION_FOLLOWS_ACTUATION_QUERY,
) -> ActuationPostconditionVerdict:
    """Run a real wasm4pm OCPQ query against an already-built Level 4 log.

    ``level4`` is the return value of :func:`build_level4_ocel` -- the log
    it carries (``level4.log``) is projected to the same OCEL 2.0 JSON dict
    ``_persist_level4_ocel`` writes to disk (:meth:`OcelLog.to_ocel2_json`)
    and handed to the native engine as-is; nothing is re-shaped or
    re-summarized on the way in.

    Raises :class:`OcpqUnavailable` if the native ``wasm4pm`` extension is
    not importable -- never returns a fabricated verdict in that case.
    """
    try:
        import wasm4pm
    except ImportError as exc:
        raise OcpqUnavailable(
            "wasm4pm (wasm4pm-bindings-py native extension) is not importable; "
            "build it with `maturin build --release` in "
            "wasm4pm/crates/wasm4pm-bindings-py and install the wheel to run "
            "real OCPQ queries"
        ) from exc

    ocel_doc = level4.log.to_ocel2_json()
    ocel_json = json.dumps(ocel_doc)

    verdict_json = wasm4pm.evaluate_ocpq(ocel_json, query)
    verdict: dict[str, Any] = json.loads(verdict_json)

    return ActuationPostconditionVerdict(
        status=str(verdict["status"]),
        violations=tuple(str(v) for v in verdict.get("violations", [])),
        query=query,
        ocel_event_count=len(ocel_doc.get("events", [])),
        ocel_object_count=len(ocel_doc.get("objects", [])),
    )


def query_level4_ocel_dir(
    evidence_dir: Path,
    *,
    query: str = OCPQ_POSTCONDITION_FOLLOWS_ACTUATION_QUERY,
) -> ActuationPostconditionVerdict:
    """Build the Level 4 OCEL log for ``evidence_dir`` and run the real OCPQ
    query against it in one call -- the convenience path a caller who has
    only the evidence directory (not an already-built :class:`Level4Ocel`)
    uses.
    """
    level4 = build_level4_ocel(evidence_dir)
    return run_actuation_postcondition_query(level4, query=query)
