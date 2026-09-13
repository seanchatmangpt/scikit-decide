"""Category-B4 Detector: Probe Heuristics & Liveness/Readiness Faults."""

from __future__ import annotations

from typing import Any
from autofde_lab_planner.models import ProbeFault


def _to_item_list(data: Any) -> list[dict[str, Any]]:
    if not data:
        return []
    if isinstance(data, dict):
        raw_items = data.get("items")
        if raw_items is None:
            return [data]
        if isinstance(raw_items, list):
            return [i for i in raw_items if isinstance(i, dict)]
        return []
    if isinstance(data, list):
        return [i for i in data if isinstance(i, dict)]
    return []


def parse_container_probes(deployment_item: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Extracts container probes and ports from a Deployment dict."""
    containers_info: dict[str, dict[str, Any]] = {}
    if not isinstance(deployment_item, dict):
        return containers_info

    spec = deployment_item.get("spec") or {}
    template = spec.get("template") or {}
    template_spec = template.get("spec") or {}
    containers = template_spec.get("containers") or []

    for c_idx, c in enumerate(containers):
        if not isinstance(c, dict):
            continue
        c_name = c.get("name", "")
        raw_ports = c.get("ports") or []
        ports = [
            p.get("containerPort")
            for p in raw_ports
            if isinstance(p, dict) and "containerPort" in p
        ]
        containers_info[c_name] = {
            "livenessProbe": c.get("livenessProbe") if isinstance(c.get("livenessProbe"), dict) else None,
            "readinessProbe": c.get("readinessProbe") if isinstance(c.get("readinessProbe"), dict) else None,
            "ports": ports,
            "index": c_idx,
        }
    return containers_info


def detect_probe_faults(
    deployments_json: dict[str, Any] | list[dict[str, Any]] | None = None,
    pods_json: dict[str, Any] | list[dict[str, Any]] | None = None,
    events_json: dict[str, Any] | list[dict[str, Any]] | None = None,
) -> list[ProbeFault]:
    """Detects readiness or liveness probe misconfigurations and aggressive timing faults.

    Operates over raw K8s API JSON structures (Deployments, Pods, Events).
    """
    items = _to_item_list(deployments_json)
    pod_items = _to_item_list(pods_json)

    # Map deployment_name -> pod statuses (ready count, max restarts)
    pod_metrics: dict[str, dict[str, Any]] = {}
    for p in pod_items:
        meta = p.get("metadata") or {}
        labels = meta.get("labels") or {}
        p_name = meta.get("name") or ""
        app_name = labels.get("app") or (p_name.split("-")[0] if p_name else "")
        status = p.get("status") or {}
        c_statuses = status.get("containerStatuses") or []
        restarts = sum(
            (cs.get("restartCount", 0) if isinstance(cs, dict) else 0)
            for cs in c_statuses
        )
        ready = (
            all((cs.get("ready", False) if isinstance(cs, dict) else False) for cs in c_statuses)
            if c_statuses
            else False
        )
        if app_name:
            if app_name not in pod_metrics:
                pod_metrics[app_name] = {"restarts": 0, "unready_count": 0}
            pod_metrics[app_name]["restarts"] += restarts
            if not ready:
                pod_metrics[app_name]["unready_count"] += 1

    faults: list[ProbeFault] = []

    for dep in items:
        metadata = dep.get("metadata") or {}
        dep_name = metadata.get("name", "")
        if not dep_name:
            continue

        spec = dep.get("spec") or {}
        desired_replicas = spec.get("replicas", 1)
        status = dep.get("status") or {}
        ready_replicas = status.get("readyReplicas", 0)

        c_probes = parse_container_probes(dep)

        for c_name, p_info in c_probes.items():
            ports = p_info.get("ports", [])
            c_idx = p_info.get("index", 0)
            for probe_type in ("readinessProbe", "livenessProbe"):
                probe = p_info.get(probe_type)
                if not probe or not isinstance(probe, dict):
                    continue

                http_get = probe.get("httpGet") if isinstance(probe.get("httpGet"), dict) else None
                tcp_socket = probe.get("tcpSocket") if isinstance(probe.get("tcpSocket"), dict) else None
                initial_delay = probe.get("initialDelaySeconds")
                period_seconds = probe.get("periodSeconds")
                failure_threshold = probe.get("failureThreshold")

                # Check 1: Aggressive Timing
                # (initialDelaySeconds <= 2 or 0, periodSeconds <= 2, failureThreshold <= 1)
                is_aggressive = (
                    initial_delay is not None
                    and initial_delay <= 2
                    and period_seconds is not None
                    and period_seconds <= 2
                    and failure_threshold is not None
                    and failure_threshold <= 1
                )

                # Check 2: Invalid Endpoint / Port divergence
                is_invalid_endpoint = False
                observed_path = None
                observed_port = None

                if http_get:
                    observed_path = http_get.get("path")
                    observed_port = http_get.get("port")
                elif tcp_socket:
                    observed_port = tcp_socket.get("port")

                # Flag endpoint mismatch if probe path is /healthz and port is 8080,
                # or if specified probe port does not match container exposed ports
                if observed_path == "/healthz" and observed_port == 8080 and 8080 not in ports:
                    is_invalid_endpoint = True
                elif observed_port is not None and isinstance(observed_port, int) and ports and observed_port not in ports:
                    is_invalid_endpoint = True

                # Determine if pod metrics indicate fault (unready replicas or restarts)
                app_pm = pod_metrics.get(dep_name, {})
                has_health_issue = (
                    ready_replicas < desired_replicas
                    or app_pm.get("unready_count", 0) > 0
                    or app_pm.get("restarts", 0) > 0
                )

                if is_invalid_endpoint:
                    faults.append(
                        ProbeFault(
                            deployment_name=dep_name,
                            container_name=c_name,
                            probe_type=probe_type,
                            fault_kind="invalid_endpoint",
                            observed_path=observed_path,
                            observed_port=observed_port,
                            initial_delay=initial_delay,
                            period_seconds=period_seconds,
                            failure_threshold=failure_threshold,
                            ready_replicas=ready_replicas,
                            desired_replicas=desired_replicas,
                            restart_count=app_pm.get("restarts", 0),
                            container_index=c_idx,
                        )
                    )
                elif is_aggressive and (has_health_issue or initial_delay == 0):
                    faults.append(
                        ProbeFault(
                            deployment_name=dep_name,
                            container_name=c_name,
                            probe_type=probe_type,
                            fault_kind="aggressive_timing",
                            observed_path=observed_path,
                            observed_port=observed_port,
                            initial_delay=initial_delay,
                            period_seconds=period_seconds,
                            failure_threshold=failure_threshold,
                            ready_replicas=ready_replicas,
                            desired_replicas=desired_replicas,
                            restart_count=app_pm.get("restarts", 0),
                            container_index=c_idx,
                        )
                    )

    return faults

