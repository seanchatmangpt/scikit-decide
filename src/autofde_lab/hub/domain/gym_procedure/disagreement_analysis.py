# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Why did the portfolio disagree, and what would the next probe settle?

This closes the dogfood loop one notch further than :mod:`dogfood`. That
module *measures* disagreement (which planners produced candidates, which
matched the committed plan, where the induced model's own predictions parted
company with the execution). This module asks the next question -- **why** --
and turns the answer into a named, cheapest-first next experiment.

Everything here is a reader over artifacts already on disk. Nothing opens an
environment, runs a planner, actuates, tunes a weight, or changes any decision
path. The output is data: a typed cause *hypothesis* per disagreeing
candidate, each carrying the exact artifact and field that supports it.

Honesty rules, enforced structurally rather than by convention
--------------------------------------------------------------
* **A hypothesis with no citation is not a hypothesis.** ``_hypothesis``
  refuses to construct any cause other than ``UNKNOWN:`` without at least one
  :class:`Citation`. There is no code path that emits a bare guess.
* **UNKNOWN is the expected majority outcome.** One episode rarely contains
  enough to separate "the induced model is wrong" from "the projection the
  planner consumed lost something". Where it does not, the cause is
  ``UNKNOWN:<reason>`` naming precisely what is missing -- never a plausible
  label chosen to fill the field.
* **N=1 is not calibration.** :func:`classify_corpus` carries ``n_episodes``
  and refuses to rank causes below
  :data:`~autofde_lab.hub.domain.gym_procedure.dogfood.MIN_EPISODES_FOR_RANKING`,
  imitating :func:`dogfood.advisory_signals` exactly.

