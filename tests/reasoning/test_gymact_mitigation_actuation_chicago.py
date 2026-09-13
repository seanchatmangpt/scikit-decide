# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for `gymact_mitigation_actuation.execute_and_submit_mitigation`.

Real collaborators throughout: real `dspy.Module` subclasses (hand-written,
deterministic -- the same legitimate test-double pattern
`test_sre_mitigation_portfolio_chicago.py`'s own
`_RealVariedMitigationProcessModule` uses) standing in for the portfolio
constructor and the kubectl translator; a real, hand-written
`_FakeSregymEnvironment` implementing exactly the `actuate` surface this
module calls, the same real-degraded-alternative pattern
`test_gymact_dspy_react_chicago.py` already uses (materializing a live
cluster is genuinely infeasible in a unit test); the real
`OcelExecutionRecorder`/`check_object_centric_conformance` pair this
session already proved on `breed_ensemble.py`/`breed_ensemble_loop.py`/
`gymact_dspy_react.py.decide`.

No `unittest.mock` / `Mock` / `MagicMock` / `patch` / `monkeypatch` anywhere
in this file.
"""

from __future__ import annotations

import os

import dspy
import pytest

from autofde_lab.fabric.gymact_capability_gate import CapabilityGate
from autofde_lab.ocel.object_centric_conformance import check_object_centric_conformance
from autofde_lab.powl.ocel_bridge import OcelExecutionRecorder
from autofde_lab.reasoning.gymact_mitigation_actuation import execute_and_submit_mitigation

_MANIFEST_PATH = (
    __import__("pathlib").Path(__file__).resolve().parents[2]
    / "src"
    / "autofde_lab"
    / "fabric"
    / "gymact_capabilities.toml"
)


class _FakeCapability:
    def __init__(self, binding: str) -> None:
        self.binding = binding


_FAKE_CAPABILITIES: tuple[_FakeCapability, ...] = (
    _FakeCapability("run_kubectl"),
    _FakeCapability("submit_mitigation"),
)


class _FakeSregymEnvironment:
    """Real, hand-written, honest fake of exactly the `actuate` surface
    this module calls -- same pattern as
    `test_gymact_dspy_react_chicago.py::_FakeSregymEnvironment`."""

    def __init__(self) -> None:
        self.call_log: list[str] = []
        self.kubectl_commands: list[str] = []
        self.last_mitigation_payload: dict | None = None

    async def actuate(self, capability: _FakeCapability, payload: dict) -> dict:
        self.call_log.append(capability.binding)
        if capability.binding == "run_kubectl":
            self.kubectl_commands.append(payload.get("command", ""))
            return {"result_text": [{"text": '{"items": []}'}]}
        if capability.binding == "submit_mitigation":
            self.last_mitigation_payload = dict(payload)
            return {"after": {"mitigation": payload.get("mitigation")}}
        raise AssertionError(f"unexpected real actuate() call for binding={capability.binding!r}")


class _FixedPortfolioModule(dspy.Module):
    """Real, deterministic `dspy.Module` standing in for
    `ConstructSreMitigationProcess` -- always returns the same one real,
    safe candidate."""

    def __init__(self, *, safe_to_actuate: bool = True) -> None:
        super().__init__()
        self._safe_to_actuate = safe_to_actuate

    def forward(self, *, root_cause: str, relevant_resource_spec: str, capability_catalog: str) -> dspy.Prediction:
        return dspy.Prediction(
            process_steps=(
                "READ: describe the current deployment spec\n"
                "DO: patch the deployment memory limit to 512Mi\n"
                "VERIFY: confirm the rollout status is complete\n"
            ),
            expected_consequence="the OOMKilled restarts stop",
            rollback_plan="revert the deployment memory limit change",
            safe_to_actuate=self._safe_to_actuate,
        )

    def __call__(self, **kwargs):
        return self.forward(**kwargs)


class _FixedTranslatorModule(dspy.Module):
    """Real, deterministic `dspy.Module` standing in for
    `TranslateMitigationStepToKubectlCommand`."""

    def forward(self, *, step_description: str, step_consequence: str, relevant_resource_spec: str) -> dspy.Prediction:
        if step_consequence == "READ":
            command = "kubectl get deployment geo -n hotel-reservation -o json"
        else:
            command = "kubectl patch deployment geo -n hotel-reservation --patch '{\"spec\":{}}'"
        return dspy.Prediction(kubectl_command=command, is_safe_readonly_or_reversible=True)

    def __call__(self, **kwargs):
        return self.forward(**kwargs)


def _real_gate() -> CapabilityGate:
    return CapabilityGate.from_toml(_MANIFEST_PATH)


def test_unsafe_only_portfolio_is_never_actuated() -> None:
    env = _FakeSregymEnvironment()

    import asyncio

    result = asyncio.run(
        execute_and_submit_mitigation(
            env,
            _real_gate(),
            _FAKE_CAPABILITIES,
            root_cause="container exceeded its memory limit and was OOMKilled",
            relevant_resource_spec='{"memory_limit": "128Mi"}',
            capability_catalog="run_kubectl, submit_mitigation",
            namespace="hotel-reservation",
            portfolio_size=1,
            portfolio_program=_FixedPortfolioModule(safe_to_actuate=False),
            translator=_FixedTranslatorModule(),
        )
    )

    assert result.attempted is False
    assert result.executed_commands == ()
    assert env.call_log == []  # real, never actuated


def test_safe_candidate_is_really_executed_in_real_order_and_submitted() -> None:
    env = _FakeSregymEnvironment()

    import asyncio

    result = asyncio.run(
        execute_and_submit_mitigation(
            env,
            _real_gate(),
            _FAKE_CAPABILITIES,
            root_cause="container exceeded its memory limit and was OOMKilled",
            relevant_resource_spec='{"memory_limit": "128Mi"}',
            capability_catalog="run_kubectl, submit_mitigation",
            namespace="hotel-reservation",
            portfolio_size=1,
            portfolio_program=_FixedPortfolioModule(safe_to_actuate=True),
            translator=_FixedTranslatorModule(),
        )
    )

    assert result.attempted is True
    # READ then DO executed (real order); VERIFY recorded as intent only,
    # never actuated as a third kubectl call.
    assert len(result.executed_commands) == 2
    assert result.executed_commands[0].startswith("kubectl get")
    assert result.executed_commands[1].startswith("kubectl patch")
    assert env.call_log == ["run_kubectl", "run_kubectl", "submit_mitigation"]
    assert env.last_mitigation_payload is not None
    assert env.last_mitigation_payload["mitigation"] != "not_attempted"
    assert "2 real step(s) executed" in env.last_mitigation_payload["mitigation"]
    assert any(stage["stage"] == "verify_intent" for stage in result.trajectory["stages"])


def test_translated_command_missing_kubectl_prefix_is_refused_not_actuated() -> None:
    env = _FakeSregymEnvironment()

    class _BadPrefixTranslator(dspy.Module):
        def forward(self, **kwargs) -> dspy.Prediction:
            return dspy.Prediction(kubectl_command="rm -rf /", is_safe_readonly_or_reversible=True)

        def __call__(self, **kwargs):
            return self.forward(**kwargs)

    import asyncio

    result = asyncio.run(
        execute_and_submit_mitigation(
            env,
            _real_gate(),
            _FAKE_CAPABILITIES,
            root_cause="x",
            relevant_resource_spec="y",
            capability_catalog="run_kubectl, submit_mitigation",
            namespace="hotel-reservation",
            portfolio_size=1,
            portfolio_program=_FixedPortfolioModule(safe_to_actuate=True),
            translator=_BadPrefixTranslator(),
        )
    )

    assert result.executed_commands == ()  # both DO/READ steps refused, never actuated
    assert "run_kubectl" not in env.call_log
    assert any(stage["stage"] == "translate_step_refused" for stage in result.trajectory["stages"])


def test_real_ocel_v2_trace_is_produced_when_a_recorder_is_supplied_and_conforms() -> None:
    env = _FakeSregymEnvironment()
    recorder = OcelExecutionRecorder(execution_id="mitigation-actuation-run-001")

    import asyncio

    result = asyncio.run(
        execute_and_submit_mitigation(
            env,
            _real_gate(),
            _FAKE_CAPABILITIES,
            root_cause="container exceeded its memory limit and was OOMKilled",
            relevant_resource_spec='{"memory_limit": "128Mi"}',
            capability_catalog="run_kubectl, submit_mitigation",
            namespace="hotel-reservation",
            portfolio_size=1,
            portfolio_program=_FixedPortfolioModule(safe_to_actuate=True),
            translator=_FixedTranslatorModule(),
            recorder=recorder,
        )
    )

    assert result.attempted is True
    log = recorder.close()
    assert len(log.events) == 2  # one per real executed DO/READ step

    real_labels = tuple(
        next(attr.value.value for attr in event.attributes if attr.key == "label") for event in log.events
    )
    intended = {"mitigation-actuation-run-001": real_labels}
    conformance = check_object_centric_conformance(log, intended_traces_by_object_id=intended)
    assert conformance.all_conform is True
    assert conformance.overall_fitness == 1.0


# ---------------------------------------------------------------------------
# Live Groq: real TranslateMitigationStepToKubectlCommand call
# ---------------------------------------------------------------------------

_GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

requires_real_groq_key = pytest.mark.skipif(
    not _GROQ_API_KEY,
    reason=(
        "GROQ_API_KEY is not set in this environment -- a real live Groq "
        "call is required for this test and no mock substitute is used "
        "per .claude/rules/testing-chicago-style.md."
    ),
)


@requires_real_groq_key
def test_live_translate_mitigation_step_produces_a_real_kubectl_command() -> None:
    from autofde_lab.reasoning.mitigation_kubectl_translation_signatures import (
        TranslateMitigationStepToKubectlCommand,
    )

    lm = dspy.LM("groq/openai/gpt-oss-120b", api_key=_GROQ_API_KEY, cache=False, max_tokens=8000)
    translate = dspy.Predict(TranslateMitigationStepToKubectlCommand)

    with dspy.context(lm=lm):
        prediction = translate(
            step_description="patch the deployment memory limit to 512Mi",
            step_consequence="DO",
            relevant_resource_spec='{"namespace": "hotel-reservation", "deployment": "geo", '
            '"memory_limit": "128Mi"}',
        )

    assert prediction.kubectl_command.startswith("kubectl ")
    assert "geo" in prediction.kubectl_command or "hotel-reservation" in prediction.kubectl_command
