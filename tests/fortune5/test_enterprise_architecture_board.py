from dataclasses import dataclass
from enum import Enum

import pytest

from autofde_lab.fortune5.enterprise_architecture_board import (
    ArchitectureAdmissionStanding,
    EnterpriseArchitectureBoard,
    EnterpriseRequirement,
    ExecutionEvidence,
    ExperimentEconomics,
    RequirementEvidence,
    RequirementStanding,
    ViewpointEvidence,
)
from autofde_lab.fortune5.enterprise_architecture_catalog import ENTERPRISE_VIEWPOINTS


@dataclass(frozen=True)
class Observation:
    observation_digest: str = "obs-digest-1"
    constraint_refs: tuple[str, ...] = (
        "constraint:residency",
        "constraint:availability",
    )


@dataclass(frozen=True)
class Candidate:
    candidate_id: str = "candidate-global-checkout-v1"
    required_capabilities: tuple[str, ...] = ("planner:temporal", "gymact:azure")
    verification_criteria: tuple[str, ...] = ("verify:slo", "verify:residency")
    authority_needs: tuple[str, ...] = ("authority:change-board",)


class FStanding(str, Enum):
    SURVIVES = "SURVIVES"
    FALSIFIED = "FALSIFIED"


@dataclass(frozen=True)
class Falsification:
    standing: FStanding
    receipt_refs: tuple[str, ...] = ("receipt:falsification:1",)
    candidate_id: str = Candidate().candidate_id


def _requirements():
    return (
        EnterpriseRequirement(
            "req:availability",
            "AvailabilitySLORequirement",
            "99.99% availability",
            source_evidence_refs=("source:slo",),
        ),
        EnterpriseRequirement(
            "req:residency",
            "DataResidencyRequirement",
            "EU data remains in EU",
            source_evidence_refs=("source:residency-policy",),
        ),
        EnterpriseRequirement(
            "req:cost",
            "CostCeilingRequirement",
            "monthly cost <= ceiling",
            mandatory=False,
            source_evidence_refs=("source:budget",),
        ),
    )


def _requirement_evidence():
    return (
        RequirementEvidence(
            "req:availability",
            RequirementStanding.SATISFIED,
            ("receipt:req:availability",),
            subject_id=Candidate().candidate_id,
        ),
        RequirementEvidence(
            "req:residency",
            RequirementStanding.SATISFIED,
            ("receipt:req:residency",),
            subject_id=Candidate().candidate_id,
        ),
        RequirementEvidence(
            "req:cost", RequirementStanding.UNKNOWN, subject_id=Candidate().candidate_id
        ),
    )


def _viewpoint_evidence():
    return tuple(
        ViewpointEvidence(
            v, (f"receipt:view:{v}",), subject_id=Candidate().candidate_id
        )
        for v in ENTERPRISE_VIEWPOINTS
    )


def test_requirement_judgment_cannot_self_certify_without_evidence():
    with pytest.raises(ValueError, match="UNRECEIPTED_REQUIREMENT_JUDGMENT"):
        RequirementEvidence(
            "req:availability",
            RequirementStanding.SATISFIED,
            subject_id=Candidate().candidate_id,
        )


def test_full_enterprise_viewpoint_court_requires_evidence_for_every_viewpoint():
    board = EnterpriseArchitectureBoard()
    viewpoints = _viewpoint_evidence()[:-1]
    assessment = board.assess_candidate(
        Candidate(),
        _requirements(),
        _requirement_evidence(),
        viewpoint_evidence=viewpoints,
        risk_classes=("OperationalRisk", "ComplianceRisk"),
    )
    assert assessment.missing_viewpoints == (tuple(ENTERPRISE_VIEWPOINTS)[-1],)


def test_information_gain_prioritization_prefers_reversible_low_risk_experiment():
    low_risk = ExperimentEconomics("intent:a", 0.8, 0.9, 1.0, 10.0, 0.1, 2.0)
    high_risk = ExperimentEconomics("intent:b", 0.9, 0.5, 1.0, 10.0, 0.8, 2.0)
    ranked = EnterpriseArchitectureBoard.prioritize_experiments((high_risk, low_risk))
    assert [item.intent_id for item in ranked] == ["intent:a", "intent:b"]


def test_falsified_candidate_is_refused_even_when_requirements_are_green():
    board = EnterpriseArchitectureBoard()
    assessment = board.assess_candidate(
        Candidate(),
        _requirements(),
        _requirement_evidence(),
        viewpoint_evidence=_viewpoint_evidence(),
        risk_classes=("OperationalRisk",),
    )
    decision = board.admit_for_manufacture(
        observation=Observation(),
        candidate=Candidate(),
        requirements=_requirements(),
        assessment=assessment,
        falsification=Falsification(FStanding.FALSIFIED),
        execution_evidence=(
            ExecutionEvidence(
                "receipt:1",
                "intent:1",
                "ALIVE",
                ("outcome:1",),
                candidate_id=Candidate().candidate_id,
            ),
        ),
        viewpoint_evidence=_viewpoint_evidence(),
        generation_profile="ggen:fortune5-v1",
    )
    assert decision.standing is ArchitectureAdmissionStanding.REFUSED
    assert decision.artifact is None