Reused, not reimplemented
-------------------------
``dogfood.compare_candidates_vs_committed`` (which planners disagreed),
``dogfood.compare_discovered_model_vs_observed`` (the induced model's own
error), ``dogfood.Unknown`` (typed absence), ``typed_induction`` (the typed
model re-induced from the trial's own probes), and
``discovered_domain.propose_discriminating_probe`` (the existing
precondition-discrimination proposer, used verbatim where it applies).

Sources read, all durable
-------------------------
``<trial>/federation.json``            -- per-planner candidate + refusal text
``<trial>/typed_probe_log.json``       -- probe records, ``representation_losses``
``<trial>/typed_validation.json``      -- soundness verdicts on candidates
``<trial>/actuation/commitment.ttl``   -- the committed plan (via dogfood)
``<parent>/crown_run.json``            -- observed final state (via dogfood)
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from autofde_lab.hub.domain.gym_procedure.discovered_domain import (
    Probe,
    induce_discovered_domain,
    propose_discriminating_probe,
)
from autofde_lab.hub.domain.gym_procedure.dogfood import (
    MIN_EPISODES_FOR_RANKING,
    CandidateComparison,
    ModelObservationDivergence,
    Unknown,
    _absent,
    _read_commitment,
    _typed_records,
    compare_candidates_vs_committed,
    compare_discovered_model_vs_observed,
)
from autofde_lab.hub.domain.gym_procedure.typed_induction import (
    TypedDomain,
    induce_typed_domain,
)

__all__ = [
    "CAUSE_VOCABULARY",
    "Citation",
    "CauseHypothesis",
    "DisagreementClassification",
    "NextExperiment",
    "CorpusClassification",
    "classify_disagreement",
    "next_discriminating_experiment",
    "classify_corpus",
]

#: The closed vocabulary of causes. Anything outside it must be an
#: ``UNKNOWN:<reason>`` string -- there is no "other" bucket that hides
#: an unclassifiable case as if it were classified.
CAUSE_VOCABULARY: tuple[str, ...] = (
    "MODEL_DEFECT",
    "PROJECTION_LOSS",
    "PLANNER_OBJECTIVE_DIFFERS",
    "INFORMATION_ASYMMETRY",
    "COST_MODEL_DIFFERS",
    "PRESERVATION_CONSTRAINT",
    "REPRESENTATION_MISMATCH",
)

#: ``proposed inapplicable action 'X' at step N; applicable=[...]`` -- the
#: refusal text the federation writes for a candidate it rejected.
_REFUSAL = re.compile(
    r"proposed inapplicable action '?(?P<action>[^']*?)'? at step (?P<step>\d+); "
    r"applicable=\[(?P<applicable>.*)\]"
)
_PRESERVATION = re.compile(r"preserv|invariant|violat", re.IGNORECASE)


# ---------------------------------------------------------------------------
# citation -- a cause without one of these is UNKNOWN by construction
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Citation:
    """One artifact field that supports (or refutes) a hypothesis.

    ``artifact`` is a real path on disk; ``field`` is the exact locator inside
    it (``federation.json::[7].detail``); ``value`` is what was actually read.
    A reader can re-open the file and check every hypothesis by hand.
    """

    artifact: str
    field: str
    value: str

    def as_dict(self) -> dict[str, str]:
        return {"artifact": self.artifact, "field": self.field, "value": self.value}


@dataclass(frozen=True)
class CauseHypothesis:
    """Why one disagreeing candidate parted company with the committed plan.

    ``cause`` is a member of :data:`CAUSE_VOCABULARY` or an
    ``UNKNOWN:<reason>`` string. ``competing`` names the causes this evidence
    could *not* rule out -- it is what
    :func:`next_discriminating_experiment` consumes.
    """

    planner: str
    candidate_plan: tuple[str, ...]
    outcome: str
    disputed_action: Optional[str]
    disputed_step: Optional[int]
    environment_applicable: Optional[tuple[str, ...]]
    model_says_applicable: Optional[bool]
    cause: str
    citations: tuple[Citation, ...]
    competing: tuple[str, ...]
    caveat: Optional[str]
    detail: str

    @property
    def is_unknown(self) -> bool:
        return self.cause.startswith("UNKNOWN")

    def as_dict(self) -> dict[str, Any]:
        return {
            "planner": self.planner,
            "candidate_plan": list(self.candidate_plan),
            "outcome": self.outcome,
            "disputed_action": self.disputed_action,
            "disputed_step": self.disputed_step,
            "environment_applicable": (
                list(self.environment_applicable)
                if self.environment_applicable is not None
                else None
            ),
            "model_says_applicable": self.model_says_applicable,
            "cause": self.cause,
            "citations": [c.as_dict() for c in self.citations],
            "competing": list(self.competing),
            "caveat": self.caveat,
            "detail": self.detail,
        }


def _hypothesis(
    *,
    planner: str,
    candidate_plan: tuple[str, ...],
    outcome: str,
    cause: str,
    citations: Sequence[Citation],
    detail: str,
    disputed_action: Optional[str] = None,
    disputed_step: Optional[int] = None,
    environment_applicable: Optional[tuple[str, ...]] = None,
    model_says_applicable: Optional[bool] = None,
    competing: Sequence[str] = (),
    caveat: Optional[str] = None,
) -> CauseHypothesis:
    """Construct a hypothesis, downgrading any uncited cause to ``UNKNOWN``.

    This is the structural enforcement of the module's central rule: a named
    cause from :data:`CAUSE_VOCABULARY` with an empty citation list is not
    emitted as that cause. It becomes
    ``UNKNOWN:UNCITED_<cause>`` instead, which is a strictly more honest
    statement of the same situation.
    """
    if cause in CAUSE_VOCABULARY and not citations:
        cause = f"UNKNOWN:UNCITED_{cause}"
        detail = (
            f"{detail} (downgraded: no artifact field supports this cause, and an "
            "uncited cause is UNKNOWN, not a guess)"
        )
    return CauseHypothesis(
        planner=planner,
        candidate_plan=candidate_plan,
        outcome=outcome,
        disputed_action=disputed_action,
        disputed_step=disputed_step,
        environment_applicable=environment_applicable,
        model_says_applicable=model_says_applicable,
        cause=cause,
        citations=tuple(citations),
        competing=tuple(competing),
        caveat=caveat,
        detail=detail,
    )


# ---------------------------------------------------------------------------
# 1. classify
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DisagreementClassification:
    trial_dir: str
    run_id: str
    committed_plan: tuple[str, ...]
    n_planners_attempted: int
    n_producing_candidates: int
    n_disagreeing: int
    hypotheses: tuple[CauseHypothesis, ...]
    cause_counts: dict[str, int]
    n_unknown: int
    model_final_state_mismatches: tuple[dict[str, Any], ...]
    representation_losses: dict[str, Any]
    sources: tuple[str, ...]
    unresolved: tuple[str, ...]
    status: str = "CLASSIFIED"

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "trial_dir": self.trial_dir,
            "run_id": self.run_id,
            "committed_plan": list(self.committed_plan),
            "n_planners_attempted": self.n_planners_attempted,
            "n_producing_candidates": self.n_producing_candidates,
            "n_disagreeing": self.n_disagreeing,
            "hypotheses": [h.as_dict() for h in self.hypotheses],
            "cause_counts": dict(sorted(self.cause_counts.items())),
            "n_unknown": self.n_unknown,
            "model_final_state_mismatches": [
                dict(m) for m in self.model_final_state_mismatches
            ],
            "representation_losses": dict(self.representation_losses),
            "sources": list(self.sources),
            "unresolved": list(self.unresolved),
        }


def _read_json(path: Path) -> Optional[Any]:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _federation_index(federation: Any, planner: str) -> int:
    if isinstance(federation, list):
        for index, attempt in enumerate(federation):
            if str(attempt.get("planner")) == planner:
                return index
    return -1


def _simulate_prefix(
    domain: TypedDomain, initial: Mapping[str, Any], prefix: Sequence[str]
) -> Optional[dict[str, Any]]:
    """State reached by the candidate's own prefix under the induced model.

    ``None`` when the model cannot carry the prefix at all (an action it never
    learned) -- absence, reported as such, not silently treated as the initial
    state.
    """
    state = dict(initial)
    for action_id in prefix:
        action = domain.actions.get(action_id)
        if action is None:
            return None
        state = domain.apply_action(action, state)
    return state


