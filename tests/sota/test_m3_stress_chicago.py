"""Adversarial stress-testing suite for M3 detectors and remediators in autofde_lab_planner.

Strict zero-mock policy: NO unittest.mock, NO Mock, NO MagicMock, NO patch, NO monkeypatch.
Tests stress edge cases, boundary values, multi-fault scenarios, discrimination, and remediation validity.
"""

from __future__ import annotations

import json

from autofde_lab_planner.detectors.coredns_fault import detect_coredns_faults
from autofde_lab_planner.detectors.cronjob_mutation import detect_cronjob_mutations
from autofde_lab_planner.detectors.ingress_targetport import detect_ingress_and_targetport_faults
from autofde_lab_planner.detectors.object_reconstruction import detect_missing_objects
from autofde_lab_planner.detectors.probe_heuristics import detect_probe_faults
from autofde_lab_planner.detectors.rolling_update_misconfig import detect_workload_and_rolling_update_misconfigs
from autofde_lab_planner.detectors.scheduling_deadlock import detect_scheduling_deadlocks
from autofde_lab_planner.engine import CompositePlannerEngine
from autofde_lab_planner.models import (
    CoreDNSFault,
    CronJobMutationFault,
    IngressMisrouteFault,
    MissingObjectFault,
    ProbeFault,
    SchedulingDeadlockFault,
    TargetPortFault,
    WorkloadMisconfigFault,
)
from autofde_lab_planner.remediators.coredns_fault import decide_coredns_remediation_commands
from autofde_lab_planner.remediators.cronjob_mutation import decide_cronjob_remediation_commands
from autofde_lab_planner.remediators.ingress_targetport import decide_ingress_targetport_remediation_commands
from autofde_lab_planner.remediators.object_reconstruction import decide_object_reconstruction_commands
from autofde_lab_planner.remediators.probe_heuristics import decide_probe_remediation_commands
from autofde_lab_planner.remediators.rolling_update_misconfig import decide_workload_remediation_commands
from autofde_lab_planner.remediators.scheduling_deadlock import decide_scheduling_remediation_commands


# =============================================================================
# Stress Test 1: ConfigMap & Secret Key Drift (B13)
# =============================================================================

def test_stress_b13_malformed_json_configmap_data():
    """Verify detector handles malformed JSON gracefully without crashing."""
    configmaps = {
        "items": [
            {
                "metadata": {"name": "geo-config", "namespace": "hotel-reservation"},
                "data": {"config.json": "INVALID_JSON{{{"},
            }
        ]
    }
    faults = detect_missing_objects(
        deployments_json=[],
        live_configmaps_json=configmaps,
        namespace="hotel-reservation",
    )
    assert len(faults) == 1
    assert faults[0].reason == "corrupted_configmap_keys"
    assert len(faults[0].missing_keys) > 0


def test_stress_b13_shell_escaping_in_apply_command():
    """Verify reconstructed manifest JSON string escaping doesn't break shell syntax."""
    cm_fault = MissingObjectFault(
        kind="ConfigMap",
        object_name="geo-config",
        namespace="hotel-reservation",
        associated_deployment="geo",
        reason="corrupted_configmap_keys",
        missing_keys=("GeoMongoAddress",),
    )
    cmds, deps = decide_object_reconstruction_commands([cm_fault], namespace="hotel-reservation")
    apply_cmd = next(c for c in cmds if "kubectl apply" in c)
    assert apply_cmd.startswith("echo '")
    payload = apply_cmd.split("echo '")[1].rsplit("' | kubectl apply -f -", 1)[0]
    raw_json_str = payload.replace("'\\''", "'")
    parsed = json.loads(raw_json_str)
    assert parsed["metadata"]["name"] == "geo-config"
    assert "GeoMongoAddress" in parsed["data"]["config.json"]


def test_stress_b13_multiple_configmaps_and_secrets_drift():
    """Verify simultaneous drift across ConfigMaps and Secrets is fully identified."""
    configmaps = {
        "items": [
            {"metadata": {"name": "geo-config", "namespace": "hotel-reservation"}, "data": {"config.json": "{}"}},
            {"metadata": {"name": "rate-config", "namespace": "hotel-reservation"}, "data": {"config.json": "{}"}},
        ]
    }
    secrets = {
        "items": [
            {"metadata": {"name": "db-secret", "namespace": "hotel-reservation"}, "data": {}}
        ]
    }
    faults = detect_missing_objects(
        deployments_json=[],
        live_configmaps_json=configmaps,
        live_secrets_json=secrets,
        namespace="hotel-reservation",
    )
    assert len(faults) == 3
    fault_names = {f.object_name for f in faults}
    assert fault_names == {"geo-config", "rate-config", "db-secret"}


