# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Real, multi-stage DSPy troubleshooting cognition graph composing
`sre_troubleshooting_signatures.py`'s six generic signatures: orient ->
normalize (O -> O*) -> hypothesize -> propose/select a discriminating probe
-> commit a diagnosis -> construct/select a mitigation.

**Nothing here is hardcoded to sregym, gymact, or any other specific
benchmark/environment** -- same claim, checked the same way, as
`k8s_signatures.py`/`k8s_diagnosis_pipeline.py`.

The probe/hypothesis loop is the caller's job, not this module's
------------------------------------------------------------------
Between `select_probe` and `commit_diagnosis` a real investigation may need
several real rounds: propose a probe -> actually execute it through the
real, gated capability surface -> normalize the real result -> re-hypothesize
-> propose the next probe. That loop genuinely needs a real environment
(`environment.actuate(...)`, per `gymact_dspy_react.py`'s
`build_gated_react_tools`), which this module deliberately does not own --
mirroring `k8s_diagnosis_pipeline.py`'s own boundary ("owns no environment
materialization, no tool wiring") and this session's earlier design decision
for multi-round investigation ("a plain Python loop in the caller, not a
second `dspy.Module`-level ReAct construct"). This module exposes each real
stage as a callable method; a caller (e.g.
`gymact_dspy_react.SreTroubleshootingDecisionBackend`) drives the loop and
supplies real, gated tool execution between stages.

DSPy reasons, GymAct actuates -- enforced by field shape, not by convention
-----------------------------------------------------------------------------
No output field on any composed signature is itself an actuation.
`select_probe`'s `probe_intent` and `select_mitigation`'s `mitigation_intent`
are real INTENTS a caller must route through the real, gated capability
surface to become an action -- this module never calls
`environment.actuate(...)` itself, anywhere.

Ensemble stages (hypothesize, commit_diagnosis)
-------------------------------------------------
Both fire `ensemble_n` independent real `dspy.ChainOfThought` completions and
reconcile them with a real `dspy.MultiChainComparison` -- the exact,
already-tested pattern `sregym_pipeline.py`'s `_EnsembleClassify` uses,
reused here rather than reinvented.

Search stages (select_probe, select_mitigation)
---------------------------------------------------
Both wrap a real `dspy.ChainOfThought` in a real `dspy.BestOfN`, scored by a
real, deterministic, pure-Python reward function computed from the
candidate's own typed output fields (`information_gain_per_cost`,
`safe_reversible_recovery_score`) -- never a second LLM call judging the
first. Both reward functions are module-level, real functions (not
closures), so they are directly unit-testable and reusable by
`gepa_train.py`'s metric construction.
"""

from __future__ import annotations

import dspy

from autofde_lab.reasoning.sre_troubleshooting_signatures import (
    CommitSreDiagnosis,
    ConstructSreMitigation,
    HypothesizeSreCauses,
    NormalizeSreEvidence,
    OrientSreIncident,
    ProposeDiscriminatingObservation,
)

__all__ = [
    "SreTroubleshootingPipeline",
    "information_gain_per_cost",
    "safe_reversible_recovery_score",
]


def information_gain_per_cost(_kwargs: dict, prediction: dspy.Prediction) -> float:
    """Real, deterministic reward for `select_probe`'s `dspy.BestOfN`:
    the candidate probe's own claimed `expected_information_gain` (clamped
    to [0, 1], since it is documented as a 0.0-1.0 estimate) divided by its
    own claimed `estimated_cost` (floored to a small epsilon so a
    zero-cost claim is never rewarded as infinitely good -- a real,
    deliberate anti-degenerate-solution guard, not an incidental one).
    """
    try:
        gain = float(getattr(prediction, "expected_information_gain", 0.0))
    except (TypeError, ValueError):
        gain = 0.0
    gain = max(0.0, min(1.0, gain))

    try:
        cost = float(getattr(prediction, "estimated_cost", 0.0))
    except (TypeError, ValueError):
        cost = 0.0
    cost = max(cost, 1e-6)

    return gain / cost


def safe_reversible_recovery_score(_kwargs: dict, prediction: dspy.Prediction) -> float:
    """Real, deterministic reward for `select_mitigation`'s `dspy.BestOfN`:
    zero for any candidate that does not honestly claim `safe_to_actuate`;
    otherwise a real, structural score rewarding a genuinely present
    `rollback_plan` and a genuinely present `expected_consequence`
    (an empty/placeholder value in either halves the score) -- computed
    from the candidate's own typed fields, never a second LLM judgment.
    """
    if not bool(getattr(prediction, "safe_to_actuate", False)):
        return 0.0

    score = 1.0 if str(getattr(prediction, "rollback_plan", "")).strip() else 0.5
    if not str(getattr(prediction, "expected_consequence", "")).strip():
        score *= 0.5
    return score


class SreTroubleshootingPipeline(dspy.Module):
    """Real, multi-stage DSPy `Module` exposing each troubleshooting-graph
    stage as a callable method backed by real sub-modules. Construct once,
    call whichever stage methods a real investigation needs, in whatever
    order the caller's real, gated tool execution requires.

    `ensemble_n`/`probe_search_n`/`mitigation_search_n` are real, honest
    knobs on real LM-call volume (each unit costs a real completion) --
    defaults are deliberately small (3/4/4) to keep a single investigation
    round bounded; a caller doing a real GEPA compile or a thorough live
    trial may raise them explicitly.
    """

    def __init__(
        self,
        *,
        ensemble_n: int = 3,
        probe_search_n: int = 4,
        mitigation_search_n: int = 4,
    ) -> None:
        super().__init__()
        self.ensemble_n = ensemble_n

        self.orient_stage = dspy.ChainOfThought(OrientSreIncident)
        self.normalize_stage = dspy.ChainOfThought(NormalizeSreEvidence)

        self._hypothesize_draft = dspy.ChainOfThought(HypothesizeSreCauses)
        self._hypothesize_compare = dspy.MultiChainComparison(HypothesizeSreCauses, M=ensemble_n)

        self._propose_probe = dspy.ChainOfThought(ProposeDiscriminatingObservation)
        self.select_probe_stage = dspy.BestOfN(
            self._propose_probe,
            N=probe_search_n,
            reward_fn=information_gain_per_cost,
            threshold=0.0,
        )

        self._commit_diagnosis_draft = dspy.ChainOfThought(CommitSreDiagnosis)
        self._commit_diagnosis_compare = dspy.MultiChainComparison(CommitSreDiagnosis, M=ensemble_n)

        self._construct_mitigation = dspy.ChainOfThought(ConstructSreMitigation)
        self.select_mitigation_stage = dspy.BestOfN(
            self._construct_mitigation,
            N=mitigation_search_n,
            reward_fn=safe_reversible_recovery_score,
            threshold=0.0,
        )

    def orient(self, *, episode_goal: str, system_context: str, capability_catalog: str) -> dspy.Prediction:
        return self.orient_stage(
            episode_goal=episode_goal,
            system_context=system_context,
            capability_catalog=capability_catalog,
        )

    def normalize(self, *, raw_evidence: str, prior_facts: str = "none") -> dspy.Prediction:
        return self.normalize_stage(raw_evidence=raw_evidence, prior_facts=prior_facts)

    def hypothesize(self, *, admitted_facts: str, prior_hypotheses: str = "none") -> dspy.Prediction:
        completions = [
            self._hypothesize_draft(admitted_facts=admitted_facts, prior_hypotheses=prior_hypotheses)
            for _ in range(self.ensemble_n)
        ]
        return self._hypothesize_compare(
            completions, admitted_facts=admitted_facts, prior_hypotheses=prior_hypotheses
        )

    def select_probe(
        self, *, admitted_facts: str, hypothesis_portfolio: str, capability_catalog: str
    ) -> dspy.Prediction:
        return self.select_probe_stage(
            admitted_facts=admitted_facts,
            hypothesis_portfolio=hypothesis_portfolio,
            capability_catalog=capability_catalog,
        )

    def commit_diagnosis(self, *, admitted_facts: str, hypothesis_portfolio: str) -> dspy.Prediction:
        completions = [
            self._commit_diagnosis_draft(
                admitted_facts=admitted_facts, hypothesis_portfolio=hypothesis_portfolio
            )
            for _ in range(self.ensemble_n)
        ]
        return self._commit_diagnosis_compare(
            completions, admitted_facts=admitted_facts, hypothesis_portfolio=hypothesis_portfolio
        )

    def select_mitigation(
        self, *, root_cause: str, relevant_resource_spec: str, capability_catalog: str
    ) -> dspy.Prediction:
        return self.select_mitigation_stage(
            root_cause=root_cause,
            relevant_resource_spec=relevant_resource_spec,
            capability_catalog=capability_catalog,
        )
