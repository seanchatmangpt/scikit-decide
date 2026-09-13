"""Chicago-style zero-mock unit tests for the RBAC misconfiguration fault mechanism.

Ground truth: ``inject_rbac_misconfiguration`` in
``vendor/gyms/sregym/sregym/generators/fault/inject_virtual.py`` (lines
2394-2467) -- binds a Deployment's pod spec to a dedicated ServiceAccount
whose ClusterRole grants only ``pods``/``services`` get/list/watch (no
``configmaps``), then adds an init container running
``kubectl get configmap app-routing-config -n <ns> -o json``, which 403s.

Strict zero-mock policy: NO unittest.mock, NO Mock, NO MagicMock, NO patch,
NO monkeypatch. All tests exercise pure functions with real Python dict/list
data structures shaped exactly like ``kubectl get <kind> -o json`` output.
"""

from __future__ import annotations

from autofde_lab_planner.detectors.rbac_misconfig import detect_rbac_misconfigurations
from autofde_lab_planner.engine import CompositePlannerEngine
from autofde_lab_planner.models import RBACMisconfigFault
from autofde_lab_planner.remediators.rbac_misconfig import decide_rbac_remediation_commands


def _base_deployment(sa_name: str = "checkout-rbac-sa") -> dict:
    return {
        "metadata": {"name": "checkout", "namespace": "hotel-reservation"},
        "spec": {
            "template": {
                "spec": {
                    "serviceAccountName": sa_name,
                    "initContainers": [
                        {
                            "name": "config-loader",
                            "image": "alpine/k8s:1.28.3",
                            "command": [
                                "kubectl",
                                "get",
                                "configmap",
                                "app-routing-config",
                                "-n",
                                "hotel-reservation",
                                "-o",
                                "json",
                            ],
                        }
                    ],
                    "containers": [{"name": "checkout", "image": "checkout:latest"}],
                }
            }
        },
    }


# =============================================================================
# Detector: missing_rbac_permission (the real sregym mechanism)
# =============================================================================

def test_detects_missing_configmaps_permission_matching_sregym_injector():
    deployments = {"items": [_base_deployment()]}
    service_accounts = {
        "items": [{"metadata": {"name": "checkout-rbac-sa", "namespace": "hotel-reservation"}}]
    }
    cluster_roles = {
        "items": [
            {
                "metadata": {"name": "checkout-rbac-role"},
                "rules": [
                    {
                        "apiGroups": [""],
                        "resources": ["pods", "services"],
                        "verbs": ["get", "list", "watch"],
                    }
                ],
            }
        ]
    }
    cluster_role_bindings = {
        "items": [
            {
                "metadata": {"name": "checkout-rbac-binding"},
                "roleRef": {
                    "apiGroup": "rbac.authorization.k8s.io",
                    "kind": "ClusterRole",
                    "name": "checkout-rbac-role",
                },
                "subjects": [
                    {
                        "kind": "ServiceAccount",
                        "name": "checkout-rbac-sa",
                        "namespace": "hotel-reservation",
                    }
                ],
            }
        ]
    }

    faults = detect_rbac_misconfigurations(
        deployments_json=deployments,
        service_accounts_json=service_accounts,
        cluster_roles_json=cluster_roles,
        cluster_role_bindings_json=cluster_role_bindings,
        namespace="hotel-reservation",
    )

    assert len(faults) == 1
    f = faults[0]
    assert isinstance(f, RBACMisconfigFault)
    assert f.deployment_name == "checkout"
    assert f.namespace == "hotel-reservation"
    assert f.service_account_name == "checkout-rbac-sa"
    assert f.fault_kind == "missing_rbac_permission"
    assert f.missing_resources == ("configmaps",)
    assert "get" in f.missing_verbs
    assert f.cluster_role_name == "checkout-rbac-role"
    assert f.cluster_role_binding_name == "checkout-rbac-binding"
    assert "configmaps" in f.details


def test_no_fault_when_configmaps_permission_present():
    deployments = {"items": [_base_deployment()]}
    service_accounts = {
        "items": [{"metadata": {"name": "checkout-rbac-sa", "namespace": "hotel-reservation"}}]
    }
    cluster_roles = {
        "items": [
            {
                "metadata": {"name": "checkout-rbac-role"},
                "rules": [
                    {
                        "apiGroups": [""],
                        "resources": ["pods", "services", "configmaps"],
                        "verbs": ["get", "list", "watch"],
                    }
                ],
            }
        ]
    }
    cluster_role_bindings = {
        "items": [
            {
                "metadata": {"name": "checkout-rbac-binding"},
                "roleRef": {"name": "checkout-rbac-role"},
                "subjects": [{"kind": "ServiceAccount", "name": "checkout-rbac-sa"}],
            }
        ]
    }

    faults = detect_rbac_misconfigurations(
        deployments_json=deployments,
        service_accounts_json=service_accounts,
        cluster_roles_json=cluster_roles,
        cluster_role_bindings_json=cluster_role_bindings,
        namespace="hotel-reservation",
    )

    assert faults == []


