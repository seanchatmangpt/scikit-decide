# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for `autofde_lab.reasoning.gepa_train`.

Real collaborators throughout: a real, seeded `faker.Faker`, a real
`dspy.Example`/`dspy.Prediction`, and (for the one live case) a real
`dspy.LM` + real `dspy.GEPA` compile against Groq -- named `skipif` on
`GROQ_API_KEY`, never a mock substitute, per
`.claude/rules/testing-chicago-style.md`.

No `unittest.mock` / `Mock` / `MagicMock` / `patch` / `monkeypatch` anywhere
in this file.
"""

from __future__ import annotations

import os

import dspy
import pytest

from autofde_lab.reasoning.gepa_train import (
    FAULT_TEMPLATES,
    SreTroubleshootingReasoningOnly,
    build_trainset,
    metric_with_feedback,
    run_gepa_optimization,
    run_gepa_optimization_for_troubleshooting_pipeline,
)

# ---------------------------------------------------------------------------
# Structural: trainset construction and anti-memorization substitution
# ---------------------------------------------------------------------------


def test_build_trainset_produces_one_example_per_template_repetition() -> None:
    trainset = build_trainset(seed=1, n_per_template=2)
    assert len(trainset) == len(FAULT_TEMPLATES) * 2


def test_build_trainset_never_reuses_the_real_vendored_names() -> None:
    """The anti-memorization property this module exists to provide: no
    real sregym service/app name from the cited vendored source appears in
    the generated trainset's text."""
    real_vendored_names = ("geo", "hotel_reservation", "social_network", "astronomy_shop", "product-catalog")
    trainset = build_trainset(seed=2, n_per_template=2)

    for example in trainset:
        haystack = " ".join(
            [example.symptom_description, example.observed_resource_state, example.faked_component]
        ).lower()
        for real_name in real_vendored_names:
            assert real_name.replace("_", "-") not in haystack.replace("_", "-")


def test_build_trainset_is_deterministic_given_the_same_seed() -> None:
    first = build_trainset(seed=7, n_per_template=1)
    second = build_trainset(seed=7, n_per_template=1)

    assert [ex.faked_component for ex in first] == [ex.faked_component for ex in second]
    assert [ex.observed_resource_state for ex in first] == [ex.observed_resource_state for ex in second]


def test_build_trainset_different_seeds_produce_different_names() -> None:
    first = build_trainset(seed=1, n_per_template=1)
    second = build_trainset(seed=999, n_per_template=1)

    assert [ex.faked_component for ex in first] != [ex.faked_component for ex in second]


# ---------------------------------------------------------------------------
# Structural: the metric is real, deterministic, and keyword-grounded
# ---------------------------------------------------------------------------


def test_metric_scores_full_marks_when_all_diagnostic_keywords_present() -> None:
    template = next(t for t in FAULT_TEMPLATES if t.fault_id == "cpu_throttling")
    example = dspy.Example(
        fault_id=template.fault_id,
        diagnostic_keywords=template.diagnostic_keywords,
    )
    prediction = dspy.Prediction(
        root_cause=(
            "The service has a CPU limit set too low, causing CFS throttling; cgroup nr_throttled is high."
        )
    )

    result = metric_with_feedback(example, prediction)

    assert result.score == pytest.approx(1.0)
    assert "all real diagnostic signature terms present" in result.feedback


def test_metric_scores_partial_marks_and_names_missing_terms() -> None:
    template = next(t for t in FAULT_TEMPLATES if t.fault_id == "missing_configmap")
    example = dspy.Example(
        fault_id=template.fault_id,
        diagnostic_keywords=template.diagnostic_keywords,
    )
    prediction = dspy.Prediction(root_cause="Pods are stuck in a crashloop for unknown reasons.")

    result = metric_with_feedback(example, prediction)

    assert 0.0 < result.score < 1.0
    assert "configmap" in result.feedback


def test_metric_never_rewards_copying_the_faked_component_name_alone() -> None:
    """A prediction that only echoes the faked resource name, without
    naming the real fault mechanism, must not score full marks -- proving
    the metric grades diagnostic content, not name-matching."""
    trainset = build_trainset(seed=3, n_per_template=1)
    example = trainset[0]
    prediction = dspy.Prediction(root_cause=f"Something is wrong with {example.faked_component}.")

    result = metric_with_feedback(example, prediction)

    assert result.score < 1.0


# ---------------------------------------------------------------------------
# Structural: the troubleshooting-pipeline reasoning-only wrapper composes
# real sub-modules and metric_with_feedback is reusable against it as-is.
# ---------------------------------------------------------------------------


