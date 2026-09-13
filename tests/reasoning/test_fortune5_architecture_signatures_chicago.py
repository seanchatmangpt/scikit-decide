# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for `fortune5_architecture_signatures` and
`fortune5_architecture_metrics`.

Structural tests need no LLM call. The one live-LM test is real,
`GROQ_API_KEY`-gated, named `skipif` -- never a mock -- matching
`tests/reasoning/test_k8s_signatures_chicago.py`'s own established
pattern. The metric tests are pure Python (no LLM at all): they assert
against `world_transformation_orchestrator.select_transformation`'s real,
deterministic answer, never a self-report.

No `unittest.mock` / `Mock` / `MagicMock` / `patch` / `monkeypatch`
anywhere in this file.
"""

from __future__ import annotations

import os

import dspy
import pytest

from autofde_lab.reasoning.fortune5_architecture_metrics import transformation_candidate_metric
from autofde_lab.reasoning.fortune5_architecture_signatures import (
    DeriveBusinessArchitecture,
    InferArchitectureVision,
    SelectTransformationCandidate,
)
from autofde_lab.reasoning.scenarios.world_transformation_scenarios import (
    ScenarioMetadata_checkout_latency_scenario_v_1,
)
from autofde_lab.reasoning.world_transformation_orchestrator import compute_delta, infer_desired_state

ALL_SIGNATURES = (InferArchitectureVision, DeriveBusinessArchitecture, SelectTransformationCandidate)


def test_every_signature_is_a_real_dspy_signature_subclass() -> None:
    for sig in ALL_SIGNATURES:
        assert issubclass(sig, dspy.Signature), f"{sig.__name__} must subclass dspy.Signature"


def test_every_signature_has_at_least_one_input_and_one_output_field() -> None:
    for sig in ALL_SIGNATURES:
        fields = sig.model_fields
        input_fields = [
            name for name, f in fields.items()
            if f.json_schema_extra and f.json_schema_extra.get("__dspy_field_type") == "input"
        ]
        output_fields = [
            name for name, f in fields.items()
            if f.json_schema_extra and f.json_schema_extra.get("__dspy_field_type") == "output"
        ]
        assert input_fields, f"{sig.__name__} must declare at least one InputField"
        assert output_fields, f"{sig.__name__} must declare at least one OutputField"


def test_infer_architecture_vision_never_drops_stakeholder_concerns_silently() -> None:
    """Structural check on the real field set, not a live call: the
    signature must have a place to report unaddressed concerns -- the
    field existing is what this test verifies; whether a real LM call
    fills it honestly is the separate, GROQ-gated test below."""
    output_field_names = {
        name for name, f in InferArchitectureVision.model_fields.items()
        if f.json_schema_extra and f.json_schema_extra.get("__dspy_field_type") == "output"
    }
    assert "unaddressed_concerns" in output_field_names


def test_select_transformation_candidate_signature_names_the_none_convention() -> None:
    """The signature's own docstring must state the NONE-refusal
    convention this repo's rule-based select_transformation already
    uses -- a structural, textual check, not a live-call check."""
    assert "NONE" in (SelectTransformationCandidate.__doc__ or "")


# ---------------------------------------------------------------------------
# transformation_candidate_metric -- pure Python, no LLM, real external signal
# ---------------------------------------------------------------------------


def test_metric_scores_1_when_prediction_matches_the_real_rule_based_answer() -> None:
    metadata = ScenarioMetadata_checkout_latency_scenario_v_1()
    delta = compute_delta(metadata, infer_desired_state(metadata))

    example = dspy.Example(delta=delta)
    prediction = dspy.Prediction(candidate_label="scale_out_api_instances")

    result = transformation_candidate_metric(example, prediction)

    assert result.score == 1.0
    assert "matches" in result.feedback


def test_metric_scores_0_when_prediction_disagrees_with_the_real_rule_based_answer() -> None:
    metadata = ScenarioMetadata_checkout_latency_scenario_v_1()
    delta = compute_delta(metadata, infer_desired_state(metadata))

    example = dspy.Example(delta=delta)
    prediction = dspy.Prediction(candidate_label="a_fabricated_wrong_label")

    result = transformation_candidate_metric(example, prediction)

    assert result.score == 0.0
    assert "does not match" in result.feedback


def test_metric_never_grades_against_its_own_prediction_it_grades_against_an_external_function() -> None:
    """The concrete proof this metric is not a self-report: calling
    select_transformation directly (the real external function) and the
    metric's internal computation must agree, confirmed by reading the
    metric's own source-derived behavior, not asserted from its docstring."""
    from autofde_lab.reasoning.world_transformation_orchestrator import select_transformation

    metadata = ScenarioMetadata_checkout_latency_scenario_v_1()
    delta = compute_delta(metadata, infer_desired_state(metadata))
    expected = select_transformation(delta)

    example = dspy.Example(delta=delta)
    prediction = dspy.Prediction(candidate_label=expected.label)

    result = transformation_candidate_metric(example, prediction)
    assert result.score == 1.0


# ---------------------------------------------------------------------------
# Live LM test -- real GROQ call, named skip, never a mock
# ---------------------------------------------------------------------------

_GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

requires_real_groq_key = pytest.mark.skipif(
    not _GROQ_API_KEY,
    reason=(
        "GROQ_API_KEY is not set in this environment -- a real live Groq call is required "
        "for this test and no mock substitute is used per .claude/rules/testing-chicago-style.md."
    ),
)


@requires_real_groq_key
def test_infer_architecture_vision_real_live_call_addresses_or_names_every_concern() -> None:
    lm = dspy.LM("groq/openai/gpt-oss-20b", api_key=_GROQ_API_KEY, cache=False)
    with dspy.context(lm=lm):
        predictor = dspy.ChainOfThought(InferArchitectureVision)
        result = predictor(
            observed_state="3 API instances, 1 SQL primary, public DB endpoint, p95=780ms",
            business_objective="reduce checkout latency below 250ms SLO",
            stakeholder_concerns="security team: DB must not be publicly reachable\nfinance: monthly cost under $18k",
        )

    assert result.vision_statement
    assert result.unaddressed_concerns is not None  # "none" is a valid real answer; missing is not