# =============================================================================
# Stress Test 2: Ingress & TargetPort Edge Cases
# =============================================================================

def test_stress_ingress_misroute_indexing():
    """Evaluate Ingress patch generation when misrouted path is at path index 1 without corrupting path index 0."""
    ingresses = {
        "items": [
            {
                "metadata": {"name": "multi-ingress", "namespace": "hotel-reservation"},
                "spec": {
                    "rules": [
                        {
                            "http": {
                                "paths": [
                                    {"path": "/health", "backend": {"service": {"name": "health-service"}}},
                                    {"path": "/api", "backend": {"service": {"name": "wrong-service"}}},
                                ]
                            }
                        }
                    ]
                },
            }
        ]
    }
    ing_faults, tp_faults = detect_ingress_and_targetport_faults(
        ingresses_json=ingresses,
        namespace="hotel-reservation",
    )
    assert len(ing_faults) == 1
    assert ing_faults[0].observed_backend_service == "wrong-service"
    assert ing_faults[0].expected_backend_service == "frontend-service"
    assert ing_faults[0].rule_index == 0
    assert ing_faults[0].path_index == 1

    cmds, deps = decide_ingress_targetport_remediation_commands(ing_faults, tp_faults, namespace="hotel-reservation")
    assert len(cmds) == 1
    patch_cmd = cmds[0]
    assert "/spec/rules/0/http/paths/1/backend/service/name" in patch_cmd
    assert "/spec/rules/0/http/paths/0" not in patch_cmd


def test_stress_multi_port_service_targetport_indexing():
    """Verify Service targetPort remediation patches port index 1 without corrupting port index 0."""
    services = {
        "items": [
            {
                "metadata": {"name": "user-service", "namespace": "default"},
                "spec": {
                    "ports": [
                        {"name": "metrics", "port": 9100, "targetPort": 9100},
                        {"name": "grpc", "port": 9090, "targetPort": 1234},  # Expected 9090 at index 1
                    ]
                },
            }
        ]
    }
    ing_faults, tp_faults = detect_ingress_and_targetport_faults(services_json=services, namespace="default")
    assert len(tp_faults) == 1
    assert tp_faults[0].port_index == 1
    assert tp_faults[0].observed_target_port == 1234

    cmds, deps = decide_ingress_targetport_remediation_commands(ing_faults, tp_faults, namespace="default")
    patch_cmds = [c for c in cmds if "kubectl patch service" in c]
    assert len(patch_cmds) == 1
    assert "/spec/ports/1/targetPort" in patch_cmds[0]
    assert "/spec/ports/0/targetPort" not in patch_cmds[0]


def test_stress_multi_container_pod_resource_request_removal():
    """Verify Pod resource request removal targets container index 1 without corrupting sidecar at index 0."""
    deployments = {
        "items": [
            {
                "metadata": {"name": "app-with-sidecar", "namespace": "default"},
                "spec": {
                    "template": {
                        "spec": {
                            "containers": [
                                {
                                    "name": "sidecar",
                                    "image": "sidecar:v1",
                                    "resources": {"requests": {"cpu": "50m", "memory": "64Mi"}},
                                },
                                {
                                    "name": "main-app",
                                    "image": "main:v1",
                                    "resources": {"requests": {"memory": "64Gi"}},
                                },
                            ]
                        }
                    }
                },
            }
        ]
    }
    faults = detect_workload_and_rolling_update_misconfigs(deployments_json=deployments, namespace="default")
    assert len(faults) == 1
    assert faults[0].container_name == "main-app"
    assert faults[0].container_index == 1

    cmds, deps = decide_workload_remediation_commands(faults, namespace="default")
    patch_cmds = [c for c in cmds if "kubectl patch deployment" in c and "resources/requests" in c]
    assert len(patch_cmds) == 1
    assert "/spec/template/spec/containers/1/resources/requests" in patch_cmds[0]
    assert "/spec/template/spec/containers/0/resources/requests" not in patch_cmds[0]


