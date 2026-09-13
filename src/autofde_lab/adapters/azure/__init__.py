"""Optional adapter: Azure incident surfaces. ALWAYS UNAVAILABLE, by construction.

Sentinel, Defender XDR, Logic Apps, Entra and Confidential Ledger are
deployment-time surfaces that exist in a customer tenant, never a dependency of
this repository's core. There is nothing on a developer filesystem that could make
them AVAILABLE, and a probe that guessed otherwise from a stray credential file or
an installed CLI would be manufacturing a tenant claim from a local artifact.

So this probe reports UNAVAILABLE unconditionally and records that its search
boundary is the empty local filesystem — a deliberately honest negative rather
than a lookup that could accidentally succeed.

This was a single module (``adapters/azure.py``) and is now a package. The
name collision was resolved by moving that module to ``azure/__init__.py``
(``git mv``, so the history follows) rather than by renaming the import path:
``from autofde_lab.adapters.azure import AzureIncidentAdapter`` and the registered
``ADAPTERS`` entry both keep working unchanged, and the existing
``test_azure_is_always_unavailable_and_says_why`` still exercises the same
object with the same unconditional ``UNAVAILABLE``. The per-surface modules
alongside are additive; none of them is a prerequisite of the core.

No Azure SDK is imported at module level anywhere in this package. The SDK is an
optional extra. Probes consult ``PATH`` and the PRESENCE of locator environment
variables only — never a credential value — and never raise.

Nothing here actuates, admits, brokers, or issues a receipt. ``request_authority``
REQUESTS; it never grants.
"""

from __future__ import annotations

from autofde_lab.adapters.azure.base import (
    AZURE_CONTRACT_REVISION,
    AzureProbe,
    AzureProbeStatus,
    AzureSurface,
    to_adapter_status,
)
from autofde_lab.adapters.azure.evidence_sink import AzureEvidenceSink
from autofde_lab.adapters.azure.identity import AzureIdentity
from autofde_lab.adapters.azure.incident_ingress import AzureIncidentIngress
from autofde_lab.adapters.azure.logic_apps import AzureLogicApps
from autofde_lab.adapters.azure.models import (
    AuthorityRequest,
    CandidateActionSubmission,
    ExecutionEvidenceRecord,
    IncidentObservation,
    NotificationDraft,
    PostconditionReading,
    SyntheticIncidentHandle,
)
from autofde_lab.adapters.azure.notification_capture import AzureNotificationCapture
from autofde_lab.adapters.azure.refusals import Refusal, RefusalCode
from autofde_lab.adapters.azure.sentinel import AzureSentinel
from autofde_lab.adapters.base import AdapterProbe, AdapterStatus

__all__ = [
    "AzureIncidentAdapter",
    "AZURE_SURFACE_ADAPTERS",
    "AZURE_CONTRACT_REVISION",
    "AzureProbe",
    "AzureProbeStatus",
    "AzureSurface",
    "to_adapter_status",
    "AzureEvidenceSink",
    "AzureIdentity",
    "AzureIncidentIngress",
    "AzureLogicApps",
    "AzureNotificationCapture",
    "AzureSentinel",
    "Refusal",
    "RefusalCode",
    "AuthorityRequest",
    "CandidateActionSubmission",
    "ExecutionEvidenceRecord",
    "IncidentObservation",
    "NotificationDraft",
    "PostconditionReading",
    "SyntheticIncidentHandle",
    "SURFACES",
    "probe_azure_surfaces",
]

SURFACES = (
    "Microsoft Sentinel",
    "Defender XDR",
    "Logic Apps",
    "Entra",
    "Azure Confidential Ledger",
)


class AzureIncidentAdapter:
    """Declares the Azure incident surfaces as deployment-time only."""

    name = "azure"

    def probe(self) -> AdapterProbe:
        return AdapterProbe(
            status=AdapterStatus.UNAVAILABLE,
            detail=(
                "Azure incident surfaces ("
                + ", ".join(SURFACES)
                + ") are deployment-time surfaces bound to a customer tenant, never "
                "a core dependency. UNAVAILABLE is returned unconditionally: no local "
                "filesystem state can establish tenant access, so none is consulted."
            ),
            searched=("<none: deployment-time surface, not locally probeable>",),
        )


#: Per-surface adapters. Additive; none is registered in the core ``ADAPTERS``
#: tuple, so none can affect ``probe_all()`` or ``available()``.
AZURE_SURFACE_ADAPTERS = (
    AzureIncidentIngress(),
    AzureSentinel(),
    AzureLogicApps(),
    AzureIdentity(),
    AzureNotificationCapture(),
    AzureEvidenceSink(),
)


def probe_azure_surfaces() -> dict[str, AzureProbe]:
    """Probe every declared Azure surface. Never raises."""
    results: dict[str, AzureProbe] = {}
    for adapter in AZURE_SURFACE_ADAPTERS:
        try:
            results[adapter.name] = adapter.probe()
        except Exception as exc:  # pragma: no cover - surfaces must not raise
            results[adapter.name] = AzureProbe(
                status=AdapterStatus.UNAVAILABLE,
                azure_status=AzureProbeStatus.UNAVAILABLE,
                detail=f"probe raised (adapter bug, treated as absent): {exc!r}",
                searched=(f"<surface {adapter.name} raised>",),
                surfaces_searched=(adapter.name,),
                methods_used=("<probe raised before any method completed>",),
                evidence=(repr(exc),),
            )
    return results
