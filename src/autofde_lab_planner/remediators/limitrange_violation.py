"""Remediator for LimitRange Violation faults."""

from __future__ import annotations

from autofde_lab_planner.models import LimitRangeViolationFault


def decide_limitrange_remediation_commands(
    faults: list[LimitRangeViolationFault],
    namespace: str = "default",
) -> tuple[list[str], list[str]]:
    """Generates kubectl patch commands to bring container resources within LimitRange bounds."""
    commands: list[str] = []
    deployments_to_restart: list[str] = []

    for f in faults:
        ns = f.namespace or namespace

        if f.fault_kind == "below_min" and f.bound_value is not None:
            target_value = f.bound_value
        elif f.fault_kind == "above_max" and f.bound_value is not None:
            target_value = f.bound_value
        elif f.fault_kind == "missing_default":
            # No safe default is knowable without the LimitRange's own default;
            # request the LimitRange's minimum as the floor value observed elsewhere,
            # falling back to a conservative baseline request.
            target_value = f.bound_value or ("100m" if f.resource_name == "cpu" else "128Mi")
        else:
            continue

        patch = (
            f"kubectl patch deployment {f.deployment_name} -n {ns} --type=json "
            f'-p=\'[{{"op": "replace", "path": '
            f'"/spec/template/spec/containers/0/resources/requests/{f.resource_name}", '
            f'"value": "{target_value}"}}]\''
        )
        commands.append(patch)

        if f.deployment_name not in deployments_to_restart:
            deployments_to_restart.append(f.deployment_name)

    for dep in deployments_to_restart:
        commands.append(f"kubectl rollout restart deployment/{dep} -n {namespace}")

    return commands, deployments_to_restart
