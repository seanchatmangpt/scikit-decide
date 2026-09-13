"""Fail-closed organizational authority rail for Forward Deployment.

This module gives organizational standing a concrete carrier without manufacturing
customer authority.  A grant is attributable only when it names the accountable
principal, decision right, exact subject/effect identities, evidence reviewed,
scope and timestamp.  Technical evidence and organizational acceptance remain
separate dimensions; enterprise standing requires both.

Nothing here actuates.  These objects are admission inputs for a downstream BRCE
broker and deliberately cannot convert a fixture into real customer adoption.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import FrozenSet


class AuthorityStanding(str, Enum):
    UNKNOWN = "UNKNOWN"
    ADMITTED = "ADMITTED"
    REFUSED_MISSING_PRINCIPAL = "REFUSED:MISSING_PRINCIPAL"
    REFUSED_MISSING_DECISION_RIGHT = "REFUSED:MISSING_DECISION_RIGHT"
    REFUSED_MISSING_SUBJECT = "REFUSED:MISSING_SUBJECT"
    REFUSED_MISSING_EFFECT = "REFUSED:MISSING_EFFECT"
    REFUSED_MISSING_EVIDENCE = "REFUSED:MISSING_EVIDENCE"
    REFUSED_SCOPE = "REFUSED:SCOPE"
    REFUSED_UNVERIFIED_REPLACEMENT = "REFUSED:UNVERIFIED_REPLACEMENT"
    REFUSED_UNATTRIBUTABLE_ACCEPTANCE = "REFUSED:UNATTRIBUTABLE_ACCEPTANCE"


@dataclass(frozen=True, slots=True)
class AuthorityGrant:
    principal_id: str
    decision_right: str
    subject_id: str
    intended_effect_id: str
    evidence_ids: tuple[str, ...]
    allowed_capabilities: FrozenSet[str]
    allowed_resources: FrozenSet[str]
    issued_at: str


@dataclass(frozen=True, slots=True)
class AcceptanceRecord:
    authority: AuthorityGrant
    replacement_id: str
    replacement_verified: bool
    accepted_postconditions: tuple[str, ...]
    operating_owner_id: str
    accepted_at: str


@dataclass(frozen=True, slots=True)
class RetirementGrant:
    authority: AuthorityGrant
    predecessor_id: str
    replacement_id: str
    replacement_verified: bool
    reviewed_evidence_ids: tuple[str, ...]
    authorized_at: str


@dataclass(frozen=True, slots=True)
class EnterpriseStanding:
    technical_alive: bool
    organizational_admitted: bool

    @property
    def alive(self) -> bool:
        return self.technical_alive and self.organizational_admitted


def admit_authority(grant: AuthorityGrant) -> AuthorityStanding:
    if not grant.principal_id.strip():
        return AuthorityStanding.REFUSED_MISSING_PRINCIPAL
    if not grant.decision_right.strip():
        return AuthorityStanding.REFUSED_MISSING_DECISION_RIGHT
    if not grant.subject_id.strip():
        return AuthorityStanding.REFUSED_MISSING_SUBJECT
    if not grant.intended_effect_id.strip():
        return AuthorityStanding.REFUSED_MISSING_EFFECT
    if not grant.evidence_ids:
        return AuthorityStanding.REFUSED_MISSING_EVIDENCE
    if not grant.allowed_capabilities or not grant.allowed_resources:
        return AuthorityStanding.REFUSED_SCOPE
    if not grant.issued_at.strip():
        return AuthorityStanding.REFUSED_MISSING_EVIDENCE
    return AuthorityStanding.ADMITTED


def admit_acceptance(record: AcceptanceRecord) -> AuthorityStanding:
    if admit_authority(record.authority) is not AuthorityStanding.ADMITTED:
        return AuthorityStanding.REFUSED_UNATTRIBUTABLE_ACCEPTANCE
    if not record.replacement_verified:
        return AuthorityStanding.REFUSED_UNVERIFIED_REPLACEMENT
    if not record.replacement_id.strip() or not record.accepted_postconditions:
        return AuthorityStanding.REFUSED_UNATTRIBUTABLE_ACCEPTANCE
    if not record.operating_owner_id.strip() or not record.accepted_at.strip():
        return AuthorityStanding.REFUSED_UNATTRIBUTABLE_ACCEPTANCE
    return AuthorityStanding.ADMITTED


def admit_retirement(record: RetirementGrant) -> AuthorityStanding:
    if admit_authority(record.authority) is not AuthorityStanding.ADMITTED:
        return AuthorityStanding.REFUSED_UNATTRIBUTABLE_ACCEPTANCE
    if not record.replacement_verified:
        return AuthorityStanding.REFUSED_UNVERIFIED_REPLACEMENT
    if not record.predecessor_id.strip() or not record.replacement_id.strip():
        return AuthorityStanding.REFUSED_UNATTRIBUTABLE_ACCEPTANCE
    if record.predecessor_id == record.replacement_id:
        return AuthorityStanding.REFUSED_UNATTRIBUTABLE_ACCEPTANCE
    if not record.reviewed_evidence_ids or not record.authorized_at.strip():
        return AuthorityStanding.REFUSED_MISSING_EVIDENCE
    return AuthorityStanding.ADMITTED
