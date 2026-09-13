"""Entra identity surface — REQUESTING authority. Never granting it.

The single most important property in this subpackage lives here:
:meth:`AzureIdentity.request_authority` requests. It has no code path that
returns a permission, and its result type has no boolean grant field. A boolean
would be an authorization verdict, and this repository issues none.

No bearer credential, token, secret, or connection string is ever read, returned,
or logged by this module. Locator variables are checked for PRESENCE only.
"""

from __future__ import annotations

from autofde_lab.adapters.azure.base import AzureProbe, AzureSurface
from autofde_lab.adapters.azure.probe import probe_surface
from autofde_lab.adapters.azure.refusals import Refusal, RefusalCode

__all__ = ["AzureIdentity", "SURFACE"]

SURFACES = ("Microsoft Entra ID", "Entra Privileged Identity Management")

SURFACE = AzureSurface(
    name="azure.identity",
    surfaces=SURFACES,
    purpose="Ask an external authority for a scope. Never to obtain or hold one.",
    required_prerequisites=(
        "an Entra tenant id",
        "a registered application or managed identity",
        "the azure-identity optional extra",
    ),
)


class AzureIdentity:
    """Declares authority REQUESTS. Never grants, never holds a credential."""

    name = "azure.identity"
    surface = SURFACE

    def probe(self) -> AzureProbe:
        return probe_surface(
            surface_name="Entra identity",
            surfaces=SURFACES,
            absent_detail="Microsoft Entra is a deployment-time surface.",
        )

    def request_authority(
        self, *, correlation_id: str, scope: str, justification: str = ""
    ) -> Refusal:
        """REQUEST authority for a scope. Returns a typed refusal; never a grant.

        The return type is a :class:`Refusal`, whose ``granted`` property is
        always ``None`` — not ``False``. ``False`` would read as a denial verdict
        issued by this repository, and no verdict of any polarity is ours to
        issue.
        """
        probe = self.probe()
        return Refusal(
            code=RefusalCode.NO_IDENTITY_PROVIDER,
            operation="request_authority",
            missing_prerequisite=(
                "an Entra tenant binding and a registered identity (none is bound "
                "in this environment)"
            ),
            detail=(
                f"Refused for correlation_id={correlation_id!r} scope={scope!r}"
                + (f" justification={justification!r}" if justification else "")
                + ". No authority was requested, and none could be granted here in "
                "any case: this operation asks an external authority and never "
                "answers on its behalf. " + probe.detail
            ),
            surfaces_searched=SURFACES,
            methods_used=probe.methods_used,
        )
