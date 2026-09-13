"""Notification surface — capturing a DRAFT. Capturing is not sending.

The draft type carries ``sent = False`` as a field with no setter and no code
path that flips it. Nothing in this repository sends a notification.
"""

from __future__ import annotations

from autofde_lab.adapters.azure.base import AzureProbe, AzureSurface
from autofde_lab.adapters.azure.probe import probe_surface
from autofde_lab.adapters.azure.refusals import Refusal, RefusalCode

__all__ = ["AzureNotificationCapture", "SURFACE"]

SURFACES = ("Azure Communication Services", "Teams webhook channel")

SURFACE = AzureSurface(
    name="azure.notification_capture",
    surfaces=SURFACES,
    purpose="Capture a draft notification as plan output. Never to deliver one.",
    required_prerequisites=(
        "a configured notification channel endpoint",
        "a channel that accepts a draft payload",
    ),
)


class AzureNotificationCapture:
    """Declares draft capture. Describes and refuses; never delivers."""

    name = "azure.notification_capture"
    surface = SURFACE

    def probe(self) -> AzureProbe:
        return probe_surface(
            surface_name="notification channel",
            surfaces=SURFACES,
            absent_detail="Azure notification channels are deployment-time surfaces.",
        )

    def capture_notification_draft(
        self, *, correlation_id: str, channel: str, subject: str
    ) -> Refusal:
        """Request capture of a notification draft. Returns a typed refusal."""
        probe = self.probe()
        return Refusal(
            code=RefusalCode.NO_NOTIFICATION_CHANNEL,
            operation="capture_notification_draft",
            missing_prerequisite=(
                "a configured notification channel endpoint (none is configured in "
                "this environment)"
            ),
            detail=(
                f"Refused for correlation_id={correlation_id!r} channel={channel!r} "
                f"subject={subject!r}. Nothing was captured and nothing was sent. "
                "This operation captures drafts only; delivery is not a capability "
                "of this repository. " + probe.detail
            ),
            surfaces_searched=SURFACES,
            methods_used=probe.methods_used,
        )
