"""Read-only enterprise standing derived from technical and customer evidence.

This module cannot issue an AdoptionDecision. It only classifies facts already
present in an admitted FDE authority model, preserving the rule that technical
success never manufactures organizational acceptance.
"""

from __future__ import annotations

from dataclasses import dataclass

from autofde_lab.fabric.fde import AuthorityError, AuthorityModel, validate_authority

_STANDING_BASES = {
    "UNKNOWN",
    "PARTIAL_ALIVE",
    "ALIVE",
    "BLOCKED",
    "BUILD_BROKEN",
    "UNSUPPORTED",
    "REFUSED",
}


@dataclass(frozen=True)
class EnterpriseStandingAssessment:
    """Three-dimensional standing plus the external evidence that supports it."""

    technical_standing: str
    organizational_standing: str
    enterprise_standing: str
    adoption_decision_iri: str | None = None
    evidence_iris: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()


def _require_standing(value: str) -> str:
    base = value.split(":", 1)[0]
    if base not in _STANDING_BASES:
        raise ValueError(f"UNKNOWN_STANDING:{value}")
    return value


def _enterprise_status(technical: str, organizational: str) -> str:
    if technical == "ALIVE" and organizational == "ALIVE":
        return "ALIVE"
    if technical == "ALIVE" or organizational == "ALIVE":
        return "PARTIAL_ALIVE"
    return "UNKNOWN"


def derive_enterprise_standing(
    model: AuthorityModel,
    *,
    technical_standing: str,
) -> EnterpriseStandingAssessment:
    """Derive standing without mutating or manufacturing authority.

    Enterprise standing is ``ALIVE`` only when the supplied technical boundary
    is ``ALIVE`` and exactly one customer-issued ``ADOPTED`` decision survives
    authority validation with PASS evidence from every verifier the grant
    requires. Missing, rejected, ambiguous, failing, or structurally invalid
    organizational evidence fails closed.
    """
    technical = _require_standing(technical_standing)

    try:
        validate_authority(model)
    except AuthorityError as exc:
        organizational = f"BLOCKED:{exc.code}"
        return EnterpriseStandingAssessment(
            technical_standing=technical,
            organizational_standing=organizational,
            enterprise_standing=_enterprise_status(technical, organizational),
            reasons=(exc.code,),
        )

    decisions = tuple(model.adoptions.values())
    if not decisions:
        organizational = "UNKNOWN"
        return EnterpriseStandingAssessment(
            technical_standing=technical,
            organizational_standing=organizational,
            enterprise_standing=_enterprise_status(technical, organizational),
            reasons=("NO_CUSTOMER_ADOPTION_DECISION",),
        )

    if len(decisions) != 1:
        organizational = "BLOCKED:AMBIGUOUS_ADOPTION_DECISION"
        return EnterpriseStandingAssessment(
            technical_standing=technical,
            organizational_standing=organizational,
            enterprise_standing=_enterprise_status(technical, organizational),
            reasons=("AMBIGUOUS_ADOPTION_DECISION",),
        )

    adoption = decisions[0]
    if adoption.adoption_decision != "ADOPTED":
        organizational = "BLOCKED:CUSTOMER_NOT_ADOPTED"
        return EnterpriseStandingAssessment(
            technical_standing=technical,
            organizational_standing=organizational,
            enterprise_standing=_enterprise_status(technical, organizational),
            adoption_decision_iri=adoption.iri,
            evidence_iris=adoption.on_evidence,
            reasons=(adoption.adoption_decision or "EMPTY_ADOPTION_DECISION",),
        )

    grant = model.the_grant()
    passing_required: set[str] = set()
    for evidence_iri in adoption.on_evidence:
        verdict = model.verdicts.get(evidence_iri)
        if verdict is None:
            organizational = "BLOCKED:INVALID_VERIFIER_EVIDENCE"
            return EnterpriseStandingAssessment(
                technical_standing=technical,
                organizational_standing=organizational,
                enterprise_standing=_enterprise_status(technical, organizational),
                adoption_decision_iri=adoption.iri,
                evidence_iris=adoption.on_evidence,
                reasons=("EVIDENCE_IS_NOT_VERIFIER_VERDICT", evidence_iri),
            )
        if verdict.verdict_decision != "PASS":
            organizational = "BLOCKED:NONPASSING_VERIFIER_EVIDENCE"
            return EnterpriseStandingAssessment(
                technical_standing=technical,
                organizational_standing=organizational,
                enterprise_standing=_enterprise_status(technical, organizational),
                adoption_decision_iri=adoption.iri,
                evidence_iris=adoption.on_evidence,
                reasons=(verdict.verdict_decision, evidence_iri),
            )
        if verdict.about_artifact not in model.consequences:
            organizational = "BLOCKED:UNBOUND_VERIFIER_EVIDENCE"
            return EnterpriseStandingAssessment(
                technical_standing=technical,
                organizational_standing=organizational,
                enterprise_standing=_enterprise_status(technical, organizational),
                adoption_decision_iri=adoption.iri,
                evidence_iris=adoption.on_evidence,
                reasons=("VERDICT_NOT_BOUND_TO_TECHNICAL_CONSEQUENCE", evidence_iri),
            )
        if verdict.verdict_by in grant.requires_verifier:
            passing_required.add(verdict.verdict_by)

    missing = tuple(sorted(set(grant.requires_verifier) - passing_required))
    if missing:
        organizational = "BLOCKED:REQUIRED_VERIFIER_EVIDENCE_INCOMPLETE"
        return EnterpriseStandingAssessment(
            technical_standing=technical,
            organizational_standing=organizational,
            enterprise_standing=_enterprise_status(technical, organizational),
            adoption_decision_iri=adoption.iri,
            evidence_iris=adoption.on_evidence,
            reasons=missing,
        )

    organizational = "ALIVE"
    return EnterpriseStandingAssessment(
        technical_standing=technical,
        organizational_standing=organizational,
        enterprise_standing=_enterprise_status(technical, organizational),
        adoption_decision_iri=adoption.iri,
        evidence_iris=adoption.on_evidence,
    )
