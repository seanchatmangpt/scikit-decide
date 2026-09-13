"""Chicago-style zero-mock unit and integration tests for Category-B fault mechanisms (B4, B6, B9, B13).

Strict zero-mock policy: NO unittest.mock, NO Mock, NO MagicMock, NO patch, NO monkeypatch.
All tests exercise pure functions with real Python data structures.
"""

from __future__ import annotations

import json
from autofde_lab_planner.baselines.k8s_baselines import (
    get_baseline_manifest,
    synthesize_configmap_manifest,
    synthesize_secret_manifest,
    synthesize_service_manifest,
)
from autofde_lab_planner.detectors.flagd_drift import detect_flagd_config_drift
from autofde_lab_planner.detectors.object_reconstruction import detect_missing_objects
from autofde_lab_planner.detectors.otel_trace import (
    detect_otel_trace_anomalies,
    parse_jaeger_traces_json,
)
from autofde_lab_planner.detectors.probe_heuristics import (
    detect_probe_faults,
    parse_container_probes,
)
from autofde_lab_planner.engine import CompositePlannerEngine
from autofde_lab_planner.models import (
    FlagdDriftResult,
    FlagDriftItem,
    MissingObjectFault,
    ParsedSpan,
    ProbeFault,
    TraceAnomalyResult,
)
from autofde_lab_planner.remediators.flagd_drift import decide_flagd_remediation_commands
from autofde_lab_planner.remediators.object_reconstruction import decide_object_reconstruction_commands
from autofde_lab_planner.remediators.otel_trace import decide_otel_remediation_commands
from autofde_lab_planner.remediators.probe_heuristics import decide_probe_remediation_commands


# =============================================================================
# B4: Probe Heuristics & Liveness/Readiness Faults Tests
# =============================================================================

def test_b4_parse_container_probes_extracts_liveness_and_readiness():
    deployment = {
        "metadata": {"name": "frontend"},
        "spec": {
            "template": {
                "spec": {
                    "containers": [
                        {
                            "name": "frontend",
                            "ports": [{"containerPort": 8080}],
                            "livenessProbe": {
                                "httpGet": {"path": "/healthz", "port": 8080},
                                "initialDelaySeconds": 10,
                                "periodSeconds": 10,
                            },
                            "readinessProbe": {
                                "httpGet": {"path": "/", "port": 8080},
                                "initialDelaySeconds": 5,
                            },
                        }
                    ]
                }
            }
        },
    }
    probes = parse_container_probes(deployment)
    assert "frontend" in probes
    assert probes["frontend"]["ports"] == [8080]
    assert probes["frontend"]["livenessProbe"]["httpGet"]["path"] == "/healthz"
    assert probes["frontend"]["readinessProbe"]["httpGet"]["path"] == "/"


def test_b4_detect_probe_faults_identifies_invalid_endpoint():
    deployments = {
        "items": [
            {
                "metadata": {"name": "cartservice"},
                "spec": {
                    "replicas": 1,
                    "template": {
                        "spec": {
                            "containers": [
                                {
                                    "name": "cartservice",
                                    "ports": [{"containerPort": 7070}],  # Container listens on 7070
                                    "readinessProbe": {
                                        "httpGet": {"path": "/healthz", "port": 8080},  # Invalid port 8080
                                        "initialDelaySeconds": 10,
                                        "periodSeconds": 10,
                                    },
                                }
                            ]
                        }
                    },
                },
                "status": {"readyReplicas": 0},
            }
        ]
    }
    faults = detect_probe_faults(deployments)
    assert len(faults) == 1
    f = faults[0]
    assert f.deployment_name == "cartservice"
    assert f.probe_type == "readinessProbe"
    assert f.fault_kind == "invalid_endpoint"
    assert f.observed_port == 8080


def test_b4_detect_probe_faults_identifies_aggressive_timing():
    deployments = [
        {
            "metadata": {"name": "checkoutservice"},
            "spec": {
                "replicas": 1,
                "template": {
                    "spec": {
                        "containers": [
                            {
                                "name": "checkoutservice",
                                "ports": [{"containerPort": 5050}],
                                "livenessProbe": {
                                    "initialDelaySeconds": 0,
                                    "periodSeconds": 1,
                                    "failureThreshold": 1,
                                },
                            }
                        ]
                    }
                },
            },
            "status": {"readyReplicas": 0},
        }
    ]
    faults = detect_probe_faults(deployments)
    assert len(faults) == 1
    f = faults[0]
    assert f.deployment_name == "checkoutservice"
    assert f.probe_type == "livenessProbe"
    assert f.fault_kind == "aggressive_timing"
    assert f.initial_delay == 0


