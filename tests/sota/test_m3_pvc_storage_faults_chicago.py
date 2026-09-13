"""Chicago-style zero-mock unit and integration tests for PVC/storage fault mechanisms.

Ground truth: `vendor/gyms/sregym/sregym/generators/fault/inject_virtual.py`
`inject_pvc_claim_mismatch` (dangling claimName) and `inject_duplicate_pvc_mounts`
(single ReadWriteOnce PVC shared by multiple replicas -> Multi-Attach conflict).

Strict zero-mock policy: NO unittest.mock, NO Mock, NO MagicMock, NO patch, NO monkeypatch.
All tests exercise pure functions with real Python dict/JSON-shaped k8s manifests, and
assert on real returned dataclass state and real command strings -- never interactions.
"""

from __future__ import annotations

from autofde_lab_planner.detectors.pvc_storage_faults import (
    detect_pvc_claim_mismatches,
    detect_pvc_multi_attach_faults,
)
from autofde_lab_planner.engine import CompositePlannerEngine
from autofde_lab_planner.models import PVCClaimMismatchFault, PVCMultiAttachFault
from autofde_lab_planner.remediators.pvc_storage_faults import (
    decide_pvc_claim_mismatch_commands,
    decide_pvc_multi_attach_commands,
)


# =============================================================================
# Storage-1: PVC Claim Mismatch (dangling claimName)
# =============================================================================

def test_pvc_claim_mismatch_detection_and_remediation():
    deployments = {
        "items": [
            {
                "metadata": {"name": "cart-service", "namespace": "astronomy-shop"},
                "spec": {
                    "replicas": 2,
                    "template": {
                        "spec": {
                            "containers": [{"name": "cart"}],
                            "volumes": [
                                {
                                    "name": "cart-volume",
                                    "persistentVolumeClaim": {"claimName": "cart-service-pvc-broken"},
                                }
                            ],
                        }
                    },
                },
                "status": {"readyReplicas": 0},
            }
        ]
    }

    # The real PVC in the namespace is "cart-service-pvc" -- the deployment's
    # claimName ("cart-service-pvc-broken") does not match any live PVC.
    pvcs = {
        "items": [
            {
                "metadata": {"name": "cart-service-pvc", "namespace": "astronomy-shop"},
                "spec": {"accessModes": ["ReadWriteOnce"]},
            }
        ]
    }

    pods = {
        "items": [
            {
                "metadata": {"name": "cart-service-abc12", "labels": {"app": "cart-service"}},
                "status": {"phase": "Pending"},
            }
        ]
    }

    faults = detect_pvc_claim_mismatches(
        deployments_json=deployments,
        pvcs_json=pvcs,
        pods_json=pods,
        namespace="astronomy-shop",
    )

    assert len(faults) == 1
    fault = faults[0]
    assert isinstance(fault, PVCClaimMismatchFault)
    assert fault.deployment_name == "cart-service"
    assert fault.namespace == "astronomy-shop"
    assert fault.volume_name == "cart-volume"
    assert fault.observed_claim_name == "cart-service-pvc-broken"
    assert fault.expected_claim_name == "cart-service-pvc"
    assert fault.container_name == "cart"
    assert fault.unready_replicas >= 1
    assert fault.desired_replicas == 2

    cmds, deps = decide_pvc_claim_mismatch_commands([fault], namespace="astronomy-shop")
    assert any("persistentVolumeClaim/claimName" in c and "cart-service-pvc" in c for c in cmds)
    assert any(c.endswith('"value": "cart-service-pvc"}]\'') for c in cmds)
    assert any("kubectl rollout restart deployment/cart-service" in c for c in cmds)
    assert deps == ["cart-service"]