def _matching_probe_index(
    records: Sequence[Mapping[str, Any]],
    state: Mapping[str, Any],
    action: str,
    applicable: bool,
) -> Optional[int]:
    """Index of a real probe of ``action`` in exactly ``state``, if one exists."""
    for index, record in enumerate(records):
        if record["action"] != action:
            continue
        if bool(record.get("applicable")) is not applicable:
            continue
        if dict(record.get("observed_pre", {})) == dict(state):
            return index
    return None


def classify_disagreement(
    trial_dir: Path | str,
) -> DisagreementClassification | Unknown:
    """Classify *why* each disagreeing candidate parted from the committed plan.

    Reuses :func:`dogfood.compare_candidates_vs_committed` for the set of
    disagreeing candidates and
    :func:`dogfood.compare_discovered_model_vs_observed` for the induced
    model's own measured error, then re-induces the typed model from the
    trial's own probe log to ask, per disputed step, whether the model and the
    environment actually agree.

    Rules applied in order, each requiring a real citation:

    1. ``PRESERVATION_CONSTRAINT`` -- the refusal text itself names a
       preservation/invariant violation.
    2. ``PROJECTION_LOSS`` -- ``typed_probe_log.json::representation_losses``
       is non-empty and names the disputed action or a dimension the induced
       model attaches to it.
    3. ``UNKNOWN:PROBE_FEDERATION_CONFLICT`` -- a real probe records the
       disputed action as *applicable* in exactly the state the candidate
       reached, while the federation records it as inapplicable. Two durable
       artifacts contradict each other; neither is privileged from one episode.
    4. ``MODEL_DEFECT`` -- the induced model predicts the disputed action
       applicable, the environment lists it as not, **and** the trial's own
       model-vs-observed comparison independently mismatched on a dimension
       the induced model attributes to the disputed action or the candidate's
       prefix.
    5. ``REPRESENTATION_MISMATCH`` -- the induced model *and* the environment
       both say the disputed action is inapplicable, yet the planner proposed
       it: the artifact the planner consumed admitted a transition both reject.
    6. ``PLANNER_OBJECTIVE_DIFFERS`` / ``COST_MODEL_DIFFERS`` -- the candidate
       was judged sound in ``typed_validation.json`` and still differs from the
       committed plan (by ordering, or by length).
    7. Otherwise ``UNKNOWN:<reason>``.
    """
    trial = Path(trial_dir)
    comparison = compare_candidates_vs_committed(trial)
    if isinstance(comparison, Unknown):
        return comparison

    probe_path = trial / "typed_probe_log.json"
    probe_document = _read_json(probe_path)
    if not isinstance(probe_document, dict) or not probe_document.get("probe_log"):
        return _absent(
            "classify_disagreement",
            [f"{probe_path}::probe_log"],
            "no probe log: there is no induced model to hold against the federation, "
            "so no disagreement here is classifiable at all.",
        )
    probe_log = list(probe_document["probe_log"])
    representation_losses = dict(probe_document.get("representation_losses") or {})

    records = _typed_records(probe_log)
    typed = induce_typed_domain(records)
    initial = records[0]["observed_pre"]

    federation_path = trial / "federation.json"
    federation = _read_json(federation_path)

    divergence = compare_discovered_model_vs_observed(trial)
    mismatches: tuple[dict[str, Any], ...] = ()
    mismatch_dims: set[str] = set()
    sources = list(comparison.sources) + [str(probe_path)]
    unresolved = list(comparison.unresolved)
    if isinstance(divergence, ModelObservationDivergence):
        mismatches = divergence.final_state_mismatches
        mismatch_dims = {str(m["dimension"]) for m in mismatches}
        sources.extend(divergence.sources)
        unresolved.extend(divergence.unresolved)
    else:
        unresolved.extend(divergence.absent)

    validation_path = trial / "typed_validation.json"
    validation = _read_json(validation_path) or {}
    verdicts = {
        tuple(v.get("plan") or ()): v for v in (validation.get("verdicts") or ())
    }
    if isinstance(validation, dict) and validation:
        sources.append(str(validation_path))

    hypotheses: list[CauseHypothesis] = []
    for candidate in comparison.candidates:
        if not candidate.produced_candidate or candidate.matches_committed is not False:
            continue
        hypotheses.append(
            _classify_one(
                candidate=candidate,
                trial=trial,
                federation=federation,
                federation_path=federation_path,
                probe_path=probe_path,
                typed=typed,
                records=records,
                initial=initial,
                representation_losses=representation_losses,
                mismatches=mismatches,
                mismatch_dims=mismatch_dims,
                verdicts=verdicts,
                validation_path=validation_path,
                committed=comparison.committed_plan,
                divergence_source=(
                    divergence.sources[-1]
                    if isinstance(divergence, ModelObservationDivergence)
                    and divergence.sources
                    else str(trial)
                ),
            )
        )

    return DisagreementClassification(
        trial_dir=str(trial),
        run_id=comparison.run_id,
        committed_plan=comparison.committed_plan,
        n_planners_attempted=comparison.n_planners_attempted,
        n_producing_candidates=sum(
            1 for c in comparison.candidates if c.produced_candidate
        ),
        n_disagreeing=len(hypotheses),
        hypotheses=tuple(hypotheses),
        cause_counts=dict(Counter(h.cause for h in hypotheses)),
        n_unknown=sum(1 for h in hypotheses if h.is_unknown),
        model_final_state_mismatches=mismatches,
        representation_losses=representation_losses,
        sources=tuple(dict.fromkeys(sources)),
        unresolved=tuple(dict.fromkeys(unresolved)),
    )