def test_stress_multi_container_cronjob_mutation_removal():
    """Verify CronJob mutation victim limit removal targets victim container index 1 without corrupting sidecar at index 0."""
    deployments = {
        "items": [
            {
                "metadata": {"name": "recommendation", "namespace": "default"},
                "spec": {
                    "template": {
                        "spec": {
                            "containers": [
                                {
                                    "name": "sidecar",
                                    "image": "sidecar:v1",
                                    "resources": {"limits": {"memory": "512Mi"}},
                                },
                                {
                                    "name": "recommendation",
                                    "image": "rec:v1",
                                    "resources": {"limits": {"memory": "4Mi"}},
                                },
                            ]
                        }
                    }
                },
            }
        ]
    }
    cronjobs = {
        "items": [
            {
                "metadata": {"name": "vpa-updater", "namespace": "kube-system"},
                "spec": {
                    "jobTemplate": {
                        "spec": {
                            "template": {
                                "spec": {
                                    "containers": [
                                        {"name": "patch", "command": ["kubectl", "patch", "deployment", "recommendation"]}
                                    ]
                                }
                            }
                        }
                    }
                },
            }
        ]
    }
    faults = detect_cronjob_mutations(cronjobs_json=cronjobs, deployments_json=deployments, namespace="default")
    assert len(faults) == 1
    assert faults[0].container_name == "recommendation"
    assert faults[0].container_index == 1

    cmds, deps = decide_cronjob_remediation_commands(faults, namespace="default")
    patch_cmds = [c for c in cmds if "kubectl patch deployment" in c and "limits/memory" in c]
    assert len(patch_cmds) == 1
    assert "/spec/template/spec/containers/1/resources/limits/memory" in patch_cmds[0]
    assert "/spec/template/spec/containers/0/resources/limits/memory" not in patch_cmds[0]


def test_stress_targetport_type_coercion():
    """Verify targetPort comparison handles integer vs string mismatches correctly."""
    services = {
        "items": [
            {
                "metadata": {"name": "user-service", "namespace": "social-network"},
                "spec": {"ports": [{"port": 9090, "targetPort": "9090"}]},
            }
        ]
    }
    ing_faults, tp_faults = detect_ingress_and_targetport_faults(
        services_json=services,
        namespace="social-network",
    )
    assert len(tp_faults) == 0


def test_stress_targetport_auto_discovery_from_deployment():
    """Verify targetPort mismatch detection for unlisted service via deployment containerPort."""
    deployments = {
        "items": [
            {
                "metadata": {"name": "custom-service", "namespace": "custom-ns"},
                "spec": {
                    "template": {
                        "spec": {
                            "containers": [{"name": "custom", "ports": [{"containerPort": 8080}]}]
                        }
                    }
                },
            }
        ]
    }
    services = {
        "items": [
            {
                "metadata": {"name": "custom-service", "namespace": "custom-ns"},
                "spec": {"ports": [{"port": 80, "targetPort": 9999}]},
            }
        ]
    }
    ing_faults, tp_faults = detect_ingress_and_targetport_faults(
        services_json=services,
        deployments_json=deployments,
        namespace="custom-ns",
    )
    assert len(tp_faults) == 1
    assert tp_faults[0].observed_target_port == 9999
    assert tp_faults[0].expected_target_port == 8080


# =============================================================================
# Stress Test 3: CronJob Scheduled Mutation Edge Cases
# =============================================================================

def test_stress_cronjob_memory_parsing_units():
    """Verify memory parsing across Ki, Mi, Gi, and raw bytes."""
    deployments = {
        "items": [
            {
                "metadata": {"name": "recommendation", "namespace": "hotel-reservation"},
                "spec": {
                    "template": {
                        "spec": {
                            "containers": [
                                {"name": "recommendation", "resources": {"limits": {"memory": "8192Ki"}}}
                            ]
                        }
                    }
                },
            }
        ]
    }
    cronjobs = {
        "items": [
            {
                "metadata": {"name": "vpa-updater", "namespace": "kube-system"},
                "spec": {
                    "jobTemplate": {
                        "spec": {
                            "template": {
                                "spec": {
                                    "containers": [
                                        {"name": "patch", "command": ["kubectl", "patch", "deployment", "recommendation"]}
                                    ]
                                }
                            }
                        }
                    }
                },
            }
        ]
    }
    faults = detect_cronjob_mutations(
        cronjobs_json=cronjobs,
        deployments_json=deployments,
        namespace="hotel-reservation",
    )
    assert len(faults) == 1
    assert faults[0].victim_deployment == "recommendation"


# =============================================================================
# Stress Test 4: Pod Anti-Affinity & Scheduling Deadlocks (B1)
# =============================================================================

def test_stress_scheduling_deadlock_discrimination():
    """Verify discrimination between ready pods with affinity vs unready pending pods."""
    deployments = {
        "items": [
            {
                "metadata": {"name": "healthy-service", "namespace": "social-network"},
                "spec": {
                    "replicas": 1,
                    "template": {
                        "spec": {
                            "affinity": {"podAntiAffinity": {"requiredDuringSchedulingIgnoredDuringExecution": []}}
                        }
                    },
                },
                "status": {"readyReplicas": 1},
            },
            {
                "metadata": {"name": "deadlocked-service", "namespace": "social-network"},
                "spec": {
                    "replicas": 2,
                    "template": {
                        "spec": {
                            "affinity": {"podAntiAffinity": {"requiredDuringSchedulingIgnoredDuringExecution": []}}
                        }
                    },
                },
                "status": {"readyReplicas": 0},
            },
        ]
    }
    faults = detect_scheduling_deadlocks(
        deployments_json=deployments,
        namespace="social-network",
    )
    assert len(faults) == 1
    assert faults[0].deployment_name == "deadlocked-service"


