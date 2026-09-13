"""Typed results for Azure surface operations.

Every operation returns one of these or a :class:`~autofde_lab.adapters.azure.refusals.Refusal`
— never a bare ``bool``, never a raw dict, never a bearer credential. None of
these types carries admission, broker, receipt or actuation semantics: they are
descriptions of observations and of *candidate* material, which some other system
may or may not act upon.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = [
    "SyntheticIncidentHandle",
    "IncidentObservation",
    "CandidateActionSubmission",
    "AuthorityRequest",
    "NotificationDraft",
    "ExecutionEvidenceRecord",
    "PostconditionReading",
]


@dataclass(frozen=True)
class SyntheticIncidentHandle:
    """A reference to a synthetic incident that WOULD be injected."""

    correlation_id: str
    surface: str
    synthetic: bool = True


@dataclass(frozen=True)
class IncidentObservation:
    """A read-only observation of incident state. Describes; does not admit."""

    correlation_id: str
    surface: str
    observed_fields: tuple[str, ...] = ()
    observed_at: str | None = None


@dataclass(frozen=True)
class CandidateActionSubmission:
    """A CANDIDATE action handed to an external broker.

    Submission is not execution and not authorization. This repository computes
    candidate plans; a broker authorizes, an executor performs, a verifier
    evaluates. ``accepted`` is intentionally absent from this type — acceptance
    is not ours to report.
    """

    correlation_id: str
    action_name: str
    parameters: tuple[tuple[str, str], ...] = ()
    submitted_to: str | None = None


@dataclass(frozen=True)
class AuthorityRequest:
    """A REQUEST for authority. Never a grant.

    There is deliberately no ``granted: bool`` field. A boolean here would be a
    permission verdict, and nothing in this repository may issue one.
    """

    correlation_id: str
    requested_scope: str
    requested_from: str
    justification: str


@dataclass(frozen=True)
class NotificationDraft:
    """A captured DRAFT notification. Capturing is not sending."""

    correlation_id: str
    channel: str
    subject: str
    body_redacted: bool = True
    sent: bool = False


@dataclass(frozen=True)
class ExecutionEvidenceRecord:
    """A record ABOUT evidence produced elsewhere.

    Not a receipt. This repository issues no receipts; it can only note that some
    other system claims to have produced one, and where that claim came from.
    """

    correlation_id: str
    sink: str
    described_by: str
    fields_recorded: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class PostconditionReading:
    """A read-only reading of a postcondition. Describes; does not verify."""

    correlation_id: str
    surface: str
    predicate: str
    reading: str | None = None
