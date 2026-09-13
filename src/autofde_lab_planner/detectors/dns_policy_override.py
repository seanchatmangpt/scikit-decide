"""Detector for Deployment-level DNS policy override faults.

Source mechanism (fault-injector evidence):
sregym/generators/fault/inject_virtual.py,
VirtualizationFaultInjector.inject_wrong_dns_policy() (around line 1036):

    patch = (
        '[{"op":"replace","path":"/spec/template/spec/dnsPolicy","value":"None"},'
        '{"op":"add","path":"/spec/template/spec/dnsConfig","value":'
        '{"nameservers":["8.8.8.8"],"searches":[]}}]'
    )
    patch_cmd = f"kubectl patch deployment {service} -n {self.namespace} --type json -p '{patch}'"

This mutates a Deployment's Pod template ``spec.dnsPolicy`` from the cluster
default (``ClusterFirst``) to ``None`` and injects an explicit
``spec.dnsConfig.nameservers`` pointing at an external resolver (``8.8.8.8``)
with an empty ``searches`` list. Pods then bypass CoreDNS entirely and cannot
resolve any ``*.svc.cluster.local`` name, even though CoreDNS itself, the
ConfigMap, and every Service object remain untouched and healthy.

This is a distinct mechanism from ``coredns_fault`` (which inspects the
CoreDNS ConfigMap's Corefile for an injected NXDOMAIN rewrite rule) and from
``ingress_targetport``/``service_selector_mismatch`` (which inspect
Service<->Deployment routing agreement). No existing detector in this repo
inspects a Deployment Pod template's ``dnsPolicy``/``dnsConfig`` fields
(confirmed via ``grep -rn "dnsPolicy\\|dnsConfig"
src/autofde_lab_planner/detectors/*.py`` -> zero matches before this file).
"""

from __future__ import annotations

from typing import Any

from autofde_lab_planner.models import DnsPolicyOverrideFault

# The cluster-default DNS policy. Anything else on a Deployment's Pod
# template is a deliberate override and, absent an explicit legitimate
# reason recorded elsewhere, treated as fault evidence.
CLUSTER_DEFAULT_DNS_POLICY = "ClusterFirst"


def detect_dns_policy_overrides(
    deployments_json: dict[str, Any] | list[dict[str, Any]] | None = None,
    namespace: str = "default",
) -> list[DnsPolicyOverrideFault]:
    """Detects Deployments whose Pod template overrides ``dnsPolicy`` away
    from the cluster default (``ClusterFirst``), which severs Pod-level DNS
    resolution against CoreDNS/cluster Services.
    """
    dep_items = _to_item_list(deployments_json)
    faults: list[DnsPolicyOverrideFault] = []

    for dep in dep_items:
        dep_meta = dep.get("metadata") or {}
        dep_name = dep_meta.get("name", "")
        dep_ns = dep_meta.get("namespace") or namespace
        if not dep_name:
            continue

        pod_spec = ((dep.get("spec") or {}).get("template") or {}).get("spec") or {}
        dns_policy = pod_spec.get("dnsPolicy")

        if not dns_policy or dns_policy == CLUSTER_DEFAULT_DNS_POLICY:
            # Unset means the Kubernetes API default (ClusterFirst) applies;
            # absence of an override is not evidence of one.
            continue

        dns_config = pod_spec.get("dnsConfig") or {}
        nameservers = tuple(dns_config.get("nameservers") or ())

        faults.append(
            DnsPolicyOverrideFault(
                deployment_name=dep_name,
                namespace=dep_ns,
                observed_dns_policy=dns_policy,
                observed_nameservers=nameservers,
            )
        )

    return faults


def _to_item_list(data: dict[str, Any] | list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not data:
        return []
    if isinstance(data, dict):
        raw_items = data.get("items")
        if isinstance(raw_items, list):
            items = raw_items
        else:
            items = [data]
    elif isinstance(data, list):
        items = data
    else:
        return []
    return [i for i in items if isinstance(i, dict)]
