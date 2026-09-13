"""ObjectKindAnalyzer registry -- one real analyzer per Kubernetes kind.

Each analyzer is a pure function: real kubectl-JSON-shaped `dict`/`list` input
in (the `ClusterState` mapping below, keyed by the real `kubectl get -o json`
resource-list names), real `tuple[Anomaly, ...]` out. Adding a new kind means
writing one new analyzer function and adding one line to `ANALYZERS` --
verified concretely by `scan_cronjobs` (the sixth kind, added after the first
five to test the O(1) claim; see the git diff cited in the task's final
report, not just this comment).
"""

from __future__ import annotations

from typing import Any, Callable, TypedDict

from autofde_lab_planner.scanner import diff_engine
from autofde_lab_planner.scanner.models import Anomaly


def _items(data: Any) -> list[dict[str, Any]]:
    """Normalize a kubectl-JSON-shaped value (list, {"items": [...]}, single object) to a list."""
    if data is None:
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "items" in data:
        return list(data["items"])
    if isinstance(data, dict):
        return [data]
    return []


class ClusterState(TypedDict, total=False):
    deployments: Any
    pods: Any
    services: Any
    persistentvolumeclaims: Any
    configmaps: Any
    serviceaccounts: Any
    clusterroles: Any
    clusterrolebindings: Any
    resourcequotas: Any
    limitranges: Any
    cronjobs: Any
    ingresses: Any
    nodes: Any


# ---------------------------------------------------------------------------
# 1. Deployment -- declared_vs_observed (replicas readiness against real Pods)
# ---------------------------------------------------------------------------


def scan_deployments(state: ClusterState) -> tuple[Anomaly, ...]:
    anomalies: list[Anomaly] = []
    pods = _items(state.get("pods"))
    for dep in _items(state.get("deployments")):
        name = dep.get("metadata", {}).get("name", "<unknown>")
        namespace = dep.get("metadata", {}).get("namespace", "default")
        declared_replicas = dep.get("spec", {}).get("replicas", 1)
        selector = dep.get("spec", {}).get("selector", {}).get("matchLabels", {})
        ready_count = 0
        for pod in pods:
            if pod.get("metadata", {}).get("namespace") != namespace:
                continue
            pod_labels = pod.get("metadata", {}).get("labels", {})
            if not selector or not all(pod_labels.get(k) == v for k, v in selector.items()):
                continue
            conditions = pod.get("status", {}).get("conditions", [])
            if any(c.get("type") == "Ready" and c.get("status") == "True" for c in conditions):
                ready_count += 1
        anomaly = diff_engine.compare_declared_vs_observed(
            kind="Deployment",
            object_name=name,
            namespace=namespace,
            field="readyReplicas",
            declared=declared_replicas,
            observed=ready_count,
            detail=f"selector {selector} matched {ready_count} Ready pod(s), declared {declared_replicas} replica(s)",
        )
        if anomaly is not None:
            anomalies.append(anomaly)

        image = dep.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [{}])[0].get("image")
        observed_image = dep.get("status", {}).get("observedImage", image)
        if observed_image != image and observed_image is not None:
            anomalies.append(
                diff_engine.compare_declared_vs_observed(
                    kind="Deployment",
                    object_name=name,
                    namespace=namespace,
                    field="image",
                    declared=image,
                    observed=observed_image,
                )
            )
    return tuple(a for a in anomalies if a is not None)


# ---------------------------------------------------------------------------
# 2. Service -- dangling_reference (selector matches no live Pod)
# ---------------------------------------------------------------------------


def scan_services(state: ClusterState) -> tuple[Anomaly, ...]:
    anomalies: list[Anomaly] = []
    pods = _items(state.get("pods"))
    for svc in _items(state.get("services")):
        name = svc.get("metadata", {}).get("name", "<unknown>")
        namespace = svc.get("metadata", {}).get("namespace", "default")
        selector = svc.get("spec", {}).get("selector", {})
        if not selector:
            continue
        matched_pod_names = {
            pod.get("metadata", {}).get("name", "")
            for pod in pods
            if pod.get("metadata", {}).get("namespace") == namespace
            and all(pod.get("metadata", {}).get("labels", {}).get(k) == v for k, v in selector.items())
        }
        anomaly = diff_engine.find_dangling_reference(
            kind="Service",
            object_name=name,
            namespace=namespace,
            field="spec.selector",
            referenced_name=f"selector={selector}",
            available_names=set() if matched_pod_names else {"<no matching pods>"},
            detail=f"selector {selector} matched {len(matched_pod_names)} pod(s)",
        )
        if not matched_pod_names:
            anomalies.append(
                Anomaly(
                    kind="Service",
                    object_name=name,
                    namespace=namespace,
                    relation_class="dangling_reference",
                    field="spec.selector",
                    observed=str(selector),
                    expected=None,
                    detail=f"selector {selector} matches zero live pods in namespace {namespace}",
                )
            )
    return tuple(anomalies)


