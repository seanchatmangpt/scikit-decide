"""Remediator for Deployment-level DNS policy override faults.

Mirrors the fault injector's own
``VirtualizationFaultInjector.recover_wrong_dns_policy()`` (inject_virtual.py
around line 1054), which removes the injected ``dnsPolicy``/``dnsConfig``
overrides via a JSON patch and restarts the rollout so CoreDNS resolution is
restored for the running Pods.
"""

from __future__ import annotations

from autofde_lab_planner.models import DnsPolicyOverrideFault


def decide_dns_policy_remediation_commands(
    faults: list[DnsPolicyOverrideFault],
    namespace: str = "default",
) -> tuple[list[str], list[str]]:
    """Generates kubectl patch + rollout-restart commands that remove the
    injected ``dnsPolicy``/``dnsConfig`` override from each affected
    Deployment's Pod template, restoring the cluster-default DNS policy.
    """
    commands: list[str] = []
    affected_deployments: list[str] = []

    for f in faults:
        ns = f.namespace or namespace
        patch = (
            '[{"op":"remove","path":"/spec/template/spec/dnsPolicy"},'
            '{"op":"remove","path":"/spec/template/spec/dnsConfig"}]'
        )
        commands.append(
            f"kubectl patch deployment {f.deployment_name} -n {ns} --type json -p '{patch}'"
        )
        commands.append(f"kubectl rollout restart deployment {f.deployment_name} -n {ns}")

        if f.deployment_name not in affected_deployments:
            affected_deployments.append(f.deployment_name)

    return commands, affected_deployments
