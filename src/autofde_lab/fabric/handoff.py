"""Typed, authority-narrowing handoffs between planning/agent components."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class HandoffStanding(str, Enum):
    ADMITTED = "ADMITTED"
    REFUSED_AUTHORITY_BROADENING = "REFUSED:HANDOFF_AUTHORITY_BROADENING"
    REFUSED_MISSING_LINEAGE = "REFUSED:HANDOFF_MISSING_LINEAGE"
    REFUSED_SCHEMA_MISMATCH = "REFUSED:HANDOFF_SCHEMA_MISMATCH"


@dataclass(frozen=True, slots=True)
class AuthorityScope:
    capabilities: frozenset[str]
    resources: frozenset[str]

    def contains(self, child: "AuthorityScope") -> bool:
        return (
            child.capabilities <= self.capabilities
            and child.resources <= self.resources
        )


@dataclass(frozen=True, slots=True)
class HandoffEnvelope:
    handoff_id: str
    input_schema_id: str
    payload_schema_id: str
    parent_authority: AuthorityScope
    delegated_authority: AuthorityScope
    evidence_lineage: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HandoffDecision:
    standing: HandoffStanding
    reason: str


def admit_handoff(envelope: HandoffEnvelope) -> HandoffDecision:
    if not envelope.evidence_lineage:
        return HandoffDecision(
            HandoffStanding.REFUSED_MISSING_LINEAGE,
            "handoff has no evidence lineage",
        )
    if envelope.input_schema_id != envelope.payload_schema_id:
        return HandoffDecision(
            HandoffStanding.REFUSED_SCHEMA_MISMATCH,
            "payload schema identity does not equal the admitted input contract",
        )
    if not envelope.parent_authority.contains(envelope.delegated_authority):
        return HandoffDecision(
            HandoffStanding.REFUSED_AUTHORITY_BROADENING,
            "delegated capability/resource scope exceeds the parent authority",
        )
    return HandoffDecision(
        HandoffStanding.ADMITTED,
        "typed handoff preserves lineage and monotonically narrows authority",
    )
