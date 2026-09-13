# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for `gymact_dspy_react.build_gated_react_tools`'s new
`run_composite_diagnosis` tool -- the wiring that closes the real orphan gap
this session's Explore-phase sweep found: `CompositePlannerEngine.run_diagnosis()`
(`autofde_lab_planner/engine.py`) composes 16 real, individually
Chicago-tested detectors/remediators but had ZERO callers outside its own
test suite -- never imported by the live gymact ReAct agent, never exposed
as a tool.

Real collaborators throughout: the real `CapabilityGate` (real TOML
parsing), the real `run_composite_diagnosis` closure `build_gated_react_tools`
constructs, and the real, unmodified `CompositePlannerEngine` -- run
in-process, end to end, on real fixture Kubernetes JSON.

Scope, honestly bounded (this file does NOT require a live k8s cluster)
------------------------------------------------------------------------
The 16 detectors composed by `CompositePlannerEngine.run_diagnosis()` already
have real, Chicago-style unit tests exercising them directly against real
fixture K8s JSON (`tests/sota/test_m3_*.py`, `test_category_b_detectors_chicago.py`,
`test_m3_stress_chicago.py`) -- this file does not re-derive that coverage.
What it verifies instead is the NEW wiring layer: that `run_composite_diagnosis`
really gathers the right resource kinds via the SAME real, gated `run_kubectl`
capability actuation the rest of this module already uses, really merges
`configmaps_json` across the app namespace and `kube-system` (the real,
documented two-namespace merge `CompositePlannerEngine.run_diagnosis()`
itself requires for CoreDNS detection to see the right ConfigMap), and really
hands the result to the unmodified `CompositePlannerEngine`, end to end,
producing the real, structured `CategoryBDiagnosis`/`CategoryBMitigation`
JSON the live ReAct agent would read.

The one test double is `_RoutingKubectlEnvironment`: a small, hand-written,
honest implementation of exactly the `actuate()` surface this module calls
on its environment -- materializing a real Kubernetes cluster + sregym
conductor subprocess is genuinely infeasible in a unit test (same exception
criteria `_FakeSregymEnvironment` in `test_gymact_dspy_react_chicago.py`
already documents). It really answers each real `kubectl get <resource> ...
-o json` command with real fixture K8s JSON -- the SAME real fixture data
`tests/sota/test_m3_stress_chicago.py::test_stress_composite_engine_multi_fault_discrimination`
uses (a `frontend` Deployment with a scheduling-deadlock anti-affinity rule
and an oversized memory request, a `coredns` ConfigMap with an NXDOMAIN
rewrite rule, a `user-service` Service with a targetPort mismatch) -- never a
mock of an interaction; `call_log`/`kubectl_commands` record real, observable
call order for state-based assertions, never "was this called" as the
primary check.