def test_pvc_claim_mismatch_no_inferrable_expected_name_recreates_pvc():
    deployments = {
        "items": [
            {
                "metadata": {"name": "checkout-service", "namespace": "default"},
                "spec": {
                    "replicas": 1,
                    "template": {
                        "spec": {
                            "containers": [{"name": "checkout"}],
                            "volumes": [
                                {
                                    "name": "data",
                                    "persistentVolumeClaim": {"claimName": "checkout-data-claim"},
                                }
                            ],
                        }
                    },
                },
                "status": {"readyReplicas": 0},
            }
        ]
    }
    # No PVC exists at all, and the claimName doesn't carry the "-broken" suffix
    # convention, so we cannot infer the pre-fault name -- the remediator must
    # instead re-create the missing PVC.
    faults = detect_pvc_claim_mismatches(deployments_json=deployments, pvcs_json=None, namespace="default")

    assert len(faults) == 1
    fault = faults[0]
    assert fault.observed_claim_name == "checkout-data-claim"
    assert fault.expected_claim_name is None

    cmds, deps = decide_pvc_claim_mismatch_commands([fault], namespace="default")
    assert any("kind: PersistentVolumeClaim" in c and "checkout-data-claim" in c for c in cmds)
    assert deps == ["checkout-service"]


def test_pvc_claim_mismatch_matching_claim_produces_no_fault():
    deployments = {
        "items": [
            {
                "metadata": {"name": "healthy-service", "namespace": "default"},
                "spec": {
                    "replicas": 1,
                    "template": {
                        "spec": {
                            "containers": [{"name": "app"}],
                            "volumes": [
                                {"name": "data", "persistentVolumeClaim": {"claimName": "healthy-pvc"}}
                            ],
                        }
                    },
                },
                "status": {"readyReplicas": 1},
            }
        ]
    }
    pvcs = {"items": [{"metadata": {"name": "healthy-pvc", "namespace": "default"}, "spec": {}}]}

    faults = detect_pvc_claim_mismatches(deployments_json=deployments, pvcs_json=pvcs, namespace="default")
    assert faults == []


# =============================================================================
# Storage-2: PVC Multi-Attach (shared ReadWriteOnce volume across replicas)
# =============================================================================

def test_pvc_multi_attach_detection_and_remediation():
    deployments = {
        "items": [
            {
                "metadata": {"name": "shipping-service", "namespace": "astronomy-shop"},
                "spec": {
                    "replicas": 2,
                    "template": {
                        "spec": {
                            "volumes": [
                                {
                                    "name": "shipping-volume",
                                    "persistentVolumeClaim": {"claimName": "shipping-service-pvc"},
                                }
                            ],
                            "affinity": {
                                "podAntiAffinity": {
                                    "requiredDuringSchedulingIgnoredDuringExecution": [
                                        {"topologyKey": "kubernetes.io/hostname"}
                                    ]
                                }
                            },
                        }
                    },
                },
            }
        ]
    }

    pvcs = {
        "items": [
            {
                "metadata": {"name": "shipping-service-pvc", "namespace": "astronomy-shop"},
                "spec": {"accessModes": ["ReadWriteOnce"]},
            }
        ]
    }

    events = {
        "items": [
            {
                "reason": "FailedAttachVolume",
                "message": "Multi-Attach error for volume \"pvc-abc\" Volume is already exclusively attached to one node",
                "involvedObject": {"name": "shipping-service-pvc", "kind": "PersistentVolumeClaim"},
            }
        ]
    }

    faults = detect_pvc_multi_attach_faults(
        deployments_json=deployments,
        pvcs_json=pvcs,
        events_json=events,
        namespace="astronomy-shop",
    )

    assert len(faults) == 1
    fault = faults[0]
    assert isinstance(fault, PVCMultiAttachFault)
    assert fault.deployment_name == "shipping-service"
    assert fault.pvc_name == "shipping-service-pvc"
    assert fault.access_modes == ("ReadWriteOnce",)
    assert fault.desired_replicas == 2
    assert fault.has_anti_affinity is True
    assert len(fault.multi_attach_events) == 1
    assert "Multi-Attach error" in fault.multi_attach_events[0]

    cmds, deps = decide_pvc_multi_attach_commands([fault], namespace="astronomy-shop")
    assert any("kubectl scale deployment shipping-service -n astronomy-shop --replicas=1" in c for c in cmds)
    assert any("/spec/template/spec/affinity/podAntiAffinity" in c for c in cmds)
    assert any("kubectl rollout restart deployment/shipping-service" in c for c in cmds)
    assert deps == ["shipping-service"]


