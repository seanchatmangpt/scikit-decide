# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""The dogfood loop: reading this system's own verified episodes back in.

``Level4AliveEvidence`` -> durable OCEL 2.0 -> divergence measurement ->
typed advisory *observations*. Every function here is a **reader**. Nothing
in this module opens an environment, runs a planner, actuates, or changes any
live decision path -- using these observations to alter behaviour is a
separate, later decision that this module deliberately does not take.

What "honest" means concretely here
-----------------------------------
Absence is not evidence (``.claude/rules/absence-is-not-evidence.md``). A
trial directory that never reached actuation has no episode OCEL; a trial
whose crown run was not archived has no observed final state. In both cases
the answer is a typed :class:`Unknown` naming the **exact absent artifact by
path**, never an empty dict, an empty list, or a zero count that a caller
could read as "checked, nothing wrong found".

Calibration is refused below :data:`MIN_EPISODES_FOR_RANKING` episodes.
:func:`advisory_signals` always carries ``n_episodes`` and, below that floor,
emits ``ranking_refused`` with the reason rather than an ordering. Three
episodes do not calibrate a planner portfolio; saying so is the function's
job, not the caller's.

The highest-value signal
------------------------
:func:`compare_discovered_model_vs_observed` measures *the induced model's own
error*: for each committed action, what the :class:`TypedDomain` induced from
the trial's probes predicted, against what the execution's receipts and OCEL
events actually recorded. A model that was wrong and got away with it is the
one thing no green verdict in the trial itself can surface.

Sources read, all durable, all written by the existing producer
---------------------------------------------------------------
``<trial>/typed_probe_log.json``      -- probe records (induction input)
``<trial>/federation.json``           -- per-planner candidate outcomes
``<trial>/actuation/commitment.ttl``  -- the committed plan sequence + digests
``<trial>/actuation/episode.ocel.json``-- the episode's OCEL 2.0 document
``<trial>/actuation/receipts.sqlite3``-- the receipt evidence ledger
``<parent>/crown_run.json``           -- observed final state / goal verdict
"""

from __future__ import annotations

import ast
import json
import re
import sqlite3
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

from autofde_lab.ocel.log import OcelLog
from autofde_lab.ocel.refusals import OcelError
from autofde_lab.hub.domain.gym_procedure.typed_induction import (
    TypedDomain,
    induce_typed_domain,
)

__all__ = [
    "MIN_EPISODES_FOR_RANKING",
    "Unknown",
    "EpisodeOcel",
    "ActionDivergence",
    "ModelObservationDivergence",
    "PlannerCandidate",
    "CandidateComparison",
    "DisagreementRecord",
    "AdvisorySignals",
    "ingest_episode",
    "compare_discovered_model_vs_observed",
    "compare_candidates_vs_committed",
    "record_disagreement",
    "advisory_signals",
]

#: Below this many *verified* episodes, :func:`advisory_signals` refuses to
#: emit any ordering. N=1 and N=3 are anecdotes; calling either "calibration"
#: is the failure this constant exists to make impossible.
MIN_EPISODES_FOR_RANKING = 5

#: OCEL event type carrying the independent final-goal verification. Mirrors
#: ``crown_evidence.GOAL_CONSEQUENCE_EVENT_TYPE`` -- restated rather than
#: imported so this reader does not drag in ``gymact``, which is an optional
#: dependency and absent in a plain checkout.
GOAL_CONSEQUENCE_EVENT_TYPE = "verify_goal_consequence"


# ---------------------------------------------------------------------------
# typed absence
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Unknown:
    """Observation was insufficient -- and this says exactly why.

    ``absent`` holds real paths (or named fields) that were looked for and not
    found. An ``Unknown`` is never returned for "looked, found nothing wrong":
    that case gets a real result record with zero findings and a non-empty
    ``sources``.
    """

    question: str
    absent: tuple[str, ...]
    detail: str
    status: str = "UNKNOWN"

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "question": self.question,
            "absent": list(self.absent),
            "detail": self.detail,
        }


def _absent(question: str, paths: Sequence[Path | str], detail: str) -> Unknown:
    return Unknown(question=question, absent=tuple(str(p) for p in paths), detail=detail)


# ---------------------------------------------------------------------------
# 1. ingest
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EpisodeOcel:
    """One verified episode's durable OCEL 2.0 log, parsed and checked."""

    trial_dir: str
    run_id: str
    source: str
    log: OcelLog
    n_events: int
    n_objects: int
    activity_counts: dict[str, int]
    digest: str
    structurally_valid: bool
    validation_error: Optional[str]
    goal_consequence_passed: Optional[bool]
    """``True``/``False`` read off the real ``verify_goal_consequence`` event.
    ``None`` means the event is **absent** from the log -- not that the goal
    failed."""
    status: str = "INGESTED"

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "trial_dir": self.trial_dir,
            "run_id": self.run_id,
            "source": self.source,
            "n_events": self.n_events,
            "n_objects": self.n_objects,
            "activity_counts": dict(sorted(self.activity_counts.items())),
            "digest": self.digest,
            "structurally_valid": self.structurally_valid,
            "validation_error": self.validation_error,
            "goal_consequence_passed": self.goal_consequence_passed,
        }