def _classify_one(
    *,
    candidate: Any,
    trial: Path,
    federation: Any,
    federation_path: Path,
    probe_path: Path,
    typed: TypedDomain,
    records: Sequence[Mapping[str, Any]],
    initial: Mapping[str, Any],
    representation_losses: Mapping[str, Any],
    mismatches: Sequence[Mapping[str, Any]],
    mismatch_dims: set[str],
    verdicts: Mapping[tuple, Any],
    validation_path: Path,
    committed: tuple[str, ...],
    divergence_source: str,
) -> CauseHypothesis:
    planner = candidate.planner
    plan = candidate.plan
    index = _federation_index(federation, planner)
    detail_field = f"[{index}].detail" if index >= 0 else f"[planner={planner}].detail"
    detail_citation = Citation(
        artifact=str(federation_path), field=detail_field, value=candidate.detail
    )

    # --- rule 1: the refusal text names a preservation violation outright ---
    if _PRESERVATION.search(candidate.detail):
        return _hypothesis(
            planner=planner,
            candidate_plan=plan,
            outcome=candidate.outcome,
            cause="PRESERVATION_CONSTRAINT",
            citations=[detail_citation],
            detail="federation refusal text names a preservation/invariant violation",
        )

    verdict = verdicts.get(tuple(plan))
    match = _REFUSAL.search(candidate.detail)

    # --- rules 6: a candidate judged sound that still differs ---
    if match is None and verdict is not None:
        sound = bool(verdict.get("sound", verdict.get("valid")))
        verdict_citation = Citation(
            artifact=str(validation_path),
            field=f"verdicts[plan={list(plan)}]",
            value=json.dumps(verdict, sort_keys=True)[:200],
        )
        if sound and len(plan) != len(committed):
            return _hypothesis(
                planner=planner,
                candidate_plan=plan,
                outcome=candidate.outcome,
                cause="COST_MODEL_DIFFERS",
                citations=[verdict_citation, detail_citation],
                detail=(
                    f"candidate judged sound and is length {len(plan)} against the "
                    f"committed plan's {len(committed)}: a cost/objective difference, "
                    "not a correctness difference"
                ),
                competing=("PLANNER_OBJECTIVE_DIFFERS",),
            )
        if sound:
            return _hypothesis(
                planner=planner,
                candidate_plan=plan,
                outcome=candidate.outcome,
                cause="PLANNER_OBJECTIVE_DIFFERS",
                citations=[verdict_citation],
                detail=(
                    "candidate judged sound and same length as the committed plan: "
                    "the planners order equally-valid plans differently"
                ),
                competing=("COST_MODEL_DIFFERS",),
            )

    if match is None:
        return _hypothesis(
            planner=planner,
            candidate_plan=plan,
            outcome=candidate.outcome,
            cause="UNKNOWN:UNPARSEABLE_REFUSAL_DETAIL",
            citations=[detail_citation],
            detail=(
                "the federation record carries no machine-readable statement of which "
                "action was disputed, and no soundness verdict for this plan exists in "
                f"{validation_path.name}. What would classify it: either a structured "
                "refusal field, or a typed_validation verdict for this exact plan."
            ),
        )

    action = match.group("action")
    step = int(match.group("step"))
    applicable_env = tuple(
        item.strip().strip("'\"")
        for item in match.group("applicable").split(",")
        if item.strip()
    )

    # --- rule 2: the projection is on record as having dropped something ---
    action_dims = set()
    typed_action = typed.actions.get(action)
    if typed_action is not None:
        action_dims |= set(typed_action.effects)
    loss_keys = {str(k) for k in representation_losses}
    hit = loss_keys & ({action} | action_dims)
    if hit:
        return _hypothesis(
            planner=planner,
            candidate_plan=plan,
            outcome=candidate.outcome,
            disputed_action=action,
            disputed_step=step,
            environment_applicable=applicable_env,
            cause="PROJECTION_LOSS",
            citations=[
                Citation(
                    artifact=str(probe_path),
                    field=f"representation_losses[{sorted(hit)[0]}]",
                    value=json.dumps(
                        {k: representation_losses[k] for k in sorted(hit)}
                    )[:200],
                ),
                detail_citation,
            ],
            detail=(
                f"the recorded representation losses name {sorted(hit)}, which the "
                f"induced model attaches to the disputed action '{action}': the "
                "propositional projection the planner consumed could not carry it"
            ),
        )

    prefix = tuple(plan[:step])
    reached = _simulate_prefix(typed, initial, prefix)
    if reached is None:
        return _hypothesis(
            planner=planner,
            candidate_plan=plan,
            outcome=candidate.outcome,
            disputed_action=action,
            disputed_step=step,
            environment_applicable=applicable_env,
            cause="UNKNOWN:PREFIX_NOT_SIMULABLE",
            citations=[detail_citation],
            detail=(
                f"the induced model never learned one of {list(prefix)}, so the state "
                "the candidate reached cannot be reconstructed and its model prediction "
                "is unavailable. What would classify it: a probe of each prefix action."
            ),
        )

    if typed_action is None:
        return _hypothesis(
            planner=planner,
            candidate_plan=plan,
            outcome=candidate.outcome,
            disputed_action=action,
            disputed_step=step,
            environment_applicable=applicable_env,
            cause="UNKNOWN:DISPUTED_ACTION_NEVER_INDUCED",
            citations=[detail_citation],
            detail=(
                f"the induced model carries no action '{action}', so there is no model "
                "prediction to compare against the environment's refusal. What would "
                f"classify it: one probe of '{action}' anywhere it is applicable."
            ),
        )

    # Repeatability is part of the model's claim, exactly as
    # ``dogfood.compare_discovered_model_vs_observed`` treats it: an action whose
    # repeatability was never observed is NOT predicted applicable a second time.
    # Dropping this guard would attribute to the induced model a claim it never
    # made, and manufacture MODEL_DEFECT out of the model's own honest silence.
    model_applicable = typed_action.applicable_in(dict(reached)) and not (
        typed_action.repeatability_unknown and action in prefix
    )
    reached_citation = Citation(
        artifact=str(probe_path),
        field=f"probe_log -> induce_typed_domain -> state after {list(prefix)}",
        value=json.dumps(
            {k: reached[k] for k in sorted(reached)}, default=str, sort_keys=True
        )[:300],
    )

    # --- rule 3: two durable artifacts contradict each other ---
    conflict = _matching_probe_index(records, reached, action, applicable=True)
    if conflict is not None and action not in applicable_env:
        return _hypothesis(
            planner=planner,
            candidate_plan=plan,
            outcome=candidate.outcome,
            disputed_action=action,
            disputed_step=step,
            environment_applicable=applicable_env,
            model_says_applicable=model_applicable,
            cause="UNKNOWN:PROBE_FEDERATION_CONFLICT",
            citations=[
                Citation(
                    artifact=str(probe_path),
                    field=f"probe_log[{conflict}]",
                    value=(
                        f"action={action} applicable=True in exactly the state this "
                        "candidate reached"
                    ),
                ),
                detail_citation,
                reached_citation,
            ],
            competing=("MODEL_DEFECT", "INFORMATION_ASYMMETRY"),
            detail=(
                f"probe_log[{conflict}] records '{action}' as APPLICABLE in exactly the "
                "state this candidate reached, while the federation records it as "
                "inapplicable there. Two durable artifacts disagree; one episode does "
                "not say which is right, and picking one would be a guess."
            ),
        )

    if model_applicable and action not in applicable_env:
        # --- rule 4: model over-permissive, with independent mismatch evidence ---
        prefix_dims: set[str] = set()
        for prefix_action in prefix:
            prefix_typed = typed.actions.get(prefix_action)
            if prefix_typed is not None:
                prefix_dims |= set(prefix_typed.effects)
        supporting = sorted(mismatch_dims & (action_dims | prefix_dims))
        if supporting:
            return _hypothesis(
                planner=planner,
                candidate_plan=plan,
                outcome=candidate.outcome,
                disputed_action=action,
                disputed_step=step,
                environment_applicable=applicable_env,
                model_says_applicable=True,
                cause="MODEL_DEFECT",
                citations=[
                    detail_citation,
                    reached_citation,
                    Citation(
                        artifact=divergence_source,
                        field="final_state_mismatches",
                        value=json.dumps(
                            [
                                dict(m)
                                for m in mismatches
                                if str(m["dimension"]) in supporting
                            ],
                            default=str,
                        )[:300],
                    ),
                ],
                competing=("INFORMATION_ASYMMETRY",),
                detail=(
                    f"the induced model predicts '{action}' applicable in the reached "
                    f"state; the environment lists only {list(applicable_env)}. The same "
                    f"model independently mispredicted {supporting} in this very "
                    "episode's observed final state, and the induced model attributes "
                    f"{supporting} to the disputed action or its prefix -- so the model, "
                    "not the planner, is the thing the evidence indicts."
                ),
                caveat=(
                    "one episode: this does not separate a wrong precondition from a "
                    "wrong effect on the same dimension"
                ),
            )
        return _hypothesis(
            planner=planner,
            candidate_plan=plan,
            outcome=candidate.outcome,
            disputed_action=action,
            disputed_step=step,
            environment_applicable=applicable_env,
            model_says_applicable=True,
            cause="UNKNOWN:MODEL_ENV_DISAGREE_NO_INDEPENDENT_EVIDENCE",
            citations=[detail_citation, reached_citation],
            competing=("MODEL_DEFECT", "PROJECTION_LOSS", "INFORMATION_ASYMMETRY"),
            detail=(
                f"the induced model predicts '{action}' applicable in the reached state "
                f"and the environment lists only {list(applicable_env)}. Nothing else in "
                "this trial says whether the model's precondition is wrong, the "
                "projection dropped the blocking fact, or the environment used state "
                f"neither saw. What would classify it: one probe of '{action}' in "
                "exactly that state."
            ),
        )

    if (
        not model_applicable
        and action not in applicable_env
        and typed_action.repeatability_unknown
        and action in prefix
        and typed_action.applicable_in(dict(reached))
    ):
        # The model's preconditions are satisfied; the only thing withholding
        # applicability is that repeating this action was never observed. That
        # is unobserved, not a claim of inapplicability -- calling it
        # REPRESENTATION_MISMATCH would credit the model with a judgement it
        # never made.
        return _hypothesis(
            planner=planner,
            candidate_plan=plan,
            outcome=candidate.outcome,
            disputed_action=action,
            disputed_step=step,
            environment_applicable=applicable_env,
            model_says_applicable=False,
            cause="UNKNOWN:REPEATABILITY_UNOBSERVED",
            citations=[detail_citation, reached_citation],
            competing=("MODEL_DEFECT", "REPRESENTATION_MISMATCH"),
            detail=(
                f"the candidate repeats '{action}', which no probe ever attempted twice, "
                "so the induced model withholds applicability rather than denying it. "
                "The environment refused; whether the model would have agreed is "
                f"unobserved. What would classify it: one probe attempting '{action}' a "
                "second time."
            ),
        )

    if not model_applicable and action not in applicable_env:
        # --- rule 5: both reject it, the planner proposed it anyway ---
        return _hypothesis(
            planner=planner,
            candidate_plan=plan,
            outcome=candidate.outcome,
            disputed_action=action,
            disputed_step=step,
            environment_applicable=applicable_env,
            model_says_applicable=False,
            cause="REPRESENTATION_MISMATCH",
            citations=[detail_citation, reached_citation],
            competing=("PROJECTION_LOSS",),
            detail=(
                f"the induced typed model and the environment agree that '{action}' is "
                "inapplicable in the reached state, yet this planner proposed it: the "
                "representation the planner consumed admitted a transition both reject."
            ),
            caveat=(
                "the exact artifact handed to the federation is not archived in the "
                "trial, so this indicts the planner's input representation as a class, "
                "not a named field in it"
            ),
        )

    return _hypothesis(
        planner=planner,
        candidate_plan=plan,
        outcome=candidate.outcome,
        disputed_action=action,
        disputed_step=step,
        environment_applicable=applicable_env,
        model_says_applicable=model_applicable,
        cause="UNKNOWN:REFUSAL_NOT_REPRODUCED",
        citations=[detail_citation, reached_citation],
        detail=(
            f"the environment lists '{action}' as applicable in its own refusal text, so "
            "the recorded reason does not reproduce against this trial's own artifacts. "
            "What would classify it: the federation's per-step state digests, which this "
            "record does not carry."
        ),
    )


