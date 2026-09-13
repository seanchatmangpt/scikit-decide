"""Detector for RBAC misconfigurations blocking in-cluster API access.

Ground truth mechanism: ``inject_rbac_misconfiguration`` in
``vendor/gyms/sregym/sregym/generators/fault/inject_virtual.py`` (lines
2394-2467). It binds a Deployment's pod spec to a dedicated ServiceAccount
whose ClusterRole grants only ``pods``/``services`` ``get``/``list``/``watch``
(explicitly withholding ``configmaps``), then adds an init container that runs
``kubectl get configmap ... -n <namespace> -o json`` -- a call the bound
identity is not authorized to make, so the init container fails with a 403
and the pod never becomes Ready.

This detector reconstructs that RBAC gap from real, parseable manifests: the
Deployment pod spec (``serviceAccountName`` + any ``kubectl get <resource>``
invocations inside init/regular containers), the live ServiceAccount list,
and the live ClusterRole / ClusterRoleBinding list -- the same shapes
produced by ``kubectl get <kind> -o json``.
"""

from __future__ import annotations

import re
from typing import Any

from autofde_lab_planner.models import RBACMisconfigFault

_KUBECTL_GET_RE = re.compile(r"kubectl\s+get\s+([a-zA-Z][a-zA-Z0-9._-]*)")

# Map singular/plural aliases a `kubectl get <noun>` command might use onto
# the canonical plural resource name used in RBAC `rules[].resources`.
_RESOURCE_ALIASES: dict[str, str] = {
    "configmap": "configmaps",
    "configmaps": "configmaps",
    "cm": "configmaps",
    "secret": "secrets",
    "secrets": "secrets",
    "pod": "pods",
    "pods": "pods",
    "service": "services",
    "services": "services",
    "svc": "services",
    "deployment": "deployments",
    "deployments": "deployments",
    "endpoint": "endpoints",
    "endpoints": "endpoints",
}


def detect_rbac_misconfigurations(
    deployments_json: dict[str, Any] | list[dict[str, Any]] | None = None,
    service_accounts_json: dict[str, Any] | list[dict[str, Any]] | None = None,
    cluster_roles_json: dict[str, Any] | list[dict[str, Any]] | None = None,
    cluster_role_bindings_json: dict[str, Any] | list[dict[str, Any]] | None = None,
    namespace: str = "default",
) -> list[RBACMisconfigFault]:
    """Detects deployments whose bound ServiceAccount lacks the API permissions
    its own pod spec (init container ``kubectl get`` calls) requires, or whose
    ``serviceAccountName``/binding chain is broken outright."""
    dep_items = _to_item_list(deployments_json)
    sa_items = _to_item_list(service_accounts_json)
    role_items = _to_item_list(cluster_roles_json)
    binding_items = _to_item_list(cluster_role_bindings_json)

    sa_names: set[str] = {(sa.get("metadata") or {}).get("name", "") for sa in sa_items}
    roles_by_name: dict[str, dict[str, Any]] = {
        (r.get("metadata") or {}).get("name", ""): r for r in role_items
    }

    # subject -> [(binding_name, role_name)]
    bindings_by_sa: dict[str, list[tuple[str, str]]] = {}
    for b in binding_items:
        b_name = (b.get("metadata") or {}).get("name", "")
        role_ref_name = (b.get("roleRef") or {}).get("name", "")
        for subj in b.get("subjects") or []:
            if not isinstance(subj, dict):
                continue
            if subj.get("kind") != "ServiceAccount":
                continue
            subj_name = subj.get("name", "")
            bindings_by_sa.setdefault(subj_name, []).append((b_name, role_ref_name))

    faults: list[RBACMisconfigFault] = []

    for dep in dep_items:
        dep_meta = dep.get("metadata") or {}
        dep_name = dep_meta.get("name", "")
        dep_ns = dep_meta.get("namespace") or namespace

        pod_spec = ((dep.get("spec") or {}).get("template") or {}).get("spec") or {}
        sa_name = pod_spec.get("serviceAccountName") or pod_spec.get("serviceAccount") or ""

        if not sa_name:
            continue

        # 1. ServiceAccount referenced but not present in the live cluster.
        if sa_name not in sa_names:
            faults.append(
                RBACMisconfigFault(
                    deployment_name=dep_name,
                    namespace=dep_ns,
                    service_account_name=sa_name,
                    fault_kind="missing_service_account",
                    details=(
                        f"Deployment {dep_name} references serviceAccountName={sa_name!r} "
                        f"which does not exist in namespace {dep_ns}."
                    ),
                )
            )
            continue

        # 2. ServiceAccount exists but no ClusterRoleBinding subjects it.
        sa_bindings = bindings_by_sa.get(sa_name, [])
        if not sa_bindings:
            faults.append(
                RBACMisconfigFault(
                    deployment_name=dep_name,
                    namespace=dep_ns,
                    service_account_name=sa_name,
                    fault_kind="missing_role_binding",
                    details=(
                        f"ServiceAccount {sa_name} used by deployment {dep_name} has no "
                        "ClusterRoleBinding subjecting it to any ClusterRole."
                    ),
                )
            )
            continue

        # 3. Determine which API resources the pod spec actually needs, by
        #    scanning init/regular container commands for `kubectl get <noun>`.
        needed_resources = _extract_needed_resources(pod_spec)
        if not needed_resources:
            continue

        # Union permissions granted across every ClusterRole this SA is bound to.
        granted_resources: set[str] = set()
        role_names_used: list[str] = []
        binding_names_used: list[str] = []
        for b_name, role_name in sa_bindings:
            binding_names_used.append(b_name)
            role = roles_by_name.get(role_name)
            if not role:
                continue
            role_names_used.append(role_name)
            for rule in role.get("rules") or []:
                if not isinstance(rule, dict):
                    continue
                verbs = rule.get("verbs") or []
                if "get" not in verbs and "*" not in verbs:
                    continue
                for res in rule.get("resources") or []:
                    granted_resources.add(res)

        missing = sorted(r for r in needed_resources if r not in granted_resources and "*" not in granted_resources)
        if missing:
            faults.append(
                RBACMisconfigFault(
                    deployment_name=dep_name,
                    namespace=dep_ns,
                    service_account_name=sa_name,
                    fault_kind="missing_rbac_permission",
                    missing_resources=tuple(missing),
                    missing_verbs=("get",),
                    cluster_role_name=role_names_used[0] if role_names_used else None,
                    cluster_role_binding_name=binding_names_used[0] if binding_names_used else None,
                    details=(
                        f"ServiceAccount {sa_name} bound via ClusterRole(s) "
                        f"{', '.join(role_names_used) or '<none>'} is missing get/list/watch "
                        f"on resources required by deployment {dep_name}: {', '.join(missing)}."
                    ),
                )
            )

    return faults


def _extract_needed_resources(pod_spec: dict[str, Any]) -> set[str]:
    needed: set[str] = set()
    all_containers = list(pod_spec.get("initContainers") or []) + list(pod_spec.get("containers") or [])
    for c in all_containers:
        if not isinstance(c, dict):
            continue
        cmd_parts = (c.get("command") or []) + (c.get("args") or [])
        cmd_str = " ".join(str(p) for p in cmd_parts)
        for match in _KUBECTL_GET_RE.finditer(cmd_str):
            noun = match.group(1).lower()
            canonical = _RESOURCE_ALIASES.get(noun)
            if canonical:
                needed.add(canonical)
    return needed


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