# =============================================================================
# Detector: missing_service_account
# =============================================================================

def test_detects_missing_service_account():
    deployments = {"items": [_base_deployment(sa_name="ghost-sa")]}
    faults = detect_rbac_misconfigurations(
        deployments_json=deployments,
        service_accounts_json={"items": []},
        cluster_roles_json={"items": []},
        cluster_role_bindings_json={"items": []},
        namespace="hotel-reservation",
    )
    assert len(faults) == 1
    assert faults[0].fault_kind == "missing_service_account"
    assert faults[0].service_account_name == "ghost-sa"


# =============================================================================
# Detector: missing_role_binding
# =============================================================================

def test_detects_missing_role_binding():
    deployments = {"items": [_base_deployment(sa_name="orphan-sa")]}
    service_accounts = {"items": [{"metadata": {"name": "orphan-sa", "namespace": "hotel-reservation"}}]}
    faults = detect_rbac_misconfigurations(
        deployments_json=deployments,
        service_accounts_json=service_accounts,
        cluster_roles_json={"items": []},
        cluster_role_bindings_json={"items": []},
        namespace="hotel-reservation",
    )
    assert len(faults) == 1
    assert faults[0].fault_kind == "missing_role_binding"
    assert faults[0].service_account_name == "orphan-sa"


# =============================================================================
# Remediator
# =============================================================================

def test_remediation_commands_for_missing_permission():
    fault = RBACMisconfigFault(
        deployment_name="checkout",
        namespace="hotel-reservation",
        service_account_name="checkout-rbac-sa",
        fault_kind="missing_rbac_permission",
        missing_resources=("configmaps",),
        missing_verbs=("get", "list", "watch"),
        cluster_role_name="checkout-rbac-role",
        cluster_role_binding_name="checkout-rbac-binding",
        details="missing configmaps permission",
    )

    cmds, deps = decide_rbac_remediation_commands([fault], namespace="hotel-reservation")

    assert any("kubectl patch clusterrole checkout-rbac-role" in c for c in cmds)
    assert any('"resources": ["configmaps"]' in c for c in cmds)
    assert deps == ["checkout"]
    assert "kubectl rollout restart deployment/checkout -n hotel-reservation" in cmds


def test_remediation_commands_for_missing_service_account():
    fault = RBACMisconfigFault(
        deployment_name="checkout",
        namespace="hotel-reservation",
        service_account_name="ghost-sa",
        fault_kind="missing_service_account",
        details="sa missing",
    )
    cmds, deps = decide_rbac_remediation_commands([fault], namespace="hotel-reservation")
    assert any("kubectl create serviceaccount ghost-sa -n hotel-reservation" in c for c in cmds)
    assert deps == ["checkout"]


def test_remediation_commands_for_missing_role_binding():
    fault = RBACMisconfigFault(
        deployment_name="checkout",
        namespace="hotel-reservation",
        service_account_name="orphan-sa",
        fault_kind="missing_role_binding",
        details="no binding",
    )
    cmds, deps = decide_rbac_remediation_commands([fault], namespace="hotel-reservation")
    assert any("kubectl create clusterrolebinding" in c and "orphan-sa" in c for c in cmds)
    assert deps == ["checkout"]


# =============================================================================
# Engine wiring (CompositePlannerEngine)
# =============================================================================

def test_engine_diagnosis_and_mitigation_include_rbac_misconfig():
    engine = CompositePlannerEngine(namespace="hotel-reservation")

    deployments = {"items": [_base_deployment()]}
    service_accounts = {
        "items": [{"metadata": {"name": "checkout-rbac-sa", "namespace": "hotel-reservation"}}]
    }
    cluster_roles = {
        "items": [
            {
                "metadata": {"name": "checkout-rbac-role"},
                "rules": [{"apiGroups": [""], "resources": ["pods"], "verbs": ["get"]}],
            }
        ]
    }
    cluster_role_bindings = {
        "items": [
            {
                "metadata": {"name": "checkout-rbac-binding"},
                "roleRef": {"name": "checkout-rbac-role"},
                "subjects": [{"kind": "ServiceAccount", "name": "checkout-rbac-sa"}],
            }
        ]
    }

    diagnosis = engine.run_diagnosis(
        deployments_json=deployments,
        service_accounts_json=service_accounts,
        cluster_roles_json=cluster_roles,
        cluster_role_bindings_json=cluster_role_bindings,
    )

    assert len(diagnosis.rbac_misconfigs) == 1
    assert diagnosis.rbac_misconfigs[0].fault_kind == "missing_rbac_permission"
    assert "RBAC misconfigurations" in diagnosis.diagnosis_text
    assert "checkout-rbac-sa" in diagnosis.diagnosis_text

    mitigation = engine.run_mitigation(diagnosis)
    assert any("kubectl patch clusterrole checkout-rbac-role" in c for c in mitigation.commands)
    assert "checkout" in mitigation.rollout_wait_deployments