def _run_id(trial_dir: Path) -> str:
    """``realtrial_<seed>_<uuid>`` -> the uuid, else the bare directory name."""
    name = trial_dir.name
    match = re.match(r"^realtrial_\d+_(?P<run>.+)$", name)
    return match.group("run") if match else name


def _event_attr(event: Any, name: str) -> Optional[str]:
    for attr in getattr(event, "attributes", ()):
        if attr.key == name:
            value = attr.value
            return str(getattr(value, "value", value))
    return None


def ingest_episode(trial_dir: Path | str) -> EpisodeOcel | Unknown:
    """Load the durable OCEL for one episode, or say what is absent.

    Reads ``actuation/episode.ocel.json`` through the repo's real
    :class:`~autofde_lab.ocel.log.OcelLog` projection and runs its real
    :meth:`~autofde_lab.ocel.log.OcelLog.validate`. A structural failure is
    recorded as ``structurally_valid=False`` with the refusal text -- the log
    is still returned, because a malformed log observed is evidence, whereas
    ``Unknown`` means nothing was observed at all.
    """
    trial = Path(trial_dir)
    ocel_path = trial / "actuation" / "episode.ocel.json"
    if not ocel_path.is_file():
        return _absent(
            "ingest_episode",
            [ocel_path],
            "no episode OCEL on disk: this trial never reached actuation, or its "
            "evidence was not archived. Absent, not empty.",
        )
    try:
        document = json.loads(ocel_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return _absent("ingest_episode", [ocel_path], f"unreadable episode OCEL: {exc}")

    log = OcelLog.from_ocel2_json(document)
    try:
        log.validate()
        valid, error = True, None
    except OcelError as exc:
        valid, error = False, str(exc)

    passed: Optional[bool] = None
    for event in log.events:
        if event.activity == GOAL_CONSEQUENCE_EVENT_TYPE:
            raw = _event_attr(event, "passed")
            if raw is not None:
                passed = raw.strip().lower() == "true"

    return EpisodeOcel(
        trial_dir=str(trial),
        run_id=_run_id(trial),
        source=str(ocel_path),
        log=log,
        n_events=len(log.events),
        n_objects=len(log.objects),
        activity_counts=dict(Counter(e.activity for e in log.events)),
        digest=log.digest(),
        structurally_valid=valid,
        validation_error=error,
        goal_consequence_passed=passed,
    )


# ---------------------------------------------------------------------------
# shared readers
# ---------------------------------------------------------------------------


def _parse_fact(fact: str) -> tuple[str, Any]:
    name, _, raw = fact.partition("=")
    try:
        return name, ast.literal_eval(raw)
    except (ValueError, SyntaxError):
        return name, raw


def _state_from_facts(facts: Iterable[str]) -> dict[str, Any]:
    return dict(_parse_fact(f) for f in facts)


def _typed_records(probe_log: Sequence[Mapping[str, Any]]) -> list[dict]:
    """Rebuild ``observed_pre`` / ``observed_post`` dicts from the durable log.

    ``typed_probe_log.json`` stores ``"name=value"`` fact strings plus the
    added/removed delta; :func:`induce_typed_domain` wants real typed values.
    The post-state is the pre-state with every added fact applied and every
    removed name whose value was not re-added dropped -- exactly the inverse
    of what ``level4_gymact_bridge`` wrote.
    """
    records: list[dict] = []
    for raw in probe_log:
        pre = _state_from_facts(raw.get("observed_pre_facts", ()))
        post = dict(pre)
        added = _state_from_facts(raw.get("delta_added", ()))
        for name, _ in (_parse_fact(f) for f in raw.get("delta_removed", ())):
            post.pop(name, None)
        post.update(added)
        records.append(
            {
                "action": raw["action"],
                "applicable": bool(raw.get("applicable", False)),
                "observed_pre": pre,
                "observed_post": post,
            }
        )
    return records


_COMMITMENT_SEQUENCE = re.compile(r"powl:sequence\s*\(([^)]*)\)")
_COMMITMENT_SCALAR = re.compile(r'powl:(\w+)\s+"([^"]*)"')


def _read_commitment(path: Path) -> Optional[dict[str, Any]]:
    """The committed plan, read from the trial's own ``commitment.ttl``."""
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    match = _COMMITMENT_SEQUENCE.search(text)
    plan = tuple(re.findall(r'"([^"]*)"', match.group(1))) if match else ()
    scalars = {k: v for k, v in _COMMITMENT_SCALAR.findall(text)}
    return {
        "plan": plan,
        "plan_digest": scalars.get("planDigest"),
        "model_digest": scalars.get("modelDigest"),
        "source": str(path),
    }


def _crown_result(trial_dir: Path) -> Optional[dict[str, Any]]:
    """This trial's row in whichever ancestor ``crown_run.json`` recorded it.

    The observed final state is written by the crown runner into its run
    ledger, not into the trial directory, so it is looked up by ``run_id``
    across the trial's ancestors. Not found -> ``None``, and the caller must
    report that absence rather than substitute an empty state.
    """
    run_id = _run_id(trial_dir)
    for ancestor in list(trial_dir.parents)[:3]:
        ledger = ancestor / "crown_run.json"
        if not ledger.is_file():
            continue
        try:
            document = json.loads(ledger.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for attempt in document.get("attempts", ()):
            for result in attempt.get("results", ()):
                if result.get("run_id") == run_id:
                    return dict(result, _ledger=str(ledger))
    return None


def _receipt_rows(ledger: Path) -> list[dict[str, Any]]:
    if not ledger.is_file():
        return []
    with sqlite3.connect(f"file:{ledger}?mode=ro", uri=True) as conn:
        rows = conn.execute(
            "SELECT receipt_json FROM receipt_evidence ORDER BY sequence"
        ).fetchall()
    return [json.loads(row[0]) for row in rows]


# ---------------------------------------------------------------------------
# 2. the model's own error
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ActionDivergence:
    """One committed step: what the induced model said, what execution did."""

    step_index: int
    action: str
    predicted_applicable: Optional[bool]
    predicted_effect: dict[str, Any]
    """Per-dimension prediction: ``{dim: {"delta": .. } | {"absolute": ..} |
    {"flip": True} | {"context_dependent": True}}``. Empty means the induced
    model claims this action changes nothing -- itself a finding."""
    predicted_repeatable: Optional[bool]
    observed_standing: Optional[str]
    observed_world_changed: Optional[bool]
    observed_pre_state_digest: Optional[str]
    observed_post_state_digest: Optional[str]
    divergences: tuple[str, ...]
    """Named, checkable disagreements. Empty tuple *with* a non-``None``
    ``observed_standing`` means checked-and-agreed."""

    def as_dict(self) -> dict[str, Any]:
        return {
            "step_index": self.step_index,
            "action": self.action,
            "predicted_applicable": self.predicted_applicable,
            "predicted_effect": self.predicted_effect,
            "predicted_repeatable": self.predicted_repeatable,
            "observed_standing": self.observed_standing,
            "observed_world_changed": self.observed_world_changed,
            "observed_pre_state_digest": self.observed_pre_state_digest,
            "observed_post_state_digest": self.observed_post_state_digest,
            "divergences": list(self.divergences),
        }


@dataclass(frozen=True)
class ModelObservationDivergence:
    """The induced model measured against the execution it authorized."""

    trial_dir: str
    run_id: str
    provider: Optional[str]
    committed_plan: tuple[str, ...]
    n_probes: int
    per_action: tuple[ActionDivergence, ...]
    predicted_final_state: dict[str, Any]
    observed_final_state: Optional[dict[str, Any]]
    """``None`` means the observed final state was **not found on disk**
    (named in ``unresolved``), never that it was empty."""
    final_state_mismatches: tuple[dict[str, Any], ...]
    unmodelled_dimensions: tuple[str, ...]
    """Dimensions present in the observed final state that the induced model
    carried no dimension for at all."""
    context_dependent_dimensions: tuple[str, ...]
    sources: tuple[str, ...]
    unresolved: tuple[str, ...]
    status: str = "MEASURED"

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "trial_dir": self.trial_dir,
            "run_id": self.run_id,
            "provider": self.provider,
            "committed_plan": list(self.committed_plan),
            "n_probes": self.n_probes,
            "per_action": [d.as_dict() for d in self.per_action],
            "predicted_final_state": self.predicted_final_state,
            "observed_final_state": self.observed_final_state,
            "final_state_mismatches": [dict(m) for m in self.final_state_mismatches],
            "unmodelled_dimensions": list(self.unmodelled_dimensions),
            "context_dependent_dimensions": list(self.context_dependent_dimensions),
            "sources": list(self.sources),
            "unresolved": list(self.unresolved),
        }


def _predicted_effect(domain: TypedDomain, action_id: str) -> dict[str, Any]:
    action = domain.actions.get(action_id)
    if action is None:
        return {}
    out: dict[str, Any] = {}
    for dim, effect in sorted(action.effects.items()):
        if effect.context_dependent:
            out[dim] = {"context_dependent": True}
        elif effect.delta is not None:
            out[dim] = {"delta": effect.delta}
        elif effect.flip:
            out[dim] = {"flip": True}
        else:
            out[dim] = {"absolute": effect.absolute_value}
    return out


def compare_discovered_model_vs_observed(
    trial_dir: Path | str,
) -> ModelObservationDivergence | Unknown:
    """Where did the induced :class:`TypedDomain` differ from the execution?

    Re-induces the model from the trial's **own** durable probe log (the same
    input the trial used), simulates the **committed** plan forward from the
    first observed pre-state, then holds that prediction against the real act
    receipts in the episode OCEL and the real observed final state.

    Three independent divergence classes are reported, each checkable:

    * per-step -- the model said applicable, the provider recorded ``REFUSED``;
      or the model claimed an effect and the receipt recorded
      ``world_changed=False``.
    * final-state -- per dimension, predicted value vs observed value.
    * unmodelled -- dimensions real in the observation that the model has no
      dimension for, and dimensions the model honestly marked context-dependent.
    """
    trial = Path(trial_dir)
    probe_path = trial / "typed_probe_log.json"
    commitment_path = trial / "actuation" / "commitment.ttl"

    if not probe_path.is_file():
        return _absent(
            "compare_discovered_model_vs_observed",
            [probe_path],
            "no probe log: nothing was induced here, so there is no model to measure.",
        )
    probe_document = json.loads(probe_path.read_text(encoding="utf-8"))
    probe_log = list(probe_document.get("probe_log", ()))
    if not probe_log:
        return _absent(
            "compare_discovered_model_vs_observed",
            [f"{probe_path}::probe_log"],
            "probe log present but carries no records: no observation to induce from.",
        )

    commitment = _read_commitment(commitment_path)
    if commitment is None or not commitment["plan"]:
        return _absent(
            "compare_discovered_model_vs_observed",
            [commitment_path],
            "no committed plan: this trial never committed (probe/plan stage outcome), "
            "so the model was never held against an execution.",
        )

    records = _typed_records(probe_log)
    domain = induce_typed_domain(records)
    plan = tuple(commitment["plan"])
    initial = records[0]["observed_pre"]

    episode = ingest_episode(trial)
    receipts = _receipt_rows(trial / "actuation" / "receipts.sqlite3")
    act_receipts = [r for r in receipts if r.get("operation") == "act"]

    sources = [str(probe_path), str(commitment_path)]
    unresolved: list[str] = []
    if isinstance(episode, EpisodeOcel):
        sources.append(episode.source)
    else:
        unresolved.extend(episode.absent)
    if act_receipts:
        sources.append(str(trial / "actuation" / "receipts.sqlite3"))
    else:
        unresolved.append(str(trial / "actuation" / "receipts.sqlite3") + "::act receipts")

    per_action: list[ActionDivergence] = []
    state = dict(initial)
    used: set[str] = set()
    for index, action_id in enumerate(plan):
        action = domain.actions.get(action_id)
        predicted_applicable: Optional[bool] = None
        predicted_repeatable: Optional[bool] = None
        if action is not None:
            predicted_repeatable = not action.repeatability_unknown
            predicted_applicable = action.applicable_in(state) and not (
                action.repeatability_unknown and action_id in used
            )
        effect = _predicted_effect(domain, action_id)

        receipt = act_receipts[index] if index < len(act_receipts) else None
        standing = receipt.get("standing") if receipt else None
        world_changed = receipt.get("world_changed") if receipt else None

        divergences: list[str] = []
        if action is None:
            divergences.append(
                f"MODEL_HAS_NO_ACTION:{action_id} (committed plan names an action the "
                "induced model never learned)"
            )
        if predicted_applicable is False and standing == "ALIVE":
            divergences.append(
                "MODEL_SAID_INAPPLICABLE_EXECUTION_SUCCEEDED (model is over-restrictive here)"
            )
        if predicted_applicable is True and standing not in (None, "ALIVE"):
            divergences.append(
                f"MODEL_SAID_APPLICABLE_EXECUTION_STANDING={standing} "
                "(model is over-permissive here)"
            )
        if effect and world_changed is False:
            divergences.append(
                "MODEL_CLAIMED_EFFECT_RECEIPT_SAYS_WORLD_UNCHANGED "
                f"(claimed dimensions={sorted(effect)})"
            )
        if not effect and world_changed is True:
            divergences.append(
                "MODEL_CLAIMED_NO_EFFECT_RECEIPT_SAYS_WORLD_CHANGED"
            )
        if receipt is None:
            divergences.append(
                "NO_ACT_RECEIPT_FOR_THIS_STEP (absent, not observed-as-failed)"
            )

        per_action.append(
            ActionDivergence(
                step_index=index,
                action=action_id,
                predicted_applicable=predicted_applicable,
                predicted_effect=effect,
                predicted_repeatable=predicted_repeatable,
                observed_standing=standing,
                observed_world_changed=world_changed,
                observed_pre_state_digest=(receipt or {}).get("pre_state_digest"),
                observed_post_state_digest=(receipt or {}).get("post_state_digest"),
                divergences=tuple(divergences),
            )
        )

        if action is not None:
            used.add(action_id)
            state = domain.apply_action(action, state)

    crown = _crown_result(trial)
    observed_final: Optional[dict[str, Any]] = None
    provider = None
    n_probes = len(probe_log)
    if crown is not None:
        sources.append(crown["_ledger"])
        provider = crown.get("provider")
        raw_final = crown.get("final_state")
        observed_final = dict(raw_final) if raw_final else None
        if not raw_final:
            unresolved.append(
                crown["_ledger"] + "::final_state (row found, final state not recorded)"
            )
    else:
        unresolved.append(
            "crown_run.json::results[run_id=" + _run_id(trial) + "] "
            "(no archived crown run recorded this trial; observed final state absent)"
        )

    mismatches: list[dict[str, Any]] = []
    unmodelled: list[str] = []
    if observed_final is not None:
        for dim in sorted(set(state) | set(observed_final)):
            if dim not in domain.dimensions:
                unmodelled.append(dim)
                continue
            predicted = state.get(dim)
            actual = observed_final.get(dim)
            if predicted != actual:
                mismatches.append(
                    {"dimension": dim, "predicted": predicted, "observed": actual}
                )

    context_dependent = sorted(
        {
            dim
            for act in domain.actions.values()
            for dim in act.context_dependent_dimensions()
        }
    )

    return ModelObservationDivergence(
        trial_dir=str(trial),
        run_id=_run_id(trial),
        provider=provider,
        committed_plan=plan,
        n_probes=n_probes,
        per_action=tuple(per_action),
        predicted_final_state=dict(state),
        observed_final_state=observed_final,
        final_state_mismatches=tuple(mismatches),
        unmodelled_dimensions=tuple(sorted(set(unmodelled))),
        context_dependent_dimensions=tuple(context_dependent),
        sources=tuple(sources),
        unresolved=tuple(unresolved),
    )


# ---------------------------------------------------------------------------
# 3. candidates vs committed
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PlannerCandidate:
    planner: str
    outcome: str
    plan: tuple[str, ...]
    duration_s: Optional[float]
    detail: str
    produced_candidate: bool
    matches_committed: Optional[bool]
    """``None`` when there is no committed plan to compare against."""

    def as_dict(self) -> dict[str, Any]:
        return {
            "planner": self.planner,
            "outcome": self.outcome,
            "plan": list(self.plan),
            "duration_s": self.duration_s,
            "detail": self.detail,
            "produced_candidate": self.produced_candidate,
            "matches_committed": self.matches_committed,
        }


@dataclass(frozen=True)
class CandidateComparison:
    trial_dir: str
    run_id: str
    n_planners_attempted: int
    committed_plan: tuple[str, ...]
    committed_plan_source: Optional[str]
    candidates: tuple[PlannerCandidate, ...]
    agreeing_planners: tuple[str, ...]
    disagreeing_planners: tuple[str, ...]
    distinct_candidate_plans: tuple[tuple[str, ...], ...]
    outcome_counts: dict[str, int]
    sources: tuple[str, ...]
    unresolved: tuple[str, ...]
    status: str = "COMPARED"

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "trial_dir": self.trial_dir,
            "run_id": self.run_id,
            "n_planners_attempted": self.n_planners_attempted,
            "committed_plan": list(self.committed_plan),
            "committed_plan_source": self.committed_plan_source,
            "candidates": [c.as_dict() for c in self.candidates],
            "agreeing_planners": list(self.agreeing_planners),
            "disagreeing_planners": list(self.disagreeing_planners),
            "distinct_candidate_plans": [list(p) for p in self.distinct_candidate_plans],
            "outcome_counts": dict(sorted(self.outcome_counts.items())),
            "sources": list(self.sources),
            "unresolved": list(self.unresolved),
        }