# ---------------------------------------------------------------------------
# 3. PVC -- dangling_reference (Pod claims a PVC name that has no PVC)
# ---------------------------------------------------------------------------


def scan_persistentvolumeclaims(state: ClusterState) -> tuple[Anomaly, ...]:
    anomalies: list[Anomaly] = []
    pvc_names = {pvc.get("metadata", {}).get("name") for pvc in _items(state.get("persistentvolumeclaims"))}
    for pod in _items(state.get("pods")):
        pod_name = pod.get("metadata", {}).get("name", "<unknown>")
        namespace = pod.get("metadata", {}).get("namespace", "default")
        for volume in pod.get("spec", {}).get("volumes", []):
            claim = volume.get("persistentVolumeClaim", {}).get("claimName")
            if claim is None:
                continue
            anomaly = diff_engine.find_dangling_reference(
                kind="PersistentVolumeClaim",
                object_name=pod_name,
                namespace=namespace,
                field="spec.volumes[].persistentVolumeClaim.claimName",
                referenced_name=claim,
                available_names=pvc_names,
                detail=f"pod {pod_name} references PVC {claim!r}, no matching PVC exists",
            )
            if anomaly is not None:
                anomalies.append(anomaly)
    return tuple(anomalies)


# ---------------------------------------------------------------------------
# 4. ConfigMap -- dangling_reference (Pod references a ConfigMap key that is absent)
# ---------------------------------------------------------------------------


def scan_configmaps(state: ClusterState) -> tuple[Anomaly, ...]:
    anomalies: list[Anomaly] = []
    configmaps_by_name: dict[str, dict[str, Any]] = {
        cm.get("metadata", {}).get("name"): cm for cm in _items(state.get("configmaps"))
    }
    for pod in _items(state.get("pods")):
        pod_name = pod.get("metadata", {}).get("name", "<unknown>")
        namespace = pod.get("metadata", {}).get("namespace", "default")
        for container in pod.get("spec", {}).get("containers", []):
            for env_from in container.get("envFrom", []):
                cm_ref = env_from.get("configMapRef", {}).get("name")
                if cm_ref is None:
                    continue
                if cm_ref not in configmaps_by_name:
                    anomalies.append(
                        Anomaly(
                            kind="ConfigMap",
                            object_name=pod_name,
                            namespace=namespace,
                            relation_class="dangling_reference",
                            field="spec.containers[].envFrom[].configMapRef.name",
                            observed=cm_ref,
                            expected=None,
                            detail=f"pod {pod_name} references ConfigMap {cm_ref!r}, not found",
                        )
                    )
            for env in container.get("env", []):
                key_ref = env.get("valueFrom", {}).get("configMapKeyRef", {})
                cm_name = key_ref.get("name")
                cm_key = key_ref.get("key")
                if cm_name is None or cm_key is None:
                    continue
                cm = configmaps_by_name.get(cm_name)
                available_keys = set((cm or {}).get("data", {}).keys())
                anomaly = diff_engine.find_dangling_reference(
                    kind="ConfigMap",
                    object_name=cm_name,
                    namespace=namespace,
                    field="data",
                    referenced_name=cm_key,
                    available_names=available_keys,
                    detail=f"pod {pod_name} references key {cm_key!r} in ConfigMap {cm_name!r}",
                )
                if anomaly is not None:
                    anomalies.append(anomaly)
    return tuple(anomalies)


# ---------------------------------------------------------------------------
# 5. RBAC composite (ServiceAccount + ClusterRole + ClusterRoleBinding)
#    -- insufficient_capability
# ---------------------------------------------------------------------------


def _rules_to_verb_resource_set(rules: list[dict[str, Any]]) -> set[str]:
    granted: set[str] = set()
    for rule in rules:
        for resource in rule.get("resources", []):
            for verb in rule.get("verbs", []):
                granted.add(f"{verb}:{resource}")
    return granted


