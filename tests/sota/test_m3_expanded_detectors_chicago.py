"""Chicago-style zero-mock unit and integration tests for M3 Expanded Fault Mechanisms.

Strict zero-mock policy: NO unittest.mock, NO Mock, NO MagicMock, NO patch, NO monkeypatch.
All tests exercise pure functions with real Python data structures and manifests.
"""

from __future__ import annotations

import json
from autofde_lab_planner.detectors.coredns_fault import detect_coredns_faults
from autofde_lab_planner.detectors.cronjob_mutation import detect_cronjob_mutations
from autofde_lab_planner.detectors.ingress_targetport import detect_ingress_and_targetport_faults
from autofde_lab_planner.detectors.object_reconstruction import detect_missing_objects
from autofde_lab_planner.detectors.rolling_update_misconfig import detect_workload_and_rolling_update_misconfigs
from autofde_lab_planner.detectors.scheduling_deadlock import detect_scheduling_deadlocks
from autofde_lab_planner.engine import CompositePlannerEngine
from autofde_lab_planner.models import (
    CoreDNSFault,
    CronJobMutationFault,
    IngressMisrouteFault,
    MissingObjectFault,
    SchedulingDeadlockFault,
    TargetPortFault,
    WorkloadMisconfigFault,
)
from autofde_lab_planner.remediators.coredns_fault import decide_coredns_remediation_commands
from autofde_lab_planner.remediators.cronjob_mutation import decide_cronjob_remediation_commands
from autofde_lab_planner.remediators.ingress_targetport import decide_ingress_targetport_remediation_commands
from autofde_lab_planner.remediators.object_reconstruction import decide_object_reconstruction_commands
from autofde_lab_planner.remediators.rolling_update_misconfig import decide_workload_remediation_commands
from autofde_lab_planner.remediators.scheduling_deadlock import decide_scheduling_remediation_commands


# =============================================================================
# Category 1: ConfigMap & Secret Key Drift (B13)
# =============================================================================

def test_b13_configmap_key_drift_detection_and_remediation():
    deployments = {
        "items": [
            {
                "metadata": {"name": "geo", "namespace": "hotel-reservation"},
                "spec": {
                    "template": {
                        "spec": {
                            "volumes": [
                                {"name": "config-volume", "configMap": {"name": "geo-config"}}
                            ]
                        }
                    }
                },
            }
        ]
    }

    # Corrupted ConfigMap missing GeoMongoAddress in config.json payload
    configmaps = {
        "items": [
            {
                "metadata": {"name": "geo-config", "namespace": "hotel-reservation"},
                "data": {
                    "config.json": json.dumps(
                        {"GeoPort": "8083"}  # GeoMongoAddress deleted!
                    )
                },
            }
        ]
    }

    faults = detect_missing_objects(
        deployments_json=deployments,
        live_configmaps_json=configmaps,
        namespace="hotel-reservation",
    )

    assert len(faults) >= 1
    cm_fault = next(f for f in faults if f.object_name == "geo-config")
    assert cm_fault.reason == "corrupted_configmap_keys"
    assert "GeoMongoAddress" in cm_fault.missing_keys
    assert cm_fault.associated_deployment == "geo"

    cmds, deps = decide_object_reconstruction_commands([cm_fault], namespace="hotel-reservation")
    assert any("kubectl apply" in cmd for cmd in cmds)
    assert any("GeoMongoAddress" in cmd for cmd in cmds)
    assert "geo" in deps
    assert "kubectl rollout restart deployment/geo -n hotel-reservation" in cmds


def test_b13_secret_key_drift_detection_and_remediation():
    configmaps = {"items": []}
    secrets = {
        "items": [
            {
                "metadata": {"name": "db-secret", "namespace": "hotel-reservation"},
                "data": {},  # missing password key
            }
        ]
    }

    faults = detect_missing_objects(
        deployments_json=[],
        live_secrets_json=secrets,
        namespace="hotel-reservation",
    )

    assert len(faults) == 1
    sec_fault = faults[0]
    assert sec_fault.kind == "Secret"
    assert sec_fault.object_name == "db-secret"
    assert sec_fault.reason == "corrupted_secret_keys"
    assert "password" in sec_fault.missing_keys

    cmds, deps = decide_object_reconstruction_commands([sec_fault], namespace="hotel-reservation")
    assert any("kubectl apply" in cmd for cmd in cmds)
    assert any("password" in cmd for cmd in cmds)