def compare_candidates_vs_committed(
    trial_dir: Path | str,
) -> CandidateComparison | Unknown:
    """Which planners produced candidates, which matched the committed plan.

    Reads the trial's real ``federation.json``. A planner "produced a
    candidate" when it returned a non-empty plan, regardless of whether the
    federation then judged it ``REFUSED`` -- the plan it proposed is the
    evidence about that planner, and folding refusals into "no candidate"
    would hide exactly the disagreement this function exists to find.
    """
    trial = Path(trial_dir)
    federation_path = trial / "federation.json"
    if not federation_path.is_file():
        return _absent(
            "compare_candidates_vs_committed",
            [federation_path],
            "no federation record: no planner portfolio was run for this trial, or its "
            "record was not archived.",
        )
    try:
        attempts = json.loads(federation_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return _absent(
            "compare_candidates_vs_committed", [federation_path], f"unreadable: {exc}"
        )
    if not isinstance(attempts, list) or not attempts:
        return _absent(
            "compare_candidates_vs_committed",
            [f"{federation_path}::attempts"],
            "federation record present but carries no planner attempts.",
        )

    commitment = _read_commitment(trial / "actuation" / "commitment.ttl")
    committed = tuple(commitment["plan"]) if commitment else ()
    crown = _crown_result(trial)

    sources = [str(federation_path)]
    unresolved: list[str] = []
    if commitment:
        sources.append(commitment["source"])
    else:
        unresolved.append(
            str(trial / "actuation" / "commitment.ttl")
            + " (no committed plan; agreement is unanswerable, not 'no agreement')"
        )
    if crown is not None:
        sources.append(crown["_ledger"])

    candidates: list[PlannerCandidate] = []
    for attempt in attempts:
        plan = tuple(attempt.get("plan") or ())
        produced = bool(plan)
        matches = (plan == committed) if committed else None
        candidates.append(
            PlannerCandidate(
                planner=str(attempt.get("planner", "?")),
                outcome=str(attempt.get("outcome", "?")),
                plan=plan,
                duration_s=attempt.get("duration_s"),
                detail=str(attempt.get("detail", ""))[:400],
                produced_candidate=produced,
                matches_committed=matches,
            )
        )

    agreeing = tuple(c.planner for c in candidates if c.matches_committed is True)
    disagreeing = tuple(
        c.planner
        for c in candidates
        if c.produced_candidate and c.matches_committed is False
    )
    distinct = tuple(sorted({c.plan for c in candidates if c.produced_candidate}))

    return CandidateComparison(
        trial_dir=str(trial),
        run_id=_run_id(trial),
        n_planners_attempted=len(candidates),
        committed_plan=committed,
        committed_plan_source=(crown or {}).get("committed_plan_source") or None,
        candidates=tuple(candidates),
        agreeing_planners=agreeing,
        disagreeing_planners=disagreeing,
        distinct_candidate_plans=distinct,
        outcome_counts=dict(Counter(c.outcome for c in candidates)),
        sources=tuple(sources),
        unresolved=tuple(unresolved),
    )


# ---------------------------------------------------------------------------
# 4. durable disagreement record
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DisagreementRecord:
    """How the portfolio disagreed, and how the disagreement resolved."""

    trial_dir: str
    run_id: str
    n_planners_attempted: int
    n_producing_candidates: int
    n_distinct_candidate_plans: int
    disagreement_detected: bool
    committed_plan: tuple[str, ...]
    committed_plan_source: Optional[str]
    resolution: str
    """One of ``COMMITTED_PLAN_MATCHED_BY_N_PLANNERS``,
    ``COMMITTED_PLAN_FROM_TYPED_SEARCH_NO_PLANNER_MATCH``,
    ``NO_COMMITMENT``."""
    agreeing_planners: tuple[str, ...]
    disagreeing_planners: tuple[str, ...]
    failure_modes: dict[str, int]
    written_to: Optional[str]
    sources: tuple[str, ...]
    unresolved: tuple[str, ...]
    status: str = "RECORDED"

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "trial_dir": self.trial_dir,
            "run_id": self.run_id,
            "n_planners_attempted": self.n_planners_attempted,
            "n_producing_candidates": self.n_producing_candidates,
            "n_distinct_candidate_plans": self.n_distinct_candidate_plans,
            "disagreement_detected": self.disagreement_detected,
            "committed_plan": list(self.committed_plan),
            "committed_plan_source": self.committed_plan_source,
            "resolution": self.resolution,
            "agreeing_planners": list(self.agreeing_planners),
            "disagreeing_planners": list(self.disagreeing_planners),
            "failure_modes": dict(sorted(self.failure_modes.items())),
            "written_to": self.written_to,
            "sources": list(self.sources),
            "unresolved": list(self.unresolved),
        }


