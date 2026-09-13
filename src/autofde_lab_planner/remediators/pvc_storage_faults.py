"""Remediator for PVC/storage-related fault mechanisms (Storage-1/Storage-2)."""

from __future__ import annotations

from autofde_lab_planner.models import PVCClaimMismatchFault, PVCMultiAttachFault


def decide_pvc_claim_mismatch_commands(
    faults: list[PVCClaimMismatchFault],
    namespace: str = "default",
) -> tuple[list[str], list[str]]:
    """Generates kubectl patch commands to restore a Deployment's volume
    ``claimName`` back to the PVC that actually exists, when it can be
    inferred (the SREGym "-broken" suffix convention); otherwise re-creates
    the missing PVC referenced by the deployment."""
    commands: list[str] = []
    deployments_to_restart: list[str] = []

    for f in faults:
        dep_name = f.deployment_name
        ns = f.namespace or namespace

        if f.expected_claim_name:
            cmd = (
                f"kubectl patch deployment {dep_name} -n {ns} --type=json "
                f'-p=\'[{{"op": "replace", '
                f'"path": "/spec/template/spec/volumes/0/persistentVolumeClaim/claimName", '
                f'"value": "{f.expected_claim_name}"}}]\''
            )
            commands.append(cmd)
        else:
            pvc_manifest = (
                f'apiVersion: v1\n'
                f'kind: PersistentVolumeClaim\n'
                f'metadata:\n'
                f'  name: {f.observed_claim_name}\n'
                f'  namespace: {ns}\n'
                f'spec:\n'
                f'  accessModes: ["ReadWriteOnce"]\n'
                f'  resources:\n'
                f'    requests:\n'
                f'      storage: 1Gi\n'
            )
            commands.append(f"kubectl apply -n {ns} -f - <<'EOF'\n{pvc_manifest}EOF")

        if dep_name not in deployments_to_restart:
            deployments_to_restart.append(dep_name)

    for dep in deployments_to_restart:
        commands.append(f"kubectl rollout restart deployment/{dep} -n {namespace}")

    return commands, deployments_to_restart


def decide_pvc_multi_attach_commands(
    faults: list[PVCMultiAttachFault],
    namespace: str = "default",
) -> tuple[list[str], list[str]]:
    """Generates kubectl commands to resolve a ReadWriteOnce PVC shared
    across multiple replicas: scale the deployment to a single replica
    (the safe, non-destructive fix that stops Multi-Attach churn without
    requiring a StorageClass migration to ReadWriteMany)."""
    commands: list[str] = []
    deployments_to_restart: list[str] = []

    for f in faults:
        dep_name = f.deployment_name
        ns = f.namespace or namespace

        commands.append(f"kubectl scale deployment {dep_name} -n {ns} --replicas=1")

        if f.has_anti_affinity:
            cmd = (
                f"kubectl patch deployment {dep_name} -n {ns} --type=json "
                '-p=\'[{"op": "remove", "path": "/spec/template/spec/affinity/podAntiAffinity"}]\''
            )
            commands.append(cmd)

        if dep_name not in deployments_to_restart:
            deployments_to_restart.append(dep_name)

    for dep in deployments_to_restart:
        commands.append(f"kubectl rollout restart deployment/{dep} -n {namespace}")

    return commands, deployments_to_restart
