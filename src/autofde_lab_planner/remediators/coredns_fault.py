"""Remediator for CoreDNS & Service Discovery Faults."""

from __future__ import annotations

import json
from autofde_lab_planner.models import CoreDNSFault


def decide_coredns_remediation_commands(
    faults: list[CoreDNSFault],
    namespace: str = "kube-system",
) -> tuple[list[str], list[str]]:
    """Generates kubectl apply and rollout restart commands for CoreDNS repair."""
    commands: list[str] = []
    deployments_to_restart: list[str] = []

    for f in faults:
        cm_name = f.configmap_name
        cm_ns = f.namespace or namespace
        repaired_corefile = f.repaired_corefile or ""

        if repaired_corefile:
            manifest = {
                "apiVersion": "v1",
                "kind": "ConfigMap",
                "metadata": {
                    "name": cm_name,
                    "namespace": cm_ns,
                },
                "data": {
                    "Corefile": repaired_corefile,
                },
            }
            manifest_json = json.dumps(manifest).replace("'", "'\\''")
            apply_cmd = f"echo '{manifest_json}' | kubectl apply -f -"
            commands.append(apply_cmd)

        commands.append(f"kubectl rollout restart deployment/{cm_name} -n {cm_ns}")
        if cm_name not in deployments_to_restart:
            deployments_to_restart.append(cm_name)

    return commands, deployments_to_restart
