"""Chicago-style zero-mock unit tests for the DNS policy override fault mechanism.

Source mechanism: sregym/generators/fault/inject_virtual.py
VirtualizationFaultInjector.inject_wrong_dns_policy() -- patches a
Deployment's Pod template ``spec.dnsPolicy`` to ``"None"`` and adds
``spec.dnsConfig.nameservers: ["8.8.8.8"]``, bypassing CoreDNS entirely.

Strict zero-mock policy: NO unittest.mock, NO Mock, NO MagicMock, NO patch,
NO monkeypatch. All tests exercise pure functions with real Python data
structures shaped like real `kubectl get deployment ... -o json` output.
"""

from __future__ import annotations

from autofde_lab_planner.detectors.dns_policy_override import detect_dns_policy_overrides
from autofde_lab_planner.engine import CompositePlannerEngine
from autofde_lab_planner.models import DnsPolicyOverrideFault
from autofde_lab_planner.remediators.dns_policy_override import decide_dns_policy_remediation_commands


def _deployment(name: str, namespace: str, dns_policy: str | None, dns_config: dict | None = None) -> dict:
    pod_spec: dict = {"containers": [{"name": name, "image": "app:latest"}]}
    if dns_policy is not None:
        pod_spec["dnsPolicy"] = dns_policy
    if dns_config is not None:
        pod_spec["dnsConfig"] = dns_config
    return {
        "metadata": {"name": name, "namespace": namespace},
        "spec": {
            "replicas": 2,
            "template": {"metadata": {"labels": {"app": name}}, "spec": pod_spec},
        },
        "status": {"readyReplicas": 2},
    }


def test_detects_dns_policy_override_to_none_with_external_nameserver():
    deployments = {
        "items": [
            _deployment(
                "geo",
                "hotel-reservation",
                dns_policy="None",
                dns_config={"nameservers": ["8.8.8.8"], "searches": []},
            ),
        ]
    }

    faults = detect_dns_policy_overrides(deployments_json=deployments, namespace="hotel-reservation")

    assert len(faults) == 1
    f = faults[0]
    assert isinstance(f, DnsPolicyOverrideFault)
    assert f.deployment_name == "geo"
    assert f.namespace == "hotel-reservation"
    assert f.observed_dns_policy == "None"
    assert f.observed_nameservers == ("8.8.8.8",)


def test_no_fault_when_dns_policy_is_cluster_default():
    deployments = {
        "items": [
            _deployment("rate", "hotel-reservation", dns_policy="ClusterFirst"),
        ]
    }

    faults = detect_dns_policy_overrides(deployments_json=deployments, namespace="hotel-reservation")

    assert faults == []


def test_no_fault_when_dns_policy_is_unset():
    """Absence of an explicit dnsPolicy means the API-server default
    (ClusterFirst) applies -- absence must not be coerced into a fault."""
    deployments = {
        "items": [
            _deployment("profile", "hotel-reservation", dns_policy=None),
        ]
    }

    faults = detect_dns_policy_overrides(deployments_json=deployments, namespace="hotel-reservation")

    assert faults == []


def test_detects_override_even_without_dns_config_present():
    deployments = {
        "items": [
            _deployment("search", "hotel-reservation", dns_policy="Default"),
        ]
    }

    faults = detect_dns_policy_overrides(deployments_json=deployments, namespace="hotel-reservation")

    assert len(faults) == 1
    assert faults[0].observed_dns_policy == "Default"
    assert faults[0].observed_nameservers == ()


def test_remediation_emits_json_patch_removing_dnspolicy_and_dnsconfig_then_restarts():
    fault = DnsPolicyOverrideFault(
        deployment_name="geo",
        namespace="hotel-reservation",
        observed_dns_policy="None",
        observed_nameservers=("8.8.8.8",),
    )

    commands, deployments = decide_dns_policy_remediation_commands(
        faults=[fault], namespace="hotel-reservation"
    )

    assert len(commands) == 2
    assert commands[0] == (
        "kubectl patch deployment geo -n hotel-reservation --type json -p "
        "'[{\"op\":\"remove\",\"path\":\"/spec/template/spec/dnsPolicy\"},"
        '{"op":"remove","path":"/spec/template/spec/dnsConfig"}]\''
    )
    assert commands[1] == "kubectl rollout restart deployment geo -n hotel-reservation"
    assert deployments == ["geo"]


def test_engine_wires_dns_policy_override_detection_and_remediation():
    engine = CompositePlannerEngine(namespace="hotel-reservation")

    deployments = {
        "items": [
            _deployment(
                "geo",
                "hotel-reservation",
                dns_policy="None",
                dns_config={"nameservers": ["8.8.8.8"], "searches": []},
            ),
        ]
    }

    diagnosis = engine.run_diagnosis(deployments_json=deployments)

    assert len(diagnosis.dns_policy_overrides) == 1
    assert "geo" in diagnosis.diagnosis_text
    assert "dnsPolicy=None" in diagnosis.diagnosis_text

    mitigation = engine.run_mitigation(diagnosis)
    assert any("dnsPolicy" in c and "remove" in c for c in mitigation.commands)
    assert any("rollout restart deployment geo" in c for c in mitigation.commands)