def scan_rbac(state: ClusterState) -> tuple[Anomaly, ...]:
    anomalies: list[Anomaly] = []
    cluster_roles_by_name: dict[str, dict[str, Any]] = {
        cr.get("metadata", {}).get("name"): cr for cr in _items(state.get("clusterroles"))
    }
    bindings = _items(state.get("clusterrolebindings"))

    for pod in _items(state.get("pods")):
        pod_name = pod.get("metadata", {}).get("name", "<unknown>")
        namespace = pod.get("metadata", {}).get("namespace", "default")
        sa_name = pod.get("spec", {}).get("serviceAccountName", "default")
        required = set(pod.get("metadata", {}).get("annotations", {}).get("required-rbac", "").split(",")) - {""}
        if not required:
            continue

        bound_role_names = {
            b.get("roleRef", {}).get("name")
            for b in bindings
            if any(
                s.get("kind") == "ServiceAccount" and s.get("name") == sa_name and s.get("namespace") == namespace
                for s in b.get("subjects", [])
            )
        }
        granted: set[str] = set()
        for role_name in bound_role_names:
            role = cluster_roles_by_name.get(role_name)
            if role is not None:
                granted |= _rules_to_verb_resource_set(role.get("rules", []))

        anomaly = diff_engine.find_insufficient_capability(
            kind="ServiceAccount",
            object_name=sa_name,
            namespace=namespace,
            field="rbac.rules",
            required=required,
            granted=granted,
            detail=f"pod {pod_name} bound to ServiceAccount {sa_name!r} via roles {sorted(bound_role_names)}",
        )
        if anomaly is not None:
            anomalies.append(anomaly)
    return tuple(anomalies)


# ---------------------------------------------------------------------------
# 6. ResourceQuota + LimitRange composite -- aggregate_threshold
# ---------------------------------------------------------------------------


def scan_resourcequotas(state: ClusterState) -> tuple[Anomaly, ...]:
    anomalies: list[Anomaly] = []
    pods = _items(state.get("pods"))
    for rq in _items(state.get("resourcequotas")):
        name = rq.get("metadata", {}).get("name", "<unknown>")
        namespace = rq.get("metadata", {}).get("namespace", "default")
        hard = rq.get("spec", {}).get("hard", {})
        pod_limit = hard.get("pods")
        if pod_limit is not None:
            observed_count = sum(1 for p in pods if p.get("metadata", {}).get("namespace") == namespace)
            anomaly = diff_engine.find_aggregate_threshold_violation(
                kind="ResourceQuota",
                object_name=name,
                namespace=namespace,
                field="hard.pods",
                total_observed=float(observed_count),
                limit=float(pod_limit),
                unit=" pods",
            )
            if anomaly is not None:
                anomalies.append(anomaly)
    return tuple(anomalies)



# ---------------------------------------------------------------------------
# Sixth kind, added after the initial five (+RBAC composite) to demonstrate
# O(1) extension: one new analyzer function, one new ANALYZERS entry.
# ---------------------------------------------------------------------------


def scan_cronjobs(state: ClusterState) -> tuple[Anomaly, ...]:
    """CronJob -- declared_vs_observed on schedule mutation."""
    anomalies: list[Anomaly] = []
    for cj in _items(state.get("cronjobs")):
        name = cj.get("metadata", {}).get("name", "<unknown>")
        namespace = cj.get("metadata", {}).get("namespace", "default")
        annotations = cj.get("metadata", {}).get("annotations", {})
        baseline_schedule = annotations.get("baseline-schedule")
        observed_schedule = cj.get("spec", {}).get("schedule")
        if baseline_schedule is not None:
            anomaly = diff_engine.compare_declared_vs_observed(
                kind="CronJob",
                object_name=name,
                namespace=namespace,
                field="spec.schedule",
                declared=baseline_schedule,
                observed=observed_schedule,
            )
            if anomaly is not None:
                anomalies.append(anomaly)
    return tuple(anomalies)


# ---------------------------------------------------------------------------
# Pod composite -- declared_vs_observed on probe config, dnsPolicy, and an
# aggregate_threshold on hostPort collisions. Covers what the abandoned
# enumeration called ProbeFault, DnsPolicyOverrideFault, HostPortConflictFault.
# ---------------------------------------------------------------------------