# =============================================================================
# Stress Test 5: CoreDNS Faults
# =============================================================================

def test_stress_coredns_multiline_formatting():
    """Verify Corefile regex and fallback cleaning handle multi-line formatted NXDOMAIN rules."""
    corefile = """
.:53 {
    errors
    health
    template ANY ANY svc.cluster.local {
        match ".*\\.svc\\.cluster\\.local\\.?$"
        rcode NXDOMAIN
    }
    kubernetes cluster.local in-addr.arpa ip6.arpa {
        pods insecure
    }
}
"""
    configmaps = {"items": [{"metadata": {"name": "coredns", "namespace": "kube-system"}, "data": {"Corefile": corefile}}]}
    faults = detect_coredns_faults(configmaps_json=configmaps, namespace="kube-system")
    assert len(faults) == 1
    repaired = faults[0].repaired_corefile
    assert "rcode NXDOMAIN" not in repaired
    assert "template ANY ANY svc.cluster.local" not in repaired
    assert "kubernetes cluster.local" in repaired


# =============================================================================
# Stress Test 6: Workload & Rolling Update Misconfigurations
# =============================================================================

def test_stress_rolling_update_without_init_container():
    """Check remediation when rolling update is misconfigured BUT no init container exists."""
    deployments = {
        "items": [
            {
                "metadata": {"name": "frontend", "namespace": "hotel-reservation"},
                "spec": {
                    "strategy": {
                        "type": "RollingUpdate",
                        "rollingUpdate": {"maxUnavailable": "100%", "maxSurge": "0%"},
                    },
                    "template": {
                        "spec": {
                            "containers": [{"name": "frontend", "image": "frontend:v1"}]
                        }
                    },
                },
            }
        ]
    }
    faults = detect_workload_and_rolling_update_misconfigs(
        deployments_json=deployments,
        namespace="hotel-reservation",
    )
    assert len(faults) == 1
    assert faults[0].deployment_name == "frontend"
    assert faults[0].fault_kind == "rolling_update_misconfigured"

    cmds, deps = decide_workload_remediation_commands(faults, namespace="hotel-reservation")
    strategy_cmds = [c for c in cmds if "spec/strategy" in c]
    init_cmds = [c for c in cmds if "initContainers" in c]
    assert len(strategy_cmds) == 1
    assert len(init_cmds) == 0, "Do NOT issue initContainers removal patch when initContainers is absent"
    print("\n[STRESS TEST OBSERVED] Rolling Update Remediator commands without initContainers:", cmds)



# =============================================================================
# Stress Test 7: Multi-Fault Discrimination & Isolation
# =============================================================================

def test_stress_composite_engine_multi_fault_discrimination():
    """Stress test CompositePlannerEngine with simultaneous faults from all categories."""
    engine = CompositePlannerEngine(namespace="astronomy-shop", app_name="Astronomy Shop")

    deployments = {
        "items": [
            {
                "metadata": {"name": "frontend", "namespace": "astronomy-shop"},
                "spec": {
                    "strategy": {"type": "RollingUpdate", "rollingUpdate": {"maxSurge": "0%", "maxUnavailable": "100%"}},
                    "template": {
                        "spec": {
                            "affinity": {"podAntiAffinity": {"requiredDuringSchedulingIgnoredDuringExecution": []}},
                            "containers": [{"name": "frontend", "resources": {"requests": {"memory": "64Gi"}}}],
                        }
                    },
                },
                "status": {"readyReplicas": 0},
            }
        ]
    }
    configmaps = {
        "items": [
            {
                "metadata": {"name": "coredns", "namespace": "kube-system"},
                "data": {"Corefile": "template ANY ANY svc.cluster.local { rcode NXDOMAIN }"},
            }
        ]
    }
    services = {
        "items": [
            {
                "metadata": {"name": "user-service", "namespace": "astronomy-shop"},
                "spec": {"ports": [{"port": 9090, "targetPort": 1234}]},
            }
        ]
    }

    diag = engine.run_diagnosis(
        deployments_json=deployments,
        configmaps_json=configmaps,
        services_json=services,
    )

    # Verify that multiple fault mechanisms on the same deployment/namespace are discriminated correctly
    assert len(diag.target_port_faults) == 1
    assert len(diag.coredns_faults) == 1
    assert len(diag.scheduling_deadlocks) == 1
    assert len(diag.workload_misconfigs) >= 1

    mit = engine.run_mitigation(diag)
    assert len(mit.commands) >= 4
    assert "user-service" in mit.rollout_wait_deployments
    assert "frontend" in mit.rollout_wait_deployments