def record_disagreement(
    trial_dir: Path | str, out_dir: Path | str | None = None
) -> DisagreementRecord | Unknown:
    """Distil planner disagreement into a durable JSON record.

    Writes ``dogfood/disagreement.json`` under ``out_dir`` (default: the trial
    directory). Writing is the only side effect in this module and it touches
    a new file only -- no existing artifact is modified, and nothing is fed
    back into a decision path.
    """
    comparison = compare_candidates_vs_committed(trial_dir)
    if isinstance(comparison, Unknown):
        return comparison

    producing = [c for c in comparison.candidates if c.produced_candidate]
    n_distinct = len(comparison.distinct_candidate_plans)
    if not comparison.committed_plan:
        resolution = "NO_COMMITMENT"
    elif comparison.agreeing_planners:
        resolution = (
            f"COMMITTED_PLAN_MATCHED_BY_{len(comparison.agreeing_planners)}_PLANNERS"
        )
    else:
        resolution = "COMMITTED_PLAN_FROM_TYPED_SEARCH_NO_PLANNER_MATCH"

    failure_modes = Counter(
        c.detail.split(":")[0].split("(")[0].strip()[:60] or c.outcome
        for c in comparison.candidates
        if c.outcome != "SOLVED" and c.detail
    )

    target = Path(out_dir) if out_dir is not None else Path(trial_dir)
    written: Optional[str] = None
    record = DisagreementRecord(
        trial_dir=comparison.trial_dir,
        run_id=comparison.run_id,
        n_planners_attempted=comparison.n_planners_attempted,
        n_producing_candidates=len(producing),
        n_distinct_candidate_plans=n_distinct,
        disagreement_detected=n_distinct > 1,
        committed_plan=comparison.committed_plan,
        committed_plan_source=comparison.committed_plan_source,
        resolution=resolution,
        agreeing_planners=comparison.agreeing_planners,
        disagreeing_planners=comparison.disagreeing_planners,
        failure_modes=dict(failure_modes),
        written_to=None,
        sources=comparison.sources,
        unresolved=comparison.unresolved,
    )
    destination = target / "dogfood" / "disagreement.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(record.as_dict() | {"written_to": str(destination)}, indent=2),
        encoding="utf-8",
    )
    written = str(destination)
    return DisagreementRecord(**{**record.__dict__, "written_to": written})


