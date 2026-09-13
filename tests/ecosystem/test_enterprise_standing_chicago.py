"""Chicago-style standing tests over committed customer-authority artifacts."""

from __future__ import annotations

from pathlib import Path

from autofde_lab.fabric.enterprise_standing import derive_enterprise_standing
from autofde_lab.fabric.fde import parse_authority_turtle

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "fde"
BASE = FIXTURES / "customer-authority.ttl"
FDE = "urn:skdecide:fde:"


def _authority_with_decision(verdict: str = "PASS", adoption: str = "ADOPTED"):
    extra = f"""
<{FDE}consequence/rebalance-verified> a <urn:skdecide:fde-term:TechnicalConsequence> ;
    <urn:skdecide:fde-term:consequenceDigest> "blake3:{"a" * 64}" .

<{FDE}verdict/rebalance-independent> a <urn:skdecide:fde-term:VerifierVerdict> ;
    <urn:skdecide:fde-term:verdictBy> <{FDE}verifier/ggen-legacy-replay> ;
    <urn:skdecide:fde-term:aboutArtifact> <{FDE}consequence/rebalance-verified> ;
    <urn:skdecide:fde-term:verdictDecision> "{verdict}" .

<{FDE}adoption/rebalance> a <urn:skdecide:fde-term:AdoptionDecision> ;
    <urn:skdecide:fde-term:decidedBy> <{FDE}owner/director-operations> ;
    <urn:skdecide:fde-term:onEvidence> <{FDE}verdict/rebalance-independent> ;
    <urn:skdecide:fde-term:adoptionDecision> "{adoption}" ;
    <urn:skdecide:fde-term:ownershipAssignedTo> <{FDE}owner/director-operations> ;
    <urn:skdecide:fde-term:operatingObligation> "24x7 customer operations ownership" .
"""
    return parse_authority_turtle(BASE.read_text(encoding="utf-8") + extra)


def test_technical_alive_without_customer_decision_is_only_partial_enterprise() -> None:
    model = parse_authority_turtle(BASE.read_text(encoding="utf-8"))

    standing = derive_enterprise_standing(model, technical_standing="ALIVE")

    assert standing.technical_standing == "ALIVE"
    assert standing.organizational_standing == "UNKNOWN"
    assert standing.enterprise_standing == "PARTIAL_ALIVE"
    assert standing.reasons == ("NO_CUSTOMER_ADOPTION_DECISION",)


def test_customer_adoption_with_required_passing_evidence_closes_enterprise() -> None:
    model = _authority_with_decision()
    before = dict(model.adoptions)

    standing = derive_enterprise_standing(model, technical_standing="ALIVE")

    assert standing.organizational_standing == "ALIVE"
    assert standing.enterprise_standing == "ALIVE"
    assert standing.adoption_decision_iri == FDE + "adoption/rebalance"
    assert standing.evidence_iris == (FDE + "verdict/rebalance-independent",)
    assert model.adoptions == before, "derivation must not mint or mutate acceptance"


def test_failing_verifier_evidence_cannot_be_promoted_to_enterprise_alive() -> None:
    model = _authority_with_decision(verdict="FAIL")

    standing = derive_enterprise_standing(model, technical_standing="ALIVE")

    assert standing.organizational_standing == "BLOCKED:NONPASSING_VERIFIER_EVIDENCE"
    assert standing.enterprise_standing == "PARTIAL_ALIVE"


def test_customer_adoption_cannot_crown_incomplete_technical_standing() -> None:
    model = _authority_with_decision()

    standing = derive_enterprise_standing(model, technical_standing="PARTIAL_ALIVE")

    assert standing.organizational_standing == "ALIVE"
    assert standing.enterprise_standing == "PARTIAL_ALIVE"


def test_explicit_customer_rejection_is_not_unknown_acceptance() -> None:
    model = _authority_with_decision(adoption="REJECTED")

    standing = derive_enterprise_standing(model, technical_standing="ALIVE")

    assert standing.organizational_standing == "BLOCKED:CUSTOMER_NOT_ADOPTED"
    assert standing.enterprise_standing == "PARTIAL_ALIVE"