# =============================================================================
# Category 2: Ingress Misroute & TargetPort Mismatches
# =============================================================================

def test_ingress_misroute_detection_and_remediation():
    ingresses = {
        "items": [
            {
                "metadata": {"name": "hotel-reservation-ingress", "namespace": "hotel-reservation"},
                "spec": {
                    "rules": [
                        {
                            "http": {
                                "paths": [
                                    {
                                        "path": "/api(/|$)(.*)",
                                        "backend": {
                                            "service": {"name": "recommendation-service", "port": {"number": 80}}
                                        },
                                    }
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
    assert len(tp_faults) == 0
    fault = ing_faults[0]
    assert fault.ingress_name == "hotel-reservation-ingress"
    assert fault.path == "/api(/|$)(.*)"
    assert fault.observed_backend_service == "recommendation-service"
    assert fault.expected_backend_service == "frontend-service"

    cmds, deps = decide_ingress_targetport_remediation_commands(ing_faults, tp_faults, namespace="hotel-reservation")
    assert len(cmds) == 1
    assert "kubectl patch ingress hotel-reservation-ingress" in cmds[0]
    assert "frontend-service" in cmds[0]


def test_targetport_mismatch_detection_and_remediation():
    services = {
        "items": [
            {
                "metadata": {"name": "user-service", "namespace": "social-network"},
                "spec": {
                    "ports": [{"port": 9090, "targetPort": 9999}]
                },
            }
        ]
    }

    ing_faults, tp_faults = detect_ingress_and_targetport_faults(
        services_json=services,
        namespace="social-network",
    )

    assert len(ing_faults) == 0
    assert len(tp_faults) == 1
    fault = tp_faults[0]
    assert fault.service_name == "user-service"
    assert fault.observed_target_port == 9999
    assert fault.expected_target_port == 9090

    cmds, deps = decide_ingress_targetport_remediation_commands(ing_faults, tp_faults, namespace="social-network")
    assert len(cmds) == 1
    assert "kubectl patch service user-service" in cmds[0]
    assert "9090" in cmds[0]
    assert "user-service" in deps


# =============================================================================
# Category 3: CronJob / Scheduled Mutations
# =============================================================================

def test_cronjob_mutation_detection_and_remediation():
    cronjobs = {
        "items": [
            {
                "metadata": {"name": "vpa-updater", "namespace": "kube-system"},
                "spec": {
                    "schedule": "* * * * *",
                    "jobTemplate": {
                        "spec": {
                            "template": {
                                "spec": {
                                    "containers": [
                                        {
                                            "name": "patch",
                                            "command": ["sh", "-c", 'kubectl patch deployment "$TARGET" -p "$PATCH"'],
                                            "envFrom": [{"configMapRef": {"name": "vpa-updater-policy"}}],
                                        }
                                    ]
                                }
                            }
                        }
                    },
                },
            }
        ]
    }

    deployments = {
        "items": [
            {
                "metadata": {"name": "recommendation", "namespace": "hotel-reservation"},
                "spec": {
                    "template": {
                        "spec": {
                            "containers": [
                                {
                                    "name": "recommendation",
                                    "resources": {"limits": {"memory": "4Mi"}},
                                }
                            ]
                        }
                    }
                },
            }
        ]
    }

    configmaps = {
        "items": [
            {
                "metadata": {"name": "vpa-updater-policy", "namespace": "kube-system"},
                "data": {
                    "TARGET": "recommendation",
                    "PATCH": '{"spec":{"template":{"spec":{"containers":[{"name":"recommendation","resources":{"limits":{"memory":"4Mi"}}}]}}}}',
                },
            }
        ]
    }

    faults = detect_cronjob_mutations(
        cronjobs_json=cronjobs,
        deployments_json=deployments,
        configmaps_json=configmaps,
        namespace="hotel-reservation",
    )

    assert len(faults) == 1
    fault = faults[0]
    assert fault.cronjob_name == "vpa-updater"
    assert fault.cronjob_namespace == "kube-system"
    assert fault.victim_deployment == "recommendation"

    cmds, deps = decide_cronjob_remediation_commands([fault], namespace="hotel-reservation")
    assert any("kubectl patch cronjob vpa-updater -n kube-system -p '{\"spec\":{\"suspend\":true}}'" in c for c in cmds)
    assert any("kubectl delete cronjob vpa-updater -n kube-system" in c for c in cmds)
    assert any("kubectl patch deployment recommendation -n hotel-reservation" in c for c in cmds)
    assert "recommendation" in deps


# =============================================================================
# Category 4: Pod Anti-Affinity & Scheduling Deadlocks (B1)
# =============================================================================

def test_scheduling_deadlock_detection_and_remediation():
    deployments = {
        "items": [
            {
                "metadata": {"name": "user-service", "namespace": "social-network"},
                "spec": {
                    "replicas": 3,
                    "template": {
                        "spec": {
                            "affinity": {
                                "podAntiAffinity": {
                                    "requiredDuringSchedulingIgnoredDuringExecution": [
                                        {"topologyKey": "kubernetes.io/hostname"}
                                    ]
                                }
                            },
                            "nodeSelector": {"extra-node": "true"},
                        }
                    },
                },
                "status": {"readyReplicas": 0},
            }
        ]
    }

    events = {
        "items": [
            {
                "reason": "FailedScheduling",
                "message": "0/1 nodes available: 1 node(s) didn't match pod anti-affinity rules",
                "involvedObject": {"name": "user-service-68749b5c77-x49p2"},
            }
        ]
    }

    faults = detect_scheduling_deadlocks(
        deployments_json=deployments,
        events_json=events,
        namespace="social-network",
    )

    assert len(faults) == 1
    fault = faults[0]
    assert fault.deployment_name == "user-service"
    assert fault.constraint_type == "both"

    cmds, deps = decide_scheduling_remediation_commands([fault], namespace="social-network")
    assert any("/spec/template/spec/affinity/podAntiAffinity" in c for c in cmds)
    assert any("/spec/template/spec/nodeSelector" in c for c in cmds)
    assert "user-service" in deps


# =============================================================================
# Category 5: CoreDNS & Service Discovery Faults
# =============================================================================

def test_coredns_fault_detection_and_remediation():
    corrupted_corefile = """
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
    prometheus :9153
    forward . /etc/resolv.conf
    cache 30
    loop
    reload
    loadbalance
}
"""
    configmaps = {
        "items": [
            {
                "metadata": {"name": "coredns", "namespace": "kube-system"},
                "data": {"Corefile": corrupted_corefile},
            }
        ]
    }

    faults = detect_coredns_faults(configmaps_json=configmaps, namespace="kube-system")

    assert len(faults) == 1
    fault = faults[0]
    assert fault.configmap_name == "coredns"
    assert fault.fault_kind == "nxdomain_template"
    assert "rcode NXDOMAIN" not in fault.repaired_corefile
    assert "template ANY ANY svc.cluster.local" not in fault.repaired_corefile

    cmds, deps = decide_coredns_remediation_commands([fault], namespace="kube-system")
    assert any("kubectl apply -f -" in c for c in cmds)
    assert any("kubectl rollout restart deployment/coredns -n kube-system" in c for c in cmds)
    assert "coredns" in deps


# =============================================================================
# Category 6: Workload & Rolling Update Misconfigurations
# =============================================================================

def test_workload_resource_request_too_large_detection_and_remediation():
    deployments = {
        "items": [
            {
                "metadata": {"name": "mongodb-rate", "namespace": "hotel-reservation"},
                "spec": {
                    "replicas": 1,
                    "template": {
                        "spec": {
                            "containers": [
                                {
                                    "name": "mongodb-rate",
                                    "resources": {"requests": {"memory": "500Gi", "cpu": "128"}},
                                }
                            ]
                        }
                    },
                },
                "status": {"readyReplicas": 0},
            }
        ]
    }

    events = {
        "items": [
            {
                "reason": "FailedScheduling",
                "message": "0/1 nodes available: 1 Insufficient memory, 1 Insufficient cpu.",
                "involvedObject": {"name": "mongodb-rate-5768cb47d9-x8j2l"},
            }
        ]
    }

    faults = detect_workload_and_rolling_update_misconfigs(
        deployments_json=deployments,
        events_json=events,
        namespace="hotel-reservation",
    )

    assert len(faults) >= 1
    fault = next(f for f in faults if f.fault_kind == "resource_request_too_large")
    assert fault.deployment_name == "mongodb-rate"

    cmds, deps = decide_workload_remediation_commands([fault], namespace="hotel-reservation")
    assert any("kubectl patch deployment mongodb-rate" in c for c in cmds)
    assert any("remove" in c and "requests" in c for c in cmds)
    assert "mongodb-rate" in deps


def test_rolling_update_misconfigured_detection_and_remediation():
    deployments = {
        "items": [
            {
                "metadata": {"name": "recommendation", "namespace": "hotel-reservation"},
                "spec": {
                    "strategy": {
                        "type": "RollingUpdate",
                        "rollingUpdate": {"maxUnavailable": "100%", "maxSurge": "0%"},
                    },
                    "template": {
                        "spec": {
                            "initContainers": [
                                {
                                    "name": "hang-init",
                                    "image": "busybox",
                                    "command": ["/bin/sh", "-c", "sleep infinity"],
                                }
                            ],
                            "containers": [
                                {"name": "recommendation", "image": "ghcr.io/sregym/hotel-reservation:latest"}
                            ],
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
    fault = faults[0]
    assert fault.deployment_name == "recommendation"
    assert fault.fault_kind == "rolling_update_misconfigured"

    cmds, deps = decide_workload_remediation_commands([fault], namespace="hotel-reservation")
    assert any("maxSurge" in c and "25%" in c for c in cmds)
    assert any("remove" in c and "initContainers" in c for c in cmds)
    assert "recommendation" in deps


# =============================================================================
# Composite Engine Multi-Fault Integration Test
# =============================================================================

def test_composite_engine_m3_full_integration():
    engine = CompositePlannerEngine(namespace="hotel-reservation", app_name="Hotel Reservation")

    deployments = {
        "items": [
            {
                "metadata": {"name": "geo", "namespace": "hotel-reservation"},
                "spec": {
                    "template": {
                        "spec": {
                            "volumes": [{"name": "cfg", "configMap": {"name": "geo-config"}}]
                        }
                    }
                },
            },
            {
                "metadata": {"name": "recommendation", "namespace": "hotel-reservation"},
                "spec": {
                    "strategy": {
                        "type": "RollingUpdate",
                        "rollingUpdate": {"maxUnavailable": "100%", "maxSurge": "0%"},
                    },
                    "template": {
                        "spec": {
                            "initContainers": [{"name": "hang-init", "command": ["sleep infinity"]}]
                        }
                    },
                },
            },
        ]
    }

    configmaps = {
        "items": [
            {
                "metadata": {"name": "geo-config", "namespace": "hotel-reservation"},
                "data": {"config.json": "{}"},  # Missing GeoMongoAddress
            },
            {
                "metadata": {"name": "coredns", "namespace": "kube-system"},
                "data": {
                    "Corefile": "template ANY ANY svc.cluster.local {\n rcode NXDOMAIN\n}"
                },
            },
        ]
    }

    ingresses = {
        "items": [
            {
                "metadata": {"name": "hotel-reservation-ingress", "namespace": "hotel-reservation"},
                "spec": {
                    "rules": [
                        {
                            "http": {
                                "paths": [
                                    {
                                        "path": "/api",
                                        "backend": {"service": {"name": "recommendation-service"}},
                                    }
                                ]
                            }
                        }
                    ]
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
                                    "containers": [{"command": ["kubectl", "patch", "deployment", "recommendation"]}]
                                }
                            }
                        }
                    }
                },
            }
        ]
    }

    diag = engine.run_diagnosis(
        deployments_json=deployments,
        configmaps_json=configmaps,
        ingresses_json=ingresses,
        cronjobs_json=cronjobs,
    )

    assert len(diag.missing_objects) >= 1
    assert len(diag.ingress_misroutes) >= 1
    assert len(diag.cronjob_mutations) >= 1
    assert len(diag.coredns_faults) >= 1
    assert len(diag.workload_misconfigs) >= 1

    mit = engine.run_mitigation(diag)
    assert len(mit.commands) >= 5
    assert len(mit.rollout_wait_deployments) >= 2
    assert "geo" in mit.rollout_wait_deployments
    assert "recommendation" in mit.rollout_wait_deployments
