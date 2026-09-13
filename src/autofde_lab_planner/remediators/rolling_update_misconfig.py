"""Remediator for Workload & Rolling Update Misconfigurations."""

from __future__ import annotations

from autofde_lab_planner.models import WorkloadMisconfigFault


def decide_workload_remediation_commands(
    faults: list[WorkloadMisconfigFault],
    namespace: str = "default",
) -> tuple[list[str], list[str]]:
    """Generates kubectl patch commands for resource request reduction and rolling update strategy reset."""
    commands: list[str] = []
    deployments_to_restart: list[str] = []

    for f in faults:
        dep_name = f.deployment_name
        ns = f.namespace or namespace
        kind = f.fault_kind

        if kind == "resource_request_too_large":
            # Remove container resource requests
            c_idx = getattr(f, "container_index", 0)
            patch_cmd = (
                f"kubectl patch deployment {dep_name} -n {ns} --type=json "
                f'-p=\'[{{\"op\": \"remove\", \"path\": \"/spec/template/spec/containers/{c_idx}/resources/requests\"}}]\''
            )
            commands.append(patch_cmd)

        elif kind == "rolling_update_misconfigured":
            # 1. Reset rolling update strategy to defaults maxSurge=25%, maxUnavailable=25%
            strategy_patch = (
                f"kubectl patch deployment {dep_name} -n {ns} --type=json "
                '-p=\'[{"op": "replace", "path": "/spec/strategy", '
                '"value": {"type": "RollingUpdate", "rollingUpdate": {"maxSurge": "25%", "maxUnavailable": "25%"}}}]\''
            )
            commands.append(strategy_patch)

            # 2. Strip hanging init containers ONLY if hanging_init container was detected
            if "hanging_init=True" in f.details or "hanging_init=true" in f.details.lower():
                init_patch = (
                    f"kubectl patch deployment {dep_name} -n {ns} --type=json "
                    '-p=\'[{"op": "remove", "path": "/spec/template/spec/initContainers"}]\''
                )
                commands.append(init_patch)


        if dep_name not in deployments_to_restart:
            deployments_to_restart.append(dep_name)

    for dep in deployments_to_restart:
        commands.append(f"kubectl rollout restart deployment/{dep} -n {namespace}")

    return commands, deployments_to_restart