# ---------------------------------------------------------------------------
# 5. advisory signals -- observations, never tuned weights
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AdvisorySignals:
    """Aggregated observations across episodes. **Not** a tuned policy.

    Four consumers are anticipated -- probe selection, planner portfolio
    ordering, candidate critique, causal-confidence calibration -- and each
    field below is a raw observed count for one of them. No field is a weight,
    a score, or a normalized confidence: turning these into behaviour is a
    separate decision this module does not take.

    ``ranking_refused`` is non-empty whenever ``n_episodes <
    MIN_EPISODES_FOR_RANKING``, and in that case ``planner_ranking`` is empty
    **because it was refused**, not because no planner was observed.
    """

    n_trial_dirs: int
    n_episodes: int
    """Trials that produced a real, ingestible episode OCEL."""
    n_goal_verified_episodes: int
    """Episodes whose real ``verify_goal_consequence`` event recorded passed."""
    min_episodes_for_ranking: int
    ranking_refused: Optional[str]
    planner_agreement_counts: dict[str, dict[str, int]]
    planner_ranking: tuple[str, ...]
    planner_failure_modes: dict[str, int]
    model_divergence_counts: dict[str, int]
    """Divergence code -> how many committed steps exhibited it, across episodes."""
    context_dependent_dimensions: dict[str, int]
    unmodelled_dimensions: dict[str, int]
    final_state_mismatch_dimensions: dict[str, int]
    providers_observed: dict[str, int]
    per_trial_status: dict[str, str]
    """Trial dir -> ``MEASURED`` or the ``UNKNOWN`` detail that stopped it."""
    unresolved: tuple[str, ...]
    status: str = "OBSERVED"

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "n_trial_dirs": self.n_trial_dirs,
            "n_episodes": self.n_episodes,
            "n_goal_verified_episodes": self.n_goal_verified_episodes,
            "min_episodes_for_ranking": self.min_episodes_for_ranking,
            "ranking_refused": self.ranking_refused,
            "planner_agreement_counts": self.planner_agreement_counts,
            "planner_ranking": list(self.planner_ranking),
            "planner_failure_modes": dict(sorted(self.planner_failure_modes.items())),
            "model_divergence_counts": dict(sorted(self.model_divergence_counts.items())),
            "context_dependent_dimensions": dict(
                sorted(self.context_dependent_dimensions.items())
            ),
            "unmodelled_dimensions": dict(sorted(self.unmodelled_dimensions.items())),
            "final_state_mismatch_dimensions": dict(
                sorted(self.final_state_mismatch_dimensions.items())
            ),
            "providers_observed": dict(sorted(self.providers_observed.items())),
            "per_trial_status": dict(sorted(self.per_trial_status.items())),
            "unresolved": list(self.unresolved),
        }


