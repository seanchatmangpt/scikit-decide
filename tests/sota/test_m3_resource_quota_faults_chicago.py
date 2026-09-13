"""Chicago-style zero-mock unit and integration tests for ResourceQuota exhaustion
and LimitRange violation fault mechanisms.

Strict zero-mock policy: NO unittest.mock, NO Mock, NO MagicMock, NO patch, NO monkeypatch.
All tests exercise pure functions with real Python data structures shaped exactly like
`kubectl get resourcequota -o json` / `kubectl get limitrange -o json` / `kubectl get
deployment -o json` output.

Mechanism ground truth: neither ResourceQuota (namespace-wide aggregate ceiling) nor
LimitRange (per-container min/max policy bound) is present as an explicit `inject_*`
method in vendor/gyms/sregym/sregym/generators/fault/inject_virtual.py -- the closest
related mechanism there is V.8 `inject_resource_request` (line 323), which mutates a
single deployment's own resources directly and has no namespace-policy-object awareness.
`resource_request_too_large` (`WorkloadMisconfigFault.fault_kind`, already built in
`rolling_update_misconfig.py`) covers that single-deployment case; these two detectors
cover the genuinely distinct namespace-policy-object mechanisms: quota exhaustion and
LimitRange bound violation.
"""

from __future__ import annotations

from autofde_lab_planner.detectors.limitrange_violation import detect_limitrange_violations
from autofde_lab_planner.detectors.resourcequota_exhaustion import detect_resourcequota_exhaustion
from autofde_lab_planner.engine import CompositePlannerEngine
from autofde_lab_planner.models import LimitRangeViolationFault, ResourceQuotaExhaustionFault
from autofde_lab_planner.remediators.limitrange_violation import decide_limitrange_remediation_commands
from autofde_lab_planner.remediators.resourcequota_exhaustion import decide_resourcequota_remediation_commands


# =============================================================================
# ResourceQuota Exhaustion
# =============================================================================

def test_resourcequota_exceeded_detection_and_remediation():
    resourcequotas = {
        "items": [
            {
                "metadata": {"name": "compute-quota", "namespace": "checkout"},
                "status": {
                    "hard": {"requests.cpu": "4", "pods": "10"},
                    "used": {"requests.cpu": "4", "pods": "6"},
                },
            }
        ]
    }
    events = {
        "items": [
            {
                "reason": "FailedCreate",
                "message": "pods \"checkout-service-abc123\" is forbidden: exceeded quota: "
                "compute-quota, requested: requests.cpu=500m, used: requests.cpu=4, limited: requests.cpu=4",
                "involvedObject": {"name": "checkout-service"},
            }
        ]
    }

    faults = detect_resourcequota_exhaustion(
        resourcequotas_json=resourcequotas,
        events_json=events,
        namespace="checkout",
    )

    assert len(faults) == 1
    fault = faults[0]
    assert isinstance(fault, ResourceQuotaExhaustionFault)
    assert fault.quota_name == "compute-quota"
    assert fault.resource_name == "requests.cpu"
    assert fault.fault_kind == "exceeded"
    assert fault.used_ratio == 1.0
    assert fault.blocked_deployment == "checkout-service"

    cmds, deps = decide_resourcequota_remediation_commands([fault], namespace="checkout")
    assert any("kubectl patch resourcequota compute-quota" in c and "requests.cpu" in c for c in cmds)
    assert any('"hard": {"requests.cpu": "6"' in c for c in cmds)
    assert any("rollout restart deployment/checkout-service" in c for c in cmds)
    assert "checkout-service" in deps


def test_resourcequota_near_exhaustion_detection():
    resourcequotas = {
        "items": [
            {
                "metadata": {"name": "mem-quota", "namespace": "cart"},
                "status": {
                    "hard": {"requests.memory": "1Gi"},
                    "used": {"requests.memory": "950Mi"},
                },
            }
        ]
    }

    faults = detect_resourcequota_exhaustion(
        resourcequotas_json=resourcequotas,
        namespace="cart",
    )

    assert len(faults) == 1
    assert faults[0].fault_kind == "near_exhaustion"
    assert faults[0].used_ratio >= 0.9
    assert faults[0].blocked_deployment is None


def test_resourcequota_healthy_produces_no_fault():
    resourcequotas = {
        "items": [
            {
                "metadata": {"name": "healthy-quota", "namespace": "cart"},
                "status": {
                    "hard": {"requests.cpu": "10"},
                    "used": {"requests.cpu": "2"},
                },
            }
        ]
    }

    faults = detect_resourcequota_exhaustion(resourcequotas_json=resourcequotas, namespace="cart")
    assert faults == []


# =============================================================================
# LimitRange Violation
# =============================================================================

def test_limitrange_below_min_detection_and_remediation():
    limitranges = {
        "items": [
            {
                "metadata": {"name": "container-limits", "namespace": "payments"},
                "spec": {
                    "limits": [
                        {
                            "type": "Container",
                            "min": {"cpu": "100m", "memory": "64Mi"},
                            "max": {"cpu": "2", "memory": "2Gi"},
                        }
                    ]
                },
            }
        ]
    }
    deployments = {
        "items": [
            {
                "metadata": {"name": "payment-worker", "namespace": "payments"},
                "spec": {
                    "template": {
                        "spec": {
                            "containers": [
                                {
                                    "name": "worker",
                                    "resources": {"requests": {"cpu": "50m", "memory": "128Mi"}},
                                }
                            ]
                        }
                    }
                },
            }
        ]
    }

    faults = detect_limitrange_violations(
        limitranges_json=limitranges,
        deployments_json=deployments,
        namespace="payments",
    )

    assert len(faults) == 1
    fault = faults[0]
    assert isinstance(fault, LimitRangeViolationFault)
    assert fault.deployment_name == "payment-worker"
    assert fault.container_name == "worker"
    assert fault.resource_name == "cpu"
    assert fault.fault_kind == "below_min"
    assert fault.observed_value == "50m"
    assert fault.bound_value == "100m"

    cmds, deps = decide_limitrange_remediation_commands([fault], namespace="payments")
    assert any("kubectl patch deployment payment-worker" in c and "requests/cpu" in c and "100m" in c for c in cmds)
    assert any("rollout restart deployment/payment-worker" in c for c in cmds)
    assert "payment-worker" in deps