# ---------------------------------------------------------------------------
# 2. the next experiment
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NextExperiment:
    trial_dir: str
    run_id: str
    competing_hypotheses: tuple[str, ...]
    experiment: Optional[dict[str, Any]]
    """``None`` exactly when ``cannot_distinguish`` is set."""
    reused_proposer: Optional[str]
    """Name of the existing proposer reused, when one applied."""
    distinguishes: tuple[str, ...]
    cannot_distinguish: Optional[str]
    would_require: tuple[str, ...]
    citations: tuple[Citation, ...]
    status: str = "PROPOSED"

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "trial_dir": self.trial_dir,
            "run_id": self.run_id,
            "competing_hypotheses": list(self.competing_hypotheses),
            "experiment": self.experiment,
            "reused_proposer": self.reused_proposer,
            "distinguishes": list(self.distinguishes),
            "cannot_distinguish": self.cannot_distinguish,
            "would_require": list(self.would_require),
            "citations": [c.as_dict() for c in self.citations],
        }


def next_discriminating_experiment(
    trial_dir: Path | str,
) -> NextExperiment | Unknown:
    """The single cheapest probe that would separate the competing hypotheses.

    Picks the most-disputed action across the classification, then reuses
    :func:`discovered_domain.propose_discriminating_probe` verbatim when that
    action's precondition hypothesis still has more than one candidate fact
    (its exact job). When the hypothesis is already minimal, the proposal
    becomes the concrete re-probe the classification itself named: attempt the
    disputed action in exactly the state the candidate reached.

    When the evidence on disk cannot separate the causes at all,
    ``cannot_distinguish`` says so and ``would_require`` names what would.
    """
    classification = classify_disagreement(trial_dir)
    if isinstance(classification, Unknown):
        return classification

    trial = Path(trial_dir)
    probe_path = trial / "typed_probe_log.json"
    probe_document = _read_json(probe_path) or {}
    probe_log = list(probe_document.get("probe_log") or ())
    records = _typed_records(probe_log)
    typed = induce_typed_domain(records)
    initial = records[0]["observed_pre"] if records else {}

    competing: set[str] = set()
    for hypothesis in classification.hypotheses:
        competing.add(hypothesis.cause)
        competing.update(hypothesis.competing)

    if not classification.hypotheses:
        return NextExperiment(
            trial_dir=str(trial),
            run_id=classification.run_id,
            competing_hypotheses=(),
            experiment=None,
            reused_proposer=None,
            distinguishes=(),
            cannot_distinguish=(
                "no candidate disagreed with the committed plan in this trial, so "
                "there is no disagreement to discriminate."
            ),
            would_require=(
                "a trial in which at least one planner produces a candidate that "
                "differs from the committed plan",
            ),
            citations=(
                Citation(
                    artifact=str(trial / "federation.json"),
                    field="disagreeing candidates",
                    value="0",
                ),
            ),
        )

    disputed = Counter(
        h.disputed_action for h in classification.hypotheses if h.disputed_action
    )
    if not disputed:
        return NextExperiment(
            trial_dir=str(trial),
            run_id=classification.run_id,
            competing_hypotheses=tuple(sorted(competing)),
            experiment=None,
            reused_proposer=None,
            distinguishes=(),
            cannot_distinguish=(
                "every disagreement in this trial was classified without a disputed "
                "action (no machine-readable refusal), so no single probe targets them."
            ),
            would_require=(
                "a structured refusal field in federation.json naming the disputed "
                "action and the state it was disputed in",
            ),
            citations=tuple(
                c for h in classification.hypotheses for c in h.citations[:1]
            ),
        )

    action, n_disputes = disputed.most_common(1)[0]
    targeted = [h for h in classification.hypotheses if h.disputed_action == action]
    target_causes = tuple(sorted({h.cause for h in targeted} | {
        c for h in targeted for c in h.competing
    }))

    discovered = induce_discovered_domain(probe_log)
    probe: Optional[Probe] = propose_discriminating_probe(discovered, action)

    reached_states = []
    for hypothesis in targeted:
        state = _simulate_prefix(
            typed, initial, hypothesis.candidate_plan[: hypothesis.disputed_step or 0]
        )
        if state is not None:
            reached_states.append(
                json.dumps({k: state[k] for k in sorted(state)}, default=str)
            )
    reached = sorted(set(reached_states))

    if probe is not None:
        experiment = {
            "kind": "PRECONDITION_DISCRIMINATION",
            "action": probe.action,
            "rationale": probe.rationale,
            "cost": "one action attempt in the live environment",
            "reached_states_to_test": reached,
        }
        reused = "discovered_domain.propose_discriminating_probe"
    else:
        experiment = {
            "kind": "REPROBE_IN_DISPUTED_STATE",
            "action": action,
            "rationale": (
                f"'{action}' is the action {n_disputes} disagreeing candidates were "
                "refused on. Its induced precondition hypothesis is already minimal, so "
                "propose_discriminating_probe returns nothing to discriminate; the open "
                "question is not which precondition fact is causal but whether the model "
                "is right at all in the specific state the candidates reached. Attempt "
                f"'{action}' in exactly that state."
            ),
            "cost": "one action attempt in the live environment",
            "reached_states_to_test": reached,
        }
        reused = None

    distinguishes: list[str] = []
    if "MODEL_DEFECT" in target_causes or any(
        c.startswith("UNKNOWN:MODEL_ENV_DISAGREE") for c in target_causes
    ):
        distinguishes.append("MODEL_DEFECT")
    if "UNKNOWN:PROBE_FEDERATION_CONFLICT" in target_causes:
        distinguishes.append("UNKNOWN:PROBE_FEDERATION_CONFLICT")
    if "REPRESENTATION_MISMATCH" in target_causes:
        distinguishes.append("REPRESENTATION_MISMATCH")
    if "UNKNOWN:REPEATABILITY_UNOBSERVED" in target_causes:
        distinguishes.append("UNKNOWN:REPEATABILITY_UNOBSERVED")

    would_require: list[str] = []
    if "PROJECTION_LOSS" in target_causes or "INFORMATION_ASYMMETRY" in target_causes:
        would_require.append(
            "archiving the exact planner-facing projection alongside federation.json: "
            "PROJECTION_LOSS and INFORMATION_ASYMMETRY are claims about an artifact "
            "this trial does not keep, so no live probe can separate them from "
            "MODEL_DEFECT"
        )

    cannot: Optional[str] = None
    if not distinguishes:
        cannot = (
            "the causes competing here are all claims about artifacts this trial does "
            "not archive, so no probe of the live environment separates them."
        )

    return NextExperiment(
        trial_dir=str(trial),
        run_id=classification.run_id,
        competing_hypotheses=tuple(sorted(competing)),
        experiment=None if cannot else experiment,
        reused_proposer=None if cannot else reused,
        distinguishes=tuple(distinguishes),
        cannot_distinguish=cannot,
        would_require=tuple(would_require),
        citations=tuple(
            [
                Citation(
                    artifact=str(trial / "federation.json"),
                    field=f"disputed action counts[{action}]",
                    value=str(n_disputes),
                )
            ]
            + [c for h in targeted[:3] for c in h.citations[:1]]
        ),
    )


