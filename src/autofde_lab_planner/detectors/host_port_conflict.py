"""Detector for container hostPort binding conflict faults.

Source mechanism (fault-injector evidence):
sregym/generators/fault/inject_virtual.py,
VirtualizationFaultInjector.inject_service_port_conflict() (around line 2667):

    ports_list = main_container.get("ports", [])
    if ports_list:
        ports_list[0]["hostPort"] = conflicting_port
    else:
        main_container["ports"] = [{"containerPort": 8080, "hostPort": conflicting_port}]
    ...
    delete_cmd = f"kubectl delete deployment {service} -n {self.namespace}"
    apply_cmd = f"kubectl apply -f {modified_yaml_path} -n {self.namespace}"

This adds a ``hostPort`` binding to a container port on a Deployment's Pod
template, then deletes and reapplies the Deployment (a raw patch cannot
change ``hostPort`` on running Pods). Kubernetes schedules at most one Pod
carrying a given ``hostPort`` per Node, so on any Node already running a
Pod that binds that host port -- either from the same Deployment scaled to
>1 replica, or from an unrelated workload -- the new Pod is refused
placement (``Ports are not available``) and the Deployment cannot reach its
desired replica count, all while the Service/Endpoints/Ingress objects that
front it remain untouched and appear healthy.

This is a distinct mechanism from ``ingress_targetport`` (which checks
Service ``spec.ports[].targetPort`` against the container's actual
``containerPort``, a Service-level routing fault) and from
``scheduling_deadlock`` (anti-affinity/taint-driven unschedulability): here
the container port list itself carries a ``hostPort`` binding that was never
part of the deployment's declared baseline. No existing detector inspects
container-level ``ports[].hostPort`` (confirmed via ``grep -rn "hostPort"
src/autofde_lab_planner/detectors/*.py`` -> zero matches before this file).
"""

from __future__ import annotations

from typing import Any

from autofde_lab_planner.models import HostPortConflictFault


def detect_host_port_conflicts(
    deployments_json: dict[str, Any] | list[dict[str, Any]] | None = None,
    namespace: str = "default",
) -> list[HostPortConflictFault]:
    """Detects containers in a Deployment's Pod template that declare a
    ``hostPort`` binding on any of their ports.

    A legitimate ``hostPort`` is rare in application microservice manifests
    (it is normally reserved for DaemonSets/node-agents), so any presence on
    a Deployment's application container is treated as fault evidence -- the
    injector's own mechanism is exactly this: adding a ``hostPort`` key that
    was not part of the Deployment's original manifest.
    """
    dep_items = _to_item_list(deployments_json)
    faults: list[HostPortConflictFault] = []

    for dep in dep_items:
        dep_meta = dep.get("metadata") or {}
        dep_name = dep_meta.get("name", "")
        dep_ns = dep_meta.get("namespace") or namespace
        if not dep_name:
            continue

        pod_spec = ((dep.get("spec") or {}).get("template") or {}).get("spec") or {}
        containers = pod_spec.get("containers") or []

        for idx, container in enumerate(containers):
            if not isinstance(container, dict):
                continue
            container_name = container.get("name", f"container-{idx}")
            ports = container.get("ports") or []

            for port_idx, port in enumerate(ports):
                if not isinstance(port, dict):
                    continue
                host_port = port.get("hostPort")
                if host_port is None:
                    continue

                container_port = port.get("containerPort", host_port)
                faults.append(
                    HostPortConflictFault(
                        deployment_name=dep_name,
                        namespace=dep_ns,
                        container_name=container_name,
                        container_port=int(container_port),
                        conflicting_host_port=int(host_port),
                        container_index=idx,
                        port_index=port_idx,
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
