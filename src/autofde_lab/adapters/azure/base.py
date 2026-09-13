"""Probe and surface primitives for the Azure adapter subpackage.

Widens the probe vocabulary for Azure surfaces to
``AVAILABLE | UNAVAILABLE | PARTIAL | INCOMPATIBLE | UNKNOWN`` and requires each
probe to state not only *where* it looked (``surfaces_searched``) but *how*
(``methods_used``), against *what* (``revision``, ``environment``) and on the
strength of *what observation* (``evidence``).

The reason for the extra fields: a path existing is not compatibility. A probe
that reports a surface usable because a directory or a binary was found has
manufactured a tenant-interface claim out of a filesystem fact. Recording the
method makes the reach of every claim inspectable.

Nothing here actuates, admits, brokers, or issues a receipt. These types
describe what exists and refuse.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import StrEnum

from autofde_lab.adapters.base import AdapterProbe, AdapterStatus

__all__ = [
    "AzureProbeStatus",
    "AzureProbe",
    "AzureSurface",
    "to_adapter_status",
    "empty_environment_fingerprint",
]

#: Revision tag for the Azure surface contracts declared in this subpackage.
#: Bumped when an operation signature or refusal code changes, so a probe result
#: recorded elsewhere can be told apart from one taken under a different contract.
AZURE_CONTRACT_REVISION = "azure-surface-contract/1"


class AzureProbeStatus(StrEnum):
    """Outcome of an Azure surface probe.

    - ``AVAILABLE`` — the surface was reached and answered.
    - ``UNAVAILABLE`` — not reachable within the recorded search boundary.
    - ``PARTIAL`` — reachable, only some of the expected surface responded.
    - ``INCOMPATIBLE`` — reachable and positively determined not to match the
      contract at :data:`AZURE_CONTRACT_REVISION`.
    - ``UNKNOWN`` — observation was insufficient to classify. Distinct from
      ``UNAVAILABLE``: "I could not tell" is not "it is not there."
    """

    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    PARTIAL = "PARTIAL"
    INCOMPATIBLE = "INCOMPATIBLE"
    UNKNOWN = "UNKNOWN"


def to_adapter_status(status: AzureProbeStatus) -> AdapterStatus:
    """Map the widened vocabulary onto the narrower core :class:`AdapterStatus`.

    ``UNKNOWN`` maps DOWN to ``UNAVAILABLE``. That is deliberate: the core enum
    has no way to say "undetermined," and reporting an undetermined surface as
    anything other than absent would let an unproven surface raise the standing
    of the core.
    """
    if status is AzureProbeStatus.UNKNOWN:
        return AdapterStatus.UNAVAILABLE
    return AdapterStatus(status.value)


@dataclass(frozen=True)
class AzureProbe(AdapterProbe):
    """An Azure surface probe result, carrying the boundary that produced it.

    Inherits the non-empty ``searched`` enforcement from :class:`AdapterProbe`
    rather than restating it — that check is the mechanical form of "an absence
    claim must carry the boundary that produced it," and there must be exactly
    one of it.

    Attributes:
        azure_status: The widened status. ``status`` (inherited) carries the
            narrowed core mapping, so existing core tooling keeps working.
        surfaces_searched: The named Azure surfaces consulted.
        methods_used: How each was consulted (e.g. ``PATH lookup for 'az'``).
            Non-empty and required: a status without a method is unfalsifiable.
        revision: The contract revision the probe was taken against.
        environment: Fingerprint of the local environment at probe time.
        evidence: The concrete observations that produced the status.
    """

    azure_status: AzureProbeStatus = AzureProbeStatus.UNKNOWN
    surfaces_searched: tuple[str, ...] = ()
    methods_used: tuple[str, ...] = ()
    revision: str = AZURE_CONTRACT_REVISION
    environment: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.surfaces_searched:
            raise ValueError(
                "AzureProbe.surfaces_searched must be non-empty: name the surfaces "
                "the claim ranges over."
            )
        if not self.methods_used:
            raise ValueError(
                "AzureProbe.methods_used must be non-empty: a path existing is not "
                "compatibility, so state what was actually checked."
            )
        if not self.evidence:
            raise ValueError(
                "AzureProbe.evidence must be non-empty: record the observation that "
                "produced the status."
            )


@dataclass(frozen=True)
class AzureSurface:
    """A declared, deployment-time Azure surface. Zero implementation."""

    name: str
    surfaces: tuple[str, ...]
    purpose: str
    required_prerequisites: tuple[str, ...] = field(default_factory=tuple)


def empty_environment_fingerprint() -> tuple[str, ...]:
    """Describe the local environment WITHOUT reading any credential material.

    Reports only whether the well-known locator variables are *set*, never their
    values, and whether an ``az`` binary is on ``PATH``. No bearer credential,
    token, connection string or secret is read, returned, or logged.
    """
    locators = (
        "AZURE_SUBSCRIPTION_ID",
        "AZURE_TENANT_ID",
        "AZURE_CLIENT_ID",
        "AZURE_CONFIG_DIR",
    )
    fingerprint = [
        f"{var}={'set' if os.environ.get(var) else 'unset'}" for var in locators
    ]
    fingerprint.append(f"PATH_entries={len([p for p in os.environ.get('PATH', '').split(os.pathsep) if p])}")
    return tuple(fingerprint)
