"""Category-B4 Remediator: Probe Heuristics & Liveness/Readiness Faults."""

from __future__ import annotations

from autofde_lab_planner.models import ProbeFault


def decide_probe_remediation_commands(
    faults: list[ProbeFault],
    namespace: str,
) -> tuple[list[str], list[str]]:
    """Generates exact kubectl JSON patch and strategic merge patch commands to revert probe misconfigurations.

    Returns:
        (commands, wait_rollout_deployments)
    """
    commands: list[str] = []
    affected_deployments: list[str] = []

    for f in faults:
        dep = f.deployment_name
        p_type = f.probe_type
        if dep not in affected_deployments:
            affected_deployments.append(dep)

        c_idx = getattr(f, "container_index", 0)
        # JSON patch to remove faulty probe
        remove_probe_cmd = (
            f"kubectl patch deployment {dep} -n {namespace} --type=json "
            f'-p=\'[{{"op": "remove", "path": "/spec/template/spec/containers/{c_idx}/{p_type}"}}]\''
        )
        commands.append(remove_probe_cmd)

        # Restore default terminationGracePeriodSeconds (30s) if mutated to 0
        restore_grace_cmd = (
            f"kubectl patch deployment {dep} -n {namespace} --type=strategic "
            f'-p=\'{{"spec":{{"template":{{"spec":{{"terminationGracePeriodSeconds":30}}}}}}}}\''
        )
        commands.append(restore_grace_cmd)


    return commands, affected_deployments
