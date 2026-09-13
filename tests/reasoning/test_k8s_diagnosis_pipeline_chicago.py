# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style test for `autofde_lab.reasoning.k8s_diagnosis_pipeline`.

Structural tests need no LLM call. The one live-LM test is real,
`GROQ_API_KEY`-gated, and named `skipif` -- never a mock.

No `unittest.mock` / `Mock` / `patch` / `monkeypatch` anywhere in this file.
"""

from __future__ import annotations

import os

import dspy
import pytest

from autofde_lab.reasoning.k8s_diagnosis_pipeline import KubernetesDiagnosisPipeline
from autofde_lab.reasoning.k8s_signatures import (
    ClassifyKubernetesAnomaly,
    DiagnoseKubernetesFault,
    ProposeKubernetesRemediation,
    SummarizeKubernetesResourceState,
)


def test_pipeline_is_a_real_dspy_module():
    pipeline = KubernetesDiagnosisPipeline()
    assert isinstance(pipeline, dspy.Module)


def test_pipeline_composes_the_four_real_documented_stages_in_declared_order():
    """Real, direct structural proof of the composition claim -- each
    sub-module attribute really exists, really is bound to the real
    signature the docstring names, in the documented stage order."""
    pipeline = KubernetesDiagnosisPipeline()

    assert isinstance(pipeline.summarize, dspy.Predict)
    assert pipeline.summarize.signature is SummarizeKubernetesResourceState \
        or pipeline.summarize.signature == SummarizeKubernetesResourceState

    assert isinstance(pipeline.classify, dspy.Predict)
    assert pipeline.classify.signature is ClassifyKubernetesAnomaly \
        or pipeline.classify.signature == ClassifyKubernetesAnomaly

    assert isinstance(pipeline.diagnose, dspy.ChainOfThought)
    # ChainOfThought wraps its real underlying Predict as `.predict`, and
    # compiles a real, EXTENDED StringSignature (it prepends its own
    # `reasoning` field) -- confirmed live, so this checks the compiled
    # signature's real field names are a superset of
    # DiagnoseKubernetesFault's own declared ones, not identity/equality
    # with the original Signature class.
    compiled_field_names = set(pipeline.diagnose.predict.signature.model_fields)
    assert set(DiagnoseKubernetesFault.model_fields) <= compiled_field_names

    assert isinstance(pipeline.propose_remediation, dspy.Predict)
    assert pipeline.propose_remediation.signature is ProposeKubernetesRemediation \
        or pipeline.propose_remediation.signature == ProposeKubernetesRemediation


def test_pipeline_forward_signature_names_every_stage_input_it_needs():
    """A real, direct check on `forward`'s own parameter list -- proves
    the pipeline's public contract genuinely requires the raw evidence
    every stage below it needs, not a partial/misleading subset."""
    import inspect

    params = set(inspect.signature(KubernetesDiagnosisPipeline.forward).parameters)
    assert {"namespace", "symptom_description", "raw_resource_json", "expected_state"} <= params


# ── Live Groq end-to-end: named skip, never a mock, when GROQ_API_KEY is unset ──

_GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

requires_real_groq_key = pytest.mark.skipif(
    not _GROQ_API_KEY,
    reason=(
        "GROQ_API_KEY is not set in this environment -- a real live Groq "
        "call is required for this test and no mock substitute is used per "
        ".claude/rules/testing-chicago-style.md."
    ),
)


@requires_real_groq_key
def test_live_groq_full_pipeline_run_produces_a_real_prediction_with_every_stage_field():
    """Real, live, end-to-end run of all four stages against a real Groq
    LM. Never asserts on exact wording (real, non-deterministic LM output)
    -- only that every real stage genuinely ran and produced a real,
    non-empty value for its own output field(s)."""
    lm = dspy.LM("groq/openai/gpt-oss-20b", api_key=_GROQ_API_KEY, cache=False)
    pipeline = KubernetesDiagnosisPipeline()

    raw_json = (
        '{"items": [{"metadata": {"name": "checkout-7d8f"}, '
        '"status": {"phase": "CrashLoopBackOff", "containerStatuses": '
        '[{"restartCount": 14, "lastState": {"terminated": {"reason": "OOMKilled"}}}]}}]}'
    )

    with dspy.context(lm=lm):
        result = pipeline(
            namespace="prod",
            symptom_description="checkout pods keep restarting",
            raw_resource_json=raw_json,
            expected_state="checkout pods should be Running with 0 restarts",
        )

    for field in (
        "summary",
        "is_anomalous",
        "anomaly_category",
        "root_cause",
        "confidence",
        "supporting_evidence",
        "remediation_action",
        "risk_assessment",
    ):
        assert hasattr(result, field), f"missing real stage output field: {field}"
    assert isinstance(result.summary, str) and len(result.summary) > 0
    assert isinstance(result.root_cause, str) and len(result.root_cause) > 0
    assert isinstance(result.remediation_action, str) and len(result.remediation_action) > 0
