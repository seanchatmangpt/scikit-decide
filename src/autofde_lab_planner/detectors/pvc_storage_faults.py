"""Detector for PVC/storage-related fault mechanisms (Storage-1/Storage-2).

Ground truth for both mechanisms: `vendor/gyms/sregym/sregym/generators/fault/inject_virtual.py`
(SREGym `VirtualizationFaultInjector`):

- ``inject_pvc_claim_mismatch`` (line 170): patches a Deployment's
  ``volumes[].persistentVolumeClaim.claimName`` to a non-existent name
  (suffixed ``-broken``), so pods go Pending referencing a PVC that does not
  exist.
- ``inject_duplicate_pvc_mounts`` (line 1691): creates a single
  ReadWriteOnce PVC, mounts it into a Deployment with >=2 replicas plus a
  ``podAntiAffinity`` rule spreading pods across nodes, producing
  Multi-Attach / FailedAttachVolume errors because RWO volumes can only be
  attached to one node at a time.

Distinct from `object_reconstruction.py` (which handles wholly *missing*
Service/ConfigMap/Secret objects and corrupted selectors/keys): these two
detectors are storage-specific — dangling PVC claim references and
multi-attach access-mode conflicts, not missing objects.
"""

from __future__ import annotations

from typing import Any

from autofde_lab_planner.models import PVCClaimMismatchFault, PVCMultiAttachFault


def detect_pvc_claim_mismatches(
    deployments_json: dict[str, Any] | list[dict[str, Any]] | None = None,
    pvcs_json: dict[str, Any] | list[dict[str, Any]] | None = None,
    pods_json: dict[str, Any] | list[dict[str, Any]] | None = None,
    namespace: str = "default",
) -> list[PVCClaimMismatchFault]:
    """Detects Deployment volumes whose ``persistentVolumeClaim.claimName``
    does not match any PVC object present in the namespace."""
    dep_items = _to_item_list(deployments_json)
    pvc_items = _to_item_list(pvcs_json)
    pod_items = _to_item_list(pods_json)

    known_pvc_names: set[str] = set()
    for pvc in pvc_items:
        name = (pvc.get("metadata") or {}).get("name", "")
        if name:
            known_pvc_names.add(name)

    unready_by_dep: dict[str, int] = {}
    for pod in pod_items:
        labels = (pod.get("metadata") or {}).get("labels") or {}
        dep_name = labels.get("app") or labels.get("io.kompose.service") or ""
        phase = (pod.get("status") or {}).get("phase", "")
        if dep_name and phase in ("Pending", "Unknown"):
            unready_by_dep[dep_name] = unready_by_dep.get(dep_name, 0) + 1

    faults: list[PVCClaimMismatchFault] = []

    for dep in dep_items:
        dep_meta = dep.get("metadata") or {}
        dep_name = dep_meta.get("name", "")
        dep_ns = dep_meta.get("namespace") or namespace

        spec = dep.get("spec") or {}
        pod_spec = ((spec.get("template") or {}).get("spec")) or {}
        volumes = pod_spec.get("volumes") or []
        containers = pod_spec.get("containers") or []
        container_name = containers[0].get("name") if containers else None

        desired_replicas = spec.get("replicas", 1)
        ready_replicas = (dep.get("status") or {}).get("readyReplicas", 0)

        for vol in volumes:
            pvc_ref = vol.get("persistentVolumeClaim") or {}
            claim_name = pvc_ref.get("claimName")
            if not claim_name:
                continue
            if claim_name in known_pvc_names:
                continue

            # A dangling claimName: attempt to infer the pre-fault expected
            # name for the SREGym "-broken" suffix convention.
            expected = claim_name[: -len("-broken")] if claim_name.endswith("-broken") else None

            faults.append(
                PVCClaimMismatchFault(
                    deployment_name=dep_name,
                    namespace=dep_ns,
                    volume_name=vol.get("name", ""),
                    observed_claim_name=claim_name,
                    expected_claim_name=expected,
                    container_name=container_name,
                    unready_replicas=max(desired_replicas - ready_replicas, unready_by_dep.get(dep_name, 0)),
                    desired_replicas=desired_replicas,
                )
            )

    return faults


def detect_pvc_multi_attach_faults(
    deployments_json: dict[str, Any] | list[dict[str, Any]] | None = None,
    pvcs_json: dict[str, Any] | list[dict[str, Any]] | None = None,
    events_json: dict[str, Any] | list[dict[str, Any]] | None = None,
    namespace: str = "default",
) -> list[PVCMultiAttachFault]:
    """Detects a ReadWriteOnce PVC shared by a Deployment with >1 desired
    replicas -- a structural Multi-Attach conflict, strengthened by any
    observed FailedAttachVolume/Multi-Attach events."""
    dep_items = _to_item_list(deployments_json)
    pvc_items = _to_item_list(pvcs_json)
    event_items = _to_item_list(events_json)

    access_modes_by_pvc: dict[str, tuple[str, ...]] = {}
    for pvc in pvc_items:
        name = (pvc.get("metadata") or {}).get("name", "")
        modes = tuple((pvc.get("spec") or {}).get("accessModes") or ())
        if name:
            access_modes_by_pvc[name] = modes

    events_by_pvc: dict[str, list[str]] = {}
    for ev in event_items:
        reason = ev.get("reason", "")
        msg = ev.get("message") or ""
        if reason in ("FailedAttachVolume", "FailedMount") or "Multi-Attach error" in msg:
            obj_name = (ev.get("involvedObject") or {}).get("name", "")
            events_by_pvc.setdefault(obj_name, []).append(msg or reason)

    faults: list[PVCMultiAttachFault] = []

    for dep in dep_items:
        dep_meta = dep.get("metadata") or {}
        dep_name = dep_meta.get("name", "")
        dep_ns = dep_meta.get("namespace") or namespace

        spec = dep.get("spec") or {}
        desired_replicas = spec.get("replicas", 1)
        pod_spec = ((spec.get("template") or {}).get("spec")) or {}
        volumes = pod_spec.get("volumes") or []
        affinity = pod_spec.get("affinity") or {}
        has_anti_affinity = bool(affinity.get("podAntiAffinity"))

        for vol in volumes:
            pvc_ref = vol.get("persistentVolumeClaim") or {}
            claim_name = pvc_ref.get("claimName")
            if not claim_name:
                continue

            modes = access_modes_by_pvc.get(claim_name)
            if modes is None:
                # PVC not observed in the live list (handled separately by
                # detect_pvc_claim_mismatches); nothing to reason about here.
                continue

            is_rwo_only = modes == ("ReadWriteOnce",)
            related_events = tuple(events_by_pvc.get(claim_name, ()))

            if desired_replicas > 1 and is_rwo_only:
                faults.append(
                    PVCMultiAttachFault(
                        deployment_name=dep_name,
                        namespace=dep_ns,
                        pvc_name=claim_name,
                        access_modes=modes,
                        desired_replicas=desired_replicas,
                        has_anti_affinity=has_anti_affinity,
                        multi_attach_events=related_events,
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
