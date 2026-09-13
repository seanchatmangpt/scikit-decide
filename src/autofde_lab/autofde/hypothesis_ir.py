"""Canonical inert IR for hypothesis-driven forward deployment.

This module models admitted evidence, hypotheses, experiments, possibility graphs,
and solution graphs. It never actuates. All consequential execution remains a
separate production concern behind the portfolio DO boundary.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any, Iterable


def _canonical(value: Any) -> bytes:
    def default(obj: Any) -> Any:
        if hasattr(obj, "__dataclass_fields__"):
            return asdict(obj)
        if isinstance(obj, (set, frozenset)):
            return sorted(obj)
        if isinstance(obj, tuple):
            return list(obj)
        raise TypeError(type(obj).__name__)

    return json.dumps(value, default=default, sort_keys=True, separators=(",", ":")).encode()


def digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


@dataclass(frozen=True)
class EvidenceBinding:
    ref: str
    kind: str
    subject_digest: str
    admitted: bool = True

    def __post_init__(self) -> None:
        if not self.ref.strip() or not self.kind.strip() or not self.subject_digest.strip():
            raise ValueError("INCOMPLETE_EVIDENCE_BINDING_REFUSED")


@dataclass(frozen=True)
class BaselineSnapshot:
    snapshot_id: str
    world_digest: str
    process_model_digests: tuple[str, ...]
    evidence: tuple[EvidenceBinding, ...]

    def __post_init__(self) -> None:
        if not self.snapshot_id.strip() or not self.world_digest.strip():
            raise ValueError("INCOMPLETE_BASELINE_REFUSED")
        if any(not e.admitted for e in self.evidence):
            raise ValueError("UNADMITTED_BASELINE_EVIDENCE_REFUSED")

    @property
    def digest(self) -> str:
        return digest(self)


@dataclass(frozen=True)
class WorldDelta:
    before_digest: str
    after_digest: str
    baseline_digest: str
    evidence: tuple[EvidenceBinding, ...]

    def __post_init__(self) -> None:
        if self.before_digest == self.after_digest:
            raise ValueError("WORLD_DELTA_EMPTY_REFUSED")
        if not self.baseline_digest.strip():
            raise ValueError("MISSING_BASELINE_BINDING_REFUSED")
        if any(not e.admitted for e in self.evidence):
            raise ValueError("UNADMITTED_DELTA_EVIDENCE_REFUSED")

    @property
    def digest(self) -> str:
        return digest(self)


@dataclass(frozen=True)
class Hypothesis:
    hypothesis_id: str
    explanation: str
    supporting_refs: tuple[str, ...] = ()
    refuting_refs: tuple[str, ...] = ()

    @property
    def standing(self) -> str:
        if self.refuting_refs:
            return "REFUTED"
        if self.supporting_refs:
            return "SUPPORTED"
        return "CANDIDATE"


@dataclass(frozen=True)
class HypothesisPortfolio:
    delta_digest: str
    hypotheses: tuple[Hypothesis, ...]

    def __post_init__(self) -> None:
        if not self.delta_digest.strip():
            raise ValueError("MISSING_DELTA_BINDING_REFUSED")
        ids = [h.hypothesis_id for h in self.hypotheses]
        if len(ids) != len(set(ids)):
            raise ValueError("DUPLICATE_HYPOTHESIS_ID_REFUSED")

    @property
    def live(self) -> tuple[Hypothesis, ...]:
        return tuple(h for h in self.hypotheses if h.standing != "REFUTED")

    @property
    def digest(self) -> str:
        return digest(self)


@dataclass(frozen=True)
class DiscriminatingExperiment:
    experiment_id: str
    distinguishes: frozenset[str]
    observation_contract: str
    authority_requirement: str = "observe"

    def __post_init__(self) -> None:
        if len(self.distinguishes) < 2:
            raise ValueError("NON_DISCRIMINATING_EXPERIMENT_REFUSED")
        if not self.observation_contract.strip():
            raise ValueError("MISSING_OBSERVATION_CONTRACT_REFUSED")
        if self.authority_requirement != "observe":
            raise ValueError("CONSEQUENTIAL_EXPERIMENT_REFUSED")


@dataclass(frozen=True)
class ExperimentPortfolio:
    hypothesis_digest: str
    experiments: tuple[DiscriminatingExperiment, ...]

    def covers(self, hypothesis_ids: Iterable[str]) -> bool:
        wanted = set(hypothesis_ids)
        if len(wanted) < 2:
            return True
        covered: set[str] = set()
        for experiment in self.experiments:
            if experiment.distinguishes <= wanted:
                covered |= set(experiment.distinguishes)
        return wanted <= covered


@dataclass(frozen=True)
class FutureCandidate:
    future_id: str
    hypothesis_id: str
    planner_id: str
    state_digest: str
    objective_score: float
    verifier_ref: str


@dataclass(frozen=True)
class PossibilityGraph:
    hypothesis_digest: str
    futures: tuple[FutureCandidate, ...]

    def __post_init__(self) -> None:
        ids = [f.future_id for f in self.futures]
        if len(ids) != len(set(ids)):
            raise ValueError("DUPLICATE_FUTURE_ID_REFUSED")
        if any(not f.verifier_ref.strip() for f in self.futures):
            raise ValueError("UNVERIFIABLE_FUTURE_REFUSED")

    @property
    def digest(self) -> str:
        return digest(self)


@dataclass(frozen=True)
class DesiredStateEnvelope:
    objective_id: str
    required_postconditions: tuple[str, ...]
    preservation_laws: tuple[str, ...]
    authority_ceiling: frozenset[str]

    def __post_init__(self) -> None:
        if not self.required_postconditions:
            raise ValueError("EMPTY_DESIRED_STATE_REFUSED")
        if not self.preservation_laws:
            raise ValueError("MISSING_PRESERVATION_LAWS_REFUSED")


@dataclass(frozen=True)
class SolutionGraph:
    solution_id: str
    possibility_graph_digest: str
    selected_future_id: str
    preconditions: tuple[str, ...]
    transformation_ref: str
    preservation_laws: tuple[str, ...]
    postconditions: tuple[str, ...]
    verifier_ref: str
    recovery_ref: str
    authority_requirements: tuple[str, ...]

    def __post_init__(self) -> None:
        required = (
            self.solution_id,
            self.possibility_graph_digest,
            self.selected_future_id,
            self.transformation_ref,
            self.verifier_ref,
            self.recovery_ref,
        )
        if any(not x.strip() for x in required):
            raise ValueError("INCOMPLETE_SOLUTION_GRAPH_REFUSED")
        if not self.preservation_laws or not self.postconditions:
            raise ValueError("UNBOUNDED_SOLUTION_GRAPH_REFUSED")

    @property
    def digest(self) -> str:
        return digest(self)


def construct_solution_graph(
    possibilities: PossibilityGraph,
    desired: DesiredStateEnvelope,
    *,
    future_id: str,
    preconditions: tuple[str, ...],
    transformation_ref: str,
    recovery_ref: str,
    authority_requirements: tuple[str, ...],
) -> SolutionGraph:
    by_id = {candidate.future_id: candidate for candidate in possibilities.futures}
    future = by_id.get(future_id)
    if future is None:
        raise ValueError("UNKNOWN_FUTURE_REFUSED")
    if not set(authority_requirements) <= desired.authority_ceiling:
        raise ValueError("AUTHORITY_CEILING_EXCEEDED_REFUSED")
    body = {
        "possibilities": possibilities.digest,
        "future": future_id,
        "desired": asdict(desired),
        "transformation": transformation_ref,
        "recovery": recovery_ref,
    }
    return SolutionGraph(
        solution_id="solution:" + digest(body)[:24],
        possibility_graph_digest=possibilities.digest,
        selected_future_id=future_id,
        preconditions=preconditions,
        transformation_ref=transformation_ref,
        preservation_laws=desired.preservation_laws,
        postconditions=desired.required_postconditions,
        verifier_ref=future.verifier_ref,
        recovery_ref=recovery_ref,
        authority_requirements=authority_requirements,
    )
