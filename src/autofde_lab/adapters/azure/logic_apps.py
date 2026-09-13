"""Logic Apps surface — handing a CANDIDATE action to an external broker.

Submission is not execution and not authorization. This repository computes
candidate plans; a broker authorizes, an executor performs, a verifier evaluates.
Nothing here crosses any of those lines.
"""

from __future__ import annotations

from autofde_lab.adapters.azure.base import AzureProbe, AzureSurface
from autofde_lab.adapters.azure.probe import probe_surface
from autofde_lab.adapters.azure.refusals import Refusal, RefusalCode

__all__ = ["AzureLogicApps", "SURFACE"]

SURFACES = ("Azure Logic Apps workflow trigger endpoint",)

SURFACE = AzureSurface(
    name="azure.logic_apps",
    surfaces=SURFACES,
    purpose="Hand a candidate action to an external broker for its own decision.",
    required_prerequisites=(
        "a Logic Apps workflow endpoint URL",
        "a workflow that accepts a candidate-action payload",
    ),
)


class AzureLogicApps:
    """Declares candidate-action submission. Describes and refuses."""

    name = "azure.logic_apps"
    surface = SURFACE

    def probe(self) -> AzureProbe:
        return probe_surface(
            surface_name="Logic Apps",
            surfaces=SURFACES,
            absent_detail="Azure Logic Apps is a deployment-time surface.",
        )

    def submit_candidate_action(
        self, *, correlation_id: str, action_name: str
    ) -> Refusal:
        """Request submission of a candidate action. Returns a typed refusal.

        Submitting a candidate is the strongest thing this operation could ever
        do. It cannot report acceptance: acceptance is the broker's to state.
        """
        probe = self.probe()
        return Refusal(
            code=RefusalCode.NO_WORKFLOW_ENDPOINT,
            operation="submit_candidate_action",
            missing_prerequisite=(
                "a Logic Apps workflow trigger endpoint (none is configured in "
                "this environment)"
            ),
            detail=(
                f"Refused for correlation_id={correlation_id!r} "
                f"action_name={action_name!r}. Nothing was submitted. Even on "
                "success this operation would hand over a CANDIDATE and would not "
                "report acceptance. " + probe.detail
            ),
            surfaces_searched=SURFACES,
            methods_used=probe.methods_used,
        )
