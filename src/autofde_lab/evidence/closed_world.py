"""Closed-world admission for negative cloud-resource knowledge.

A point observation such as HTTP 404 is never sufficient to manufacture
`ABSENT`.  Negative knowledge enters O* only when a closure witness proves
that the exact observation scope was exhaustively enumerated under matching
authority, the enumeration completed without pagination/failure gaps, the
provider consistency window has closed, and the witness is still fresh.

This module is deliberately provider-neutral.  Provider adapters may project
Azure/AWS/GCP observations into these types; they may not weaken the admission
predicate here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum


class ObservationKind(str, Enum):
    """What the transport actually observed, without semantic coercion."""

    PRESENT = "PRESENT"
    NOT_FOUND = "NOT_FOUND"
    UNKNOWN = "UNKNOWN"


class Knowledge(str, Enum):
    """Admitted semantic standing for the subject."""

    PRESENT = "PRESENT"
    ABSENT = "ABSENT"
    UNKNOWN = "UNKNOWN"


class RefusalReason(str, Enum):
    """Typed reasons why negative knowledge cannot enter O*."""

    OBSERVATION_NOT_NOT_FOUND = "OBSERVATION_NOT_NOT_FOUND"
    SCOPE_MISMATCH = "SCOPE_MISMATCH"
    AUTHORITY_MISMATCH = "AUTHORITY_MISMATCH"
    INSUFFICIENT_AUTHORITY = "INSUFFICIENT_AUTHORITY"
    ENUMERATION_FAILED = "ENUMERATION_FAILED"
    INCOMPLETE_PAGINATION = "INCOMPLETE_PAGINATION"
    EVENTUAL_CONSISTENCY_WINDOW = "EVENTUAL_CONSISTENCY_WINDOW"
    STALE = "STALE"
    CONFLICT = "CONFLICT"


@dataclass(frozen=True)
class ObservationScope:
    """The exact closed-world boundary to which a claim may apply."""

    provider: str
    tenant: str
    account: str
    container: str
    resource_type: str
    api_version: str
    authority_fingerprint: str


@dataclass(frozen=True)
class Observation:
    """A transport observation about one canonical resource identity."""

    subject: str
    scope: ObservationScope
    kind: ObservationKind
    observed_at: datetime


@dataclass(frozen=True)
class ClosureWitness:
    """Evidence that enumeration closed the exact world for one scope.

    ``subjects`` contains the canonical identities returned by enumeration.
    ``authority_complete`` is an adapter-supplied assertion that the active
    principal had sufficient list visibility for this scope.  It remains
    separately bound by ``authority_fingerprint`` through ``scope`` so a
    witness obtained under one principal cannot discharge a 404 observed
    under another.
    """

    scope: ObservationScope
    subjects: frozenset[str]
    enumerated_at: datetime
    fresh_until: datetime
    enumeration_succeeded: bool
    pagination_complete: bool
    authority_complete: bool
    consistency_window_closed: bool


@dataclass(frozen=True)
class AdmissionDecision:
    """Typed O -> O* decision; UNKNOWN preserves every failed premise."""

    knowledge: Knowledge
    subject: str
    reasons: tuple[RefusalReason, ...] = ()

    @property
    def admitted(self) -> bool:
        return self.knowledge is not Knowledge.UNKNOWN


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("evidence timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


def admit_presence(observation: Observation) -> AdmissionDecision:
    """A positive direct observation may establish PRESENT for its subject."""

    if observation.kind is ObservationKind.PRESENT:
        return AdmissionDecision(Knowledge.PRESENT, observation.subject)
    return AdmissionDecision(Knowledge.UNKNOWN, observation.subject)


def admit_absence(
    observation: Observation,
    closure: ClosureWitness,
    *,
    now: datetime,
) -> AdmissionDecision:
    """Admit ABSENT only from a matching, complete, conflict-free closure.

    A raw 404 therefore remains UNKNOWN unless every closure premise below is
    observed.  Reasons are accumulated rather than short-circuited so callers
    retain diagnostic evidence without manufacturing a stronger claim.
    """

    reasons: list[RefusalReason] = []

    if observation.kind is not ObservationKind.NOT_FOUND:
        reasons.append(RefusalReason.OBSERVATION_NOT_NOT_FOUND)
    if observation.scope != closure.scope:
        reasons.append(RefusalReason.SCOPE_MISMATCH)
        if (
            observation.scope.authority_fingerprint
            != closure.scope.authority_fingerprint
        ):
            reasons.append(RefusalReason.AUTHORITY_MISMATCH)
    if not closure.authority_complete:
        reasons.append(RefusalReason.INSUFFICIENT_AUTHORITY)
    if not closure.enumeration_succeeded:
        reasons.append(RefusalReason.ENUMERATION_FAILED)
    if not closure.pagination_complete:
        reasons.append(RefusalReason.INCOMPLETE_PAGINATION)
    if not closure.consistency_window_closed:
        reasons.append(RefusalReason.EVENTUAL_CONSISTENCY_WINDOW)
    if _utc(now) > _utc(closure.fresh_until):
        reasons.append(RefusalReason.STALE)
    if observation.subject in closure.subjects:
        reasons.append(RefusalReason.CONFLICT)

    if reasons:
        return AdmissionDecision(Knowledge.UNKNOWN, observation.subject, tuple(reasons))
    return AdmissionDecision(Knowledge.ABSENT, observation.subject)
