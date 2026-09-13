"""Remediator for ResourceQuota Exhaustion faults."""

from __future__ import annotations

from autofde_lab_planner.models import ResourceQuotaExhaustionFault


def decide_resourcequota_remediation_commands(
    faults: list[ResourceQuotaExhaustionFault],
    namespace: str = "default",
) -> tuple[list[str], list[str]]:
    """Generates kubectl commands to raise an exhausted ResourceQuota's hard ceiling.

    The lawful remediation for a quota exhaustion fault is to raise the quota's
    `hard` ceiling for the affected resource (never to silently drop the quota
    object, which would remove the namespace's own governance control), then
    retry-restart any deployment observed to be blocked by it.
    """
    commands: list[str] = []
    deployments_to_restart: list[str] = []

    for f in faults:
        ns = f.namespace or namespace
        raised_value = _bump_quantity(f.hard, factor=1.5)
        patch = (
            f"kubectl patch resourcequota {f.quota_name} -n {ns} --type=merge "
            f'-p=\'{{"spec": {{"hard": {{"{f.resource_name}": "{raised_value}"}}}}}}\''
        )
        commands.append(patch)

        if f.blocked_deployment and f.blocked_deployment not in deployments_to_restart:
            deployments_to_restart.append(f.blocked_deployment)

    for dep in deployments_to_restart:
        commands.append(f"kubectl rollout restart deployment/{dep} -n {namespace}")

    return commands, deployments_to_restart


def _bump_quantity(value: str, factor: float) -> str:
    """Multiplies a Kubernetes resource quantity string by `factor`, preserving its unit suffix."""
    text = str(value).strip()
    suffix = ""
    numeric_part = text
    for candidate in ("Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "m", "K", "M", "G", "T", "P", "E"):
        if text.endswith(candidate):
            suffix = candidate
            numeric_part = text[: -len(candidate)]
            break
    try:
        bumped = float(numeric_part) * factor
    except ValueError:
        return text
    if bumped == int(bumped):
        return f"{int(bumped)}{suffix}"
    return f"{bumped:.2f}{suffix}"