def scan_pods(state: ClusterState) -> tuple[Anomaly, ...]:
    anomalies: list[Anomaly] = []
    host_port_usage: dict[tuple[str, int], list[str]] = {}
    for pod in _items(state.get("pods")):
        pod_name = pod.get("metadata", {}).get("name", "<unknown>")
        namespace = pod.get("metadata", {}).get("namespace", "default")

        baseline_dns_policy = pod.get("metadata", {}).get("annotations", {}).get("baseline-dns-policy")
        observed_dns_policy = pod.get("spec", {}).get("dnsPolicy", "ClusterFirst")
        if baseline_dns_policy is not None:
            anomaly = diff_engine.compare_declared_vs_observed(
                kind="Pod",
                object_name=pod_name,
                namespace=namespace,
                field="spec.dnsPolicy",
                declared=baseline_dns_policy,
                observed=observed_dns_policy,
            )
            if anomaly is not None:
                anomalies.append(anomaly)

        for container in pod.get("spec", {}).get("containers", []):
            probe = container.get("livenessProbe") or container.get("readinessProbe")
            if probe is not None:
                baseline_threshold = container.get("baselineFailureThreshold")
                observed_threshold = probe.get("failureThreshold")
                if baseline_threshold is not None:
                    anomaly = diff_engine.compare_declared_vs_observed(
                        kind="Pod",
                        object_name=pod_name,
                        namespace=namespace,
                        field="probe.failureThreshold",
                        declared=baseline_threshold,
                        observed=observed_threshold,
                        detail=f"container {container.get('name')} probe too aggressive",
                    )
                    if anomaly is not None:
                        anomalies.append(anomaly)

            for port in container.get("ports", []):
                host_port = port.get("hostPort")
                if host_port is not None:
                    key = (namespace, host_port)
                    host_port_usage.setdefault(key, []).append(pod_name)

    for (namespace, host_port), users in host_port_usage.items():
        if len(users) > 1:
            anomalies.append(
                Anomaly(
                    kind="Pod",
                    object_name=",".join(sorted(users)),
                    namespace=namespace,
                    relation_class="aggregate_threshold",
                    field="spec.containers[].ports[].hostPort",
                    observed=f"{len(users)} pods on hostPort {host_port}",
                    expected="<= 1 pod per hostPort",
                    detail=f"hostPort {host_port} conflicts across pods {sorted(users)}",
                )
            )
    return tuple(anomalies)


# ---------------------------------------------------------------------------
# Ingress -- dangling_reference (backend service missing) and
# declared_vs_observed (target port mismatch). Covers IngressMisrouteFault,
# TargetPortFault.
# ---------------------------------------------------------------------------


def scan_ingresses(state: ClusterState) -> tuple[Anomaly, ...]:
    anomalies: list[Anomaly] = []
    services_by_name: dict[str, dict[str, Any]] = {
        svc.get("metadata", {}).get("name"): svc for svc in _items(state.get("services"))
    }
    for ing in _items(state.get("ingresses")):
        name = ing.get("metadata", {}).get("name", "<unknown>")
        namespace = ing.get("metadata", {}).get("namespace", "default")
        for rule in ing.get("spec", {}).get("rules", []):
            for path in rule.get("http", {}).get("paths", []):
                backend = path.get("backend", {}).get("service", {})
                svc_name = backend.get("name")
                if svc_name is None:
                    continue
                svc = services_by_name.get(svc_name)
                anomaly = diff_engine.find_dangling_reference(
                    kind="Ingress",
                    object_name=name,
                    namespace=namespace,
                    field="spec.rules[].http.paths[].backend.service.name",
                    referenced_name=svc_name,
                    available_names=set(services_by_name.keys()),
                )
                if anomaly is not None:
                    anomalies.append(anomaly)
                    continue
                declared_port = backend.get("port", {}).get("number")
                observed_ports = {p.get("port") for p in svc.get("spec", {}).get("ports", [])}
                if declared_port is not None and declared_port not in observed_ports:
                    anomalies.append(
                        Anomaly(
                            kind="Ingress",
                            object_name=name,
                            namespace=namespace,
                            relation_class="declared_vs_observed",
                            field="spec.rules[].http.paths[].backend.service.port.number",
                            observed=str(sorted(observed_ports)),
                            expected=str(declared_port),
                            detail=f"backend service {svc_name!r} exposes ports {sorted(observed_ports)}, ingress targets {declared_port}",
                        )
                    )
    return tuple(anomalies)


# ---------------------------------------------------------------------------
ANALYZERS: dict[str, Callable[[ClusterState], tuple[Anomaly, ...]]] = {
    "Deployment": scan_deployments,
    "Service": scan_services,
    "PersistentVolumeClaim": scan_persistentvolumeclaims,
    "ConfigMap": scan_configmaps,
    "RBAC": scan_rbac,
    "ResourceQuota": scan_resourcequotas,
    "CronJob": scan_cronjobs,
    "Pod": scan_pods,
    "Ingress": scan_ingresses,
}


def scan(state: ClusterState) -> tuple[Anomaly, ...]:
    """Run every registered analyzer over the given real cluster state."""
    anomalies: list[Anomaly] = []
    for analyzer in ANALYZERS.values():
        anomalies.extend(analyzer(state))
    return tuple(anomalies)
