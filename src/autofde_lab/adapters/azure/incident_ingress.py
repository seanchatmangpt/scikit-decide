"""Incident ingress surface — synthetic incident injection into a customer tenant.

Declared only. Injection requires a provisioned tenant; on any machine without
one, :meth:`AzureIncidentIngress.inject_synthetic_incident` returns a typed
:class:`Refusal` naming the exact missing prerequisite.
"""

from __future__ import annotations

from autofde_lab.adapters.azure.base import AzureProbe, AzureSurface
from autofde_lab.adapters.azure.probe import probe_surface
from autofde_lab.adapters.azure.refusals import Refusal, RefusalCode

__all__ = ["AzureIncidentIngress", "SURFACE"]

SURFACES = ("Microsoft Sentinel incident ingress", "Defender XDR alert ingress")

SURFACE = AzureSurface(
    name="azure.incident_ingress",
    surfaces=SURFACES,
    purpose="Inject a synthetic incident so a planner has an observable to plan over.",
    required_prerequisites=(
        "a provisioned Azure subscription",
        "a Sentinel workspace with an ingestion endpoint",
        "the azure-monitor-ingestion optional extra",
    ),
)


class AzureIncidentIngress:
    """Declares incident ingress. Describes and refuses; never actuates."""

    name = "azure.incident_ingress"
    surface = SURFACE

    def probe(self) -> AzureProbe:
        return probe_surface(
            surface_name="incident ingress",
            surfaces=SURFACES,
            absent_detail="Azure incident ingress is a deployment-time surface.",
        )

    def inject_synthetic_incident(
        self, *, correlation_id: str, title: str = ""
    ) -> Refusal:
        """Request injection of a synthetic incident. Returns a typed refusal.

        Args:
            correlation_id: Caller-chosen id used to correlate later observations.
            title: Incident title. Never a credential; nothing secret is accepted.
        """
        probe = self.probe()
        return Refusal(
            code=RefusalCode.NO_SUBSCRIPTION,
            operation="inject_synthetic_incident",
            missing_prerequisite=(
                "a provisioned Azure subscription with a Sentinel workspace "
                "ingestion endpoint (none is bound in this environment)"
            ),
            detail=(
                f"Refused for correlation_id={correlation_id!r}"
                + (f" title={title!r}" if title else "")
                + ". No incident was injected, no request was issued. "
                + probe.detail
            ),
            surfaces_searched=SURFACES,
            methods_used=probe.methods_used,
        )