def test_unknown_mandatory_requirement_blocks_manufacturing_admission():
    board = EnterpriseArchitectureBoard()
    evidence = (
        RequirementEvidence(
            "req:availability",
            RequirementStanding.SATISFIED,
            ("receipt:req:availability",),
            subject_id=Candidate().candidate_id,
        ),
        RequirementEvidence(
            "req:residency",
            RequirementStanding.UNKNOWN,
            subject_id=Candidate().candidate_id,
        ),
    )
    assessment = board.assess_candidate(
        Candidate(),
        _requirements(),
        evidence,
        viewpoint_evidence=_viewpoint_evidence(),
    )
    decision = board.admit_for_manufacture(
        observation=Observation(),
        candidate=Candidate(),
        requirements=_requirements(),
        assessment=assessment,
        falsification=Falsification(FStanding.SURVIVES),
        execution_evidence=(
            ExecutionEvidence(
                "receipt:1",
                "intent:1",
                "ALIVE",
                ("outcome:1",),
                candidate_id=Candidate().candidate_id,
            ),
        ),
        viewpoint_evidence=_viewpoint_evidence(),
        generation_profile="ggen:fortune5-v1",
    )
    assert decision.standing is ArchitectureAdmissionStanding.UNKNOWN


def test_survivor_with_receipted_requirements_viewpoints_and_execution_becomes_manufacturing_input_only():
    board = EnterpriseArchitectureBoard()
    assessment = board.assess_candidate(
        Candidate(),
        _requirements(),
        _requirement_evidence(),
        viewpoint_evidence=_viewpoint_evidence(),
        risk_classes=("OperationalRisk", "ComplianceRisk", "ResilienceRisk"),
    )
    execution = ExecutionEvidence(
        receipt_id="gymact:receipt:sha256:abc",
        intent_id="intent:global-checkout",
        standing="ALIVE",
        observed_outcome_refs=("outcome:availability", "outcome:residency"),
        candidate_id=Candidate().candidate_id,
        ocel_evidence_ref="ocel:experiment:42",
    )
    decision = board.admit_for_manufacture(
        observation=Observation(),
        candidate=Candidate(),
        requirements=_requirements(),
        assessment=assessment,
        falsification=Falsification(FStanding.SURVIVES),
        execution_evidence=(execution,),
        viewpoint_evidence=_viewpoint_evidence(),
        generation_profile="ggen:fortune5-v1",
    )
    assert decision.standing is ArchitectureAdmissionStanding.ADMITTED_FOR_MANUFACTURE
    assert decision.artifact is not None
    assert decision.artifact.technical_standing == "TECHNICALLY_ADMITTED"
    assert decision.artifact.organizational_standing == "UNKNOWN"
    assert "gymact:receipt:sha256:abc" in decision.artifact.evidence_dag_refs
    assert decision.artifact.authority_requirements == ("authority:change-board",)


def test_alive_execution_evidence_requires_receipt_identity_and_observed_outcome():
    with pytest.raises(ValueError, match="UNRECEIPTED_EXECUTION_EVIDENCE"):
        ExecutionEvidence(
            "",
            "intent:1",
            "ALIVE",
            ("outcome:1",),
            candidate_id=Candidate().candidate_id,
        )
    with pytest.raises(ValueError, match="UNRECEIPTED_EXECUTION_EVIDENCE"):
        ExecutionEvidence(
            "receipt:1", "intent:1", "ALIVE", (), candidate_id=Candidate().candidate_id
        )


def test_cross_subject_evidence_is_refused_before_assessment():
    board = EnterpriseArchitectureBoard()
    wrong = (
        RequirementEvidence(
            "req:availability",
            RequirementStanding.SATISFIED,
            ("receipt:req:other",),
            subject_id="candidate:other",
        ),
    )
    with pytest.raises(ValueError, match="REQUIREMENT_EVIDENCE_SUBJECT_MISMATCH"):
        board.assess_candidate(
            Candidate(),
            _requirements(),
            wrong,
            viewpoint_evidence=_viewpoint_evidence(),
        )


