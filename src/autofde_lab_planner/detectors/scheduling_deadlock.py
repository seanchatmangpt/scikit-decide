"""Detector for Pod Anti-Affinity & Scheduling Deadlocks (Category-B1)."""

from __future__ import annotations

from typing import Any
from autofde_lab_planner.models import SchedulingDeadlockFault


def detect_scheduling_deadlocks(
    deployments_json: dict[str, Any] | list[dict[str, Any]] | None = None,
    pods_json: dict[str, Any] | list[dict[str, Any]] | None = None,
    events_json: dict[str, Any] | list[dict[str, Any]] | None = None,
    namespace: str = "default",
) -> list[SchedulingDeadlockFault]:
    """Detects strict podAntiAffinity rules and unsatisfiable nodeSelector constraints causing pending pod deadlocks."""
    dep_items = _to_item_list(deployments_json)
    pod_items = _to_item_list(pods_json)
    event_items = _to_item_list(events_json)

    faults: list[SchedulingDeadlockFault] = []

    # Map unready pod count per deployment
    unready_by_dep: dict[str, int] = {}
    for pod in pod_items:
        labels = (pod.get("metadata") or {}).get("labels") or {}
        dep_name = labels.get("app") or labels.get("io.kompose.service") or ""
        phase = (pod.get("status") or {}).get("phase", "")
        if phase in ("Pending", "Unknown") or not _is_pod_ready(pod):
            if dep_name:
                unready_by_dep[dep_name] = unready_by_dep.get(dep_name, 0) + 1

    # Check FailedScheduling events
    failed_scheduling_deps: set[str] = set()
    for ev in event_items:
        reason = ev.get("reason", "")
        msg = ev.get("message") or ""
        if reason == "FailedScheduling" or "didn't match" in msg or "0/" in msg:
            obj_name = (ev.get("involvedObject") or {}).get("name", "")
            # Pod name usually starts with deployment name
            for dep in dep_items:
                d_name = (dep.get("metadata") or {}).get("name", "")
                if d_name and obj_name.startswith(d_name):
                    failed_scheduling_deps.add(d_name)

    for dep in dep_items:
        dep_meta = dep.get("metadata") or {}
        dep_name = dep_meta.get("name", "")
        dep_ns = dep_meta.get("namespace") or namespace

        spec_rep = (dep.get("spec") or {}).get("replicas", 1)
        ready_rep = (dep.get("status") or {}).get("readyReplicas", 0)

        # Check if deployment has unready replicas
        is_unready = (
            spec_rep > ready_rep
            or unready_by_dep.get(dep_name, 0) > 0
            or dep_name in failed_scheduling_deps
        )

        pod_spec = ((dep.get("spec") or {}).get("template") or {}).get("spec") or {}
        affinity = pod_spec.get("affinity") or {}
        has_anti_affinity = bool(affinity and isinstance(affinity, dict) and affinity.get("podAntiAffinity"))
        has_node_selector = bool(pod_spec.get("nodeSelector"))

        if is_unready and (has_anti_affinity or has_node_selector):
            if has_anti_affinity and has_node_selector:
                c_type = "both"
            elif has_anti_affinity:
                c_type = "podAntiAffinity"
            else:
                c_type = "nodeSelector"

            faults.append(
                SchedulingDeadlockFault(
                    deployment_name=dep_name,
                    namespace=dep_ns,
                    constraint_type=c_type,
                    unready_replicas=spec_rep - ready_rep,
                    desired_replicas=spec_rep,
                )
            )

    return faults


def _is_pod_ready(pod: dict[str, Any]) -> bool:
    conditions = (pod.get("status") or {}).get("conditions") or []
    for cond in conditions:
        if isinstance(cond, dict) and cond.get("type") == "Ready" and cond.get("status") == "True":
            return True
    return False


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

