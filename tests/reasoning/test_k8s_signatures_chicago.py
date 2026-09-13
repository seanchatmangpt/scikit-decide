# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style test for `autofde_lab.reasoning.k8s_signatures`.

Structural tests need no LLM call and make none -- constructing/inspecting
a `dspy.Signature` class is pure Python, never a network call. The one
live-LM test is real, `GROQ_API_KEY`-gated, and named `skipif` -- never a
mock -- matching `tests/reasoning/test_gymact_dspy_react_chicago.py`'s own
established pattern.

No `unittest.mock` / `Mock` / `patch` / `monkeypatch` anywhere in this file.
"""

from __future__ import annotations

import os

import dspy
import pytest

from autofde_lab.reasoning.k8s_signatures import (
    ClassifyKubernetesAnomaly,
    DecideNextKubernetesInvestigationStep,
    DiagnoseKubernetesFault,
    ProposeKubernetesRemediation,
    SummarizeKubernetesResourceState,
)

ALL_SIGNATURES = (
    SummarizeKubernetesResourceState,
    DiagnoseKubernetesFault,
    ClassifyKubernetesAnomaly,
    ProposeKubernetesRemediation,
    DecideNextKubernetesInvestigationStep,
)

# Vocabulary this module's whole point is to avoid -- any of these leaking
# into a real field description would mean a signature isn't actually
# reusable outside sregym/gymact, contradicting this module's own claim.
_FORBIDDEN_VOCABULARY = ("sregym", "gymact", "problem_id", "conductor", "benchmark")


def test_every_signature_is_a_real_dspy_signature_subclass():
    for sig in ALL_SIGNATURES:
        assert issubclass(sig, dspy.Signature), f"{sig.__name__} must subclass dspy.Signature"


def test_every_signature_has_at_least_one_input_and_one_output_field():
    for sig in ALL_SIGNATURES:
        fields = sig.model_fields
        input_fields = [
            name for name, f in fields.items() if f.json_schema_extra and f.json_schema_extra.get("__dspy_field_type") == "input"
        ]
        output_fields = [
            name for name, f in fields.items() if f.json_schema_extra and f.json_schema_extra.get("__dspy_field_type") == "output"
        ]
        assert input_fields, f"{sig.__name__} must declare at least one InputField"
        assert output_fields, f"{sig.__name__} must declare at least one OutputField"


def test_no_signature_leaks_caller_specific_vocabulary_into_field_descriptions():
    """The real, direct proof of this module's own claim: every field's
    `desc` and the signature's own docstring are checked against a real,
    named forbidden-vocabulary list -- not asserted from memory."""
    for sig in ALL_SIGNATURES:
        docstring = (sig.__doc__ or "").lower()
        for banned in _FORBIDDEN_VOCABULARY:
            assert banned not in docstring, f"{sig.__name__}'s docstring leaks {banned!r}"
        for field_name, field in sig.model_fields.items():
            desc = str(field.json_schema_extra.get("desc", "") if field.json_schema_extra else "").lower()
            for banned in _FORBIDDEN_VOCABULARY:
                assert banned not in desc, (
                    f"{sig.__name__}.{field_name}'s description leaks {banned!r}: {desc!r}"
                )


def test_each_signature_binds_to_a_real_dspy_predict_module_without_any_lm_call():
    """Constructing `dspy.Predict(signature)` is real, structural wiring --
    it builds a real module ready to call an LM, but does not itself call
    one. Proves every signature here is genuinely usable, not just
    syntactically valid."""
    for sig in ALL_SIGNATURES:
        predictor = dspy.Predict(sig)
        assert predictor.signature is sig or predictor.signature == sig


def test_classify_kubernetes_anomaly_declares_the_documented_output_shape():
    fields = ClassifyKubernetesAnomaly.model_fields
    assert "is_anomalous" in fields
    assert "anomaly_category" in fields
    assert "rationale" in fields


def test_diagnose_kubernetes_fault_declares_the_documented_output_shape():
    fields = DiagnoseKubernetesFault.model_fields
    assert "root_cause" in fields
    assert "confidence" in fields
    assert "supporting_evidence" in fields


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
def test_live_groq_summarize_kubernetes_resource_state():
    """Real, live LM call proving `SummarizeKubernetesResourceState` is
    genuinely usable end to end -- real Groq request, real response,
    structurally validated (never asserted on exact wording, which would
    be flaky against a real, non-deterministic LM)."""
    lm = dspy.LM("groq/openai/gpt-oss-20b", api_key=_GROQ_API_KEY, cache=False)
    predictor = dspy.Predict(SummarizeKubernetesResourceState)

    raw_json = (
        '{"items": [{"metadata": {"name": "checkout-7d8f"}, '
        '"status": {"phase": "CrashLoopBackOff", "containerStatuses": '
        '[{"restartCount": 14, "lastState": {"terminated": {"reason": "OOMKilled"}}}]}}]}'
    )

    with dspy.context(lm=lm):
        result = predictor(
            raw_resource_json=raw_json,
            question="which pods are unhealthy and why?",
        )

    assert isinstance(result.summary, str)
    assert len(result.summary) > 0
