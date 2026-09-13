"""Remediator for RBAC misconfigurations blocking in-cluster API access."""

from __future__ import annotations

from autofde_lab_planner.models import RBACMisconfigFault


def decide_rbac_remediation_commands(
    faults: list[RBACMisconfigFault],
    namespace: str = "default",
) -> tuple[list[str], list[str]]:
    """Generates kubectl commands to repair ServiceAccount/RBAC gaps: create a
    missing ServiceAccount, create a missing ClusterRoleBinding, or patch a
    ClusterRole's rules to grant the missing resources/verbs."""
    commands: list[str] = []
    deployments_to_restart: list[str] = []

    for f in faults:
        ns = f.namespace or namespace
        kind = f.fault_kind

        if kind == "missing_service_account":
            commands.append(
                f"kubectl create serviceaccount {f.service_account_name} -n {ns} "
                f"--dry-run=client -o yaml | kubectl apply -f -"
            )

        elif kind == "missing_role_binding":
            role_name = f.cluster_role_name or f"{f.service_account_name}-role"
            binding_name = f.cluster_role_binding_name or f"{f.service_account_name}-binding"
            commands.append(
                f"kubectl create clusterrolebinding {binding_name} "
                f"--clusterrole={role_name} "
                f"--serviceaccount={ns}:{f.service_account_name} "
                f"--dry-run=client -o yaml | kubectl apply -f -"
            )

        elif kind == "missing_rbac_permission":
            role_name = f.cluster_role_name or f"{f.service_account_name}-role"
            for resource in f.missing_resources:
                verbs_json = ", ".join(f'"{v}"' for v in (f.missing_verbs or ("get", "list", "watch")))
                patch = (
                    f"kubectl patch clusterrole {role_name} --type=json "
                    f"-p='[{{\"op\": \"add\", \"path\": \"/rules/-\", "
                    f"\"value\": {{\"apiGroups\": [\"\"], "
                    f'"resources": ["{resource}"], "verbs": [{verbs_json}]}}}}]\''
                )
                commands.append(patch)

        if f.deployment_name and f.deployment_name not in deployments_to_restart:
            deployments_to_restart.append(f.deployment_name)

    for dep in deployments_to_restart:
        commands.append(f"kubectl rollout restart deployment/{dep} -n {namespace}")

    return commands, deployments_to_restart
