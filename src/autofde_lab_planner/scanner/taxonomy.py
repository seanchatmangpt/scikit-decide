"""Map a raw Anomaly to a real SREGym fault-injector method name, or UNCLASSIFIED.

The label set is not invented -- every value below is a real method name
grepped from
`vendor/gyms/sregym/sregym/generators/fault/inject_virtual.py`
(`grep -n "def inject_" ...`), the same ground-truth source the abandoned
14-function enumeration (src/autofde_lab_planner/{models,engine}.py,
commit 72c8dfa) was built against. Anomalies that don't match a known
signature return "UNCLASSIFIED" honestly rather than guessing, per
`.claude/rules/absence-is-not-evidence.md`.
"""

from __future__ import annotations

from autofde_lab_planner.scanner.models import Anomaly

UNCLASSIFIED = "UNCLASSIFIED"

# Real inject_* method names from vendor/gyms/sregym/sregym/generators/fault/inject_virtual.py
INJECT_SCALE_PODS_TO_ZERO = "inject_scale_pods_to_zero"
INJECT_PVC_CLAIM_MISMATCH = "inject_pvc_claim_mismatch"
INJECT_DUPLICATE_PVC_MOUNTS = "inject_duplicate_pvc_mounts"
INJECT_MISSING_CONFIGMAP = "inject_missing_configmap"
INJECT_CONFIGMAP_DRIFT = "inject_configmap_drift"
INJECT_MISSING_SERVICE = "inject_missing_service"
INJECT_WRONG_SERVICE_SELECTOR = "inject_wrong_service_selector"
INJECT_SERVICE_WRONG_POD_SELECTION = "inject_service_wrong_pod_selection"
INJECT_RBAC_MISCONFIGURATION = "inject_rbac_misconfiguration"
INJECT_ROLLING_UPDATE_MISCONFIGURED = "inject_rolling_update_misconfigured"
INJECT_MISCONFIG_K8S = "inject_misconfig_k8s"
INJECT_RESOURCE_REQUEST = "inject_resource_request"
INJECT_WRONG_DNS_POLICY = "inject_wrong_dns_policy"
INJECT_LIVENESS_PROBE_TOO_AGGRESSIVE = "inject_liveness_probe_too_aggressive"
INJECT_LIVENESS_PROBE_MISCONFIGURATION = "inject_liveness_probe_misconfiguration"
INJECT_SIDECAR_PORT_CONFLICT = "inject_sidecar_port_conflict"
INJECT_MISSING_SERVICE_INGRESS = "inject_missing_service"


def classify(anomaly: Anomaly) -> str:
    """Best-effort, evidence-bounded classification. Never guesses."""
    kind = anomaly.kind
    field = anomaly.field
    rel = anomaly.relation_class

    if kind == "Deployment" and field == "readyReplicas" and rel == "declared_vs_observed":
        return INJECT_SCALE_PODS_TO_ZERO
    if kind == "Deployment" and field == "image" and rel == "declared_vs_observed":
        return INJECT_MISCONFIG_K8S
    if kind == "PersistentVolumeClaim" and rel == "dangling_reference":
        return INJECT_PVC_CLAIM_MISMATCH
    if kind == "PersistentVolumeClaim" and rel == "aggregate_threshold":
        return INJECT_DUPLICATE_PVC_MOUNTS
    if kind == "ConfigMap" and rel == "dangling_reference" and field == "data":
        return INJECT_MISSING_CONFIGMAP
    if kind == "ConfigMap" and rel == "declared_vs_observed":
        return INJECT_CONFIGMAP_DRIFT
    if kind == "Service" and rel == "dangling_reference" and field == "spec.selector":
        return INJECT_WRONG_SERVICE_SELECTOR
    if kind == "Service" and rel == "declared_vs_observed":
        return INJECT_MISSING_SERVICE
    if kind == "ServiceAccount" and rel == "insufficient_capability":
        return INJECT_RBAC_MISCONFIGURATION
    if kind == "CronJob" and rel == "declared_vs_observed":
        return INJECT_ROLLING_UPDATE_MISCONFIGURED
    if kind == "ResourceQuota" and rel == "aggregate_threshold":
        return INJECT_RESOURCE_REQUEST
    if kind == "Pod" and field == "spec.dnsPolicy":
        return INJECT_WRONG_DNS_POLICY
    if kind == "Pod" and field == "probe.failureThreshold":
        return INJECT_LIVENESS_PROBE_TOO_AGGRESSIVE
    if kind == "Pod" and rel == "aggregate_threshold" and "hostPort" in field:
        return INJECT_SIDECAR_PORT_CONFLICT
    if kind == "Ingress" and rel == "dangling_reference":
        return INJECT_MISSING_SERVICE_INGRESS
    if kind == "Ingress" and rel == "declared_vs_observed":
        return INJECT_MISCONFIG_K8S

    return UNCLASSIFIED
