"""Shared, filesystem-and-PATH-only probing for Azure surfaces.

No Azure SDK is imported here or anywhere else in this subpackage, at module
level or otherwise. The SDK is an optional extra; this module determines what it
can from ``PATH`` and from whether locator environment variables are *set* — it
never reads a credential value and never executes a discovered binary.

Every function here is total: probes NEVER raise. A probe that throws when the
backend is absent defeats the purpose of probing, so any ``OSError`` is folded
into an ``UNAVAILABLE`` result whose evidence names the error.
"""

from __future__ import annotations

import os
import shutil

from autofde_lab.adapters.azure.base import (
    AZURE_CONTRACT_REVISION,
    AzureProbe,
    AzureProbeStatus,
    empty_environment_fingerprint,
    to_adapter_status,
)

__all__ = ["locate_az_cli", "probe_surface"]

#: Locator variables consulted for tenant binding. Presence only, never values.
TENANT_LOCATORS = ("AZURE_SUBSCRIPTION_ID", "AZURE_TENANT_ID")


def locate_az_cli() -> tuple[str | None, tuple[str, ...]]:
    """Return ``(path_to_az_or_None, methods_used)``. Never raises, never execs."""
    methods = ("shutil.which('az') over PATH (binary located, NOT executed)",)
    try:
        return shutil.which("az"), methods
    except OSError as exc:  # pragma: no cover - defensive; probes never raise
        return None, methods + (f"PATH lookup raised {exc!r}",)


def probe_surface(
    *,
    surface_name: str,
    surfaces: tuple[str, ...],
    absent_detail: str,
) -> AzureProbe:
    """Probe one deployment-time Azure surface. Total; never raises.

    The result is ``UNAVAILABLE`` unless a tenant binding is BOTH declared via
    locator variables AND an ``az`` client is present — and even then the status
    is ``UNKNOWN``, not ``AVAILABLE``: locator variables being set proves a
    configuration intent, not a reachable tenant. Claiming ``AVAILABLE`` from
    them would manufacture a tenant claim out of a local artifact, which is the
    exact error this subpackage exists to make impossible.
    """
    az_path, methods = locate_az_cli()
    locators_set = tuple(v for v in TENANT_LOCATORS if os.environ.get(v))
    methods = methods + (
        "os.environ presence check for "
        + ", ".join(TENANT_LOCATORS)
        + " (presence only; no value read, no credential material touched)",
    )
    searched = ("PATH:az",) + tuple(f"env:{v}" for v in TENANT_LOCATORS)
    environment = empty_environment_fingerprint()

    if az_path is None:
        return AzureProbe(
            status=to_adapter_status(AzureProbeStatus.UNAVAILABLE),
            azure_status=AzureProbeStatus.UNAVAILABLE,
            detail=(
                f"{absent_detail} No 'az' client on PATH, so no client-side path to "
                f"the {surface_name} surface exists. These are deployment-time "
                "surfaces bound to a customer tenant, never a core dependency."
            ),
            searched=searched,
            surfaces_searched=surfaces,
            methods_used=methods,
            revision=AZURE_CONTRACT_REVISION,
            environment=environment,
            evidence=("shutil.which('az') returned None",),
        )

    if not locators_set:
        return AzureProbe(
            status=to_adapter_status(AzureProbeStatus.UNAVAILABLE),
            azure_status=AzureProbeStatus.UNAVAILABLE,
            detail=(
                f"{absent_detail} An 'az' client was located at {az_path}, but no "
                "tenant locator variable is set, so no subscription or tenant is "
                "bound. A binary on PATH is not a tenant."
            ),
            searched=searched,
            surfaces_searched=surfaces,
            methods_used=methods,
            located_at=az_path,
            revision=AZURE_CONTRACT_REVISION,
            environment=environment,
            evidence=(f"az located at {az_path}", "no tenant locator variable set"),
        )

    return AzureProbe(
        status=to_adapter_status(AzureProbeStatus.UNKNOWN),
        azure_status=AzureProbeStatus.UNKNOWN,
        detail=(
            f"{absent_detail} An 'az' client is present at {az_path} and locator "
            f"variables {', '.join(locators_set)} are set, but nothing was contacted: "
            "no request was issued and no interface was exercised. UNKNOWN, not "
            "AVAILABLE — configuration intent is not a reachable tenant."
        ),
        searched=searched,
        surfaces_searched=surfaces,
        methods_used=methods,
        located_at=az_path,
        revision=AZURE_CONTRACT_REVISION,
        environment=environment,
        evidence=(
            f"az located at {az_path}",
            "locator variables set: " + ", ".join(locators_set),
            "no network call was made; no interface was exercised",
        ),
    )