def test_execution_receipt_must_bind_candidate_and_not_alias_intent():
    with pytest.raises(ValueError, match="RECEIPT_IDENTITY_COLLIDES_WITH_INTENT"):
        ExecutionEvidence(
            "intent:1",
            "intent:1",
            "ALIVE",
            ("outcome:1",),
            candidate_id=Candidate().candidate_id,
        )

    board = EnterpriseArchitectureBoard()
    assessment = board.assess_candidate(
        Candidate(),
        _requirements(),
        _requirement_evidence(),
        viewpoint_evidence=_viewpoint_evidence(),
    )
    decision = board.admit_for_manufacture(
        observation=Observation(),
        candidate=Candidate(),
        requirements=_requirements(),
        assessment=assessment,
        falsification=Falsification(FStanding.SURVIVES),
        execution_evidence=(
            ExecutionEvidence(
                "receipt:other",
                "intent:1",
                "ALIVE",
                ("outcome:1",),
                candidate_id="candidate:other",
            ),
        ),
        viewpoint_evidence=_viewpoint_evidence(),
        generation_profile="ggen:fortune5-v1",
    )
    assert decision.standing is ArchitectureAdmissionStanding.REFUSED
    assert "EXECUTION_EVIDENCE_SUBJECT_MISMATCH" in decision.reason


def test_cross_subject_falsification_is_refused():
    board = EnterpriseArchitectureBoard()
    assessment = board.assess_candidate(
        Candidate(),
        _requirements(),
        _requirement_evidence(),
        viewpoint_evidence=_viewpoint_evidence(),
    )
    decision = board.admit_for_manufacture(
        observation=Observation(),
        candidate=Candidate(),
        requirements=_requirements(),
        assessment=assessment,
        falsification=Falsification(FStanding.SURVIVES, candidate_id="candidate:other"),
        execution_evidence=(
            ExecutionEvidence(
                "receipt:1",
                "intent:1",
                "ALIVE",
                ("outcome:1",),
                candidate_id=Candidate().candidate_id,
            ),
        ),
        viewpoint_evidence=_viewpoint_evidence(),
        generation_profile="ggen:fortune5-v1",
    )
    assert decision.standing is ArchitectureAdmissionStanding.REFUSED
    assert decision.reason == "REFUSED:FALSIFICATION_SUBJECT_MISMATCH"


def test_unreceipted_falsification_cannot_crown_candidate():
    board = EnterpriseArchitectureBoard()
    assessment = board.assess_candidate(
        Candidate(),
        _requirements(),
        _requirement_evidence(),
        viewpoint_evidence=_viewpoint_evidence(),
    )
    decision = board.admit_for_manufacture(
        observation=Observation(),
        candidate=Candidate(),
        requirements=_requirements(),
        assessment=assessment,
        falsification=Falsification(FStanding.SURVIVES, receipt_refs=()),
        execution_evidence=(
            ExecutionEvidence(
                "receipt:1",
                "intent:1",
                "ALIVE",
                ("outcome:1",),
                candidate_id=Candidate().candidate_id,
            ),
        ),
        viewpoint_evidence=_viewpoint_evidence(),
        generation_profile="ggen:fortune5-v1",
    )
    assert decision.standing is ArchitectureAdmissionStanding.UNKNOWN
    assert decision.reason == "UNKNOWN:UNRECEIPTED_FALSIFICATION_STANDING"


def test_committed_enterprise_catalog_is_exact_projection_of_ggen_ontology():
    from pathlib import Path

    from rdflib import Graph

    from autofde_lab.fortune5.enterprise_architecture_catalog import (
        ENTERPRISE_ARCHITECTURE_PRINCIPLES,
        ENTERPRISE_REQUIREMENT_KINDS,
        ENTERPRISE_RISK_CLASSES,
        ENTERPRISE_VIEWPOINTS,
    )

    root = Path(__file__).resolve().parents[2]
    graph = Graph().parse(root / "ggen/fortune5/ontology/enterprise-architecture.ttl")
    rows = graph.query(
        """
        PREFIX afl: <urn:autofde-lab:>
        PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
        SELECT ?category ?identifier ?label WHERE {
          VALUES (?type ?category) {
            (afl:EnterpriseArchitectureViewpoint "viewpoint")
            (afl:EnterpriseRequirementKind "requirement_kind")
            (afl:EnterpriseRiskClass "risk_class")
            (afl:EnterpriseArchitecturePrinciple "principle")
          }
          ?concept a ?type ; skos:prefLabel ?label .
          BIND(REPLACE(STR(?concept), "^urn:autofde-lab:", "") AS ?identifier)
        }
        ORDER BY ?category ?identifier
        """
    )
    projected: dict[str, dict[str, str]] = {
        "viewpoint": {},
        "requirement_kind": {},
        "risk_class": {},
        "principle": {},
    }
    for category, identifier, label in rows:
        projected[str(category)][str(identifier)] = str(label)

    assert ENTERPRISE_VIEWPOINTS == projected["viewpoint"]
    assert ENTERPRISE_REQUIREMENT_KINDS == projected["requirement_kind"]
    assert ENTERPRISE_RISK_CLASSES == projected["risk_class"]
    assert ENTERPRISE_ARCHITECTURE_PRINCIPLES == projected["principle"]
