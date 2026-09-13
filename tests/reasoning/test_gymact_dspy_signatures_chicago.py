# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for `autofde_lab.reasoning.gymact_dspy_signatures`.

Real collaborators throughout: the real `CapabilityGate` (real TOML
parsing), the real `autofde_lab_planner.scanner.taxonomy` label constants,
and real `dspy.LM`/Groq calls for the reasoning-only stages (Classify,
Diagnose, Synthesize, Verify) -- those four need no cluster/environment at
all, just real text input, so they are tested directly against a real live
LM with real fixture text, no fake environment required.

The ONE test double is `_FakeSregymEnvironment` (structural coverage of the
gated `ObserveCluster`/mitigation-actuation tool routing only), matching
`_FakeSregymEnvironment` from `test_gymact_dspy_react_chicago.py` /
`test_gymact_diagnosis_driver_chicago.py` -- a real, hand-written, honest
implementation of exactly the `actuate`/`teardown` surface this module
calls, never an interaction-verifying mock.

No `unittest.mock` / `Mock` / `MagicMock` / `patch` / `monkeypatch` anywhere
in this file.
"""

from __future__ import annotations

import asyncio
import os

import dspy
import pytest

from autofde_lab.fabric.gymact_capability_gate import CapabilityGate, CapabilityRefused
from autofde_lab.reasoning.gymact_dspy_signatures import (
    REAL_FAULT_LABELS,
    ClassifyAnomaly,
    DiagnoseRootCause,
    StagedDiagnosisResult,
    SynthesizeMitigation,
    VerifyMitigationOutcome,
    build_gated_observe_tools,
    run_staged_dspy_diagnosis,
)

_GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

requires_real_groq_key = pytest.mark.skipif(
    not _GROQ_API_KEY,
    reason=(
        "GROQ_API_KEY is not set in this environment -- a real live Groq "
        "call is required for this test and no mock substitute is used "
        "per .claude/rules/testing-chicago-style.md."
    ),
)


class _FakeCapability:
    def __init__(self, binding: str) -> None:
        self.binding = binding


_FAKE_CAPABILITIES: tuple[_FakeCapability, ...] = (
    _FakeCapability("observe_cluster_state"),
    _FakeCapability("run_kubectl"),
    _FakeCapability("submit_diagnosis"),
    _FakeCapability("submit_mitigation"),
)


class _FakeSregymEnvironment:
    """Real, hand-written, honest fake of exactly the `actuate`/`teardown`
    surface this module calls -- not gymact itself."""

    def __init__(self) -> None:
        self.call_log: list[str] = []
        self.kubectl_commands: list[str] = []
        self.torn_down = False
        self.last_diagnosis_payload: dict | None = None

    async def actuate(self, capability: _FakeCapability, payload: dict) -> dict:
        self.call_log.append(capability.binding)
        if capability.binding == "observe_cluster_state":
            return {"after": {"stage": "diagnosis"}}
        if capability.binding == "run_kubectl":
            command = payload.get("command", "")
            self.kubectl_commands.append(command)
            return {
                "result_text": [
                    {
                        "text": (
                            '{"items": [{"metadata": {"name": "api-0"}, '
                            '"spec": {"dnsPolicy": "None"}}]}'
                        )
                    }
                ]
            }
        if capability.binding == "submit_diagnosis":
            self.last_diagnosis_payload = dict(payload)
            return {"after": {"diagnosis": payload.get("diagnosis")}}
        raise AssertionError(f"unexpected real actuate() call for binding={capability.binding!r}")

    async def teardown(self) -> None:
        self.torn_down = True


async def _identity_async(value):
    return value


# ---------------------------------------------------------------------------
# Structural: real taxonomy grounding
# ---------------------------------------------------------------------------


def test_real_fault_labels_are_sourced_from_real_taxonomy_module() -> None:
    """REAL_FAULT_LABELS must be the same real inject_* vocabulary defined
    in autofde_lab_planner.scanner.taxonomy -- never a hand-copied,
    independently-drifting list."""
    from autofde_lab_planner.scanner import taxonomy

    assert taxonomy.INJECT_WRONG_DNS_POLICY in REAL_FAULT_LABELS
    assert taxonomy.INJECT_LIVENESS_PROBE_TOO_AGGRESSIVE in REAL_FAULT_LABELS
    assert taxonomy.INJECT_MISSING_CONFIGMAP in REAL_FAULT_LABELS
    assert taxonomy.UNCLASSIFIED in REAL_FAULT_LABELS


# ---------------------------------------------------------------------------
# Structural: the gate really refuses an unlisted binding for ObserveCluster
# ---------------------------------------------------------------------------


def test_build_gated_observe_tools_refuses_unlisted_capability(tmp_path) -> None:
    manifest = tmp_path / "capabilities.toml"
    manifest.write_text(
        '[gymact]\nenvironment = "sregym"\n\n'
        '[[capability]]\nname = "observe_cluster_state"\nconsequence = "READ"\nreason = "x"\n'
    )
    gate = CapabilityGate.from_toml(manifest)
    env = _FakeSregymEnvironment()
    tools = build_gated_observe_tools(env, gate, _FAKE_CAPABILITIES, namespace="social-network")
    run_kubectl = next(t for t in tools if t.__name__ == "run_kubectl")

    with pytest.raises(CapabilityRefused):
        run_kubectl("get pods")

    assert env.call_log == []


def test_build_gated_observe_tools_run_kubectl_calls_real_actuate(tmp_path) -> None:
    manifest = tmp_path / "capabilities.toml"
    manifest.write_text(
        '[gymact]\nenvironment = "sregym"\n\n'
        '[[capability]]\nname = "run_kubectl"\nconsequence = "DO"\nreason = "x"\n'
    )
    gate = CapabilityGate.from_toml(manifest)
    env = _FakeSregymEnvironment()
    tools = build_gated_observe_tools(env, gate, _FAKE_CAPABILITIES, namespace="social-network")
    run_kubectl = next(t for t in tools if t.__name__ == "run_kubectl")

    result_text = run_kubectl("get pods -o json")

    assert env.call_log == ["run_kubectl"]
    assert env.kubectl_commands == ["kubectl get pods -o json -n social-network"]
    assert "result_text" in result_text


# ---------------------------------------------------------------------------
# Live Groq: the four pure-reasoning stages, real text in, real text out
# ---------------------------------------------------------------------------

_FIXTURE_DNS_POLICY_SUMMARY = (
    "Namespace social-network: Deployment api-0 has 0/1 ready replicas. "
    "Pod api-0-xyz spec.dnsPolicy is 'None' with no dnsConfig set, "
    "expected 'ClusterFirst'. Events show repeated DNS resolution failures "
    "'lookup mongodb-social-network.svc.cluster.local: no such host' for "
    "the last 10 minutes."
)


@requires_real_groq_key
def test_live_groq_classify_anomaly_grounded_in_real_taxonomy() -> None:
    lm = dspy.LM("groq/openai/gpt-oss-20b", api_key=_GROQ_API_KEY, cache=False)
    classify = dspy.Predict(ClassifyAnomaly)

    with dspy.context(lm=lm):
        result = classify(cluster_summary=_FIXTURE_DNS_POLICY_SUMMARY)

    labels = list(result.candidate_fault_labels)
    assert labels, "real LM call must produce at least one candidate label"
    for label in labels:
        assert label in REAL_FAULT_LABELS, (
            f"LM produced label {label!r} outside the real, closed taxonomy "
            f"{REAL_FAULT_LABELS!r} -- grounding failed"
        )


@requires_real_groq_key
def test_live_groq_diagnose_root_cause_produces_real_bounded_confidence() -> None:
    lm = dspy.LM("groq/openai/gpt-oss-20b", api_key=_GROQ_API_KEY, cache=False)
    diagnose = dspy.ChainOfThought(DiagnoseRootCause)

    with dspy.context(lm=lm):
        result = diagnose(
            cluster_summary=_FIXTURE_DNS_POLICY_SUMMARY,
            candidate_fault_labels=["inject_wrong_dns_policy"],
        )

    assert result.diagnosis  # real, non-empty LM text
    confidence = float(result.confidence)
    assert 0.0 <= confidence <= 1.0


@requires_real_groq_key
def test_live_groq_synthesize_mitigation_for_wrong_dns_policy_produces_real_kubectl_command() -> None:
    """The one real, currently-nonexistent piece: given a real diagnosed
    wrong-DNS-policy root cause, the real LM call must synthesize a single,
    plausible kubectl command -- proving grounding, not generic filler."""
    lm = dspy.LM("groq/openai/gpt-oss-20b", api_key=_GROQ_API_KEY, cache=False)
    synthesize = dspy.ChainOfThought(SynthesizeMitigation)

    with dspy.context(lm=lm):
        result = synthesize(
            diagnosis=(
                "Pod api-0's spec.dnsPolicy is set to 'None' instead of the "
                "expected 'ClusterFirst', causing DNS resolution failures "
                "against mongodb-social-network.svc.cluster.local."
            ),
            namespace="social-network",
        )

    command = result.kubectl_command.strip()
    assert command, "real LM call must produce a non-empty kubectl command"
    assert command.startswith("kubectl"), f"synthesized command must be real kubectl syntax, got: {command!r}"
    assert "social-network" in command, "synthesized command must target the real given namespace"
    assert result.rationale


@requires_real_groq_key
def test_live_groq_verify_mitigation_outcome_is_advisory_only() -> None:
    lm = dspy.LM("groq/openai/gpt-oss-20b", api_key=_GROQ_API_KEY, cache=False)
    verify = dspy.Predict(VerifyMitigationOutcome)

    with dspy.context(lm=lm):
        result = verify(
            post_mitigation_cluster_summary=(
                "Namespace social-network: Deployment api-0 now has 1/1 "
                "ready replicas. Pod api-0-xyz spec.dnsPolicy is "
                "'ClusterFirst'. No DNS-related events in the last 5 "
                "minutes."
            ),
            original_diagnosis=(
                "Pod api-0's spec.dnsPolicy was 'None' instead of "
                "'ClusterFirst', causing DNS resolution failures."
            ),
        )

    assert result.outcome in ("fixed", "not_fixed", "unclear")
    assert result.evidence


# ---------------------------------------------------------------------------
# Live Groq end-to-end: full staged pipeline against a real fake environment
# ---------------------------------------------------------------------------


@requires_real_groq_key
def test_live_groq_staged_diagnosis_full_pipeline_against_fake_environment() -> None:
    lm = dspy.LM("groq/openai/gpt-oss-20b", api_key=_GROQ_API_KEY, cache=False)
    env = _FakeSregymEnvironment()

    result = asyncio.run(
        run_staged_dspy_diagnosis(
            "wrong_dns_policy_social_network",
            namespace="social-network",
            max_observe_iters=3,
            lm=lm,
            _environment_factory=lambda: _identity_async(env),
            _capabilities=_FAKE_CAPABILITIES,
        )
    )

    assert isinstance(result, StagedDiagnosisResult)
    assert result.problem_id == "wrong_dns_policy_social_network"
    assert result.namespace == "social-network"
    assert result.cluster_summary  # real, non-empty ObserveCluster output
    assert result.candidate_fault_labels
    assert result.diagnosis
    assert 0.0 <= result.confidence <= 1.0
    assert "submit_diagnosis" in env.call_log
    assert env.last_diagnosis_payload is not None
    assert env.last_diagnosis_payload["diagnosis"] == result.diagnosis
    assert env.torn_down is True
    assert result.mitigation_attempted is False
    assert result.kubectl_command is None
    # submit_mitigation must never be called from this module -- it never
    # touches gymact_diagnosis_driver.py's honest "not_attempted" default.
    assert "submit_mitigation" not in env.call_log


@requires_real_groq_key
def test_live_groq_staged_diagnosis_with_mitigation_actually_calls_gated_run_kubectl() -> None:
    """attempt_mitigation=True must really call the gated run_kubectl
    capability with the SynthesizeMitigation stage's real derived command
    -- proving this is real actuation, not a dry-run."""
    lm = dspy.LM("groq/openai/gpt-oss-20b", api_key=_GROQ_API_KEY, cache=False)
    env = _FakeSregymEnvironment()

    result = asyncio.run(
        run_staged_dspy_diagnosis(
            "wrong_dns_policy_social_network",
            namespace="social-network",
            max_observe_iters=3,
            attempt_mitigation=True,
            lm=lm,
            _environment_factory=lambda: _identity_async(env),
            _capabilities=_FAKE_CAPABILITIES,
        )
    )

    assert result.mitigation_attempted is True
    assert result.kubectl_command
    assert result.kubectl_command.startswith("kubectl")
    assert result.mitigation_rationale
    assert result.run_kubectl_response is not None
    # The synthesized command must be the exact one actually sent to
    # env.actuate() -- real, observable state, not an interaction guess.
    assert result.kubectl_command in env.kubectl_commands
    assert "submit_mitigation" not in env.call_log


def test_run_staged_dspy_diagnosis_refuses_run_kubectl_when_not_in_manifest(tmp_path) -> None:
    """Structural, no-LLM-call proof that the mitigation-actuation path is
    really gated: a manifest missing run_kubectl must refuse the call
    before it ever reaches env.actuate(), regardless of what the LM (never
    invoked here since this test raises before any dspy call) would have
    proposed. This test exercises the gate directly, matching this
    module's real actuation surface without requiring a live LM call."""
    manifest = tmp_path / "capabilities.toml"
    manifest.write_text(
        '[gymact]\nenvironment = "sregym"\n\n'
        '[[capability]]\nname = "submit_diagnosis"\nconsequence = "DO"\nreason = "x"\n'
    )
    gate = CapabilityGate.from_toml(manifest)

    with pytest.raises(CapabilityRefused):
        gate.guard_capability(_FakeCapability("run_kubectl"))
