"""Composite multi-detector planning engine for Category-B and expanded fault mechanisms."""

from __future__ import annotations

from typing import Any

from autofde_lab_planner.detectors.coredns_fault import detect_coredns_faults
from autofde_lab_planner.detectors.cronjob_mutation import detect_cronjob_mutations
from autofde_lab_planner.detectors.dns_policy_override import detect_dns_policy_overrides
from autofde_lab_planner.detectors.flagd_drift import detect_flagd_config_drift
from autofde_lab_planner.detectors.host_port_conflict import detect_host_port_conflicts
from autofde_lab_planner.detectors.ingress_targetport import detect_ingress_and_targetport_faults
from autofde_lab_planner.detectors.limitrange_violation import detect_limitrange_violations
from autofde_lab_planner.detectors.object_reconstruction import detect_missing_objects
from autofde_lab_planner.detectors.otel_trace import detect_otel_trace_anomalies
from autofde_lab_planner.detectors.probe_heuristics import detect_probe_faults
from autofde_lab_planner.detectors.pvc_storage_faults import (
    detect_pvc_claim_mismatches,
    detect_pvc_multi_attach_faults,
)
from autofde_lab_planner.detectors.rbac_misconfig import detect_rbac_misconfigurations
from autofde_lab_planner.detectors.resourcequota_exhaustion import detect_resourcequota_exhaustion
from autofde_lab_planner.detectors.rolling_update_misconfig import detect_workload_and_rolling_update_misconfigs
from autofde_lab_planner.detectors.scheduling_deadlock import detect_scheduling_deadlocks
from autofde_lab_planner.models import CategoryBDiagnosis, CategoryBMitigation
from autofde_lab_planner.remediators.coredns_fault import decide_coredns_remediation_commands
from autofde_lab_planner.remediators.cronjob_mutation import decide_cronjob_remediation_commands
from autofde_lab_planner.remediators.dns_policy_override import decide_dns_policy_remediation_commands
from autofde_lab_planner.remediators.flagd_drift import decide_flagd_remediation_commands
from autofde_lab_planner.remediators.host_port_conflict import decide_host_port_conflict_remediation_commands
from autofde_lab_planner.remediators.ingress_targetport import decide_ingress_targetport_remediation_commands
from autofde_lab_planner.remediators.limitrange_violation import decide_limitrange_remediation_commands
from autofde_lab_planner.remediators.object_reconstruction import decide_object_reconstruction_commands
from autofde_lab_planner.remediators.otel_trace import decide_otel_remediation_commands
from autofde_lab_planner.remediators.probe_heuristics import decide_probe_remediation_commands
from autofde_lab_planner.remediators.pvc_storage_faults import (
    decide_pvc_claim_mismatch_commands,
    decide_pvc_multi_attach_commands,
)
from autofde_lab_planner.remediators.rbac_misconfig import decide_rbac_remediation_commands
from autofde_lab_planner.remediators.resourcequota_exhaustion import decide_resourcequota_remediation_commands
from autofde_lab_planner.remediators.rolling_update_misconfig import decide_workload_remediation_commands
from autofde_lab_planner.remediators.scheduling_deadlock import decide_scheduling_remediation_commands


