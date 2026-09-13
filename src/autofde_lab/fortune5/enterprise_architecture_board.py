"""Evidence-bounded Fortune-5 enterprise architecture portfolio court.

This module joins existing AutoFDE-Lab laboratory artifacts and planner-league
outcomes without granting execution or organizational authority. Candidate
claims are hypotheses; only independently supplied requirement evidence and
executed experiment evidence can raise technical standing.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite
from typing import Any, Iterable, Sequence

from autofde_lab.fortune5.enterprise_architecture_catalog import (
    ENTERPRISE_ARCHITECTURE_PRINCIPLES,
    ENTERPRISE_REQUIREMENT_KINDS,
    ENTERPRISE_RISK_CLASSES,
    ENTERPRISE_VIEWPOINTS,
)


class RequirementStanding(str, Enum):
    SATISFIED = "SATISFIED"
    VIOLATED = "VIOLATED"
    UNKNOWN = "UNKNOWN"
    UNSUPPORTED = "UNSUPPORTED"


class ArchitectureAdmissionStanding(str, Enum):
    ADMITTED_FOR_MANUFACTURE = "ADMITTED_FOR_MANUFACTURE"
    REFUSED = "REFUSED"
    UNKNOWN = "UNKNOWN"
    UNSUPPORTED = "UNSUPPORTED"


@dataclass(frozen=True, slots=True)
class EnterpriseRequirement:
    requirement_id: str
    kind_id: str
    statement: str
    mandatory: bool = True
    source_evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.kind_id not in ENTERPRISE_REQUIREMENT_KINDS:
            raise ValueError(f"REFUSED:UNKNOWN_REQUIREMENT_KIND:{self.kind_id}")
        if not self.requirement_id.strip():
            raise ValueError("REFUSED:EMPTY_REQUIREMENT_ID")


@dataclass(frozen=True, slots=True)
class RequirementEvidence:
    requirement_id: str
    standing: RequirementStanding
    evidence_refs: tuple[str, ...] = ()
    subject_id: str = ""
    rationale: str = ""

    def __post_init__(self) -> None:
        if (
            self.standing
            in (RequirementStanding.SATISFIED, RequirementStanding.VIOLATED)
            and not self.evidence_refs
        ):
            raise ValueError("REFUSED:UNRECEIPTED_REQUIREMENT_JUDGMENT")


@dataclass(frozen=True, slots=True)
class PlannerRoute:
    role_id: str
    compatible_planners: tuple[str, ...]
    refused_planners: tuple[str, ...]
    unsupported_planners: tuple[str, ...]
    novelty_request: Any | None


@dataclass(frozen=True, slots=True)
class CandidateAssessment:
    candidate_id: str
    requirement_results: tuple[RequirementEvidence, ...]
    covered_viewpoints: tuple[str, ...]
    missing_viewpoints: tuple[str, ...]
    risk_classes: tuple[str, ...]

    @property
    def violated_requirements(self) -> tuple[str, ...]:
        return tuple(
            r.requirement_id
            for r in self.requirement_results
            if r.standing is RequirementStanding.VIOLATED
        )


@dataclass(frozen=True, slots=True)
class ViewpointEvidence:
    viewpoint_id: str
    evidence_refs: tuple[str, ...]
    subject_id: str = ""

    def __post_init__(self) -> None:
        if self.viewpoint_id not in ENTERPRISE_VIEWPOINTS:
            raise ValueError(f"REFUSED:UNKNOWN_VIEWPOINT:{self.viewpoint_id}")
        if not self.evidence_refs:
            raise ValueError("REFUSED:UNRECEIPTED_VIEWPOINT_COVERAGE")


@dataclass(frozen=True, slots=True)
class ExecutionEvidence:
    receipt_id: str
    intent_id: str
    standing: str
    observed_outcome_refs: tuple[str, ...]
    candidate_id: str = ""
    ocel_evidence_ref: str | None = None

    def __post_init__(self) -> None:
        if self.standing == "ALIVE" and (
            not self.receipt_id.strip()
            or not self.intent_id.strip()
            or not self.candidate_id.strip()
            or not self.observed_outcome_refs
        ):
            raise ValueError("REFUSED:UNRECEIPTED_EXECUTION_EVIDENCE")
        if self.standing == "ALIVE" and self.receipt_id == self.intent_id:
            raise ValueError("REFUSED:RECEIPT_IDENTITY_COLLIDES_WITH_INTENT")


@dataclass(frozen=True, slots=True)
class ExperimentEconomics:
    intent_id: str
    expected_information_gain: float
    reversibility: float
    consequence_value: float
    cost: float
    execution_risk: float
    time: float

    def __post_init__(self) -> None:
        values = (
            self.expected_information_gain,
            self.reversibility,
            self.consequence_value,
            self.cost,
            self.execution_risk,
            self.time,
        )
        if not all(isfinite(v) and v >= 0.0 for v in values):
            raise ValueError("REFUSED:INVALID_EXPERIMENT_ECONOMICS")

    @property
    def priority_score(self) -> float:
        numerator = (
            self.expected_information_gain * self.reversibility * self.consequence_value
        )
        denominator = max(self.cost * self.execution_risk * self.time, 1e-12)
        return numerator / denominator


@dataclass(frozen=True, slots=True)
class AdmittedArchitecture:
    candidate_id: str
    observation_digest: str
    evidence_dag_refs: tuple[str, ...]
    requirement_refs: tuple[str, ...]
    constraint_refs: tuple[str, ...]
    required_capabilities: tuple[str, ...]
    generation_profile: str
    verification_obligations: tuple[str, ...]
    authority_requirements: tuple[str, ...]
    technical_standing: str = "TECHNICALLY_ADMITTED"
    organizational_standing: str = "UNKNOWN"

    def __post_init__(self) -> None:
        if not self.evidence_dag_refs:
            raise ValueError("REFUSED:ADMITTED_ARCHITECTURE_REQUIRES_EVIDENCE")
        if self.organizational_standing != "UNKNOWN":
            raise ValueError("REFUSED:ORGANIZATIONAL_STANDING_IS_EXTERNAL")


@dataclass(frozen=True, slots=True)
class ArchitectureAdmissionDecision:
    candidate_id: str
    standing: ArchitectureAdmissionStanding
    reason: str
    artifact: AdmittedArchitecture | None = None


class EnterpriseArchitectureBoard:
    """Mechanical architecture board for SELECT/CONSTRUCT; never DO."""

    def __init__(self, required_viewpoints: Iterable[str] | None = None) -> None:
        viewpoints = tuple(required_viewpoints or ENTERPRISE_VIEWPOINTS.keys())
        unknown = tuple(v for v in viewpoints if v not in ENTERPRISE_VIEWPOINTS)
        if unknown:
            raise ValueError(f"REFUSED:UNKNOWN_VIEWPOINT:{unknown[0]}")
        self.required_viewpoints = viewpoints

    @staticmethod
    def route_planner_results(results: Sequence[Any]) -> PlannerRoute:
        if not results:
            raise ValueError("REFUSED:EMPTY_PLANNER_ROUTE")
        from autofde_lab.planner_league.core import PlannerLeague

        roles = {r.role_id for r in results}
        if len(roles) != 1:
            raise ValueError("REFUSED:MIXED_ROLE_ROUTE")
        role_id = next(iter(roles))

        def standing_value(result: Any) -> str:
            standing = result.standing
            return str(getattr(standing, "value", standing))

        return PlannerRoute(
            role_id=role_id,
            compatible_planners=tuple(
                r.planner_id for r in results if standing_value(r) == "COMPATIBLE"
            ),
            refused_planners=tuple(
                r.planner_id for r in results if standing_value(r) == "REFUSED"
            ),
            unsupported_planners=tuple(
                r.planner_id for r in results if standing_value(r) == "UNSUPPORTED"
            ),
            novelty_request=PlannerLeague.novelty_frontier(results),
        )

    def assess_candidate(
        self,
        candidate: Any,
        requirements: Sequence[EnterpriseRequirement],
        evidence: Sequence[RequirementEvidence],
        *,
        viewpoint_evidence: Sequence[ViewpointEvidence],
        risk_classes: Iterable[str] = (),
    ) -> CandidateAssessment:
        candidate_id = str(candidate.candidate_id)
        for item in evidence:
            if item.subject_id != candidate_id:
                raise ValueError(
                    f"REFUSED:REQUIREMENT_EVIDENCE_SUBJECT_MISMATCH:{item.requirement_id}"
                )
        for item in viewpoint_evidence:
            if item.subject_id != candidate_id:
                raise ValueError(
                    f"REFUSED:VIEWPOINT_EVIDENCE_SUBJECT_MISMATCH:{item.viewpoint_id}"
                )
        evidence_by_requirement = {item.requirement_id: item for item in evidence}
        results: list[RequirementEvidence] = []
        for requirement in requirements:
            result = evidence_by_requirement.get(requirement.requirement_id)
            if result is None:
                result = RequirementEvidence(
                    requirement_id=requirement.requirement_id,
                    standing=RequirementStanding.UNKNOWN,
                    subject_id=candidate_id,
                    rationale="no independent evidence was supplied",
                )
            results.append(result)

        covered = tuple(dict.fromkeys(item.viewpoint_id for item in viewpoint_evidence))
        risks = tuple(dict.fromkeys(risk_classes))
        unknown_risks = tuple(r for r in risks if r not in ENTERPRISE_RISK_CLASSES)
        if unknown_risks:
            raise ValueError(f"REFUSED:UNKNOWN_RISK_CLASS:{unknown_risks[0]}")

        missing = tuple(v for v in self.required_viewpoints if v not in covered)
        return CandidateAssessment(
            candidate_id=candidate_id,
            requirement_results=tuple(results),
            covered_viewpoints=covered,
            missing_viewpoints=missing,
            risk_classes=risks,
        )

    @staticmethod
    def prioritize_experiments(
        items: Iterable[ExperimentEconomics],
    ) -> tuple[ExperimentEconomics, ...]:
        return tuple(
            sorted(items, key=lambda item: (-item.priority_score, item.intent_id))
        )

    def admit_for_manufacture(
        self,
        *,
        observation: Any,
        candidate: Any,
        requirements: Sequence[EnterpriseRequirement],
        assessment: CandidateAssessment,
        falsification: Any,
        execution_evidence: Sequence[ExecutionEvidence],
        viewpoint_evidence: Sequence[ViewpointEvidence],
        generation_profile: str,
    ) -> ArchitectureAdmissionDecision:
        if assessment.candidate_id != str(candidate.candidate_id):
            return ArchitectureAdmissionDecision(
                candidate_id=str(candidate.candidate_id),
                standing=ArchitectureAdmissionStanding.REFUSED,
                reason="REFUSED:ASSESSMENT_SUBJECT_MISMATCH",
            )
        candidate_id = str(candidate.candidate_id)
        mandatory_requirements = tuple(r for r in requirements if r.mandatory)
        mandatory = {r.requirement_id for r in mandatory_requirements}
        for requirement in mandatory_requirements:
            if not requirement.source_evidence_refs:
                return ArchitectureAdmissionDecision(
                    candidate_id,
                    ArchitectureAdmissionStanding.UNKNOWN,
                    f"UNKNOWN:UNGROUNDED_MANDATORY_REQUIREMENT:{requirement.requirement_id}",
                )
        result_by_id = {r.requirement_id: r for r in assessment.requirement_results}
        for requirement_id in mandatory:
            result = result_by_id.get(requirement_id)
            if result is None or result.standing is RequirementStanding.UNKNOWN:
                return ArchitectureAdmissionDecision(
                    str(candidate.candidate_id),
                    ArchitectureAdmissionStanding.UNKNOWN,
                    f"UNKNOWN:MANDATORY_REQUIREMENT:{requirement_id}",
                )
            if result.standing is RequirementStanding.UNSUPPORTED:
                return ArchitectureAdmissionDecision(
                    str(candidate.candidate_id),
                    ArchitectureAdmissionStanding.UNSUPPORTED,
                    f"UNSUPPORTED:MANDATORY_REQUIREMENT:{requirement_id}",
                )
            if result.standing is RequirementStanding.VIOLATED:
                return ArchitectureAdmissionDecision(
                    str(candidate.candidate_id),
                    ArchitectureAdmissionStanding.REFUSED,
                    f"REFUSED:MANDATORY_REQUIREMENT_VIOLATED:{requirement_id}",
                )

        if assessment.missing_viewpoints:
            return ArchitectureAdmissionDecision(
                candidate_id,
                ArchitectureAdmissionStanding.UNKNOWN,
                f"UNKNOWN:MISSING_VIEWPOINT:{assessment.missing_viewpoints[0]}",
            )
        supplied_viewpoints = {item.viewpoint_id for item in viewpoint_evidence}
        for item in viewpoint_evidence:
            if item.subject_id != candidate_id:
                return ArchitectureAdmissionDecision(
                    candidate_id,
                    ArchitectureAdmissionStanding.REFUSED,
                    f"REFUSED:VIEWPOINT_EVIDENCE_SUBJECT_MISMATCH:{item.viewpoint_id}",
                )
        missing_at_admission = tuple(
            v for v in self.required_viewpoints if v not in supplied_viewpoints
        )
        if missing_at_admission:
            return ArchitectureAdmissionDecision(
                candidate_id,
                ArchitectureAdmissionStanding.UNKNOWN,
                f"UNKNOWN:MISSING_ADMISSION_VIEWPOINT_EVIDENCE:{missing_at_admission[0]}",
            )

        falsification_subject_id = str(getattr(falsification, "candidate_id", ""))
        if falsification_subject_id != candidate_id:
            return ArchitectureAdmissionDecision(
                candidate_id,
                ArchitectureAdmissionStanding.REFUSED,
                "REFUSED:FALSIFICATION_SUBJECT_MISMATCH",
            )
        falsification_value = getattr(
            getattr(falsification, "standing", None),
            "value",
            getattr(falsification, "standing", None),
        )
        falsification_evidence_refs = tuple(
            dict.fromkeys(
                tuple(getattr(falsification, "receipt_refs", ()))
                + tuple(getattr(falsification, "counterexample_refs", ()))
            )
        )
        if (
            falsification_value in {"FALSIFIED", "SURVIVES"}
            and not falsification_evidence_refs
        ):
            return ArchitectureAdmissionDecision(
                candidate_id,
                ArchitectureAdmissionStanding.UNKNOWN,
                "UNKNOWN:UNRECEIPTED_FALSIFICATION_STANDING",
            )
        if falsification_value == "FALSIFIED":
            return ArchitectureAdmissionDecision(
                candidate_id,
                ArchitectureAdmissionStanding.REFUSED,
                "REFUSED:CANDIDATE_FALSIFIED",
            )
        if falsification_value == "UNSUPPORTED":
            return ArchitectureAdmissionDecision(
                str(candidate.candidate_id),
                ArchitectureAdmissionStanding.UNSUPPORTED,
                "UNSUPPORTED:FALSIFICATION_EVIDENCE",
            )
        if falsification_value != "SURVIVES":
            return ArchitectureAdmissionDecision(
                str(candidate.candidate_id),
                ArchitectureAdmissionStanding.UNKNOWN,
                f"UNKNOWN:FALSIFICATION_STANDING:{falsification_value}",
            )

        evidence_refs: list[str] = []
        for item in execution_evidence:
            if item.candidate_id != candidate_id:
                return ArchitectureAdmissionDecision(
                    candidate_id,
                    ArchitectureAdmissionStanding.REFUSED,
                    f"REFUSED:EXECUTION_EVIDENCE_SUBJECT_MISMATCH:{item.receipt_id}",
                )
        alive_execution = tuple(
            item for item in execution_evidence if item.standing == "ALIVE"
        )
        if not alive_execution:
            return ArchitectureAdmissionDecision(
                str(candidate.candidate_id),
                ArchitectureAdmissionStanding.UNKNOWN,
                "UNKNOWN:NO_ALIVE_EXECUTION_RECEIPT",
            )
        for item in alive_execution:
            evidence_refs.append(item.receipt_id)
            evidence_refs.extend(item.observed_outcome_refs)
            if item.ocel_evidence_ref:
                evidence_refs.append(item.ocel_evidence_ref)
        evidence_refs.extend(falsification_evidence_refs)
        for requirement in requirements:
            evidence_refs.extend(requirement.source_evidence_refs)
        for result in assessment.requirement_results:
            evidence_refs.extend(result.evidence_refs)
        for item in viewpoint_evidence:
            evidence_refs.extend(item.evidence_refs)
        evidence_refs = list(dict.fromkeys(evidence_refs))
        if not evidence_refs:
            return ArchitectureAdmissionDecision(
                str(candidate.candidate_id),
                ArchitectureAdmissionStanding.UNKNOWN,
                "UNKNOWN:NO_OBSERVED_EVIDENCE_FOR_ADMISSION",
            )

        artifact = AdmittedArchitecture(
            candidate_id=str(candidate.candidate_id),
            observation_digest=str(observation.observation_digest),
            evidence_dag_refs=tuple(evidence_refs),
            requirement_refs=tuple(r.requirement_id for r in requirements),
            constraint_refs=tuple(getattr(observation, "constraint_refs", ())),
            required_capabilities=tuple(
                getattr(candidate, "required_capabilities", ())
            ),
            generation_profile=generation_profile,
            verification_obligations=tuple(
                getattr(candidate, "verification_criteria", ())
            ),
            authority_requirements=tuple(getattr(candidate, "authority_needs", ())),
        )
        return ArchitectureAdmissionDecision(
            str(candidate.candidate_id),
            ArchitectureAdmissionStanding.ADMITTED_FOR_MANUFACTURE,
            "ADMITTED:TECHNICAL_EVIDENCE_COMPLETE:ORGANIZATIONAL_AUTHORITY_EXTERNAL",
            artifact,
        )


__all__ = [
    "AdmittedArchitecture",
    "ArchitectureAdmissionDecision",
    "ArchitectureAdmissionStanding",
    "CandidateAssessment",
    "EnterpriseArchitectureBoard",
    "EnterpriseRequirement",
    "ExecutionEvidence",
    "ExperimentEconomics",
    "PlannerRoute",
    "RequirementEvidence",
    "ViewpointEvidence",
    "RequirementStanding",
    "ENTERPRISE_ARCHITECTURE_PRINCIPLES",
]
