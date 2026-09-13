"""Control-flow conformance of a real Level 4 trial against a *committed* intended model.

What this answers
-----------------
"Did the observed episode follow the intended Level 4 procedure?" — measured by real
token-based replay in the real ``wpm`` binary (``wasm4pm``), against a Petri net that is
**committed to disk and thereafter fixed**: :data:`INTENDED_MODEL_PATH`
(``ontology/level4-intended-process.pnml``).

How the committed model was produced
------------------------------------
By running ``wpm mining discover --algo ilp-petri-net`` over a **hand-authored golden
log** (:data:`GOLDEN_LOG_PATH`, ``ontology/level4-golden-trace.json``) — six hand-written
variants of the intended chain, exercising the ``ProbeExecuted+``, ``PlanConstructed+``
and actuation-cycle repetitions. That output was then committed. **It is now fixed**: it
is *not* re-mined, and the model under test is never derived from the log under test.

This is deliberate. :func:`autofde_lab.ocel.wasm4pm_bridge.discover_and_check` mines the
model from the very log it then scores, so its fitness is near-tautological — it measures
"can the ILP miner fit this log", not "did this episode conform to what we intended".
Nothing in this module calls it.

The honest ceiling — what a high number here does NOT mean
---------------------------------------------------------
This measures **activity-sequence fitness only.**

* The wasm4pm log format this feeds (see
  :func:`autofde_lab.ocel.wasm4pm_bridge.session_traces_to_wasm4pm_json`, and
  :func:`level4_trace_to_wasm4pm_json` below, which follows it) keeps **only**
  ``concept:name``. Every object, every event-to-object qualifier, every O2O edge, and
  every attribute is dropped on the way in.
* Therefore this **cannot** establish that the ``ActuationClosed`` which occurred is the
  closure of the ``ActuationOpened`` whose authority was admitted, nor that the receipt
  emitted refers to that same actuation. A trace can score perfectly while every
  object-identity join in it is dangling or crossed.
* Object-identity conformance is the SHACL layer's job (see
  ``autofde_lab.fabric.shacl_conformance``, which runs real ``pyshacl`` against committed
  shapes). **A high fitness score here is not Level 4 standing**, and must never be
  reported as one. It is one necessary, far-from-sufficient control-flow check.

Two measured defects you must know before reading any number from here
----------------------------------------------------------------------
Both were established this session by real runs, not by reading code alone.

1. **``wpm mining discover`` mislabels two of its printed metrics.**
   ``wasm4pm/src/ilp_discovery.rs`` ends ``build_ilp_petri_net`` with
   ``(petri_net, fitness, precision)``, while
   ``crates/wasm4pm-cli/src/commands/mining.rs:111`` binds it as
   ``let (net, simplicity, fitness) = discover_ilp_petri_net_from_log(...)``. So the row
   printed as **"Simplicity" is really token-replay fitness**, and the row printed as
   **"Fitness (self)" is really precision** (from ``calculate_precision``, a *different*
   implementation than the ETConformance ``compute_precision`` that ``conformance``
   reports). ``compute_simplicity`` is never called on this code path. Consequently
   :class:`autofde_lab.ocel.wasm4pm_bridge.DiscoveryResult`'s ``simplicity`` and
   ``self_fitness`` fields are both misnamed — they read those two mislabeled rows. The
   fields are left named as-is here to avoid a rename cascade through existing callers;
   :func:`golden_model_metric_swap_witness` pins the swap so it cannot change silently.

2. **The committed model does not replay its own golden log perfectly.**
   ``wpm mining conformance`` scores the golden log against the net mined *from that
   same golden log* at avg fitness **0.8685**, not 1.0, with a constant 2 missing / 3
   remaining tokens on every trace — a source/sink boundary artifact of the ILP miner's
   net. **1.0 is therefore not the reachable ceiling.** Any trial number must be read
   against :func:`golden_baseline`, which recomputes that ceiling by real subprocess at
   call time rather than hardcoding it. Comparing a trial to 1.0 would understate
   conformance; comparing it to the golden baseline is the honest comparison.

What the measured trial numbers actually say
--------------------------------------------
Measured this session over the ten ``docs/evidence/crown1/attempt4/realtrial_*`` dirs:
trial avg fitness **0.7825** against a golden ceiling of **0.8685** (ratio 0.901),
**0 / 10** conforming cases. The dominant cause is not subtle deviation, it is
**truncation**: only three of the ten trials reach ``ReplayCompleted``; three stop at
``PlanConstructed`` and four stop at ``ProbeExecuted`` after 3-4 events. The two
lowest-scoring cases (0.45, 0.619) are those short trials. ``AuthorityAdmitted`` is never
emitted by any trial — ``build_level4_ocel`` reports it absent — so the intended
``POWLCommitted -> AuthorityAdmitted -> ActuationOpened`` edge is unobserved in every case.
That is a finding about the trials, not about this measurement.

Tie-breaking, and why the default is the unflattering one
---------------------------------------------------------
:func:`autofde_lab.hub.domain.gym_procedure.level4_ocel.build_level4_ocel` emits
``ActuationOpened``, ``ActuationClosed`` and ``ReceiptEmitted`` for one receipt at the
**identical** ``timestamp_ns`` (they inherit the source OCEL event's timestamp). The
intra-receipt order is therefore genuinely **UNKNOWN from the trace itself** — it is not
recorded. It is not "correct" and it is not "wrong"; it is absent, and per
``.claude/rules/absence-is-not-evidence.md`` absence is not resolved by assumption.

Two tie-breaks are offered and both are real:

* ``"id"`` (**the default**) — break ties on the event id, which is neutral with respect
  to the model. On real trials this happens to place ``ActuationClosed`` before
  ``ActuationOpened``, and the resulting misfit is reported rather than removed.
* ``"chain"`` — break ties on position in
  :data:`~autofde_lab.hub.domain.gym_procedure.level4_ocel.LEVEL4_EVENT_TYPES`. This
  orders the tied events **into** the shape the model expects, so it is
  **model-biased by construction and its fitness is not evidence of conformance.** It is
  exposed only as a diagnostic, to separate "how much of the misfit is the missing
  intra-receipt ordering" from "how much is real deviation". Never report a ``"chain"``
  number as a conformance result.
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Literal, Sequence

from autofde_lab.ocel.wasm4pm_bridge import (
    ACTIVITY_KEY,
    ConformanceReport,
    check_conformance,
    discover_petri_net,
    resolve_wpm_binary,
)

__all__ = [
    "GOLDEN_LOG_PATH",
    "INTENDED_MODEL_PATH",
    "Level4FitnessResult",
    "TieBreak",
    "check_trial_fitness",
    "golden_baseline",
    "golden_model_metric_swap_witness",
    "level4_trace_to_wasm4pm_json",
    "trial_activity_sequence",
]

_ONTOLOGY = Path(__file__).resolve().parents[3] / "ontology"

#: The committed intended Level 4 process model. Fixed — never re-mined at runtime.
INTENDED_MODEL_PATH: Path = _ONTOLOGY / "level4-intended-process.pnml"

#: The hand-authored golden log the committed model was mined from, kept so the
#: derivation is auditable and :func:`golden_baseline` is reproducible.
GOLDEN_LOG_PATH: Path = _ONTOLOGY / "level4-golden-trace.json"

TieBreak = Literal["id", "chain"]


@dataclass(frozen=True)
class Level4FitnessResult:
    """A real conformance report plus the golden ceiling it must be read against."""

    report: ConformanceReport
    baseline: ConformanceReport
    tie_break: TieBreak

    case_ids: tuple[str, ...]
    """Evidence-directory names, in the order they were written into the log.

    ``wpm`` reports ``TraceDeviation.case_id`` as the **positional index** of the trace,
    not the trace's ``concept:name`` attribute, so a deviation with ``case_id="3"`` is
    ``case_ids[3]``. Kept explicit rather than inferred, since a silent off-by-one here
    would misattribute a deviation to the wrong trial.
    """

    @property
    def fitness_vs_baseline(self) -> float:
        """Trial avg fitness as a fraction of the golden log's own avg fitness.

        Not a conformance verdict on its own — see this module's docstring for why
        ``1.0`` is unreachable and what this measurement structurally cannot see.
        """
        if self.baseline.avg_fitness == 0.0:
            raise ZeroDivisionError(
                "golden baseline avg_fitness is 0.0 -- the committed model does not "
                "replay its own golden log at all; the baseline is UNKNOWN, not 1.0"
            )
        return self.report.avg_fitness / self.baseline.avg_fitness


def _string_attr(key: str, value: str) -> dict:
    return {"key": key, "value": {"type": "String", "content": value}, "own_attributes": None}


def level4_trace_to_wasm4pm_json(cases: Sequence[tuple[str, Sequence[str]]]) -> dict:
    """Build a ``wasm4pm-compat::event_log::EventLog`` document from activity names.

    ``cases`` is ``[(case_id, [activity, ...]), ...]``. Shape follows
    :func:`autofde_lab.ocel.wasm4pm_bridge.session_traces_to_wasm4pm_json` exactly; the
    difference is only the source of the sequence (a Level 4 evidence directory rather
    than a session-scoped SQLite OCEL store). Only ``concept:name`` survives — see the
    module docstring's ceiling section.
    """
    return {
        "attributes": [],
        "traces": [
            {
                "attributes": [_string_attr(ACTIVITY_KEY, case_id)],
                "events": [
                    {"attributes": [_string_attr(ACTIVITY_KEY, activity)]}
                    for activity in activities
                ],
            }
            for case_id, activities in cases
        ],
        "extensions": None,
        "classifiers": None,
        "global_trace_attrs": None,
        "global_event_attrs": None,
    }


def trial_activity_sequence(
    evidence_dir: Path, *, tie_break: TieBreak = "id"
) -> list[str]:
    """The real Level 4 activity sequence a trial left on disk, in observed order.

    Built by :func:`~autofde_lab.hub.domain.gym_procedure.level4_ocel.build_level4_ocel`
    from the trial's own artifacts — nothing is synthesised here. See the module
    docstring on ``tie_break``: ``"chain"`` is model-biased and is a diagnostic only.
    """
    from autofde_lab.hub.domain.gym_procedure.level4_ocel import (
        LEVEL4_EVENT_TYPES,
        build_level4_ocel,
    )

    built = build_level4_ocel(Path(evidence_dir))
    if tie_break == "id":
        ordered = sorted(built.log.events, key=lambda e: (e.timestamp_ns, e.id))
    elif tie_break == "chain":
        order = {name: i for i, name in enumerate(LEVEL4_EVENT_TYPES)}
        ordered = sorted(
            built.log.events,
            key=lambda e: (e.timestamp_ns, order.get(e.activity, len(order)), e.id),
        )
    else:  # pragma: no cover - Literal-typed, but a wrong string must not pass silently
        raise ValueError(f"UNKNOWN_TIE_BREAK: {tie_break!r} (expected 'id' or 'chain')")
    return [e.activity for e in ordered]


async def _conformance_of(cases: Sequence[tuple[str, Sequence[str]]], *, timeout_s: float) -> ConformanceReport:
    with tempfile.TemporaryDirectory(prefix="level4_fitness_") as tmp:
        log_path = Path(tmp) / "log.json"
        log_path.write_text(json.dumps(level4_trace_to_wasm4pm_json(cases)))
        return await check_conformance(
            log_path, INTENDED_MODEL_PATH, timeout_s=timeout_s
        )


async def golden_baseline(*, timeout_s: float = 60.0) -> ConformanceReport:
    """Replay the committed golden log against the committed model, for real.

    This is the reachable ceiling, recomputed by real subprocess rather than hardcoded —
    see defect 2 in the module docstring for why it is **not** 1.0.
    """
    if not INTENDED_MODEL_PATH.is_file():
        raise FileNotFoundError(f"NO_COMMITTED_MODEL: {INTENDED_MODEL_PATH}")
    if not GOLDEN_LOG_PATH.is_file():
        raise FileNotFoundError(f"NO_GOLDEN_LOG: {GOLDEN_LOG_PATH}")
    return await check_conformance(GOLDEN_LOG_PATH, INTENDED_MODEL_PATH, timeout_s=timeout_s)


async def check_trial_fitness(
    evidence_dirs: Iterable[Path],
    *,
    tie_break: TieBreak = "id",
    timeout_s: float = 120.0,
) -> Level4FitnessResult:
    """Score real trial evidence directories against the committed intended model.

    One case per evidence directory. Runs the real ``wpm`` binary twice: once for the
    trials, once for the golden baseline they must be read against.
    """
    if not INTENDED_MODEL_PATH.is_file():
        raise FileNotFoundError(f"NO_COMMITTED_MODEL: {INTENDED_MODEL_PATH}")
    resolve_wpm_binary()  # fail loudly and early rather than mid-way through the pair

    cases: list[tuple[str, list[str]]] = []
    for d in evidence_dirs:
        d = Path(d)
        cases.append((d.name, trial_activity_sequence(d, tie_break=tie_break)))
    if not cases:
        raise ValueError("NO_EVIDENCE_DIRS: refusing to report conformance over zero cases")

    report = await _conformance_of(cases, timeout_s=timeout_s)
    baseline = await golden_baseline(timeout_s=timeout_s)
    return Level4FitnessResult(
        report=report,
        baseline=baseline,
        tie_break=tie_break,
        case_ids=tuple(c for c, _ in cases),
    )


async def golden_model_metric_swap_witness(*, timeout_s: float = 60.0) -> tuple[float, float]:
    """Witness defect 1: ``discover``'s "Simplicity" IS ``conformance``'s avg fitness.

    Returns ``(discover_simplicity_row, conformance_avg_fitness)`` from two real ``wpm``
    invocations over the committed golden log. They are equal **because the CLI
    destructures the miner's ``(net, fitness, precision)`` return as
    ``(net, simplicity, fitness)``** — not because simplicity and fitness coincide.
    Pinned by a test so an upstream fix surfaces as a failure rather than as a silently
    changed number.
    """
    with tempfile.TemporaryDirectory(prefix="level4_swap_") as tmp:
        discovery = await discover_petri_net(
            GOLDEN_LOG_PATH, output_path=Path(tmp) / "remined.pnml", timeout_s=timeout_s
        )
    baseline = await golden_baseline(timeout_s=timeout_s)
    return discovery.simplicity, baseline.avg_fitness