class CompositePlannerEngine:
    """Orchestrates detection and remediation generation across all SREGym fault mechanisms."""

    def __init__(self, namespace: str = "default", app_name: str = ""):
        self.namespace = namespace
        self.app_name = app_name

    def run_diagnosis(
        self,
        deployments_json: dict[str, Any] | list[dict[str, Any]],
        services_json: dict[str, Any] | list[dict[str, Any]] | None = None,
        configmaps_json: dict[str, Any] | list[dict[str, Any]] | None = None,
        secrets_json: dict[str, Any] | list[dict[str, Any]] | None = None,
        pods_json: dict[str, Any] | list[dict[str, Any]] | None = None,
        events_json: dict[str, Any] | list[dict[str, Any]] | None = None,
        ingresses_json: dict[str, Any] | list[dict[str, Any]] | None = None,
        cronjobs_json: dict[str, Any] | list[dict[str, Any]] | None = None,
        pvcs_json: dict[str, Any] | list[dict[str, Any]] | None = None,
        resourcequotas_json: dict[str, Any] | list[dict[str, Any]] | None = None,
        limitranges_json: dict[str, Any] | list[dict[str, Any]] | None = None,
        flagd_configmap_json: str | dict[str, Any] | None = None,
        raw_traces_by_service: dict[str, Any] | None = None,
        elevated_revision_deployments: set[str] | None = None,
        service_accounts_json: dict[str, Any] | list[dict[str, Any]] | None = None,
        cluster_roles_json: dict[str, Any] | list[dict[str, Any]] | None = None,
        cluster_role_bindings_json: dict[str, Any] | list[dict[str, Any]] | None = None,
    ) -> CategoryBDiagnosis:
        """Executes all Category-B and expanded detectors and generates structured diagnosis report."""
        # 1. B13: Missing/Corrupted K8s Objects
        missing_objects = detect_missing_objects(
            deployments_json=deployments_json,
            live_services_json=services_json,
            live_configmaps_json=configmaps_json,
            live_secrets_json=secrets_json,
            pods_json=pods_json,
            namespace=self.namespace,
            elevated_revision_deployments=elevated_revision_deployments,
        )

        # 2. B4: Probe Heuristics (Readiness/Liveness)
        probe_faults = detect_probe_faults(
            deployments_json=deployments_json,
            pods_json=pods_json,
            events_json=events_json,
        )

        # 3. B9: flagd Config Drift
        flagd_drift = None
        if flagd_configmap_json:
            flagd_drift = detect_flagd_config_drift(
                configmap_json_input=flagd_configmap_json,
                namespace=self.namespace,
            )

        # 4. B6: OTel Trace Diffing
        trace_anomalies = None
        if raw_traces_by_service:
            trace_anomalies = detect_otel_trace_anomalies(raw_traces_by_service)

        # 5. Ingress & TargetPort Misconfigurations
        ingress_misroutes, target_port_faults = detect_ingress_and_targetport_faults(
            ingresses_json=ingresses_json,
            services_json=services_json,
            deployments_json=deployments_json,
            namespace=self.namespace,
        )

        # 6. CronJob / Scheduled Mutations
        cronjob_mutations = detect_cronjob_mutations(
            cronjobs_json=cronjobs_json,
            deployments_json=deployments_json,
            configmaps_json=configmaps_json,
            namespace=self.namespace,
        )

        # 7. B1: Pod Anti-Affinity & Scheduling Deadlocks
        scheduling_deadlocks = detect_scheduling_deadlocks(
            deployments_json=deployments_json,
            pods_json=pods_json,
            events_json=events_json,
            namespace=self.namespace,
        )

        # 8. CoreDNS & Service Discovery Faults
        coredns_faults = detect_coredns_faults(
            configmaps_json=configmaps_json,
            namespace="kube-system",
        )

        # 9. Workload & Rolling Update Misconfigurations
        workload_misconfigs = detect_workload_and_rolling_update_misconfigs(
            deployments_json=deployments_json,
            pods_json=pods_json,
            events_json=events_json,
            namespace=self.namespace,
        )

        # 10. Deployment-level DNS Policy Overrides
        dns_policy_overrides = detect_dns_policy_overrides(
            deployments_json=deployments_json,
            namespace=self.namespace,
        )

        # 11. Container hostPort Binding Conflicts
        host_port_conflicts = detect_host_port_conflicts(
            deployments_json=deployments_json,
            namespace=self.namespace,
        )

        # 12. Storage: PVC claim mismatches
        pvc_claim_mismatches = detect_pvc_claim_mismatches(
            deployments_json=deployments_json,
            pvcs_json=pvcs_json,
            pods_json=pods_json,
            namespace=self.namespace,
        )

        # 13. Storage: PVC multi-attach (shared RWO volume) faults
        pvc_multi_attach_faults = detect_pvc_multi_attach_faults(
            deployments_json=deployments_json,
            pvcs_json=pvcs_json,
            events_json=events_json,
            namespace=self.namespace,
        )

        # 14. RBAC Misconfigurations
        rbac_misconfigs = detect_rbac_misconfigurations(
            deployments_json=deployments_json,
            service_accounts_json=service_accounts_json,
            cluster_roles_json=cluster_roles_json,
            cluster_role_bindings_json=cluster_role_bindings_json,
            namespace=self.namespace,
        )

        # 15. ResourceQuota Exhaustion
        resourcequota_exhaustions = detect_resourcequota_exhaustion(
            resourcequotas_json=resourcequotas_json,
            events_json=events_json,
            namespace=self.namespace,
        )

        # 16. LimitRange Violations
        limitrange_violations = detect_limitrange_violations(
            limitranges_json=limitranges_json,
            deployments_json=deployments_json,
            namespace=self.namespace,
        )

        # Build natural-language diagnosis text
        text_parts: list[str] = []

        if missing_objects:
            objs_str = ", ".join(f"{mo.kind}/{mo.object_name} ({mo.reason})" for mo in missing_objects)
            text_parts.append(f"Detected missing or corrupted Kubernetes objects in namespace {self.namespace}: {objs_str}.")

        if probe_faults:
            pf_str = ", ".join(f"{pf.deployment_name}:{pf.probe_type} ({pf.fault_kind})" for pf in probe_faults)
            text_parts.append(f"Detected probe misconfigurations in namespace {self.namespace}: {pf_str}.")

        if flagd_drift and flagd_drift.has_drift:
            flags_str = ", ".join(f"{df.flag_name}='{df.current_variant}'" for df in flagd_drift.drifted_flags)
            text_parts.append(f"Detected flagd feature flag config drift in namespace {self.namespace}: {flags_str}.")

        if trace_anomalies and trace_anomalies.has_anomaly:
            text_parts.append(f"Detected OTel trace RPC anomalies: {trace_anomalies.reasoning}")

        if ingress_misroutes:
            ing_str = ", ".join(f"{ing.ingress_name} path {ing.path} -> {ing.observed_backend_service}" for ing in ingress_misroutes)
            text_parts.append(f"Detected Ingress backend misroutes in namespace {self.namespace}: {ing_str}.")

        if target_port_faults:
            tp_str = ", ".join(f"{tp.service_name} targetPort={tp.observed_target_port}" for tp in target_port_faults)
            text_parts.append(f"Detected Service targetPort mismatches in namespace {self.namespace}: {tp_str}.")

        if cronjob_mutations:
            cj_str = ", ".join(f"CronJob {cj.cronjob_namespace}/{cj.cronjob_name} -> victim {cj.victim_deployment}" for cj in cronjob_mutations)
            text_parts.append(f"Detected mutator CronJobs targeting deployments: {cj_str}.")

        if scheduling_deadlocks:
            sd_str = ", ".join(f"{sd.deployment_name} ({sd.constraint_type})" for sd in scheduling_deadlocks)
            text_parts.append(f"Detected scheduling deadlocks in namespace {self.namespace}: {sd_str}.")

        if coredns_faults:
            dns_str = ", ".join(f"{cd.configmap_name} ({cd.fault_kind})" for cd in coredns_faults)
            text_parts.append(f"Detected CoreDNS configuration faults in kube-system: {dns_str}.")

        if workload_misconfigs:
            wm_str = ", ".join(f"{wm.deployment_name} ({wm.fault_kind})" for wm in workload_misconfigs)
            text_parts.append(f"Detected workload/rolling update misconfigurations in namespace {self.namespace}: {wm_str}.")

        if dns_policy_overrides:
            dp_str = ", ".join(
                f"{dp.deployment_name} dnsPolicy={dp.observed_dns_policy}"
                f" nameservers={list(dp.observed_nameservers)}"
                for dp in dns_policy_overrides
            )
            text_parts.append(f"Detected Deployment DNS policy overrides in namespace {self.namespace}: {dp_str}.")

        if host_port_conflicts:
            hp_str = ", ".join(
                f"{hp.deployment_name}/{hp.container_name} hostPort={hp.conflicting_host_port}"
                for hp in host_port_conflicts
            )
            text_parts.append(f"Detected container hostPort binding conflicts in namespace {self.namespace}: {hp_str}.")

        if pvc_claim_mismatches:
            pcm_str = ", ".join(
                f"{f.deployment_name} vol {f.volume_name} -> claim '{f.observed_claim_name}'"
                for f in pvc_claim_mismatches
            )
            text_parts.append(f"Detected dangling PVC claim references in namespace {self.namespace}: {pcm_str}.")

        if pvc_multi_attach_faults:
            pma_str = ", ".join(
                f"{f.deployment_name} -> PVC {f.pvc_name} (replicas={f.desired_replicas}, modes={f.access_modes})"
                for f in pvc_multi_attach_faults
            )
            text_parts.append(f"Detected PVC multi-attach conflicts in namespace {self.namespace}: {pma_str}.")

        if rbac_misconfigs:
            rbac_str = ", ".join(f"{rf.deployment_name}/{rf.service_account_name} ({rf.fault_kind})" for rf in rbac_misconfigs)
            text_parts.append(f"Detected RBAC misconfigurations in namespace {self.namespace}: {rbac_str}.")

        if resourcequota_exhaustions:
            rq_str = ", ".join(
                f"{rq.quota_name}/{rq.resource_name} ({rq.used}/{rq.hard}, {rq.fault_kind})"
                for rq in resourcequota_exhaustions
            )
            text_parts.append(f"Detected ResourceQuota exhaustion in namespace {self.namespace}: {rq_str}.")

        if limitrange_violations:
            lr_str = ", ".join(
                f"{lv.deployment_name}/{lv.container_name}:{lv.resource_name} ({lv.fault_kind})"
                for lv in limitrange_violations
            )
            text_parts.append(f"Detected LimitRange violations in namespace {self.namespace}: {lr_str}.")

        if not text_parts:
            diagnosis_text = f"No fault mechanism anomalies detected in namespace {self.namespace}."
        else:
            diagnosis_text = " ".join(text_parts)

        return CategoryBDiagnosis(
            probe_faults=tuple(probe_faults),
            trace_anomalies=trace_anomalies,
            flagd_drift=flagd_drift,
            missing_objects=tuple(missing_objects),
            ingress_misroutes=tuple(ingress_misroutes),
            target_port_faults=tuple(target_port_faults),
            cronjob_mutations=tuple(cronjob_mutations),
            scheduling_deadlocks=tuple(scheduling_deadlocks),
            coredns_faults=tuple(coredns_faults),
            workload_misconfigs=tuple(workload_misconfigs),
            dns_policy_overrides=tuple(dns_policy_overrides),
            host_port_conflicts=tuple(host_port_conflicts),
            pvc_claim_mismatches=tuple(pvc_claim_mismatches),
            pvc_multi_attach_faults=tuple(pvc_multi_attach_faults),
            rbac_misconfigs=tuple(rbac_misconfigs),
            resourcequota_exhaustions=tuple(resourcequota_exhaustions),
            limitrange_violations=tuple(limitrange_violations),
            diagnosis_text=diagnosis_text,
        )

    def run_mitigation(self, diagnosis: CategoryBDiagnosis) -> CategoryBMitigation:
        """Generates all remediation commands across all fault mechanisms."""
        commands: list[str] = []
        rollout_wait: list[str] = []

        # 1. B13 Remediations
        if diagnosis.missing_objects:
            b13_cmds, b13_deps = decide_object_reconstruction_commands(
                list(diagnosis.missing_objects), self.namespace
            )
            commands.extend(b13_cmds)
            rollout_wait.extend(b13_deps)

        # 2. B4 Remediations
        if diagnosis.probe_faults:
            b4_cmds, b4_deps = decide_probe_remediation_commands(
                list(diagnosis.probe_faults), self.namespace
            )
            commands.extend(b4_cmds)
            rollout_wait.extend(b4_deps)

        # 3. B9 Remediations
        if diagnosis.flagd_drift and diagnosis.flagd_drift.has_drift:
            b9_cmds, b9_deps = decide_flagd_remediation_commands(diagnosis.flagd_drift)
            commands.extend(b9_cmds)
            rollout_wait.extend(b9_deps)

        # 4. B6 Remediations
        if diagnosis.trace_anomalies and diagnosis.trace_anomalies.has_anomaly:
            b6_cmds, b6_deps = decide_otel_remediation_commands(
                diagnosis.trace_anomalies, self.namespace
            )
            commands.extend(b6_cmds)
            rollout_wait.extend(b6_deps)

        # 5. Ingress & TargetPort Remediations
        if diagnosis.ingress_misroutes or diagnosis.target_port_faults:
            ing_cmds, ing_deps = decide_ingress_targetport_remediation_commands(
                ingress_faults=list(diagnosis.ingress_misroutes),
                target_port_faults=list(diagnosis.target_port_faults),
                namespace=self.namespace,
            )
            commands.extend(ing_cmds)
            rollout_wait.extend(ing_deps)

        # 6. CronJob Remediations
        if diagnosis.cronjob_mutations:
            cj_cmds, cj_deps = decide_cronjob_remediation_commands(
                faults=list(diagnosis.cronjob_mutations),
                namespace=self.namespace,
            )
            commands.extend(cj_cmds)
            rollout_wait.extend(cj_deps)

        # 7. Scheduling Deadlock Remediations
        if diagnosis.scheduling_deadlocks:
            sd_cmds, sd_deps = decide_scheduling_remediation_commands(
                faults=list(diagnosis.scheduling_deadlocks),
                namespace=self.namespace,
            )
            commands.extend(sd_cmds)
            rollout_wait.extend(sd_deps)

        # 8. CoreDNS Remediations
        if diagnosis.coredns_faults:
            dns_cmds, dns_deps = decide_coredns_remediation_commands(
                faults=list(diagnosis.coredns_faults),
                namespace="kube-system",
            )
            commands.extend(dns_cmds)
            rollout_wait.extend(dns_deps)

        # 9. Workload & Rolling Update Remediations
        if diagnosis.workload_misconfigs:
            wm_cmds, wm_deps = decide_workload_remediation_commands(
                faults=list(diagnosis.workload_misconfigs),
                namespace=self.namespace,
            )
            commands.extend(wm_cmds)
            rollout_wait.extend(wm_deps)

        # 10. DNS Policy Override Remediations
        if diagnosis.dns_policy_overrides:
            dp_cmds, dp_deps = decide_dns_policy_remediation_commands(
                faults=list(diagnosis.dns_policy_overrides),
                namespace=self.namespace,
            )
            commands.extend(dp_cmds)
            rollout_wait.extend(dp_deps)

        # 11. hostPort Conflict Remediations
        if diagnosis.host_port_conflicts:
            hp_cmds, hp_deps = decide_host_port_conflict_remediation_commands(
                faults=list(diagnosis.host_port_conflicts),
                namespace=self.namespace,
            )
            commands.extend(hp_cmds)
            rollout_wait.extend(hp_deps)

        # 12. Storage: PVC claim mismatch Remediations
        if diagnosis.pvc_claim_mismatches:
            pcm_cmds, pcm_deps = decide_pvc_claim_mismatch_commands(
                faults=list(diagnosis.pvc_claim_mismatches),
                namespace=self.namespace,
            )
            commands.extend(pcm_cmds)
            rollout_wait.extend(pcm_deps)

        # 13. Storage: PVC multi-attach Remediations
        if diagnosis.pvc_multi_attach_faults:
            pma_cmds, pma_deps = decide_pvc_multi_attach_commands(
                faults=list(diagnosis.pvc_multi_attach_faults),
                namespace=self.namespace,
            )
            commands.extend(pma_cmds)
            rollout_wait.extend(pma_deps)

        # 14. RBAC Remediations
        if diagnosis.rbac_misconfigs:
            rbac_cmds, rbac_deps = decide_rbac_remediation_commands(
                faults=list(diagnosis.rbac_misconfigs),
                namespace=self.namespace,
            )
            commands.extend(rbac_cmds)
            rollout_wait.extend(rbac_deps)

        # 15. ResourceQuota Exhaustion Remediations
        if diagnosis.resourcequota_exhaustions:
            rq_cmds, rq_deps = decide_resourcequota_remediation_commands(
                faults=list(diagnosis.resourcequota_exhaustions),
                namespace=self.namespace,
            )
            commands.extend(rq_cmds)
            rollout_wait.extend(rq_deps)

        # 16. LimitRange Violation Remediations
        if diagnosis.limitrange_violations:
            lr_cmds, lr_deps = decide_limitrange_remediation_commands(
                faults=list(diagnosis.limitrange_violations),
                namespace=self.namespace,
            )
            commands.extend(lr_cmds)
            rollout_wait.extend(lr_deps)

        # Deduplicate wait deployments
        unique_wait = tuple(dict.fromkeys(rollout_wait))
        mitigation_text = (
            f"Generated {len(commands)} remediation actions targeting deployments: {', '.join(unique_wait)}."
            if commands
            else "No remediation actions required."
        )

        return CategoryBMitigation(
            commands=tuple(commands),
            rollout_wait_deployments=unique_wait,
            mitigation_text=mitigation_text,
        )