def test_b4_decide_probe_remediation_commands_generates_valid_patches():
    faults = [
        ProbeFault(
            deployment_name="cartservice",
            container_name="cartservice",
            probe_type="readinessProbe",
            fault_kind="invalid_endpoint",
            observed_port=8080,
        )
    ]
    commands, wait_deps = decide_probe_remediation_commands(faults, namespace="astronomy-shop")
    assert len(commands) == 2
    assert "kubectl patch deployment cartservice -n astronomy-shop --type=json" in commands[0]
    assert '{"op": "remove", "path": "/spec/template/spec/containers/0/readinessProbe"}' in commands[0]
    assert "terminationGracePeriodSeconds" in commands[1]
    assert wait_deps == ["cartservice"]


# =============================================================================
# B6: OTel Trace Diffing Tests
# =============================================================================

def test_b6_parse_jaeger_traces_json_handles_raw_payload():
    raw_jaeger_payload = {
        "data": [
            {
                "traceID": "4bf92f3577b34da6a3ce929d0e0e4736",
                "spans": [
                    {
                        "traceID": "4bf92f3577b34da6a3ce929d0e0e4736",
                        "spanID": "s1",
                        "operationName": "GET /checkout",
                        "processID": "p1",
                        "duration": 50000,
                        "tags": [{"key": "http.status_code", "value": 200}],
                    },
                    {
                        "traceID": "4bf92f3577b34da6a3ce929d0e0e4736",
                        "spanID": "s2",
                        "operationName": "RPC Charge",
                        "processID": "p2",
                        "duration": 1500000,
                        "references": [{"refType": "CHILD_OF", "spanID": "s1"}],
                        "tags": [{"key": "error", "value": True}, {"key": "rpc.grpc.status_code", "value": 14}],
                    },
                ],
                "processes": {
                    "p1": {"serviceName": "frontend"},
                    "p2": {"serviceName": "paymentservice"},
                },
            }
        ]
    }

    trees = parse_jaeger_traces_json(raw_jaeger_payload)
    assert len(trees) == 1
    t = trees[0]
    assert t.trace_id == "4bf92f3577b34da6a3ce929d0e0e4736"
    assert len(t.spans_by_id) == 2
    assert t.spans_by_id["s2"].service_name == "paymentservice"
    assert t.spans_by_id["s2"].has_error is True


def test_b6_detect_otel_trace_anomalies_isolates_downstream_root_cause():
    raw_traces = {
        "frontend": json.dumps(
            {
                "data": [
                    {
                        "traceID": "t1",
                        "spans": [
                            {
                                "spanID": "s1",
                                "operationName": "GET /cart",
                                "processID": "p1",
                                "duration": 2500000,
                                "tags": [{"key": "error", "value": True}],
                            },
                            {
                                "spanID": "s2",
                                "operationName": "RPC GetCart",
                                "processID": "p2",
                                "duration": 2400000,
                                "references": [{"refType": "CHILD_OF", "spanID": "s1"}],
                                "tags": [{"key": "error", "value": True}, {"key": "rpc.grpc.status_code", "value": 14}],
                            },
                        ],
                        "processes": {
                            "p1": {"serviceName": "frontend"},
                            "p2": {"serviceName": "cartservice"},
                        },
                    }
                ]
            }
        )
    }

    result = detect_otel_trace_anomalies(raw_traces, error_rate_threshold=0.20)
    assert result.has_anomaly is True
    assert result.root_cause_service == "cartservice"
    assert "cartservice" in result.affected_services


def test_b6_decide_otel_remediation_commands_returns_rollout_undo():
    anomaly_result = TraceAnomalyResult(
        has_anomaly=True,
        root_cause_service="paymentservice",
        affected_services=("frontend", "paymentservice"),
    )
    commands, wait_deps = decide_otel_remediation_commands(anomaly_result, namespace="astronomy-shop")
    assert commands == ["kubectl rollout undo deployment/paymentservice -n astronomy-shop"]
    assert wait_deps == ["paymentservice"]


