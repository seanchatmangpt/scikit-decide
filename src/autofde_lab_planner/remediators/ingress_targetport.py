"""Remediator for Ingress Path Misroutes and Service targetPort Mismatches."""

from __future__ import annotations

from autofde_lab_planner.models import IngressMisrouteFault, TargetPortFault


def decide_ingress_targetport_remediation_commands(
    ingress_faults: list[IngressMisrouteFault],
    target_port_faults: list[TargetPortFault],
    namespace: str = "default",
) -> tuple[list[str], list[str]]:
    """Generates kubectl patch commands for Ingress misroutes and Service targetPort mismatches."""
    commands: list[str] = []
    deployments_to_restart: list[str] = []

    for ing_f in ingress_faults:
        ns = ing_f.namespace or namespace
        rule_idx = getattr(ing_f, "rule_index", 0)
        path_idx = getattr(ing_f, "path_index", 0)
        patch_cmd = (
            f"kubectl patch ingress {ing_f.ingress_name} -n {ns} --type=json "
            f'-p=\'[{{\"op\": \"replace\", \"path\": \"/spec/rules/{rule_idx}/http/paths/{path_idx}/backend/service/name\", \"value\": \"{ing_f.expected_backend_service}\"}}]\''
        )
        commands.append(patch_cmd)

    for tp_f in target_port_faults:
        ns = tp_f.namespace or namespace
        port_idx = getattr(tp_f, "port_index", 0)
        # If expected_target_port is an integer vs string
        val_repr = tp_f.expected_target_port if isinstance(tp_f.expected_target_port, int) else f'"{tp_f.expected_target_port}"'
        patch_cmd = (
            f"kubectl patch service {tp_f.service_name} -n {ns} --type=json "
            f'-p=\'[{{\"op\": \"replace\", \"path\": \"/spec/ports/{port_idx}/targetPort\", \"value\": {val_repr}}}]\''
        )
        commands.append(patch_cmd)

        if tp_f.service_name not in deployments_to_restart:
            deployments_to_restart.append(tp_f.service_name)

    return commands, deployments_to_restart
