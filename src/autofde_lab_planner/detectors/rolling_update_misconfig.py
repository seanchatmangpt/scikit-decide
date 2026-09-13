"""Detector for Workload & Rolling Update Misconfigurations."""

from __future__ import annotations

from typing import Any
from autofde_lab_planner.models import WorkloadMisconfigFault


def detect_workload_and_rolling_update_misconfigs(
    deployments_json: dict[str, Any] | list[dict[str, Any]] | None = None,
    pods_json: dict[str, Any] | list[dict[str, Any]] | None = None,
    events_json: dict[str, Any] | list[dict[str, Any]] | None = None,
    namespace: str = "default",
) -> list[WorkloadMisconfigFault]:
    """Detects unfulfillable memory/CPU requests, hanging init containers, and zero-surge rolling update misconfigs."""
    dep_items = _to_item_list(deployments_json)
    pod_items = _to_item_list(pods_json)
    event_items = _to_item_list(events_json)

    faults: list[WorkloadMisconfigFault] = []
    seen_fault_keys: set[str] = set()

    # Check Insufficient memory / cpu events
    insufficient_resource_deps: set[str] = set()
    for ev in event_items:
        msg = ev.get("message") or ""
        if "Insufficient memory" in msg or "Insufficient cpu" in msg:
            obj_name = (ev.get("involvedObject") or {}).get("name", "")
            for dep in dep_items:
                d_name = (dep.get("metadata") or {}).get("name", "")
                if d_name and obj_name.startswith(d_name):
                    insufficient_resource_deps.add(d_name)

    for dep in dep_items:
        dep_meta = dep.get("metadata") or {}
        dep_name = dep_meta.get("name", "")
        dep_ns = dep_meta.get("namespace") or namespace

        pod_spec = ((dep.get("spec") or {}).get("template") or {}).get("spec") or {}
        containers = pod_spec.get("containers") or []
        init_containers = pod_spec.get("initContainers") or []
        strategy = (dep.get("spec") or {}).get("strategy") or {}

        # 1. Resource Request Too Large check
        has_large_request = dep_name in insufficient_resource_deps
        target_cname = None
        target_cidx = 0
        for c_idx, c in enumerate(containers):
            if not isinstance(c, dict):
                continue
            c_name = c.get("name", "")
            requests = (c.get("resources") or {}).get("requests") or {}
            mem_req = requests.get("memory", "")
            cpu_req = requests.get("cpu", "")
            if (mem_req and _parse_memory_to_gb(mem_req) >= 32.0) or (cpu_req and _parse_cpu_cores(cpu_req) >= 32.0):
                has_large_request = True
                target_cname = c_name
                target_cidx = c_idx
            elif requests and not target_cname and has_large_request:
                target_cname = c_name
                target_cidx = c_idx

        if has_large_request:
            fault_key = f"{dep_name}:resource_request_too_large"
            if fault_key not in seen_fault_keys:
                seen_fault_keys.add(fault_key)
                faults.append(
                    WorkloadMisconfigFault(
                        deployment_name=dep_name,
                        namespace=dep_ns,
                        fault_kind="resource_request_too_large",
                        details=f"Unfulfillable memory/CPU requests detected on deployment {dep_name}",
                        container_name=target_cname,
                        container_index=target_cidx,
                    )
                )

        # 2. Rolling Update Misconfigured check
        rolling_update = strategy.get("rollingUpdate") or {}
        max_unavailable = str(rolling_update.get("maxUnavailable", ""))
        max_surge = str(rolling_update.get("maxSurge", ""))

        is_zero_surge = max_surge in ("0", "0%")
        is_full_unavailable = max_unavailable in ("100%", "100", "1")

        has_hanging_init = False
        for ic in init_containers:
            if not isinstance(ic, dict):
                continue
            ic_name = ic.get("name", "")
            ic_cmd = " ".join((ic.get("command") or []) + (ic.get("args") or []))
            if ic_name == "hang-init" or "sleep infinity" in ic_cmd or "sleep 9999" in ic_cmd:
                has_hanging_init = True

        if (is_zero_surge and is_full_unavailable) or has_hanging_init:
            fault_key = f"{dep_name}:rolling_update_misconfigured"
            if fault_key not in seen_fault_keys:
                seen_fault_keys.add(fault_key)
                faults.append(
                    WorkloadMisconfigFault(
                        deployment_name=dep_name,
                        namespace=dep_ns,
                        fault_kind="rolling_update_misconfigured",
                        details=(
                            f"Rolling update strategy misconfiguration (maxUnavailable={max_unavailable}, "
                            f"maxSurge={max_surge}, hanging_init={has_hanging_init}) on {dep_name}"
                        ),
                    )
                )

    return faults


def _parse_memory_to_gb(mem_str: str) -> float:
    s = mem_str.strip()
    if s.endswith("Gi"):
        try:
            return float(s[:-2])
        except ValueError:
            return 0.0
    elif s.endswith("Mi"):
        try:
            return float(s[:-2]) / 1024.0
        except ValueError:
            return 0.0
    try:
        return float(s) / (1024.0 * 1024.0 * 1024.0)
    except ValueError:
        return 0.0


def _parse_cpu_cores(cpu_str: str) -> float:
    s = cpu_str.strip()
    if s.endswith("m"):
        try:
            return float(s[:-1]) / 1000.0
        except ValueError:
            return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


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

