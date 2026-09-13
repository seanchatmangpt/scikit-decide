"""Microsoft Sentinel surface — read-only incident and postcondition observation.

Reading is the only thing this surface would ever do. It observes; it does not
admit an observation as true, and it does not verify. A verifier is a separate
role held outside this repository.
"""

from __future__ import annotations

from autofde_lab.adapters.azure.base import AzureProbe, AzureSurface
from autofde_lab.adapters.azure.probe import probe_surface
from autofde_lab.adapters.azure.refusals import Refusal, RefusalCode

__all__ = ["AzureSentinel", "SURFACE"]

SURFACES = ("Microsoft Sentinel", "Log Analytics workspace (KQL query surface)")

SURFACE = AzureSurface(
    name="azure.sentinel",
    surfaces=SURFACES,
    purpose="Read incident state and postcondition predicates as planning observables.",
    required_prerequisites=(
        "a Sentinel workspace id",
        "a Log Analytics query endpoint",
        "the azure-monitor-query optional extra",
    ),
)


class AzureSentinel:
    """Declares Sentinel reads. Describes and refuses; never actuates."""

    name = "azure.sentinel"
    surface = SURFACE

    def probe(self) -> AzureProbe:
        return probe_surface(
            surface_name="Sentinel",
            surfaces=SURFACES,
            absent_detail="Microsoft Sentinel is a deployment-time surface.",
        )

    def read_incident_observation(self, *, correlation_id: str) -> Refusal:
        """Request a read of incident state. Returns a typed refusal."""
        probe = self.probe()
        return Refusal(
            code=RefusalCode.NO_WORKSPACE,
            operation="read_incident_observation",
            missing_prerequisite=(
                "a Sentinel / Log Analytics workspace id and query endpoint "
                "(none is bound in this environment)"
            ),
            detail=(
                f"Refused for correlation_id={correlation_id!r}. No query was issued "
                "and no observation was produced. " + probe.detail
            ),
            surfaces_searched=SURFACES,
            methods_used=probe.methods_used,
        )

    def read_postcondition(self, *, correlation_id: str, predicate: str) -> Refusal:
        """Request a read of a postcondition predicate. Returns a typed refusal.

        A postcondition READING is not a verification verdict. Even with a live
        workspace this would report what the surface said, never that a plan
        succeeded.
        """
        probe = self.probe()
        return Refusal(
            code=RefusalCode.NO_WORKSPACE,
            operation="read_postcondition",
            missing_prerequisite=(
                "a Sentinel / Log Analytics workspace id and query endpoint "
                "(none is bound in this environment)"
            ),
            detail=(
                f"Refused for correlation_id={correlation_id!r} "
                f"predicate={predicate!r}. Nothing was read, and this operation "
                "would not issue a verification verdict even if it succeeded. "
                + probe.detail
            ),
            surfaces_searched=SURFACES,
            methods_used=probe.methods_used,
        )
