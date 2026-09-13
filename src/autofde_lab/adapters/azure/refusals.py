"""Typed refusals for Azure surface operations.

Every operation in this subpackage returns a typed result. When the prerequisite
for an operation is absent — which, on any machine without a provisioned tenant,
is always — the result is a :class:`Refusal` naming the EXACT missing
prerequisite, not a bare ``False`` and not an exception.

A boolean would be the dangerous shape: ``False`` from an authority request is
indistinguishable from "denied," and ``True`` would be a grant. These operations
never grant anything. ``request_authority`` REQUESTS; a broker outside this
repository is the only thing that could answer.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

__all__ = ["RefusalCode", "Refusal"]


class RefusalCode(StrEnum):
    """Why an Azure surface operation could not be attempted."""

    NO_AZURE_CLI = "AZ-001-NO_AZURE_CLI"
    NO_AZURE_SDK = "AZ-002-NO_AZURE_SDK"
    NO_SUBSCRIPTION = "AZ-003-NO_SUBSCRIPTION"
    NO_TENANT_BINDING = "AZ-004-NO_TENANT_BINDING"
    NO_WORKSPACE = "AZ-005-NO_SENTINEL_WORKSPACE"
    NO_WORKFLOW_ENDPOINT = "AZ-006-NO_LOGIC_APPS_WORKFLOW"
    NO_IDENTITY_PROVIDER = "AZ-007-NO_ENTRA_IDENTITY_PROVIDER"
    NO_NOTIFICATION_CHANNEL = "AZ-008-NO_NOTIFICATION_CHANNEL"
    NO_EVIDENCE_SINK = "AZ-009-NO_CONFIDENTIAL_LEDGER"
    SURFACE_IS_DEPLOYMENT_TIME = "AZ-010-SURFACE_IS_DEPLOYMENT_TIME"
    OUT_OF_SCOPE_FOR_THIS_REPOSITORY = "AZ-011-OUT_OF_SCOPE_NOT_AN_ACTUATOR"


@dataclass(frozen=True)
class Refusal:
    """A typed refusal. Never a permission, never a denial verdict.

    Attributes:
        code: Machine-readable reason.
        operation: The operation that was refused.
        missing_prerequisite: The exact absent thing, named.
        detail: Human-readable explanation.
        surfaces_searched: The surfaces the refusal ranges over. Non-empty.
        methods_used: How absence was determined. Non-empty.
        revision: Contract revision the refusal was issued under.
    """

    code: RefusalCode
    operation: str
    missing_prerequisite: str
    detail: str
    surfaces_searched: tuple[str, ...] = ()
    methods_used: tuple[str, ...] = ()
    revision: str = "azure-surface-contract/1"

    def __post_init__(self) -> None:
        if not self.surfaces_searched:
            raise ValueError(
                "Refusal.surfaces_searched must be non-empty: an absence claim must "
                "carry the boundary that produced it."
            )
        if not self.methods_used:
            raise ValueError("Refusal.methods_used must be non-empty.")
        if not self.missing_prerequisite:
            raise ValueError("Refusal.missing_prerequisite must name the exact absent thing.")

    @property
    def granted(self) -> None:
        """Always ``None``. There is no boolean permission in this subpackage.

        Deliberately not a ``bool``: ``False`` would read as an authorization
        decision, and this repository issues none. ``None`` means "no decision
        was made here, by anyone."
        """
        return None
