"""Remediator for CronJob / Scheduled Mutations (e.g. vpa-updater squeezing deployment limits)."""

from __future__ import annotations

from autofde_lab_planner.models import CronJobMutationFault


def decide_cronjob_remediation_commands(
    faults: list[CronJobMutationFault],
    namespace: str = "default",
) -> tuple[list[str], list[str]]:
    """Generates dual-step remediation: (1) suspend & delete CronJob, (2) restore victim limits."""
    commands: list[str] = []
    deployments_to_restart: list[str] = []

    for f in faults:
        cj_name = f.cronjob_name
        cj_ns = f.cronjob_namespace or "kube-system"
        victim_dep = f.victim_deployment
        victim_ns = f.victim_namespace or namespace

        # Step 1: Suspend and delete CronJob + policy ConfigMap
        commands.append(f"kubectl patch cronjob {cj_name} -n {cj_ns} -p '{{\"spec\":{{\"suspend\":true}}}}'")
        commands.append(f"kubectl delete cronjob {cj_name} -n {cj_ns}")
        if cj_name == "vpa-updater":
            commands.append(f"kubectl delete configmap vpa-updater-policy -n {cj_ns}")

        # Step 2: Restore victim deployment memory limits
        c_idx = getattr(f, "container_index", 0)
        patch_cmd = (
            f"kubectl patch deployment {victim_dep} -n {victim_ns} --type=json "
            f'-p=\'[{{\"op\": \"remove\", \"path\": \"/spec/template/spec/containers/{c_idx}/resources/limits/memory\"}}]\''
        )
        commands.append(patch_cmd)

        if victim_dep not in deployments_to_restart:
            deployments_to_restart.append(victim_dep)

    for dep in deployments_to_restart:
        commands.append(f"kubectl rollout restart deployment/{dep} -n {namespace}")

    return commands, deployments_to_restart
