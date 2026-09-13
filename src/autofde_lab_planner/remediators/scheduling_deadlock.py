"""Remediator for Pod Anti-Affinity & Scheduling Deadlocks (Category-B1)."""

from __future__ import annotations

from autofde_lab_planner.models import SchedulingDeadlockFault


def decide_scheduling_remediation_commands(
    faults: list[SchedulingDeadlockFault],
    namespace: str = "default",
) -> tuple[list[str], list[str]]:
    """Generates kubectl patch commands to remove unsatisfiable anti-affinity and nodeSelector rules."""
    commands: list[str] = []
    deployments_to_restart: list[str] = []

    for f in faults:
        dep_name = f.deployment_name
        ns = f.namespace or namespace
        c_type = f.constraint_type

        if c_type in ("podAntiAffinity", "both"):
            cmd = (
                f"kubectl patch deployment {dep_name} -n {ns} --type=json "
                '-p=\'[{"op": "remove", "path": "/spec/template/spec/affinity/podAntiAffinity"}]\''
            )
            commands.append(cmd)

        if c_type in ("nodeSelector", "both"):
            cmd = (
                f"kubectl patch deployment {dep_name} -n {ns} --type=json "
                '-p=\'[{"op": "remove", "path": "/spec/template/spec/nodeSelector"}]\''
            )
            commands.append(cmd)

        if dep_name not in deployments_to_restart:
            deployments_to_restart.append(dep_name)

    for dep in deployments_to_restart:
        commands.append(f"kubectl rollout restart deployment/{dep} -n {namespace}")

    return commands, deployments_to_restart