# =============================================================================
# B9: flagd Config Drift Tests
# =============================================================================

def test_b9_detect_flagd_config_drift_identifies_mutated_variant():
    cm_json = {
        "metadata": {"name": "flagd-config", "namespace": "astronomy-shop"},
        "data": {
            "demo.flagd.json": json.dumps(
                {
                    "flags": {
                        "adFailure": {"state": "ENABLED", "defaultVariant": "on"},
                        "cartFailure": {"state": "ENABLED", "defaultVariant": "off"},
                    }
                }
            )
        },
    }

    drift_res = detect_flagd_config_drift(cm_json, namespace="astronomy-shop")
    assert drift_res.has_drift is True
    assert len(drift_res.drifted_flags) == 1
    assert drift_res.drifted_flags[0].flag_name == "adFailure"
    assert drift_res.drifted_flags[0].current_variant == "on"
    assert drift_res.drifted_flags[0].target_deployments == ("ad",)
    assert drift_res.repaired_flagd_json is not None
    assert '"adFailure": {\n      "state": "ENABLED",\n      "defaultVariant": "off"' in drift_res.repaired_flagd_json


def test_b9_detect_flagd_config_drift_returns_no_drift_when_clean():
    cm_json = {
        "data": {
            "demo.flagd.json": json.dumps(
                {
                    "flags": {
                        "adFailure": {"state": "ENABLED", "defaultVariant": "off"},
                    }
                }
            )
        }
    }
    drift_res = detect_flagd_config_drift(cm_json)
    assert drift_res.has_drift is False


def test_b9_decide_flagd_remediation_commands_generates_patch_and_rollouts():
    drift_res = FlagdDriftResult(
        has_drift=True,
        configmap_name="flagd-config",
        namespace="astronomy-shop",
        drifted_flags=(
            FlagDriftItem(flag_name="adFailure", current_variant="on", canonical_variant="off", target_deployments=("ad",)),
        ),
        repaired_flagd_json='{"flags":{"adFailure":{"defaultVariant":"off"}}}',
    )

    commands, wait_deps = decide_flagd_remediation_commands(drift_res)
    assert len(commands) == 3
    assert "kubectl create configmap flagd-config -n astronomy-shop" in commands[0]
    assert "kubectl rollout restart deployment/flagd -n astronomy-shop" in commands[1]
    assert "kubectl rollout restart deployment/ad -n astronomy-shop" in commands[2]
    assert set(wait_deps) == {"flagd", "ad"}


# =============================================================================
# B13: Missing/Corrupted Object Reconstruction Tests
# =============================================================================

def test_b13_detect_missing_objects_identifies_missing_service():
    deployments = [
        {"metadata": {"name": "frontend", "namespace": "hotel-reservation"}},
        {"metadata": {"name": "profile", "namespace": "hotel-reservation"}},
    ]
    services = [
        {"metadata": {"name": "frontend", "namespace": "hotel-reservation"}, "spec": {"selector": {"app": "frontend"}}}
    ]

    faults = detect_missing_objects(
        deployments_json=deployments,
        live_services_json=services,
        namespace="hotel-reservation",
    )
    assert len(faults) == 1
    assert faults[0].kind == "Service"
    assert faults[0].object_name == "profile"
    assert faults[0].reason == "missing_service_for_deployment"


def test_b13_detect_missing_objects_identifies_missing_configmap_ref():
    deployments = [
        {
            "metadata": {"name": "geo-service", "namespace": "hotel-reservation"},
            "spec": {
                "template": {
                    "spec": {
                        "containers": [
                            {
                                "name": "geo-service",
                                "env": [
                                    {
                                        "name": "GEO_CONFIG",
                                        "valueFrom": {"configMapKeyRef": {"name": "geo-config", "key": "GeoPort"}},
                                    }
                                ],
                            }
                        ]
                    }
                }
            },
        }
    ]
    configmaps: list[dict] = []  # geo-config missing

    faults = detect_missing_objects(
        deployments_json=deployments,
        live_configmaps_json=configmaps,
        namespace="hotel-reservation",
    )
    assert any(f.kind == "ConfigMap" and f.object_name == "geo-config" for f in faults)