def test_pvc_multi_attach_single_replica_no_fault():
    deployments = {
        "items": [
            {
                "metadata": {"name": "single-service", "namespace": "default"},
                "spec": {
                    "replicas": 1,
                    "template": {
                        "spec": {
                            "volumes": [
                                {"name": "vol", "persistentVolumeClaim": {"claimName": "single-pvc"}}
                            ]
                        }
                    },
                },
            }
        ]
    }
    pvcs = {"items": [{"metadata": {"name": "single-pvc"}, "spec": {"accessModes": ["ReadWriteOnce"]}}]}

    faults = detect_pvc_multi_attach_faults(deployments_json=deployments, pvcs_json=pvcs, namespace="default")
    assert faults == []


def test_pvc_multi_attach_readwritemany_no_fault():
    deployments = {
        "items": [
            {
                "metadata": {"name": "shared-service", "namespace": "default"},
                "spec": {
                    "replicas": 3,
                    "template": {
                        "spec": {
                            "volumes": [
                                {"name": "vol", "persistentVolumeClaim": {"claimName": "shared-pvc"}}
                            ]
                        }
                    },
                },
            }
        ]
    }
    # ReadWriteMany legitimately supports concurrent multi-node attach.
    pvcs = {"items": [{"metadata": {"name": "shared-pvc"}, "spec": {"accessModes": ["ReadWriteMany"]}}]}

    faults = detect_pvc_multi_attach_faults(deployments_json=deployments, pvcs_json=pvcs, namespace="default")
    assert faults == []


# =============================================================================
# Composite engine integration
# =============================================================================

def test_composite_engine_storage_fault_integration():
    deployments = {
        "items": [
            {
                "metadata": {"name": "payment-service", "namespace": "astronomy-shop"},
                "spec": {
                    "replicas": 2,
                    "template": {
                        "spec": {
                            "containers": [{"name": "payment"}],
                            "volumes": [
                                {
                                    "name": "vol",
                                    "persistentVolumeClaim": {"claimName": "payment-service-pvc-broken"},
                                }
                            ],
                        }
                    },
                },
                "status": {"readyReplicas": 0},
            },
            {
                "metadata": {"name": "review-service", "namespace": "astronomy-shop"},
                "spec": {
                    "replicas": 2,
                    "template": {
                        "spec": {
                            "volumes": [
                                {
                                    "name": "vol",
                                    "persistentVolumeClaim": {"claimName": "review-service-pvc"},
                                }
                            ]
                        }
                    },
                },
            },
        ]
    }

    pvcs = {
        "items": [
            {
                "metadata": {"name": "payment-service-pvc", "namespace": "astronomy-shop"},
                "spec": {"accessModes": ["ReadWriteOnce"]},
            },
            {
                "metadata": {"name": "review-service-pvc", "namespace": "astronomy-shop"},
                "spec": {"accessModes": ["ReadWriteOnce"]},
            },
        ]
    }

    engine = CompositePlannerEngine(namespace="astronomy-shop")
    diagnosis = engine.run_diagnosis(deployments_json=deployments, pvcs_json=pvcs)

    assert len(diagnosis.pvc_claim_mismatches) == 1
    assert diagnosis.pvc_claim_mismatches[0].deployment_name == "payment-service"

    assert len(diagnosis.pvc_multi_attach_faults) == 1
    assert diagnosis.pvc_multi_attach_faults[0].deployment_name == "review-service"

    assert "dangling PVC claim" in diagnosis.diagnosis_text
    assert "multi-attach" in diagnosis.diagnosis_text.lower()

    mitigation = engine.run_mitigation(diagnosis)
    assert any("payment-service-pvc" in c for c in mitigation.commands)
    assert any("kubectl scale deployment review-service" in c for c in mitigation.commands)
    assert "payment-service" in mitigation.rollout_wait_deployments
    assert "review-service" in mitigation.rollout_wait_deployments
