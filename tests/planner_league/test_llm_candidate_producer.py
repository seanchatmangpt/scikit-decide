# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for `llm_candidate_producer` -- real GLM-5.3-flash
calls against the real Z.ai API (`ZAI_API_KEY` required, gated with
`pytest.mark.skipif`, same pattern as `receipts/llm_agent.py`'s
`is_server_available()` gate for the local TurboFieldfare server). No
`unittest.mock` / `Mock` / `MagicMock` / `patch` / `monkeypatch` anywhere in
this file.

Two tests (`test_malformed_llm_output_raises_not_silently_admitted`,
`test_graduation_packet_unreachable_without_benchmark`) do not need
`ZAI_API_KEY` -- they exercise real parsing/type logic with no network call
-- and are intentionally left ungated so they always run.
"""

from __future__ import annotations

import asyncio
import inspect
import os

import pytest

from autofde_lab.planner_league.llm_candidate_producer import (
    DEFAULT_MODEL_ID,
    BackoffPolicy,
    ConcurrencyProbe,
    LLMCandidateParseError,
    LLMCandidatePoolPolicy,
    LLMCandidateRawOutput,
    LLMCandidateRequest,
    PoolRunFailure,
    admit_llm_candidate,
    call_glm_with_backoff,
    run_llm_candidate_pool,
)
from autofde_lab.planning.fond_hddl_product import CandidatePolicy
from autofde_lab.reasoning.lab_standing import GraduationPacket

requires_zai = pytest.mark.skipif(
    not os.environ.get("ZAI_API_KEY"),
    reason="requires real ZAI_API_KEY (Chicago-style: no mocking Z.ai)",
)


def _ready_choices():
    return {"s1": ("advance", "wait"), "s2": ("commit",)}


@requires_zai
def test_call_glm_with_backoff_returns_raw_output():
    request = LLMCandidateRequest(ready_choices=_ready_choices(), prompt_seed="t1")
    raw = asyncio.run(call_glm_with_backoff(request, backoff=BackoffPolicy()))
    assert isinstance(raw, LLMCandidateRawOutput)
    assert raw.model_id == DEFAULT_MODEL_ID
    assert raw.latency_s > 0
    assert len(raw.raw_response_sha256) == 64
    assert raw.raw_text  # real, non-empty model output


@requires_zai
def test_admit_llm_candidate_produces_typed_candidate_policy():
    request = LLMCandidateRequest(ready_choices=_ready_choices(), prompt_seed="t2")
    raw = asyncio.run(call_glm_with_backoff(request, backoff=BackoffPolicy()))
    try:
        candidate = admit_llm_candidate(raw)
    except LLMCandidateParseError as exc:
        pytest.fail(
            f"real model output failed to parse into an admitted candidate: {exc}\n"
            f"raw_text={raw.raw_text!r}"
        )
    assert isinstance(candidate, CandidatePolicy)
    # Built exclusively via candidate_policy_over_product -- never hand-built:
    # every chosen action must be one of the request's own admitted choices.
    for state, action in candidate.actions.items():
        assert action in _ready_choices()[state]


def test_malformed_llm_output_raises_not_silently_admitted():
    request = LLMCandidateRequest(ready_choices=_ready_choices(), prompt_seed="t3")

    not_json = LLMCandidateRawOutput(
        request=request,
        raw_text="not json at all",
        model_id=DEFAULT_MODEL_ID,
        latency_s=0.01,
    )
    with pytest.raises(LLMCandidateParseError):
        admit_llm_candidate(not_json)

    inadmissible_action = LLMCandidateRawOutput(
        request=request,
        raw_text='{"s1": "self_destruct"}',
        model_id=DEFAULT_MODEL_ID,
        latency_s=0.01,
    )
    with pytest.raises(LLMCandidateParseError):
        admit_llm_candidate(inadmissible_action)

    unknown_state = LLMCandidateRawOutput(
        request=request,
        raw_text='{"s99": "advance"}',
        model_id=DEFAULT_MODEL_ID,
        latency_s=0.01,
    )
    with pytest.raises(LLMCandidateParseError):
        admit_llm_candidate(unknown_state)

    empty = LLMCandidateRawOutput(
        request=request, raw_text="{}", model_id=DEFAULT_MODEL_ID, latency_s=0.01
    )
    with pytest.raises(LLMCandidateParseError):
        admit_llm_candidate(empty)


@requires_zai
def test_run_llm_candidate_pool_respects_max_concurrency():
    requests = tuple(
        LLMCandidateRequest(ready_choices=_ready_choices(), prompt_seed=f"seed-{i}")
        for i in range(8)
    )
    probe = ConcurrencyProbe()
    policy = LLMCandidatePoolPolicy(max_concurrency=3)

    result = asyncio.run(
        run_llm_candidate_pool(requests, policy=policy, concurrency_probe=probe)
    )

    assert probe.peak <= 3
    assert probe.peak >= 1  # the pool actually ran calls, this isn't vacuous
    assert len(result.admitted) + len(result.failures) == len(requests)
    assert len(result.identity_sha256) == 64


@requires_zai
def test_pool_run_result_reports_failures_explicitly():
    """Drives one real failure mode (a genuinely invalid API key against the
    real Z.ai endpoint -- a real HTTP round trip, not a mock) through
    max_retries=0 so it is not retried away, and asserts it lands in
    PoolRunResult.failures rather than being silently dropped."""

    async def _bad_key_call(_request: LLMCandidateRequest, model_id: str) -> str:
        import dspy

        def _call() -> str:
            lm = dspy.LM(
                model_id, api_key="sk-invalid-cap11-test", max_tokens=10, cache=False
            )
            result = lm("ping")
            return str(result[0]) if isinstance(result, list) else str(result)

        return await asyncio.to_thread(_call)

    requests = (
        LLMCandidateRequest(ready_choices=_ready_choices(), prompt_seed="fail-1"),
    )
    policy = LLMCandidatePoolPolicy(backoff=BackoffPolicy(max_retries=0))

    result = asyncio.run(
        run_llm_candidate_pool(requests, policy=policy, call_fn=_bad_key_call)
    )

    assert result.admitted == ()
    assert len(result.failures) == 1
    failure = result.failures[0]
    assert isinstance(failure, PoolRunFailure)
    assert failure.request is requests[0]
    assert failure.error  # a real error message was captured, not swallowed


def test_graduation_packet_unreachable_without_benchmark():
    """Structural proof that there is no constructor path from a
    CandidatePolicy / LLMCandidateRawOutput straight to GraduationPacket:
    the only accepted verdict-carrying field is a real FalsificationResult,
    and GraduationPacket's own __post_init__ rejects anything else."""

    params = inspect.signature(GraduationPacket.__init__).parameters
    assert "falsification" in params
    for name in ("candidate_policy", "llm_output", "raw_output"):
        assert name not in params

    wrong_type_falsification: object = CandidatePolicy(actions={"s1": "advance"})
    with pytest.raises(TypeError):
        GraduationPacket(
            candidate_id="c1",
            falsification=wrong_type_falsification,  # type: ignore[arg-type]
            world_ref_digest="deadbeef",
            receipt_refs=(),
            benchmark_refs=(),
            falsifier_refs=(),
            limits=(),
        )