def test_limitrange_above_max_detection():
    limitranges = {
        "items": [
            {
                "metadata": {"name": "container-limits", "namespace": "payments"},
                "spec": {
                    "limits": [
                        {
                            "type": "Container",
                            "max": {"memory": "1Gi"},
                        }
                    ]
                },
            }
        ]
    }
    deployments = {
        "items": [
            {
                "metadata": {"name": "oversized-worker", "namespace": "payments"},
                "spec": {
                    "template": {
                        "spec": {
                            "containers": [
                                {
                                    "name": "worker",
                                    "resources": {"requests": {"memory": "4Gi"}},
                                }
                            ]
                        }
                    }
                },
            }
        ]
    }

    faults = detect_limitrange_violations(
        limitranges_json=limitranges,
        deployments_json=deployments,
        namespace="payments",
    )

    assert len(faults) == 1
    assert faults[0].fault_kind == "above_max"
    assert faults[0].resource_name == "memory"
    assert faults[0].observed_value == "4Gi"
    assert faults[0].bound_value == "1Gi"


def test_limitrange_missing_default_detection():
    limitranges = {
        "items": [
            {
                "metadata": {"name": "container-limits", "namespace": "payments"},
                "spec": {
                    "limits": [
                        {
                            "type": "Container",
                            "min": {"cpu": "100m"},
                            "max": {"cpu": "2"},
                        }
                    ]
                },
            }
        ]
    }
    deployments = {
        "items": [
            {
                "metadata": {"name": "bare-worker", "namespace": "payments"},
                "spec": {
                    "template": {
                        "spec": {"containers": [{"name": "worker", "resources": {}}]}
                    }
                },
            }
        ]
    }

    faults = detect_limitrange_violations(
        limitranges_json=limitranges,
        deployments_json=deployments,
        namespace="payments",
    )

    assert len(faults) == 1
    assert faults[0].fault_kind == "missing_default"
    assert faults[0].resource_name == "cpu"
    assert faults[0].observed_value is None


def test_limitrange_within_bounds_produces_no_fault():
    limitranges = {
        "items": [
            {
                "metadata": {"name": "container-limits", "namespace": "payments"},
                "spec": {
                    "limits": [
                        {"type": "Container", "min": {"cpu": "50m"}, "max": {"cpu": "2"}}
                    ]
                },
            }
        ]
    }
    deployments = {
        "items": [
            {
                "metadata": {"name": "fine-worker", "namespace": "payments"},
                "spec": {
                    "template": {
                        "spec": {
                            "containers": [
                                {"name": "worker", "resources": {"requests": {"cpu": "200m"}}}
                            ]
                        }
                    }
                },
            }
        ]
    }

    faults = detect_limitrange_violations(
        limitranges_json=limitranges,
        deployments_json=deployments,
        namespace="payments",
    )
    assert faults == []


# =============================================================================
# CompositePlannerEngine integration
# =============================================================================

def test_composite_engine_resource_quota_and_limitrange_integration():
    deployments = {
        "items": [
            {
                "metadata": {"name": "worker", "namespace": "checkout"},
                "spec": {
                    "template": {
                        "spec": {
                            "containers": [
                                {"name": "worker", "resources": {"requests": {"cpu": "50m"}}}
                            ]
                        }
                    }
                },
            }
        ]
    }
    resourcequotas = {
        "items": [
            {
                "metadata": {"name": "compute-quota", "namespace": "checkout"},
                "status": {
                    "hard": {"requests.cpu": "4"},
                    "used": {"requests.cpu": "4"},
                },
            }
        ]
    }
    limitranges = {
        "items": [
            {
                "metadata": {"name": "container-limits", "namespace": "checkout"},
                "spec": {"limits": [{"type": "Container", "min": {"cpu": "100m"}}]},
            }
        ]
    }

    engine = CompositePlannerEngine(namespace="checkout")
    diagnosis = engine.run_diagnosis(
        deployments_json=deployments,
        resourcequotas_json=resourcequotas,
        limitranges_json=limitranges,
    )

    assert len(diagnosis.resourcequota_exhaustions) == 1
    assert diagnosis.resourcequota_exhaustions[0].fault_kind == "exceeded"
    assert len(diagnosis.limitrange_violations) == 1
    assert diagnosis.limitrange_violations[0].fault_kind == "below_min"
    assert "ResourceQuota exhaustion" in diagnosis.diagnosis_text
    assert "LimitRange violations" in diagnosis.diagnosis_text

    mitigation = engine.run_mitigation(diagnosis)
    assert any("kubectl patch resourcequota compute-quota" in c for c in mitigation.commands)
    assert any("kubectl patch deployment worker" in c for c in mitigation.commands)
    assert "worker" in mitigation.rollout_wait_deployments