# ---------------------------------------------------------------------------
# 3. corpus -- with the sample size attached, and a refusal below the floor
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CorpusClassification:
    """Causes aggregated across episodes. **Not** a ranking below the floor.

    ``ranking_refused`` is non-empty whenever ``n_episodes <
    MIN_EPISODES_FOR_RANKING``, and ``cause_ranking`` is then empty *because it
    was refused*, not because no cause was observed. This imitates
    :func:`dogfood.advisory_signals` deliberately: the two must refuse on the
    same floor or the loop grows a second, weaker standard.
    """

    n_trial_dirs: int
    n_episodes: int
    min_episodes_for_ranking: int
    ranking_refused: Optional[str]
    cause_counts: dict[str, int]
    cause_ranking: tuple[str, ...]
    n_unknown: int
    n_hypotheses: int
    per_trial_status: dict[str, str]
    unresolved: tuple[str, ...]
    status: str = "OBSERVED"

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "n_trial_dirs": self.n_trial_dirs,
            "n_episodes": self.n_episodes,
            "min_episodes_for_ranking": self.min_episodes_for_ranking,
            "ranking_refused": self.ranking_refused,
            "cause_counts": dict(sorted(self.cause_counts.items())),
            "cause_ranking": list(self.cause_ranking),
            "n_unknown": self.n_unknown,
            "n_hypotheses": self.n_hypotheses,
            "per_trial_status": dict(sorted(self.per_trial_status.items())),
            "unresolved": list(self.unresolved),
        }


