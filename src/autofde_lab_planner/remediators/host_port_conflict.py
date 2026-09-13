"""Remediator for container hostPort binding conflict faults."""

from __future__ import annotations

from autofde_lab_planner.models import HostPortConflictFault


def decide_host_port_conflict_remediation_commands(
    faults: list[HostPortConflictFault],
    namespace: str = "default",
) -> tuple[list[str], list[str]]:
    """Generates kubectl patch commands that remove the injected
    ``hostPort`` key from the affected container's port entry, restoring
    normal (non-host-bound) Pod scheduling, followed by a rollout restart
    so already-unschedulable Pods are replaced.
    """
    commands: list[str] = []
    affected_deployments: list[str] = []

    for f in faults:
        ns = f.namespace or namespace
        path = (
            f"/spec/template/spec/containers/{f.container_index}"
            f"/ports/{f.port_index}/hostPort"
        )
        cmd = (
            f"kubectl patch deployment {f.deployment_name} -n {ns} --type=json "
            f'-p=\'[{{"op": "remove", "path": "{path}"}}]\''
        )
        commands.append(cmd)
        commands.append(f"kubectl rollout restart deployment {f.deployment_name} -n {ns}")

        if f.deployment_name not in affected_deployments:
            affected_deployments.append(f.deployment_name)

    return commands, affected_deployments