def test_b13_detect_missing_objects_identifies_corrupted_service_selector():
    deployments = [{"metadata": {"name": "reservation", "namespace": "hotel-reservation"}}]
    services = [
        {
            "metadata": {"name": "reservation", "namespace": "hotel-reservation"},
            "spec": {"selector": {}},  # Corrupted empty selector
        }
    ]

    faults = detect_missing_objects(
        deployments_json=deployments,
        live_services_json=services,
        namespace="hotel-reservation",
    )
    assert len(faults) == 1
    assert faults[0].kind == "Service"
    assert faults[0].object_name == "reservation"
    assert faults[0].reason == "corrupted_service_selector"


def test_b13_decide_object_reconstruction_commands_generates_apply_and_patch():
    faults = [
        MissingObjectFault(
            kind="Service",
            object_name="profile",
            namespace="hotel-reservation",
            associated_deployment="profile",
            reason="missing_service_for_deployment",
        ),
        MissingObjectFault(
            kind="ConfigMap",
            object_name="geo-config",
            namespace="hotel-reservation",
            associated_deployment="geo",
            reason="missing_referenced_configmap",
        ),
    ]

    commands, wait_deps = decide_object_reconstruction_commands(faults, namespace="hotel-reservation")
    assert len(commands) == 4
    assert "echo '" in commands[0] and "kubectl apply -f -" in commands[0]
    assert "echo '" in commands[1] and "kubectl apply -f -" in commands[1]
    assert "kubectl rollout restart deployment/profile -n hotel-reservation" in commands[2]
    assert "kubectl rollout restart deployment/geo -n hotel-reservation" in commands[3]
    assert set(wait_deps) == {"profile", "geo"}


def test_b13_baselines_synthesize_valid_manifests():
    svc_manifest = synthesize_service_manifest("frontend", "test-ns", target_port=8080)
    assert svc_manifest["kind"] == "Service"
    assert svc_manifest["metadata"]["name"] == "frontend"
    assert svc_manifest["spec"]["selector"]["app"] == "frontend"

    cm_manifest = synthesize_configmap_manifest("geo-config", "test-ns")
    assert cm_manifest["kind"] == "ConfigMap"
    assert "GeoMongoAddress" in cm_manifest["data"]

    sec_manifest = synthesize_secret_manifest("jwt-secret", "test-ns")
    assert sec_manifest["kind"] == "Secret"
    assert "secret" in sec_manifest["data"]


# =============================================================================
# CompositePlannerEngine Integration Tests
# =============================================================================

def test_composite_planner_engine_runs_diagnosis_and_mitigation():
    engine = CompositePlannerEngine(namespace="astronomy-shop", app_name="Astronomy Shop")

    deployments = [
        {
            "metadata": {"name": "cartservice", "namespace": "astronomy-shop"},
            "spec": {
                "replicas": 1,
                "template": {
                    "spec": {
                        "containers": [
                            {
                                "name": "cartservice",
                                "ports": [{"containerPort": 7070}],
                                "readinessProbe": {
                                    "httpGet": {"path": "/healthz", "port": 8080},
                                    "initialDelaySeconds": 10,
                                },
                            }
                        ]
                    }
                },
            },
            "status": {"readyReplicas": 0},
        }
    ]

    cm_flagd = {
        "metadata": {"name": "flagd-config", "namespace": "astronomy-shop"},
        "data": {
            "demo.flagd.json": json.dumps(
                {
                    "flags": {
                        "adFailure": {"state": "ENABLED", "defaultVariant": "on"},
                    }
                }
            )
        },
    }

    diag = engine.run_diagnosis(
        deployments_json=deployments,
        flagd_configmap_json=cm_flagd,
    )

    assert len(diag.probe_faults) == 1
    assert diag.flagd_drift is not None and diag.flagd_drift.has_drift is True
    assert "Detected probe misconfigurations" in diag.diagnosis_text
    assert "Detected flagd feature flag config drift" in diag.diagnosis_text

    mitigation = engine.run_mitigation(diag)
    assert len(mitigation.commands) > 0
    assert "cartservice" in mitigation.rollout_wait_deployments
    assert "flagd" in mitigation.rollout_wait_deployments
    assert "ad" in mitigation.rollout_wait_deployments
