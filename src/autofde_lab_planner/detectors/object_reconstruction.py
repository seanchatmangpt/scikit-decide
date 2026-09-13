"""Category-B13 Detector: Missing/Corrupted Object Reconstruction."""

from __future__ import annotations

from typing import Any
from autofde_lab_planner.models import MissingObjectFault

# Services that are expected to exist per deployment (1:1 name-matched) across known apps.
# When this is None (default), the detector uses revision evidence to narrow the search;
# when provided explicitly (e.g. from a known-service-topology), it's used directly.
_APPS_WITH_SERVICE_PER_DEPLOYMENT: frozenset[str] = frozenset({
    "hotel-reservation",
    "social-network",
})


def detect_missing_objects(
    deployments_json: dict[str, Any] | list[dict[str, Any]],
    live_services_json: dict[str, Any] | list[dict[str, Any]] | None = None,
    live_configmaps_json: dict[str, Any] | list[dict[str, Any]] | None = None,
    live_secrets_json: dict[str, Any] | list[dict[str, Any]] | None = None,
    pods_json: dict[str, Any] | list[dict[str, Any]] | None = None,
    namespace: str = "default",
    elevated_revision_deployments: set[str] | None = None,
) -> list[MissingObjectFault]:
    """Scans Kubernetes state for missing or corrupted core objects (Service, ConfigMap, Secret).

    `elevated_revision_deployments`: optional set of deployment names with observed elevated
    `deployment.kubernetes.io/revision` annotation (real, standard Kubernetes evidence of a
    recent rollout). When provided, the missing-Service check is NARROWED to only these
    deployments -- preventing false positives in apps (like hotel-reservation, social-network)
    where many deployments legitimately do not have a 1:1 Service object named after them,
    but the elevated-revision signal identifies which deployment was recently mutated.
    """
    # Import baselines inside function to avoid circular imports
    try:
        from autofde_lab_planner.baselines.k8s_baselines import KNOWN_CONFIGMAP_BASELINES
    except ImportError:
        KNOWN_CONFIGMAP_BASELINES = {}  # type: ignore[assignment]
    dep_items = _to_item_list(deployments_json)
    svc_items = _to_item_list(live_services_json)
    cm_items = _to_item_list(live_configmaps_json)
    secret_items = _to_item_list(live_secrets_json)
    pod_items = _to_item_list(pods_json)

    live_svc_names: dict[str, dict[str, Any]] = {
        (s.get("metadata") or {}).get("name"): s
        for s in svc_items
        if (s.get("metadata") or {}).get("name")
    }
    live_cm_names: set[str] = {
        (c.get("metadata") or {}).get("name")
        for c in cm_items
        if (c.get("metadata") or {}).get("name")
    }
    live_secret_names: set[str] = {
        (sec.get("metadata") or {}).get("name")
        for sec in secret_items
        if (sec.get("metadata") or {}).get("name")
    }

    faults: list[MissingObjectFault] = []
    seen_fault_keys: set[str] = set()

    # Build full live CM dicts for key-level validation (Rule 1b)
    live_cm_by_name: dict[str, dict[str, Any]] = {
        (c.get("metadata") or {}).get("name"): c
        for c in cm_items
        if (c.get("metadata") or {}).get("name")
    }

    for dep in dep_items:
        dep_meta = dep.get("metadata") or {}
        dep_name = dep_meta.get("name", "")
        dep_ns = dep_meta.get("namespace") or namespace
        if not dep_name:
            continue

        # Rule 1: Check for corresponding Service -- ONLY for deployments where real anomaly
        # evidence (elevated revision) suggests something recently changed, to avoid flooding
        # the diagnosis with false positives for apps (hotel-reservation, social-network) where
        # many deployments legitimately do not have a 1:1 Service.
        should_check_service = (
            elevated_revision_deployments is None  # no hint => check all (legacy behaviour)
            or dep_name in elevated_revision_deployments  # real anomaly evidence
        )
        if should_check_service:
            if dep_name not in live_svc_names:
                fault_key = f"Service:{dep_name}"
                if fault_key not in seen_fault_keys:
                    seen_fault_keys.add(fault_key)
                    faults.append(
                        MissingObjectFault(
                            kind="Service",
                            object_name=dep_name,
                            namespace=dep_ns,
                            associated_deployment=dep_name,
                            reason="missing_service_for_deployment",
                        )
                    )
            else:
                svc_item = live_svc_names[dep_name]
                selector = (svc_item.get("spec") or {}).get("selector") or {}
                if not selector or selector.get("app") != dep_name:
                    fault_key = f"Service:{dep_name}:selector"
                    if fault_key not in seen_fault_keys:
                        seen_fault_keys.add(fault_key)
                        faults.append(
                            MissingObjectFault(
                                kind="Service",
                                object_name=dep_name,
                                namespace=dep_ns,
                                associated_deployment=dep_name,
                                reason="corrupted_service_selector",
                            )
                        )

        # Rule 2 & 3: Check referenced ConfigMaps and Secrets in Pod spec template
        dep_spec = dep.get("spec") or {}
        pod_template_spec = (dep_spec.get("template") or {}).get("spec") or {}
        containers = pod_template_spec.get("containers") or []
        volumes = pod_template_spec.get("volumes") or []

        for v in volumes:
            if not isinstance(v, dict):
                continue
            cm_ref = (v.get("configMap") or {}).get("name")
            if cm_ref and cm_ref not in live_cm_names:
                fault_key = f"ConfigMap:{cm_ref}"
                if fault_key not in seen_fault_keys:
                    seen_fault_keys.add(fault_key)
                    faults.append(
                        MissingObjectFault(
                            kind="ConfigMap",
                            object_name=cm_ref,
                            namespace=dep_ns,
                            associated_deployment=dep_name,
                            reason="missing_referenced_configmap",
                        )
                    )
            sec_ref = (v.get("secret") or {}).get("secretName")
            if sec_ref and sec_ref not in live_secret_names:
                fault_key = f"Secret:{sec_ref}"
                if fault_key not in seen_fault_keys:
                    seen_fault_keys.add(fault_key)
                    faults.append(
                        MissingObjectFault(
                            kind="Secret",
                            object_name=sec_ref,
                            namespace=dep_ns,
                            associated_deployment=dep_name,
                            reason="missing_referenced_secret",
                        )
                    )

        for c in containers:
            if not isinstance(c, dict):
                continue
            env = c.get("env") or []
            for e in env:
                if not isinstance(e, dict):
                    continue
                val_from = e.get("valueFrom") or {}
                cm_key_ref = (val_from.get("configMapKeyRef") or {}).get("name")
                if cm_key_ref and cm_key_ref not in live_cm_names:
                    fault_key = f"ConfigMap:{cm_key_ref}"
                    if fault_key not in seen_fault_keys:
                        seen_fault_keys.add(fault_key)
                        faults.append(
                            MissingObjectFault(
                                kind="ConfigMap",
                                object_name=cm_key_ref,
                                namespace=dep_ns,
                                associated_deployment=dep_name,
                                reason="missing_referenced_configmap",
                            )
                        )
                sec_key_ref = (val_from.get("secretKeyRef") or {}).get("name")
                if sec_key_ref and sec_key_ref not in live_secret_names:
                    fault_key = f"Secret:{sec_key_ref}"
                    if fault_key not in seen_fault_keys:
                        seen_fault_keys.add(fault_key)
                        faults.append(
                            MissingObjectFault(
                                kind="Secret",
                                object_name=sec_key_ref,
                                namespace=dep_ns,
                                associated_deployment=dep_name,
                                reason="missing_referenced_secret",
                            )
                        )

    # Rule 4: Check Pod container statuses for CreateContainerConfigError
    for pod in pod_items:
        pod_meta = pod.get("metadata") or {}
        pod_ns = pod_meta.get("namespace") or namespace
        c_statuses = (pod.get("status") or {}).get("containerStatuses") or []
        for cs in c_statuses:
            if not isinstance(cs, dict):
                continue
            waiting = (cs.get("state") or {}).get("waiting") or {}
            reason = waiting.get("reason", "")
            msg = waiting.get("message") or ""
            if reason == "CreateContainerConfigError":
                # Try to extract object name from message
                # e.g. configmap "media-mongodb" not found or secret "foo" not found
                if 'configmap "' in msg.lower():
                    cm_name = msg.split('configmap "')[1].split('"')[0]
                    fault_key = f"ConfigMap:{cm_name}"
                    if fault_key not in seen_fault_keys:
                        seen_fault_keys.add(fault_key)
                        faults.append(
                            MissingObjectFault(
                                kind="ConfigMap",
                                object_name=cm_name,
                                namespace=pod_ns,
                                reason="missing_referenced_configmap",
                            )
                        )
                elif 'secret "' in msg.lower():
                    sec_name = msg.split('secret "')[1].split('"')[0]
                    fault_key = f"Secret:{sec_name}"
                    if fault_key not in seen_fault_keys:
                        seen_fault_keys.add(fault_key)
                        faults.append(
                            MissingObjectFault(
                                kind="Secret",
                                object_name=sec_name,
                                namespace=pod_ns,
                                reason="missing_referenced_secret",
                            )
                        )

    # Rule 1b: Check live ConfigMaps against known baselines for missing required keys/JSON fields.
    try:
        from autofde_lab_planner.baselines.k8s_baselines import KNOWN_SECRET_BASELINES
    except ImportError:
        KNOWN_SECRET_BASELINES = {}  # type: ignore[assignment]

    import json

    live_secret_by_name: dict[str, dict[str, Any]] = {
        (sec.get("metadata") or {}).get("name"): sec
        for sec in secret_items
        if (sec.get("metadata") or {}).get("name")
    }

    # Map ConfigMaps/Secrets to candidate associated deployments
    dep_by_cm_mount: dict[str, str] = {}
    dep_by_secret_mount: dict[str, str] = {}
    for dep in dep_items:
        d_name = (dep.get("metadata") or {}).get("name", "")
        vols = (((dep.get("spec") or {}).get("template") or {}).get("spec") or {}).get("volumes") or []
        for v in vols:
            if not isinstance(v, dict):
                continue
            cm_r = (v.get("configMap") or {}).get("name")
            if cm_r:
                dep_by_cm_mount[cm_r] = d_name
            sec_r = (v.get("secret") or {}).get("secretName")
            if sec_r:
                dep_by_secret_mount[sec_r] = d_name

    for cm_name, baseline_data in KNOWN_CONFIGMAP_BASELINES.items():
        if cm_name not in live_cm_by_name:
            continue
        live_cm = live_cm_by_name[cm_name]
        live_data = live_cm.get("data", {}) or {}
        missing_keys: list[str] = []

        for b_key, b_val in baseline_data.items():
            if b_key == "demo.flagd.json":
                continue
            if b_key not in live_data:
                # Check if it's missing inside a JSON config (e.g. config.json)
                if "config.json" in live_data:
                    try:
                        live_json = json.loads(live_data["config.json"])
                        if isinstance(live_json, dict) and b_key not in live_json:
                            missing_keys.append(b_key)
                    except (json.JSONDecodeError, TypeError):
                        missing_keys.append(b_key)
                else:
                    missing_keys.append(b_key)

        if missing_keys:
            fault_key = f"ConfigMap:{cm_name}:keys"
            if fault_key not in seen_fault_keys:
                seen_fault_keys.add(fault_key)
                assoc_dep = dep_by_cm_mount.get(cm_name)
                if not assoc_dep and cm_name.endswith("-config"):
                    assoc_dep = cm_name[:-7]
                faults.append(
                    MissingObjectFault(
                        kind="ConfigMap",
                        object_name=cm_name,
                        namespace=namespace,
                        associated_deployment=assoc_dep,
                        reason="corrupted_configmap_keys",
                        missing_keys=tuple(missing_keys),
                    )
                )

    for secret_name, baseline_data in KNOWN_SECRET_BASELINES.items():
        if secret_name not in live_secret_by_name:
            continue
        live_sec = live_secret_by_name[secret_name]
        live_data = live_sec.get("data", {}) or {}
        live_string_data = live_sec.get("stringData", {}) or {}
        missing_keys = [
            k for k in baseline_data if k not in live_data and k not in live_string_data
        ]
        if missing_keys:
            fault_key = f"Secret:{secret_name}:keys"
            if fault_key not in seen_fault_keys:
                seen_fault_keys.add(fault_key)
                assoc_dep = dep_by_secret_mount.get(secret_name)
                faults.append(
                    MissingObjectFault(
                        kind="Secret",
                        object_name=secret_name,
                        namespace=namespace,
                        associated_deployment=assoc_dep,
                        reason="corrupted_secret_keys",
                        missing_keys=tuple(missing_keys),
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