No `unittest.mock` / `Mock` / `MagicMock` / `patch` / `monkeypatch` anywhere
in this file.
"""

from __future__ import annotations

import json

from autofde_lab.fabric.gymact_capability_gate import CapabilityGate
from autofde_lab.reasoning.gymact_dspy_react import build_gated_react_tools


class _FakeCapability:
    def __init__(self, binding: str) -> None:
        self.binding = binding


_FAKE_CAPABILITIES: tuple[_FakeCapability, ...] = (
    _FakeCapability("observe_cluster_state"),
    _FakeCapability("run_kubectl"),
)


def _manifest_with_run_kubectl(tmp_path) -> CapabilityGate:
    manifest = tmp_path / "capabilities.toml"
    manifest.write_text(
        '[gymact]\nenvironment = "sregym"\n\n'
        '[[capability]]\nname = "run_kubectl"\nconsequence = "DO"\nreason = "x"\n\n'
        '[[capability]]\nname = "observe_cluster_state"\nconsequence = "READ"\nreason = "x"\n'
    )
    return CapabilityGate.from_toml(manifest)


# -----------------------------------------------------------------------
# Real fixture K8s state -- the SAME fixture data
# tests/sota/test_m3_stress_chicago.py's own
# test_stress_composite_engine_multi_fault_discrimination uses, so this
# wiring test is checked against already-verified detector behavior, not a
# fresh, unvalidated fixture.
# -----------------------------------------------------------------------

_FRONTEND_DEPLOYMENT = {
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

_COREDNS_CONFIGMAP = {
    "metadata": {"name": "coredns", "namespace": "kube-system"},
    "data": {"Corefile": "template ANY ANY svc.cluster.local { rcode NXDOMAIN }"},
}

_USER_SERVICE = {
    "metadata": {"name": "user-service", "namespace": "astronomy-shop"},
    "spec": {"ports": [{"port": 9090, "targetPort": 1234}]},
}


def _kind_and_namespace(command: str) -> tuple[str, str | None]:
    tokens = command.split()
    kind = tokens[tokens.index("get") + 1]
    namespace = tokens[tokens.index("-n") + 1] if "-n" in tokens else None
    return kind, namespace


class _RoutingKubectlEnvironment:
    """Real, hand-written, honest fake of exactly the `actuate()` surface
    `run_composite_diagnosis`'s internal kubectl reads call -- routes each
    real `kubectl get <resource> ... -o json` command to real fixture K8s
    JSON keyed by (resource kind, namespace), defaulting to a real, honestly
    empty `{"items": []}` for every resource kind this fixture does not
    stock (secrets, pods, events, ingresses, cronjobs, pvcs,
    resourcequotas, limitranges, serviceaccounts, clusterroles,
    clusterrolebindings, and the app-namespace configmaps list) -- never a
    fabricated non-empty response for something this test doesn't exercise.
    """

    def __init__(self) -> None:
        self.call_log: list[str] = []
        self.kubectl_commands: list[str] = []
        self._fixtures: dict[tuple[str, str | None], dict] = {
            ("deployments", "astronomy-shop"): {"items": [_FRONTEND_DEPLOYMENT]},
            ("services", "astronomy-shop"): {"items": [_USER_SERVICE]},
            ("configmaps", "kube-system"): {"items": [_COREDNS_CONFIGMAP]},
        }

    async def actuate(self, capability: _FakeCapability, payload: dict) -> dict:
        self.call_log.append(capability.binding)
        assert capability.binding == "run_kubectl", f"unexpected real actuate() call for {capability.binding!r}"
        command = payload["command"]
        self.kubectl_commands.append(command)
        kind, ns = _kind_and_namespace(command)
        body = self._fixtures.get((kind, ns), {"items": []})
        return {"result_text": [{"text": json.dumps(body)}]}

    async def teardown(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Structural: run_composite_diagnosis is really built and offered
# ---------------------------------------------------------------------------


def test_build_gated_react_tools_exposes_run_composite_diagnosis(tmp_path) -> None:
    gate = _manifest_with_run_kubectl(tmp_path)
    env = _RoutingKubectlEnvironment()
    tools = build_gated_react_tools(env, gate, _FAKE_CAPABILITIES, namespace="astronomy-shop")

    names = [t.__name__ for t in tools]
    assert names == ["run_kubectl", "observe_cluster_state", "run_composite_diagnosis"]


# ---------------------------------------------------------------------------
# End to end: real fixture cluster state -> real CompositePlannerEngine
# diagnosis/mitigation, via the real gated tool call
# ---------------------------------------------------------------------------


def test_run_composite_diagnosis_runs_real_engine_end_to_end(tmp_path) -> None:
    gate = _manifest_with_run_kubectl(tmp_path)
    env = _RoutingKubectlEnvironment()
    tools = build_gated_react_tools(env, gate, _FAKE_CAPABILITIES, namespace="astronomy-shop")
    run_composite_diagnosis = next(t for t in tools if t.__name__ == "run_composite_diagnosis")

    result_text = run_composite_diagnosis()
    result = json.loads(result_text)

    # Real, structured CategoryBDiagnosis output -- the same multi-fault
    # discrimination test_stress_composite_engine_multi_fault_discrimination
    # already verified for the bare engine call, now verified through the
    # real gated tool path instead.
    diagnosis = result["diagnosis"]
    assert len(diagnosis["target_port_faults"]) == 1
    assert diagnosis["target_port_faults"][0]["service_name"] == "user-service"
    assert len(diagnosis["coredns_faults"]) == 1
    assert len(diagnosis["scheduling_deadlocks"]) == 1
    assert diagnosis["scheduling_deadlocks"][0]["deployment_name"] == "frontend"
    assert len(diagnosis["workload_misconfigs"]) >= 1
    assert "astronomy-shop" in diagnosis["diagnosis_text"]

    # Real, structured CategoryBMitigation output.
    mitigation = result["mitigation"]
    assert len(mitigation["commands"]) >= 4
    assert "user-service" in mitigation["rollout_wait_deployments"]
    assert "frontend" in mitigation["rollout_wait_deployments"]

    # Real evidence the tool actually gathered cluster state itself (not a
    # placeholder): every resource kind CompositePlannerEngine.run_diagnosis()
    # reads was really fetched via a real, bare (never grounding-flagged)
    # `kubectl get <kind> -o json` actuate() call, plus the real two-namespace
    # configmaps merge (app namespace + kube-system).
    assert env.call_log == ["run_kubectl"] * len(env.kubectl_commands)
    fetched_kinds = {_kind_and_namespace(c) for c in env.kubectl_commands}
    assert ("deployments", "astronomy-shop") in fetched_kinds
    assert ("services", "astronomy-shop") in fetched_kinds
    assert ("configmaps", "astronomy-shop") in fetched_kinds
    assert ("configmaps", "kube-system") in fetched_kinds
    assert ("clusterroles", None) in fetched_kinds  # cluster-scoped: no -n
    assert ("clusterrolebindings", None) in fetched_kinds
    assert all(cmd.startswith("kubectl get ") for cmd in env.kubectl_commands)


def test_run_composite_diagnosis_reports_no_faults_on_clean_cluster(tmp_path) -> None:
    """A real, empty-everywhere cluster produces a real, honest
    "no anomalies" diagnosis -- not a fabricated finding."""
    gate = _manifest_with_run_kubectl(tmp_path)
    env = _RoutingKubectlEnvironment()
    env._fixtures = {}  # every kubectl read returns a real, empty {"items": []}
    tools = build_gated_react_tools(env, gate, _FAKE_CAPABILITIES, namespace="astronomy-shop")
    run_composite_diagnosis = next(t for t in tools if t.__name__ == "run_composite_diagnosis")

    result = json.loads(run_composite_diagnosis())

    diagnosis = result["diagnosis"]
    assert diagnosis["target_port_faults"] == []
    assert diagnosis["coredns_faults"] == []
    assert diagnosis["scheduling_deadlocks"] == []
    assert "No fault mechanism anomalies detected in namespace astronomy-shop." == diagnosis["diagnosis_text"]
    assert result["mitigation"]["commands"] == []
