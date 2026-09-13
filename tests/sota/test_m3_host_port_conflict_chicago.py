"""Chicago-style zero-mock unit tests for the hostPort binding conflict fault mechanism.

Source mechanism: sregym/generators/fault/inject_virtual.py
VirtualizationFaultInjector.inject_service_port_conflict() -- adds a
``hostPort`` binding to a container's port entry on a Deployment's Pod
template, causing scheduling refusal ("Ports are not available") for any
additional Pod placed on a Node that already binds that host port.

Strict zero-mock policy: NO unittest.mock, NO Mock, NO MagicMock, NO patch,
NO monkeypatch. All tests exercise pure functions with real Python data
structures shaped like real `kubectl get deployment ... -o json` output.
"""

from __future__ import annotations

from autofde_lab_planner.detectors.host_port_conflict import detect_host_port_conflicts
from autofde_lab_planner.engine import CompositePlannerEngine
from autofde_lab_planner.models import HostPortConflictFault
from autofde_lab_planner.remediators.host_port_conflict import (
    decide_host_port_conflict_remediation_commands,
)


def _deployment(name: str, namespace: str, containers: list[dict]) -> dict:
    return {
        "metadata": {"name": name, "namespace": namespace},
        "spec": {
            "replicas": 2,
            "template": {
                "metadata": {"labels": {"app": name}},
                "spec": {"containers": containers},
            },
        },
        "status": {"readyReplicas": 1},
    }


def test_detects_host_port_added_to_existing_container_port():
    deployments = {
        "items": [
            _deployment(
                "geo",
                "hotel-reservation",
                containers=[
                    {
                        "name": "geo",
                        "image": "geo:latest",
                        "ports": [{"containerPort": 8083, "hostPort": 31083}],
                    }
                ],
            ),
        ]
    }

    faults = detect_host_port_conflicts(deployments_json=deployments, namespace="hotel-reservation")

    assert len(faults) == 1
    f = faults[0]
    assert isinstance(f, HostPortConflictFault)
    assert f.deployment_name == "geo"
    assert f.container_name == "geo"
    assert f.container_port == 8083
    assert f.conflicting_host_port == 31083
    assert f.container_index == 0
    assert f.port_index == 0


def test_no_fault_when_no_container_declares_host_port():
    deployments = {
        "items": [
            _deployment(
                "rate",
                "hotel-reservation",
                containers=[{"name": "rate", "ports": [{"containerPort": 8084}]}],
            ),
        ]
    }

    faults = detect_host_port_conflicts(deployments_json=deployments, namespace="hotel-reservation")

    assert faults == []


def test_no_fault_when_container_has_no_ports_declared_at_all():
    deployments = {
        "items": [
            _deployment("profile", "hotel-reservation", containers=[{"name": "profile"}]),
        ]
    }

    faults = detect_host_port_conflicts(deployments_json=deployments, namespace="hotel-reservation")

    assert faults == []


def test_detects_host_port_on_second_container_at_correct_indices():
    deployments = {
        "items": [
            _deployment(
                "search",
                "hotel-reservation",
                containers=[
                    {"name": "sidecar", "ports": [{"containerPort": 9090}]},
                    {
                        "name": "search",
                        "ports": [
                            {"containerPort": 8082},
                            {"containerPort": 8443, "hostPort": 8443},
                        ],
                    },
                ],
            ),
        ]
    }

    faults = detect_host_port_conflicts(deployments_json=deployments, namespace="hotel-reservation")

    assert len(faults) == 1
    f = faults[0]
    assert f.container_name == "search"
    assert f.container_index == 1
    assert f.port_index == 1
    assert f.container_port == 8443
    assert f.conflicting_host_port == 8443


def test_remediation_emits_json_patch_removing_hostport_then_restarts():
    fault = HostPortConflictFault(
        deployment_name="geo",
        namespace="hotel-reservation",
        container_name="geo",
        container_port=8083,
        conflicting_host_port=31083,
        container_index=0,
        port_index=0,
    )

    commands, deployments = decide_host_port_conflict_remediation_commands(
        faults=[fault], namespace="hotel-reservation"
    )

    assert len(commands) == 2
    assert commands[0] == (
        "kubectl patch deployment geo -n hotel-reservation --type=json "
        '-p=\'[{"op": "remove", "path": '
        '"/spec/template/spec/containers/0/ports/0/hostPort"}]\''
    )
    assert commands[1] == "kubectl rollout restart deployment geo -n hotel-reservation"
    assert deployments == ["geo"]


def test_engine_wires_host_port_conflict_detection_and_remediation():
    engine = CompositePlannerEngine(namespace="hotel-reservation")

    deployments = {
        "items": [
            _deployment(
                "geo",
                "hotel-reservation",
                containers=[
                    {
                        "name": "geo",
                        "ports": [{"containerPort": 8083, "hostPort": 31083}],
                    }
                ],
            ),
        ]
    }

    diagnosis = engine.run_diagnosis(deployments_json=deployments)

    assert len(diagnosis.host_port_conflicts) == 1
    assert "geo" in diagnosis.diagnosis_text
    assert "hostPort=31083" in diagnosis.diagnosis_text

    mitigation = engine.run_mitigation(diagnosis)
    assert any("hostPort" in c and "remove" in c for c in mitigation.commands)
    assert any("rollout restart deployment geo" in c for c in mitigation.commands)
