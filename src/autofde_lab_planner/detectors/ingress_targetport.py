"""Detector for Ingress Path Misroutes and Service targetPort Mismatches."""

from __future__ import annotations

from typing import Any
from autofde_lab_planner.models import IngressMisrouteFault, TargetPortFault

# Known baseline target ports for application microservices across benchmarks
KNOWN_SERVICE_TARGET_PORTS: dict[str, int | str] = {
    "user-service": 9090,
    "frontend-service": 5000,
    "recommendation-service": 8085,
    "geo": 8083,
    "rate": 8084,
    "profile": 8081,
    "search": 8082,
    "reservation": 8087,
    "user": 8086,
    "auth": 8089,
    "frontend": 5000,
    "recommendation": 8085,
}

# Known baseline ingress routing paths mapping (path_prefix -> expected_service)
KNOWN_INGRESS_PATH_MAP: dict[str, str] = {
    "/api": "frontend-service",
}


def detect_ingress_and_targetport_faults(
    ingresses_json: dict[str, Any] | list[dict[str, Any]] | None = None,
    services_json: dict[str, Any] | list[dict[str, Any]] | None = None,
    deployments_json: dict[str, Any] | list[dict[str, Any]] | None = None,
    namespace: str = "default",
) -> tuple[list[IngressMisrouteFault], list[TargetPortFault]]:
    """Detects Ingress path backend misroutes and Service targetPort misconfigurations."""
    ingress_items = _to_item_list(ingresses_json)
    service_items = _to_item_list(services_json)
    deployment_items = _to_item_list(deployments_json)

    ingress_faults: list[IngressMisrouteFault] = []
    target_port_faults: list[TargetPortFault] = []

    # 1. Ingress Path Misroute Detection
    for ing in ingress_items:
        ing_meta = ing.get("metadata") or {}
        ing_name = ing_meta.get("name", "")
        ing_ns = ing_meta.get("namespace") or namespace
        rules = (ing.get("spec") or {}).get("rules") or []

        for rule_idx, rule in enumerate(rules):
            if not isinstance(rule, dict):
                continue
            http_paths = (rule.get("http") or {}).get("paths") or []
            for path_idx, path_entry in enumerate(http_paths):
                if not isinstance(path_entry, dict):
                    continue
                path = path_entry.get("path", "")
                backend_svc = (
                    (path_entry.get("backend") or {})
                    .get("service") or {}
                ).get("name", "")

                # Check if path starts with a known route (e.g. /api)
                for known_path, expected_svc in KNOWN_INGRESS_PATH_MAP.items():
                    if path.startswith(known_path) and backend_svc and backend_svc != expected_svc:
                        ingress_faults.append(
                            IngressMisrouteFault(
                                ingress_name=ing_name,
                                namespace=ing_ns,
                                path=path,
                                observed_backend_service=backend_svc,
                                expected_backend_service=expected_svc,
                                rule_index=rule_idx,
                                path_index=path_idx,
                            )
                        )

    # Map deployments by name for containerPort lookup
    dep_ports_by_name: dict[str, set[int | str]] = {}
    for dep in deployment_items:
        d_name = (dep.get("metadata") or {}).get("name", "")
        containers = (((dep.get("spec") or {}).get("template") or {}).get("spec") or {}).get("containers") or []
        ports = set()
        for c in containers:
            if not isinstance(c, dict):
                continue
            for p in (c.get("ports") or []):
                if not isinstance(p, dict):
                    continue
                cp = p.get("containerPort")
                if cp is not None:
                    ports.add(cp)
        if d_name and ports:
            dep_ports_by_name[d_name] = ports

    # 2. Service targetPort Misconfig Detection
    for svc in service_items:
        svc_meta = svc.get("metadata") or {}
        svc_name = svc_meta.get("name", "")
        svc_ns = svc_meta.get("namespace") or namespace
        ports = (svc.get("spec") or {}).get("ports") or []

        for port_idx, port_spec in enumerate(ports):
            if not isinstance(port_spec, dict):
                continue
            p_name = (port_spec.get("name") or "").lower()
            if p_name in ("metrics", "telemetry", "prometheus", "health", "healthz", "admin"):
                continue
            target_port = port_spec.get("targetPort")
            if target_port is None:
                continue

            expected_tp: int | str | None = None
            if svc_name in KNOWN_SERVICE_TARGET_PORTS:
                expected_tp = KNOWN_SERVICE_TARGET_PORTS[svc_name]
            elif svc_name in dep_ports_by_name:
                dep_ports = dep_ports_by_name[svc_name]
                if target_port not in dep_ports and dep_ports:
                    expected_tp = sorted(dep_ports)[0]

            if expected_tp is not None and str(target_port) != str(expected_tp):
                target_port_faults.append(
                    TargetPortFault(
                        service_name=svc_name,
                        namespace=svc_ns,
                        observed_target_port=target_port,
                        expected_target_port=expected_tp,
                        port_index=port_idx,
                    )
                )

    return ingress_faults, target_port_faults


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