def advisory_signals(trial_dirs: Sequence[Path | str]) -> AdvisorySignals | Unknown:
    """Aggregate across episodes into signals -- with the sample size attached.

    Returns :class:`Unknown` only when **no** trial directory yielded any
    episode at all: that is the "zero verified episodes on disk" case, and it
    must not be reported as a clean aggregate over nothing.
    """
    dirs = [Path(d) for d in trial_dirs]
    if not dirs:
        return _absent(
            "advisory_signals", ["<trial_dirs>"], "no trial directories were supplied."
        )

    per_trial_status: dict[str, str] = {}
    unresolved: list[str] = []
    agreement: dict[str, dict[str, int]] = {}
    failure_modes: Counter[str] = Counter()
    divergence_counts: Counter[str] = Counter()
    context_dims: Counter[str] = Counter()
    unmodelled: Counter[str] = Counter()
    mismatch_dims: Counter[str] = Counter()
    providers: Counter[str] = Counter()
    n_episodes = 0
    n_goal_verified = 0

    for trial in dirs:
        episode = ingest_episode(trial)
        if isinstance(episode, EpisodeOcel):
            n_episodes += 1
            if episode.goal_consequence_passed is True:
                n_goal_verified += 1
        else:
            unresolved.extend(episode.absent)

        comparison = compare_candidates_vs_committed(trial)
        if isinstance(comparison, CandidateComparison):
            for candidate in comparison.candidates:
                row = agreement.setdefault(
                    candidate.planner,
                    {"attempts": 0, "produced_candidate": 0, "matched_committed": 0},
                )
                row["attempts"] += 1
                row["produced_candidate"] += int(candidate.produced_candidate)
                row["matched_committed"] += int(candidate.matches_committed is True)
                if candidate.outcome != "SOLVED":
                    failure_modes[f"{candidate.planner}:{candidate.outcome}"] += 1
        else:
            unresolved.extend(comparison.absent)

        divergence = compare_discovered_model_vs_observed(trial)
        if isinstance(divergence, ModelObservationDivergence):
            per_trial_status[str(trial)] = "MEASURED"
            if divergence.provider:
                providers[divergence.provider] += 1
            for action in divergence.per_action:
                for code in action.divergences:
                    divergence_counts[code.split(" ")[0]] += 1
            for dim in divergence.context_dependent_dimensions:
                context_dims[dim] += 1
            for dim in divergence.unmodelled_dimensions:
                unmodelled[dim] += 1
            for mismatch in divergence.final_state_mismatches:
                mismatch_dims[str(mismatch["dimension"])] += 1
            unresolved.extend(divergence.unresolved)
        else:
            per_trial_status[str(trial)] = f"UNKNOWN: {divergence.detail}"
            unresolved.extend(divergence.absent)

    if n_episodes == 0:
        return _absent(
            "advisory_signals",
            tuple(dict.fromkeys(unresolved)) or tuple(str(d) for d in dirs),
            f"zero verified episodes across {len(dirs)} trial directories: no "
            "actuation OCEL was found in any of them. This is absence of evidence, "
            "not evidence that the loop is clean.",
        )

    refused: Optional[str] = None
    ranking: tuple[str, ...] = ()
    if n_episodes < MIN_EPISODES_FOR_RANKING:
        refused = (
            f"n_episodes={n_episodes} < MIN_EPISODES_FOR_RANKING="
            f"{MIN_EPISODES_FOR_RANKING}: a planner ordering from this many episodes "
            "would be an anecdote, not a calibration. Counts are reported; the "
            "ordering is refused."
        )
    else:
        ranking = tuple(
            planner
            for planner, _ in sorted(
                agreement.items(),
                key=lambda kv: (
                    -kv[1]["matched_committed"],
                    -kv[1]["produced_candidate"],
                    kv[0],
                ),
            )
        )

    return AdvisorySignals(
        n_trial_dirs=len(dirs),
        n_episodes=n_episodes,
        n_goal_verified_episodes=n_goal_verified,
        min_episodes_for_ranking=MIN_EPISODES_FOR_RANKING,
        ranking_refused=refused,
        planner_agreement_counts=agreement,
        planner_ranking=ranking,
        planner_failure_modes=dict(failure_modes),
        model_divergence_counts=dict(divergence_counts),
        context_dependent_dimensions=dict(context_dims),
        unmodelled_dimensions=dict(unmodelled),
        final_state_mismatch_dimensions=dict(mismatch_dims),
        providers_observed=dict(providers),
        per_trial_status=per_trial_status,
        unresolved=tuple(dict.fromkeys(unresolved)),
    )