def classify_corpus(trial_dirs: Sequence[Path | str]) -> CorpusClassification | Unknown:
    """Aggregate causes across trials, refusing to rank below the floor."""
    dirs = [Path(d) for d in trial_dirs]
    if not dirs:
        return _absent(
            "classify_corpus", ["<trial_dirs>"], "no trial directories were supplied."
        )

    counts: Counter[str] = Counter()
    per_trial: dict[str, str] = {}
    unresolved: list[str] = []
    n_episodes = 0
    n_hypotheses = 0
    n_unknown = 0

    for trial in dirs:
        classification = classify_disagreement(trial)
        if isinstance(classification, Unknown):
            per_trial[str(trial)] = f"UNKNOWN: {classification.detail}"
            unresolved.extend(classification.absent)
            continue
        n_episodes += 1
        per_trial[str(trial)] = "CLASSIFIED"
        counts.update(classification.cause_counts)
        n_hypotheses += len(classification.hypotheses)
        n_unknown += classification.n_unknown
        unresolved.extend(classification.unresolved)

    if n_episodes == 0:
        return _absent(
            "classify_corpus",
            tuple(dict.fromkeys(unresolved)) or tuple(str(d) for d in dirs),
            f"no classifiable trial among {len(dirs)}: this is absence of evidence, "
            "not evidence that the portfolio agreed.",
        )

    refused: Optional[str] = None
    ranking: tuple[str, ...] = ()
    if n_episodes < MIN_EPISODES_FOR_RANKING:
        refused = (
            f"n_episodes={n_episodes} < MIN_EPISODES_FOR_RANKING="
            f"{MIN_EPISODES_FOR_RANKING}: a cause ordering from this many episodes "
            "would be an anecdote, not a calibration. Counts are reported; the "
            "ordering is refused."
        )
    else:
        ranking = tuple(cause for cause, _ in counts.most_common())

    return CorpusClassification(
        n_trial_dirs=len(dirs),
        n_episodes=n_episodes,
        min_episodes_for_ranking=MIN_EPISODES_FOR_RANKING,
        ranking_refused=refused,
        cause_counts=dict(counts),
        cause_ranking=ranking,
        n_unknown=n_unknown,
        n_hypotheses=n_hypotheses,
        per_trial_status=per_trial,
        unresolved=tuple(dict.fromkeys(unresolved)),
    )