def test_sre_troubleshooting_reasoning_only_composes_real_pipeline_stages() -> None:
    program = SreTroubleshootingReasoningOnly()
    predictor_names = {name for name, _ in program.named_predictors()}

    # SreTroubleshootingPipeline always constructs all 8 real sub-modules
    # (select_probe/select_mitigation included); forward() only ever CALLS
    # the reasoning-only subset (orient/normalize/hypothesize/commit) -- the
    # scoping rule is about which stages the offline metric evaluates via
    # forward()'s real return value, not which sub-modules exist on the
    # underlying pipeline instance.
    assert predictor_names == {
        "_pipeline.orient_stage.predict",
        "_pipeline.normalize_stage.predict",
        "_pipeline._hypothesize_draft.predict",
        "_pipeline._hypothesize_compare.predict",
        "_pipeline._propose_probe.predict",
        "_pipeline._commit_diagnosis_draft.predict",
        "_pipeline._commit_diagnosis_compare.predict",
        "_pipeline._construct_mitigation.predict",
    }


def test_metric_with_feedback_is_reusable_against_reasoning_only_prediction() -> None:
    """metric_with_feedback only inspects prediction.root_cause and the
    example's own diagnostic_keywords/fault_id -- proven here by scoring a
    Prediction shaped exactly like SreTroubleshootingReasoningOnly.forward()'s
    real return value, not DiagnoseKubernetesFault's."""
    template = next(t for t in FAULT_TEMPLATES if t.fault_id == "incorrect_image")
    example = dspy.Example(fault_id=template.fault_id, diagnostic_keywords=template.diagnostic_keywords)
    prediction = dspy.Prediction(
        root_cause="the deployment pulls a non-existent image tag causing ImagePullBackOff",
        confidence=80,
        supporting_evidence="observed events",
    )

    result = metric_with_feedback(example, prediction)

    assert result.score == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Live Groq end-to-end: a real, small, bounded GEPA compile
#
# HARD-DISABLED (2026-08-10, direct user instruction: "comment out gepa or
# anything like that that could cost a lot"): a real dspy.GEPA compile makes
# many real LM calls per candidate per reflection round (task_lm + a
# separate reflection_lm), and this repo's own module docstring already
# flags that cost. Both live GEPA tests below are marked
# `pytest.mark.skip` unconditionally -- not just GROQ_API_KEY-gated -- so
# they never run by accident. To re-enable deliberately: remove the
# `pytest.mark.skip(...)` decorators below.
# ---------------------------------------------------------------------------

_disabled_pending_explicit_reenable = pytest.mark.skip(
    reason=(
        "Hard-disabled per direct user instruction: a real dspy.GEPA compile "
        "makes many real, billed LM calls. Remove this skip mark to "
        "deliberately re-enable."
    )
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


@_disabled_pending_explicit_reenable
@requires_real_groq_key
def test_live_gepa_compile_produces_a_real_dspy_module() -> None:
    """Real, small, bounded end-to-end: a real dspy.GEPA pass compiles a
    real DiagnoseKubernetesFault program against the real offline,
    faker-substituted trainset, backed by a real Groq LM call for both the
    task model and the reflection model. Kept deliberately tiny
    (n_per_template=1, auto='light') to bound real API cost."""
    task_lm = dspy.LM("groq/openai/gpt-oss-20b", api_key=_GROQ_API_KEY, cache=False)
    reflection_lm = dspy.LM("groq/openai/gpt-oss-20b", api_key=_GROQ_API_KEY, cache=False, temperature=1.0)

    compiled = run_gepa_optimization(
        seed=5,
        n_per_template=1,
        reflection_lm=reflection_lm,
        task_lm=task_lm,
        auto="light",
        num_threads=2,
    )

    assert isinstance(compiled, dspy.Module)


@_disabled_pending_explicit_reenable
@requires_real_groq_key
def test_live_gepa_compile_for_troubleshooting_pipeline_produces_real_module() -> None:
    """Real, small, bounded end-to-end: a real dspy.GEPA pass compiles the
    multi-stage SreTroubleshootingReasoningOnly program against the same
    real offline trainset. Kept tiny (n_per_template=1, auto='light')."""
    task_lm = dspy.LM("groq/openai/gpt-oss-120b", api_key=_GROQ_API_KEY, cache=False, max_tokens=16000)
    reflection_lm = dspy.LM(
        "groq/openai/gpt-oss-120b", api_key=_GROQ_API_KEY, cache=False, temperature=1.0, max_tokens=16000
    )

    compiled = run_gepa_optimization_for_troubleshooting_pipeline(
        seed=5,
        n_per_template=1,
        reflection_lm=reflection_lm,
        task_lm=task_lm,
        auto="light",
        num_threads=2,
    )

    assert isinstance(compiled, dspy.Module)
