"""Domain models and data structures for Category-B fault mechanisms."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


# -----------------------------------------------------------------------------
# B4: Probe Fault Models
# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class ProbeFault:
    deployment_name: str
    container_name: str
    probe_type: Literal["readinessProbe", "livenessProbe"]
    fault_kind: Literal["invalid_endpoint", "aggressive_timing"]
    observed_path: str | None = None
    observed_port: int | str | None = None
    initial_delay: int | None = None
    period_seconds: int | None = None
    failure_threshold: int | None = None
    ready_replicas: int = 0
    desired_replicas: int = 1
    restart_count: int = 0
    event_messages: tuple[str, ...] = ()
    container_index: int = 0


# -----------------------------------------------------------------------------
# B6: OTel Trace Diffing Models
# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class ParsedSpan:
    span_id: str
    trace_id: str
    operation_name: str
    service_name: str
    duration_ms: float
    has_error: bool
    status_code: str | None = None
    parent_span_id: str | None = None
    tags: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TraceTree:
    trace_id: str
    spans_by_id: dict[str, ParsedSpan]
    children_by_parent: dict[str, list[str]]
    root_span_ids: list[str]


@dataclass(frozen=True)
class ServiceMetrics:
    service_name: str
    total_spans: int
    error_spans: int
    error_rate: float
    avg_duration_ms: float
    max_duration_ms: float
    downstream_call_count: int


@dataclass(frozen=True)
class TraceAnomalyResult:
    has_anomaly: bool
    root_cause_service: str | None = None
    affected_services: tuple[str, ...] = ()
    anomalous_traces_count: int = 0
    metrics_by_service: dict[str, ServiceMetrics] = field(default_factory=dict)
    reasoning: str = ""


# -----------------------------------------------------------------------------
# B9: flagd Config Drift Models
# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class FlagDriftItem:
    flag_name: str
    current_variant: str
    canonical_variant: str = "off"
    target_deployments: tuple[str, ...] = ()


@dataclass(frozen=True)
class FlagdDriftResult:
    has_drift: bool
    configmap_name: str = "flagd-config"
    namespace: str = "astronomy-shop"
    drifted_flags: tuple[FlagDriftItem, ...] = ()
    repaired_flagd_json: str | None = None


# -----------------------------------------------------------------------------
# B13: Object Reconstruction Models
# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class MissingObjectFault:
    kind: Literal["Service", "ConfigMap", "Secret", "PVC"]
    object_name: str
    namespace: str
    associated_deployment: str | None = None
    reason: Literal[
        "missing_service_for_deployment",
        "missing_referenced_configmap",
        "missing_referenced_secret",
        "corrupted_service_selector",
        "corrupted_configmap_keys",
        "corrupted_secret_keys",
    ] = "missing_service_for_deployment"
    missing_keys: tuple[str, ...] = ()


# -----------------------------------------------------------------------------
# Ingress & TargetPort Misconfig Models
# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class IngressMisrouteFault:
    ingress_name: str
    namespace: str
    path: str
    observed_backend_service: str
    expected_backend_service: str
    rule_index: int = 0
    path_index: int = 0


@dataclass(frozen=True)
class TargetPortFault:
    service_name: str
    namespace: str
    observed_target_port: int | str
    expected_target_port: int | str
    port_index: int = 0


# -----------------------------------------------------------------------------
# CronJob / Scheduled Mutation Models
# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class CronJobMutationFault:
    cronjob_name: str
    cronjob_namespace: str
    victim_deployment: str
    victim_namespace: str
    injected_memory_limit: str = "4Mi"
    container_name: str | None = None
    container_index: int = 0


# -----------------------------------------------------------------------------
# B1: Scheduling & Anti-Affinity Deadlock Models
# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class SchedulingDeadlockFault:
    deployment_name: str
    namespace: str
    constraint_type: Literal["podAntiAffinity", "nodeSelector", "both"]
    unready_replicas: int = 0
    desired_replicas: int = 1


# -----------------------------------------------------------------------------
# CoreDNS & Service Discovery Fault Models
# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class CoreDNSFault:
    configmap_name: str = "coredns"
    namespace: str = "kube-system"
    fault_kind: Literal["nxdomain_template", "invalid_rewrite"] = "nxdomain_template"
    repaired_corefile: str | None = None


# -----------------------------------------------------------------------------
# Workload & Rolling Update Misconfig Models
# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class WorkloadMisconfigFault:
    deployment_name: str
    namespace: str
    fault_kind: Literal["resource_request_too_large", "rolling_update_misconfigured"]
    details: str = ""
    container_name: str | None = None
    container_index: int = 0


# -----------------------------------------------------------------------------
# Network/DNS Faults: DNS Policy Override & hostPort Conflict
# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class DnsPolicyOverrideFault:
    deployment_name: str
    namespace: str
    observed_dns_policy: str
    observed_nameservers: tuple[str, ...] = ()
    fault_kind: Literal["dns_policy_override"] = "dns_policy_override"


@dataclass(frozen=True)
class HostPortConflictFault:
    deployment_name: str
    namespace: str
    container_name: str
    container_port: int
    conflicting_host_port: int
    container_index: int = 0
    port_index: int = 0
    fault_kind: Literal["host_port_conflict"] = "host_port_conflict"


# -----------------------------------------------------------------------------
# Storage / PVC Fault Models
# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class PVCClaimMismatchFault:
    """A Deployment volume references a PersistentVolumeClaim name that has no
    matching PVC object in the namespace (SREGym `inject_pvc_claim_mismatch`:
    the claimName is suffixed with "-broken"), leaving pods stuck Pending."""

    deployment_name: str
    namespace: str
    volume_name: str
    observed_claim_name: str
    expected_claim_name: str | None = None
    container_name: str | None = None
    unready_replicas: int = 0
    desired_replicas: int = 1


@dataclass(frozen=True)
class PVCMultiAttachFault:
    """A single ReadWriteOnce PersistentVolumeClaim is mounted by a Deployment
    with replicas > 1 (optionally combined with podAntiAffinity forcing pods
    onto different nodes), producing FailedAttachVolume / Multi-Attach errors
    (SREGym `inject_duplicate_pvc_mounts`)."""

    deployment_name: str
    namespace: str
    pvc_name: str
    access_modes: tuple[str, ...] = ()
    desired_replicas: int = 1
    has_anti_affinity: bool = False
    multi_attach_events: tuple[str, ...] = ()


# -----------------------------------------------------------------------------
# RBAC Misconfiguration Fault Models
# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class RBACMisconfigFault:
    deployment_name: str
    namespace: str
    service_account_name: str
    fault_kind: Literal[
        "missing_rbac_permission",
        "missing_service_account",
        "missing_role_binding",
    ]
    missing_resources: tuple[str, ...] = ()
    missing_verbs: tuple[str, ...] = ()
    cluster_role_name: str | None = None
    cluster_role_binding_name: str | None = None
    details: str = ""


# -----------------------------------------------------------------------------
# ResourceQuota Exhaustion Models
# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class ResourceQuotaExhaustionFault:
    quota_name: str
    namespace: str
    resource_name: str
    used: str
    hard: str
    used_ratio: float
    blocked_deployment: str | None = None
    fault_kind: Literal["near_exhaustion", "exceeded"] = "near_exhaustion"


# -----------------------------------------------------------------------------
# LimitRange Violation Models
# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class LimitRangeViolationFault:
    limitrange_name: str
    namespace: str
    deployment_name: str
    container_name: str
    resource_name: str
    fault_kind: Literal["below_min", "above_max", "missing_default", "ratio_exceeded"]
    observed_value: str | None = None
    bound_value: str | None = None


# -----------------------------------------------------------------------------
# Aggregate Engine Diagnosis & Mitigation Models
# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class CategoryBDiagnosis:
    probe_faults: tuple[ProbeFault, ...] = ()
    trace_anomalies: TraceAnomalyResult | None = None
    flagd_drift: FlagdDriftResult | None = None
    missing_objects: tuple[MissingObjectFault, ...] = ()
    ingress_misroutes: tuple[IngressMisrouteFault, ...] = ()
    target_port_faults: tuple[TargetPortFault, ...] = ()
    cronjob_mutations: tuple[CronJobMutationFault, ...] = ()
    scheduling_deadlocks: tuple[SchedulingDeadlockFault, ...] = ()
    coredns_faults: tuple[CoreDNSFault, ...] = ()
    workload_misconfigs: tuple[WorkloadMisconfigFault, ...] = ()
    dns_policy_overrides: tuple[DnsPolicyOverrideFault, ...] = ()
    host_port_conflicts: tuple[HostPortConflictFault, ...] = ()
    pvc_claim_mismatches: tuple[PVCClaimMismatchFault, ...] = ()
    pvc_multi_attach_faults: tuple[PVCMultiAttachFault, ...] = ()
    rbac_misconfigs: tuple[RBACMisconfigFault, ...] = ()
    resourcequota_exhaustions: tuple[ResourceQuotaExhaustionFault, ...] = ()
    limitrange_violations: tuple[LimitRangeViolationFault, ...] = ()
    diagnosis_text: str = ""


@dataclass(frozen=True)
class CategoryBMitigation:
    commands: tuple[str, ...] = ()
    rollout_wait_deployments: tuple[str, ...] = ()
    mitigation_text: str = ""

