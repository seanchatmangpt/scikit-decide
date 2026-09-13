"""Category-B9 Remediator: flagd Config Drift Patch & Rollout Restart."""

from __future__ import annotations

from autofde_lab_planner.models import FlagdDriftResult


def decide_flagd_remediation_commands(
    drift_result: FlagdDriftResult,
) -> tuple[list[str], list[str]]:
    """Generates ConfigMap patch and workload rollout restart commands to fix flagd drift."""
    if not drift_result.has_drift or not drift_result.repaired_flagd_json:
        return [], []

    cm_name = drift_result.configmap_name
    namespace = drift_result.namespace

    # Escape quotes for shell command embedding
    json_payload = drift_result.repaired_flagd_json.replace("'", "'\\''")
    patch_cmd = (
        f"kubectl create configmap {cm_name} -n {namespace} "
        f"--from-literal=demo.flagd.json='{json_payload}' "
        f"--dry-run=client -o yaml | kubectl apply -f -"
    )

    commands = [patch_cmd]
    deployments_to_restart: list[str] = ["flagd"]

    for item in drift_result.drifted_flags:
        for dep in item.target_deployments:
            if dep not in deployments_to_restart:
                deployments_to_restart.append(dep)

    for dep in deployments_to_restart:
        commands.append(f"kubectl rollout restart deployment/{dep} -n {namespace}")

    return commands, deployments_to_restart
