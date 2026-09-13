# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for the harbor/terminus-2 DecisionBasis extraction (Lane B).

`current_harbor_terminus2_basis()` is cross-checked here against the real, already-persisted
`result.json` from this session's real, successful (reward 1.0) `hello-world-v3` trial --
not a hand-authored fixture. `materialize_harbor_invocation()` is asserted against the real
command line this session actually ran. No `unittest.mock`, `Mock`, `patch`, or
`monkeypatch` anywhere in this file.
"""

from __future__ import annotations

import json

import pytest

from autofde_lab.sota.decision_basis import DecisionBasis
from autofde_lab.sota.materialize_harbor import (
    HARBOR_ROOT,
    current_harbor_terminus2_basis,
    materialize_harbor_invocation,
)

_REAL_TRIAL_RESULT = (
    HARBOR_ROOT
    / "jobs"
    / "autofde-lab-level4-harbor-terminus2-hello-world-v3"
    / "hello-world__Q7JV4qH"
    / "result.json"
)

pytestmark = pytest.mark.skipif(
    not HARBOR_ROOT.is_dir(),
    reason=f"BLOCKED:HARBOR_CHECKOUT_ABSENT: {HARBOR_ROOT} does not exist",
)


def test_current_harbor_terminus2_basis_matches_the_real_dimension_values() -> None:
    basis = current_harbor_terminus2_basis()
    assert isinstance(basis, DecisionBasis)
    assert basis.planner.name == "harbor:terminus-2"
    assert basis.tool_policy.tool_names == ("bash_command",)
    assert basis.repair_policy.max_attempts == 3
    assert basis.budget.max_steps == 1_000_000
    assert basis.budget.llm_max_retries == 3


def test_basis_matches_the_real_already_persisted_trial_result() -> None:
    """Cross-check against the actual, real, already-on-disk result.json from this session's
    real trial -- not a memory of what the trial did, the durable artifact itself."""
    if not _REAL_TRIAL_RESULT.is_file():
        pytest.skip(
            f"BLOCKED:REAL_TRIAL_ARTIFACT_ABSENT: {_REAL_TRIAL_RESULT} not on disk -- run "
            "the real hello-world-v3 harbor trial (docs/2026-08-08-local-server-agent-"
            "driven-harbor-checkpoint.md) before re-enabling this check"
        )
    real_result = json.loads(_REAL_TRIAL_RESULT.read_text())
    basis = current_harbor_terminus2_basis()

    assert real_result["agent_info"]["model_info"]["provider"] == "hosted_vllm"
    assert real_result["agent_info"]["name"] == "terminus-2"
    assert real_result["verifier_result"]["rewards"]["reward"] == 1.0
    assert real_result["agent_result"]["metadata"]["n_episodes"] == 4
    # No real turn-count ceiling was ever configured for this real run, matching this
    # dimension's own "no such knob was set" default.
    assert "max_turns" not in real_result["config"]["agent"]["kwargs"]
    assert basis.model.id.endswith(real_result["agent_info"]["model_info"]["name"])


def test_materialize_matches_the_real_command_this_session_actually_ran() -> None:
    basis = current_harbor_terminus2_basis()
    argv, env = materialize_harbor_invocation(basis)

    assert argv == [
        "harbor", "run",
        "--agent", "terminus-2",
        "--model", "hosted_vllm/gemma-4-26b-a4b-it",
        "--path", "examples/tasks/hello-world",
        "--ak", "api_base=http://127.0.0.1:8080/v1",
        "--ak",
        'model_info={"max_input_tokens":32768,"max_output_tokens":4096,'
        '"input_cost_per_token":0,"output_cost_per_token":0}',
    ]
    assert env == {"HARBOR_TELEMETRY": "0"}


def test_materialize_refuses_an_unknown_planner_identity() -> None:
    from dataclasses import replace

    basis = current_harbor_terminus2_basis()
    wrong = replace(basis, planner=replace(basis.planner, name="sregym:stratus:mitigation_agent"))
    with pytest.raises(ValueError, match="terminus-2 planner identity"):
        materialize_harbor_invocation(wrong)


def test_model_info_kwarg_omitted_for_a_non_hosted_vllm_model() -> None:
    """The model_info workaround is specific to LiteLLM's hosted_vllm provider needing
    explicit cost/limit metadata -- a real, named provider with built-in metadata shouldn't
    carry it, per materialize_harbor_invocation's own docstring contract."""
    basis = current_harbor_terminus2_basis(model_id="anthropic/claude-sonnet-4-6")
    argv, _ = materialize_harbor_invocation(basis)
    assert "model_info" not in " ".join(argv)
