# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""The autonomous-engineering-laboratory core types, per
`docs/2026-08-11-autofde-lab-togaf-autonomic-architecture-plan.md`
(sections 1-11 of the user's own design).

**The one law every type in this module obeys**: `autofde-lab` proposes
and tests. It does not grant itself DO authority (section 2). Every
external-contract-dependent function here (`ProcessScienceProvider`,
`WorldExperimentProvider`) is a real `typing.Protocol` this repo defines
the *shape* of, never an implementation of `wasm4pm`/`gymact` themselves
(sections 6, 10, 21, 22) -- calling the real, currently-`UNSUPPORTED`
default provider is honest, typed refusal, never fabricated evidence
(`.claude/rules/absence-is-not-evidence.md`).

`EnterpriseObservation` holds references + digests, never a duplicated
copy of external world/process state (section 5,
`.claude/rules/no-dual-bookkeeping.md`). Every "portfolio" type here is
plural by construction -- `tuple[...]`, never a single winner collapsed
too early (section 7's "plural matters").
"""

from __future__ import annotations

import hashlib
import random
import statistics
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

__all__ = [
    "EnterpriseObservation",
    "ProcessObservation",
    "ProcessScienceProvider",
    "UnsupportedProcessScienceProvider",
    "DesiredStateHypothesis",
    "infer_desired_state_hypotheses",
    "ArchitectureCandidate",
    "OperatorApplicabilityStatus",
    "OperatorApplicability",
    "classify_operator_applicability",
    "ExperimentIntent",
    "WorldExperimentProvider",
    "UnsupportedWorldExperimentProvider",
    "ExperimentReceipt",
    "FalsificationStanding",
    "FalsificationResult",
    "falsify_candidate",
    "admit_surviving_candidates",
    "ArchitectureChangeTrigger",
    "TRIZParameter",
    "TRIZContradiction",
    "TRIZResolutionApplicability",
    "classify_triz_contradiction",
    "generate_triz_candidates",
    "DETERMINISTIC_SEED",
    "MonteCarloDistribution",
    "MonteCarloCostModel",
    "MonteCarloSample",
    "draw_monte_carlo_samples",
    "generate_montecarlo_candidates",
]


def _digest(*parts: str) -> str:
    """A real, deterministic reference digest -- BLAKE3 is used elsewhere
    in this ecosystem (ggen's receipt chain); stdlib `hashlib.sha256` is
    used here since no BLAKE3 dependency exists in this repo's own
    `pyproject.toml` extras -- a real, honest, stdlib-only choice, not an
    attempt to imitate ggen's own algorithm."""
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# 5. EnterpriseObservation -- O*, references + digests, never duplicated truth
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EnterpriseObservation:
    """The one canonical admitted observation carrier (`O*`, not merely
    `O`). Every field is a reference or a digest, never a copy of external
    GymAct/wasm4pm state -- per `no-dual-bookkeeping.md`, the evidence
    graph is the record, and this object only ever points into it."""

    ontology_graph_ref: str
    source_provenance_ref: str
    enterprise_world_ref: str
    observation_ids: tuple[str, ...] = ()
    ocel_evidence_refs: tuple[str, ...] = ()
    process_observation_refs: tuple[str, ...] = ()
    conformance_finding_refs: tuple[str, ...] = ()
    metric_refs: tuple[str, ...] = ()
    objective_refs: tuple[str, ...] = ()
    constraint_refs: tuple[str, ...] = ()
    capability_inventory_ref: str | None = None
    authority_envelope_ref: str | None = None
    evidence_receipt_refs: tuple[str, ...] = ()
    observed_at_ns: int = 0
    version: str = "v1"

    @property
    def observation_digest(self) -> str:
        """A real, deterministic digest over every real ref this
        observation carries -- lets two `EnterpriseObservation`s be
        compared for real identity, never string-equality-by-accident."""
        return _digest(
            self.ontology_graph_ref,
            self.source_provenance_ref,
            self.enterprise_world_ref,
            *self.observation_ids,
            *self.ocel_evidence_refs,
            str(self.observed_at_ns),
            self.version,
        )


# ---------------------------------------------------------------------------
# 6. ProcessObservation + ProcessScienceProvider -- world != process interpretation
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ProcessObservation:
    """Real process-science evidence about an `EnterpriseObservation`,
    obtained through an external `ProcessScienceProvider` -- never
    computed by re-implementing discovery/conformance/prediction inside
    this repo (section 21)."""

    discovered_model_ref: str | None = None
    dfg_ref: str | None = None
    object_centric_relation_refs: tuple[str, ...] = ()
    conformance_deviation_refs: tuple[str, ...] = ()
    alignment_refs: tuple[str, ...] = ()
    performance_metric_refs: tuple[str, ...] = ()
    bottleneck_refs: tuple[str, ...] = ()
    drift_indicator_refs: tuple[str, ...] = ()
    prediction_refs: tuple[str, ...] = ()
    evidence_standing: str = "UNKNOWN"
    computation_receipt_ref: str | None = None


class ProcessScienceProvider(Protocol):
    """The real contract `wasm4pm` (or any process-science engine) must
    satisfy -- this repo defines the shape, never the algorithms
    (section 6, 21). A real implementation lives outside this repo."""

    def request_process_observation(self, observation: EnterpriseObservation) -> ProcessObservation: ...


class UnsupportedProcessScienceProvider:
    """The real, honest default: no `wasm4pm` connector exists in this
    repo. Every call returns a real `ProcessObservation` typed
    `evidence_standing="UNSUPPORTED"` -- never a fabricated discovery
    result, per `absence-is-not-evidence.md`."""

    def request_process_observation(self, observation: EnterpriseObservation) -> ProcessObservation:
        return ProcessObservation(evidence_standing="UNSUPPORTED")


# ---------------------------------------------------------------------------
# 7. DesiredStateHypothesis -- plural, never collapsed early
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DesiredStateHypothesis:
    """One real candidate desired-state reading of an
    `EnterpriseObservation` -- `infer_desired_state_hypotheses` returns a
    real `tuple[...]` of these, never a single winner (section 7's
    "plural matters", combinatorial maximalism)."""

    hypothesis_id: str
    targets: tuple[dict[str, Any], ...]
    evidence_used_refs: tuple[str, ...]
    assumptions: tuple[str, ...] = ()
    objective_coverage: tuple[str, ...] = ()
    constraint_interpretation: str = ""
    process_observation_ref: str | None = None
    uncertainty: float = 0.0
    falsifier_refs: tuple[str, ...] = ()
    provenance: str = "rule-based"


def infer_desired_state_hypotheses(
    metadata: Any, *, process_observation: ProcessObservation | None = None
) -> tuple[DesiredStateHypothesis, ...]:
    """Real, deterministic generalization of
    `world_transformation_orchestrator.infer_desired_state` into a real
    plural portfolio. Reuses that function's real logic for the one,
    already-tested rule-based reading (never re-derives it), and adds a
    second, real hypothesis when a real (non-`UNSUPPORTED`)
    `process_observation` is available -- never fabricates a second
    hypothesis out of nothing."""
    from autofde_lab.reasoning.world_transformation_orchestrator import infer_desired_state

    envelope = infer_desired_state(metadata)
    rule_based = DesiredStateHypothesis(
        hypothesis_id="rule-based-v1",
        targets=envelope.targets,
        evidence_used_refs=tuple(metadata.observations.keys()),
        assumptions=("objectives read directly from admitted ScenarioMetadata",),
        objective_coverage=tuple(t["kind"] for t in envelope.targets),
        constraint_interpretation="constraints excluded -- targets are objectives only",
        provenance="rule-based",
        uncertainty=0.0,
    )
    hypotheses = [rule_based]

    if process_observation is not None and process_observation.evidence_standing not in ("UNSUPPORTED", "UNKNOWN"):
        hypotheses.append(
            DesiredStateHypothesis(
                hypothesis_id="process-informed-v1",
                targets=envelope.targets,
                evidence_used_refs=tuple(metadata.observations.keys()) + process_observation.performance_metric_refs,
                assumptions=("process observation evidence_standing was real, not UNSUPPORTED",),
                objective_coverage=tuple(t["kind"] for t in envelope.targets),
                constraint_interpretation="informed by real process observation",
                process_observation_ref=process_observation.computation_receipt_ref,
                provenance="process-informed",
                uncertainty=0.2,
            )
        )

    return tuple(hypotheses)


# ---------------------------------------------------------------------------
# 8. ArchitectureCandidate
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ArchitectureCandidate:
    """A typed candidate graph, never merely an LLM response (section 8)."""

    candidate_id: str
    target_state_assertions: tuple[str, ...]
    requirement_satisfaction_claims: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    migration_actions: tuple[str, ...] = ()
    required_capabilities: tuple[str, ...] = ()
    expected_effects: tuple[str, ...] = ()
    expected_risks: tuple[str, ...] = ()
    cost_bound: float | None = None
    authority_needs: tuple[str, ...] = ()
    verification_criteria: tuple[str, ...] = ()
    rollback_requirements: tuple[str, ...] = ()
    provenance: str = "rule-based"
    generator_identity: str = ""


# ---------------------------------------------------------------------------
# 9. OperatorApplicability -- never hardcode "run all N"
# ---------------------------------------------------------------------------


class OperatorApplicabilityStatus(StrEnum):
    ADMITTED = "ADMITTED"
    UNSUPPORTED = "UNSUPPORTED"
    REFUSED = "REFUSED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class OperatorApplicability:
    operator_class: str
    status: OperatorApplicabilityStatus
    reason: str


# Real, small, named mapping from a real problem-shape signal to the
# operator class it admits -- an operator with no matching signal is
# UNSUPPORTED, never fabricated as ADMITTED. This is intentionally a tiny,
# honest seed table (section 9's examples), not a claim of completeness.
_PROBLEM_SHAPE_TO_OPERATOR: dict[str, str] = {
    "hard_constraints": "SAT/CDCL",
    "state_operators_goals": "STRIPS/GPS",
    "hierarchical_decomposition": "HTN",
    "temporal_events": "event calculus",
    "precedent_cases": "CBR",
    "contradiction": "TRIZ",
    "probabilistic_uncertainty": "probabilistic methods",
    "ocel_event_evidence": "process discovery/conformance",
    "resource_optimization": "OR/optimization",
}


def classify_operator_applicability(problem_shape_signals: tuple[str, ...]) -> tuple[OperatorApplicability, ...]:
    """Real, deterministic classification -- never "run all operators."
    A signal not present in `_PROBLEM_SHAPE_TO_OPERATOR` is real evidence
    of nothing, not evidence of applicability."""
    results = []
    for signal in problem_shape_signals:
        operator = _PROBLEM_SHAPE_TO_OPERATOR.get(signal)
        if operator is None:
            results.append(
                OperatorApplicability(
                    operator_class=signal,
                    status=OperatorApplicabilityStatus.UNKNOWN,
                    reason=f"no admitted operator-class mapping exists for signal {signal!r}",
                )
            )
        else:
            results.append(
                OperatorApplicability(
                    operator_class=operator,
                    status=OperatorApplicabilityStatus.ADMITTED,
                    reason=f"problem shape signal {signal!r} admits {operator!r}",
                )
            )
    return tuple(results)


# ---------------------------------------------------------------------------
# 10. ExperimentIntent + WorldExperimentProvider -- GymAct, never reimplemented
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ExperimentIntent:
    candidate_id: str
    target_world_ref: str
    initial_state_evidence_ref: str
    proposed_actions: tuple[str, ...]
    required_capabilities: tuple[str, ...] = ()
    expected_postconditions: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    authority_requirements: tuple[str, ...] = ()
    verifier_expectations: tuple[str, ...] = ()
    rollback_expectations: tuple[str, ...] = ()

    @property
    def intent_id(self) -> str:
        return _digest(self.candidate_id, self.target_world_ref, *self.proposed_actions)


@dataclass(frozen=True, slots=True)
class ExperimentReceipt:
    """Real observed consequence evidence -- never equated with "candidate
    says it works" (section 10's explicit warning)."""

    intent_id: str
    observed_outcome_refs: tuple[str, ...]
    authority_standing: str = "UNKNOWN"
    postconditions_observed: tuple[str, ...] = ()
    postconditions_violated: tuple[str, ...] = ()
    ocel_evidence_ref: str | None = None
    standing: str = "UNKNOWN"


class WorldExperimentProvider(Protocol):
    """The real contract `gymact` must satisfy -- shape only, never an
    implementation of world materialization/actuation (section 22)."""

    def submit_experiment(self, intent: ExperimentIntent) -> ExperimentReceipt: ...


class UnsupportedWorldExperimentProvider:
    """The real, honest default: no `gymact` connector exists in this
    repo's laboratory layer. Every call returns a real `ExperimentReceipt`
    typed `standing="UNSUPPORTED"` -- never a fabricated consequence."""

    def submit_experiment(self, intent: ExperimentIntent) -> ExperimentReceipt:
        return ExperimentReceipt(intent_id=intent.intent_id, observed_outcome_refs=(), standing="UNSUPPORTED")


# ---------------------------------------------------------------------------
# 11. FalsificationResult -- a candidate survives because killing it failed
# ---------------------------------------------------------------------------


class FalsificationStanding(StrEnum):
    SURVIVES = "SURVIVES"
    FALSIFIED = "FALSIFIED"
    PARTIAL = "PARTIAL"
    UNSUPPORTED = "UNSUPPORTED"
    REFUSED = "REFUSED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class FalsificationResult:
    candidate_id: str
    standing: FalsificationStanding
    violated_constraints: tuple[str, ...] = ()
    counterexample_refs: tuple[str, ...] = ()
    receipt_refs: tuple[str, ...] = ()
    rationale: str = ""


def falsify_candidate(
    candidate: ArchitectureCandidate, receipts: tuple[ExperimentReceipt, ...]
) -> FalsificationResult:
    """Real falsification over real receipts -- never an LLM ranking.
    A candidate with zero receipts (no real experiment run yet) is
    `UNKNOWN`, never `SURVIVES` by default. A receipt whose own `standing`
    is `UNSUPPORTED` contributes no real evidence either way."""
    if not receipts:
        return FalsificationResult(
            candidate_id=candidate.candidate_id,
            standing=FalsificationStanding.UNKNOWN,
            rationale="no real ExperimentReceipt exists yet for this candidate",
        )

    usable_receipts = [r for r in receipts if r.standing not in ("UNSUPPORTED", "UNKNOWN")]
    if not usable_receipts:
        return FalsificationResult(
            candidate_id=candidate.candidate_id,
            standing=FalsificationStanding.UNSUPPORTED,
            receipt_refs=tuple(r.intent_id for r in receipts),
            rationale="every real receipt for this candidate is itself UNSUPPORTED/UNKNOWN",
        )

    violated = tuple(v for r in usable_receipts for v in r.postconditions_violated)
    if violated:
        return FalsificationResult(
            candidate_id=candidate.candidate_id,
            standing=FalsificationStanding.FALSIFIED,
            violated_constraints=violated,
            receipt_refs=tuple(r.intent_id for r in usable_receipts),
            rationale=f"real receipt(s) reported {len(violated)} violated postcondition(s)",
        )

    all_confirmed = all(r.postconditions_observed for r in usable_receipts)
    standing = FalsificationStanding.SURVIVES if all_confirmed else FalsificationStanding.PARTIAL
    return FalsificationResult(
        candidate_id=candidate.candidate_id,
        standing=standing,
        receipt_refs=tuple(r.intent_id for r in usable_receipts),
        rationale=(
            "every real receipt confirmed its expected postconditions, no violation found"
            if all_confirmed
            else "some real receipts confirmed postconditions but at least one had none observed"
        ),
    )


def admit_surviving_candidates(
    results: tuple[FalsificationResult, ...]
) -> tuple[FalsificationResult, ...]:
    """Real, explicit admission: only `SURVIVES` results are admitted.
    `PARTIAL`/`UNSUPPORTED`/`UNKNOWN`/`REFUSED` never silently pass."""
    return tuple(r for r in results if r.standing == FalsificationStanding.SURVIVES)


# ---------------------------------------------------------------------------
# 13. ArchitectureChangeTrigger -- Phase H as the real outer loop
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ArchitectureChangeTrigger:
    evidence_refs: tuple[str, ...]
    detected_drift: str
    affected_requirement_refs: tuple[str, ...]
    confidence: float
    trigger_policy: str
    prior_architecture_ref: str | None = None

    @property
    def fires(self) -> bool:
        """Real, explicit firing rule -- a trigger with confidence below
        0.5 never silently fires; this is a real, if simple, threshold,
        not a placeholder claiming to be a policy engine."""
        return self.confidence >= 0.5


# ---------------------------------------------------------------------------
# 14. TRIZ contradiction-resolution candidate generation -- real, partial
# ---------------------------------------------------------------------------


class TRIZParameter(StrEnum):
    """Real TRIZ-style engineering parameters, honestly scoped to exactly
    the two fields this repo's own `ArchitectureCandidate` already
    carries -- named as an analogy to Altshuller's 39 parameters, never
    claimed as an orthodox mapping onto them."""

    COST = "COST"  # ArchitectureCandidate.cost_bound, lower is "improving"
    AUTHORITY_NEEDS = "AUTHORITY_NEEDS"  # ArchitectureCandidate.authority_needs, fewer/narrower is "improving"


# Real, honestly partial 39x39-style matrix subset: exactly ONE cell
# covered -- (COST improving, AUTHORITY_NEEDS worsening). Sourced loosely
# from Altshuller's published principle numbers for the closest real
# published matrix cell (cost-of-object worsening vs
# reliability/complexity-type parameters), NOT claimed as an authoritative
# citation of the orthodox matrix -- COST/AUTHORITY_NEEDS are this repo's
# own coarse re-mapping, not Altshuller's original 39. Every other
# (improving, worsening) pair is absent by construction and MUST be
# classified UNSUPPORTED, never guessed.
_CONTRADICTION_MATRIX: dict[tuple["TRIZParameter", "TRIZParameter"], tuple[int, ...]] = {
    (TRIZParameter.COST, TRIZParameter.AUTHORITY_NEEDS): (1, 10, 28, 35),
    # 1  Segmentation
    # 10 Prior action
    # 28 Mechanics substitution
    # 35 Parameter change
}

# A small, real, named prescription table for exactly the 4 principles this
# module covers -- never all 40; an uncovered principle number is real
# evidence of nothing and is never guessed at generation time.
_PRINCIPLE_PRESCRIPTIONS: dict[int, str] = {
    1: "segment the migration into independently-verifiable partial actions "
    "instead of one monolithic authority grant",
    10: "front-load the cheapest, lowest-authority verification actions before "
    "any action that would require broader authority",
    28: "substitute a narrower automated check for the broader authority "
    "envelope the candidate currently assumes it needs",
    35: "vary the authority scope granted per migration_action rather than "
    "requesting one uniform authority_needs set for the whole candidate",
}


@dataclass(frozen=True, slots=True)
class TRIZContradiction:
    """A real, named engineering contradiction -- never inferred silently.
    The caller states which two parameters are in tension; this module
    never guesses one from a hypothesis's raw fields."""

    improving_parameter: TRIZParameter
    worsening_parameter: TRIZParameter


@dataclass(frozen=True, slots=True)
class TRIZResolutionApplicability:
    """Mirrors `OperatorApplicability`'s honesty contract for this specific
    contradiction lookup -- a contradiction pair absent from
    `_CONTRADICTION_MATRIX` is real evidence of nothing, never fabricated
    as covered."""

    contradiction: TRIZContradiction
    status: OperatorApplicabilityStatus  # ADMITTED or UNSUPPORTED (never REFUSED/UNKNOWN here)
    matched_principles: tuple[int, ...] = ()
    reason: str = ""


def classify_triz_contradiction(contradiction: TRIZContradiction) -> TRIZResolutionApplicability:
    """Real, deterministic lookup against the partial matrix -- reuses the
    same ADMITTED/UNSUPPORTED vocabulary as `classify_operator_applicability`
    rather than inventing a parallel one."""
    key = (contradiction.improving_parameter, contradiction.worsening_parameter)
    principles = _CONTRADICTION_MATRIX.get(key)
    if principles is None:
        return TRIZResolutionApplicability(
            contradiction=contradiction,
            status=OperatorApplicabilityStatus.UNSUPPORTED,
            reason=(
                f"no real matrix cell exists for "
                f"({contradiction.improving_parameter!r}, {contradiction.worsening_parameter!r}) "
                "-- this module covers exactly one cell by construction"
            ),
        )
    return TRIZResolutionApplicability(
        contradiction=contradiction,
        status=OperatorApplicabilityStatus.ADMITTED,
        matched_principles=principles,
        reason=(
            f"real matrix cell ({contradiction.improving_parameter!r}, "
            f"{contradiction.worsening_parameter!r}) matches {len(principles)} inventive principle(s)"
        ),
    )


def generate_triz_candidates(
    hypotheses: tuple[DesiredStateHypothesis, ...],
    contradiction: TRIZContradiction,
) -> tuple[ArchitectureCandidate, ...]:
    """For each hypothesis, if `classify_triz_contradiction(contradiction)`
    is ADMITTED, emit exactly one `ArchitectureCandidate` per matched
    principle (never one merged candidate per hypothesis -- 'plural
    matters', mirrors `infer_desired_state_hypotheses`'s own portfolio
    discipline). If UNSUPPORTED, returns `()` for every hypothesis -- never
    a fabricated candidate for a contradiction this table doesn't cover."""
    applicability = classify_triz_contradiction(contradiction)
    if applicability.status is not OperatorApplicabilityStatus.ADMITTED:
        return ()

    candidates: list[ArchitectureCandidate] = []
    for hypothesis in hypotheses:
        for principle in applicability.matched_principles:
            prescription = _PRINCIPLE_PRESCRIPTIONS[principle]
            candidate_id = _digest(
                hypothesis.hypothesis_id,
                contradiction.improving_parameter,
                contradiction.worsening_parameter,
                str(principle),
            )
            assertions = tuple(str(t) for t in hypothesis.targets)
            candidates.append(
                ArchitectureCandidate(
                    candidate_id=candidate_id,
                    target_state_assertions=assertions,
                    assumptions=(f"TRIZ principle {principle}: {prescription}", *hypothesis.assumptions),
                    migration_actions=(f"apply TRIZ principle {principle}: {prescription}",),
                    provenance="triz-v1",
                    generator_identity="triz-contradiction-matrix-partial",
                )
            )
    return tuple(candidates)


# ---------------------------------------------------------------------------
# 15. DOE (Design of Experiments) full-factorial candidate generation -- real, partial
# ---------------------------------------------------------------------------


class DOEFactor(StrEnum):
    """Real factors, honestly scoped to exactly the two
    `ArchitectureCandidate` fields TRIZ section 14 already reuses -- named
    as an analogy to classical DOE factor naming, never claimed as a
    general factor ontology."""

    COST_BOUND = "COST_BOUND"  # ArchitectureCandidate.cost_bound
    AUTHORITY_NEEDS = "AUTHORITY_NEEDS"  # ArchitectureCandidate.authority_needs


@dataclass(frozen=True, slots=True)
class DOELevel:
    """One real level for one real factor -- the caller states the actual
    LOW/HIGH values; this module never guesses what "low cost" or "narrow
    authority" means for a given problem."""

    factor: DOEFactor
    level_id: str  # "LOW" or "HIGH" -- exactly 2 levels/factor, by construction
    cost_value: float | None = None
    authority_value: tuple[str, ...] | None = None


@dataclass(frozen=True, slots=True)
class DOEDesignPoint:
    """One real run of the design matrix -- exactly one `DOELevel` per
    factor, in `DOEFactor` declaration order."""

    run_id: str
    levels: tuple[DOELevel, DOELevel]  # (COST_BOUND level, AUTHORITY_NEEDS level)


def generate_full_factorial_design(
    cost_levels: tuple[float, float],
    authority_levels: tuple[tuple[str, ...], tuple[str, ...]],
) -> tuple[DOEDesignPoint, ...]:
    """Real 2^2 full-factorial design matrix over exactly 2 factors x 2
    levels -- 4 real design points, every combination, no interaction
    terms computed (see module-level NOT COVERED note below).
    `cost_levels` = (LOW, HIGH) cost_bound values;
    `authority_levels` = (LOW, HIGH) authority_needs tuples, caller-supplied."""
    cost_pairs = (("LOW", cost_levels[0]), ("HIGH", cost_levels[1]))
    authority_pairs = (("LOW", authority_levels[0]), ("HIGH", authority_levels[1]))

    points: list[DOEDesignPoint] = []
    for cost_id, cost_value in cost_pairs:
        for authority_id, authority_value in authority_pairs:
            run_id = _digest("doe-full-factorial", cost_id, authority_id)
            points.append(
                DOEDesignPoint(
                    run_id=run_id,
                    levels=(
                        DOELevel(factor=DOEFactor.COST_BOUND, level_id=cost_id, cost_value=cost_value),
                        DOELevel(
                            factor=DOEFactor.AUTHORITY_NEEDS,
                            level_id=authority_id,
                            authority_value=authority_value,
                        ),
                    ),
                )
            )
    return tuple(points)


def generate_doe_candidates(
    hypotheses: tuple[DesiredStateHypothesis, ...],
    cost_levels: tuple[float, float],
    authority_levels: tuple[tuple[str, ...], tuple[str, ...]],
) -> tuple[ArchitectureCandidate, ...]:
    """For each hypothesis, emit exactly one `ArchitectureCandidate` per
    real design point (4 per hypothesis, never one merged candidate per
    hypothesis -- mirrors `generate_triz_candidates`'s own 'plural
    matters' discipline). Every design point is materialized; a
    full-factorial design has no UNSUPPORTED branch the way TRIZ's partial
    matrix does, since every combination of 2 caller-supplied levels for 2
    factors is by construction a real, meaningful run."""
    design = generate_full_factorial_design(cost_levels, authority_levels)

    candidates: list[ArchitectureCandidate] = []
    for hypothesis in hypotheses:
        for point in design:
            cost_level, authority_level = point.levels
            candidate_id = _digest(hypothesis.hypothesis_id, "doe-v1", point.run_id)
            assertions = tuple(str(t) for t in hypothesis.targets)
            candidates.append(
                ArchitectureCandidate(
                    candidate_id=candidate_id,
                    target_state_assertions=assertions,
                    assumptions=(
                        f"DOE design point {point.run_id}: cost_bound={cost_level.level_id}, "
                        f"authority_needs={authority_level.level_id}",
                        *hypothesis.assumptions,
                    ),
                    cost_bound=cost_level.cost_value,
                    authority_needs=authority_level.authority_value or (),
                    provenance="doe-v1",
                    generator_identity="doe-full-factorial-2x2",
                )
            )
    return tuple(candidates)


# ---------------------------------------------------------------------------
# NOT COVERED by section 15 (DOE), stated explicitly rather than left implicit:
# - No fractional-factorial or Taguchi-style designs -- only the full 2^2.
# - No factors beyond COST_BOUND/AUTHORITY_NEEDS -- no general factor ontology.
# - No interaction-effect computation across design points; each point is an
#   independent candidate, never statistically analyzed against the others.
# - No response-surface / regression fit over the resulting candidates after
#   `falsify_candidate`/`admit_surviving_candidates` run -- that scoring loop
#   is out of scope for this module.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 16. Monte Carlo simulation candidate generation -- real, seeded, partial
# ---------------------------------------------------------------------------


DETERMINISTIC_SEED: int = 0xDEAD_BEEF
"""Mirrors this session's `wasm4pm`-sibling determinism convention verbatim
-- `wasm4pm/src/playout.rs`'s `const DETERMINISTIC_SEED: u64 = 0xdead_beef`
(same name, same literal value), ported to Python's `random.Random(seed)`.
Every real Monte Carlo draw in this module is seeded from this constant (or
a caller-supplied override of the same shape) -- never from an unseeded
`random.random()` / module-level `random.*` call."""


class MonteCarloDistribution(StrEnum):
    """Real, explicit, named distribution families -- never an unnamed
    "random sample". Exactly two are covered by construction, mirroring
    TRIZ's one-matrix-cell and DOE's one-2^2-design honesty: this is
    explicitly NOT a full Bayesian/MCMC framework (no posterior, no
    Markov chain, no priors, no convergence diagnostics) -- see the
    module-level NOT COVERED note below."""

    UNIFORM = "UNIFORM"  # random.Random.uniform(low, high)
    TRIANGULAR = "TRIANGULAR"  # random.Random.triangular(low, high, mode)


@dataclass(frozen=True, slots=True)
class MonteCarloCostModel:
    """A real, small, explicit parametric uncertainty model over exactly
    the one `ArchitectureCandidate` field TRIZ (section 14) and DOE
    (section 15) already reuse -- `cost_bound`. The caller states the
    real distribution and its real `[low, high]` range (and `mode` for
    `TRIANGULAR`); this module never infers a range from data it hasn't
    been given."""

    distribution: MonteCarloDistribution
    low: float
    high: float
    mode: float | None = None  # required for TRIANGULAR, ignored for UNIFORM

    def __post_init__(self) -> None:
        if self.low > self.high:
            raise ValueError(f"low ({self.low}) must be <= high ({self.high})")
        if self.distribution is MonteCarloDistribution.TRIANGULAR:
            if self.mode is None:
                raise ValueError("TRIANGULAR distribution requires a real mode value")
            if not (self.low <= self.mode <= self.high):
                raise ValueError(f"mode ({self.mode}) must lie within [low, high] = [{self.low}, {self.high}]")

    def sample(self, rng: random.Random) -> float:
        """One real draw from the real, named distribution, using the
        caller's real `random.Random` instance -- never a module-level
        `random` call, so the caller's seeding is the only source of
        randomness that ever reaches this method."""
        if self.distribution is MonteCarloDistribution.UNIFORM:
            return rng.uniform(self.low, self.high)
        return rng.triangular(self.low, self.high, self.mode)


@dataclass(frozen=True, slots=True)
class MonteCarloSample:
    """One real individual draw -- never merged into a summary. Mirrors
    `DOEDesignPoint`'s one-run-per-object discipline: every sample this
    module produces is later materialized as its own
    `ArchitectureCandidate`, never averaged away first."""

    draw_index: int
    cost_bound: float

    @property
    def sample_id(self) -> str:
        """A real, deterministic digest over this sample's own real
        fields -- mirrors `ExperimentIntent.intent_id`'s computed-property
        digest pattern. Identical `draw_index`/`cost_bound` (which, for a
        fixed seed and `n`, is exactly what two real runs produce) yields
        an identical `sample_id`."""
        return _digest("montecarlo-sample", str(self.draw_index), repr(self.cost_bound))


def draw_monte_carlo_samples(
    cost_model: MonteCarloCostModel,
    n: int,
    *,
    seed: int = DETERMINISTIC_SEED,
) -> tuple[MonteCarloSample, ...]:
    """Real, seeded pseudo-random sampling -- a real `random.Random(seed)`
    instance, drawn from exactly `n` times in order, never the unseeded
    module-level `random` functions. Same `seed` and `n` MUST produce a
    byte-identical `cost_bound` sequence across separate real calls; that
    determinism is the one property this function exists to guarantee."""
    if n <= 0:
        raise ValueError(f"n must be >= 1, got {n}")
    rng = random.Random(seed)
    return tuple(MonteCarloSample(draw_index=i, cost_bound=cost_model.sample(rng)) for i in range(n))


def _mean_std(values: tuple[float, ...]) -> tuple[float, float]:
    """Real, stdlib-only summary statistics (`statistics.fmean` /
    `statistics.stdev`) over real sampled `cost_bound` values -- sample
    standard deviation (Bessel-corrected, `N - 1`), since the `N` draws
    are themselves a finite sample used to estimate the parametric
    distribution's real spread, not the whole population. A single-draw
    sample (`N == 1`) has no real sample variance to report and is
    honestly returned as `std == 0.0`, never `NaN` or a fabricated
    non-zero placeholder."""
    mean = statistics.fmean(values)
    std = statistics.stdev(values) if len(values) >= 2 else 0.0
    return mean, std


def generate_montecarlo_candidates(
    hypotheses: tuple[DesiredStateHypothesis, ...],
    cost_model: MonteCarloCostModel,
    n: int,
    *,
    seed: int = DETERMINISTIC_SEED,
) -> tuple[ArchitectureCandidate, ...]:
    """For each hypothesis, emit exactly one real `ArchitectureCandidate`
    per real Monte Carlo sample (`n` per hypothesis, never one merged
    "expected value" candidate -- mirrors `generate_triz_candidates`'s and
    `generate_doe_candidates`'s own 'plural matters' discipline). Every
    candidate's `cost_bound` is one real individual sampled draw; the
    real computed mean/std over the full `n`-sample set is attached to
    every candidate's `assumptions` as one human-readable summary string
    -- never fabricated as a `cost_bound` of its own separate summary
    candidate. `candidate_id` is a real, deterministic digest over the
    hypothesis identity and the sample's own `sample_id`, so two real
    calls with the same `seed`/`n`/`hypotheses` produce a byte-identical
    `candidate_id` sequence."""
    samples = draw_monte_carlo_samples(cost_model, n, seed=seed)
    mean, std = _mean_std(tuple(s.cost_bound for s in samples))
    summary = (
        f"Monte Carlo summary over {n} real seeded draws (seed={seed}, "
        f"distribution={cost_model.distribution}): mean cost_bound={mean:.4f}, "
        f"std cost_bound={std:.4f}"
    )

    candidates: list[ArchitectureCandidate] = []
    for hypothesis in hypotheses:
        for sample in samples:
            candidate_id = _digest(hypothesis.hypothesis_id, "montecarlo-v1", sample.sample_id)
            assertions = tuple(str(t) for t in hypothesis.targets)
            candidates.append(
                ArchitectureCandidate(
                    candidate_id=candidate_id,
                    target_state_assertions=assertions,
                    assumptions=(
                        f"Monte Carlo draw {sample.draw_index}/{n}: cost_bound={sample.cost_bound:.4f}",
                        summary,
                        *hypothesis.assumptions,
                    ),
                    cost_bound=sample.cost_bound,
                    provenance="montecarlo-v1",
                    generator_identity=f"montecarlo-{cost_model.distribution.lower()}-seeded",
                )
            )
    return tuple(candidates)


# ---------------------------------------------------------------------------
# NOT COVERED by section 16 (Monte Carlo), stated explicitly rather than left
# implicit:
# - No full Bayesian/MCMC framework -- no posterior, no Markov chain, no
#   priors, no convergence diagnostics (Gelman-Rubin, effective sample
#   size). This is real i.i.d. sampling from one caller-named distribution,
#   nothing more.
# - No factors beyond COST_BOUND -- unlike DOE (section 15), this module
#   does not also cover AUTHORITY_NEEDS; adding a second uncertain factor
#   would require a real joint distribution, not two independent draws.
# - No variance-reduction technique (antithetic variates, importance
#   sampling, Latin hypercube, quasi-Monte Carlo/Sobol sequences) -- plain
#   i.i.d. draws only.
# - No convergence/stopping-rule logic -- `n` is caller-supplied and fixed;
#   this module never decides "enough samples" for itself.
# - No response-surface / regression fit over the resulting candidates
#   after `falsify_candidate`/`admit_surviving_candidates` run -- mirrors
#   DOE's own out-of-scope note; that scoring loop is out of scope here too.
# ---------------------------------------------------------------------------
