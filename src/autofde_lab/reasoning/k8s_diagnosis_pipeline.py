# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Real, multi-stage DSPy pipeline composing `k8s_signatures.py`'s
generic, reusable signatures -- matching DSPy's own documented
multi-stage `Module` composition pattern
(https://dspy.ai/tutorials/custom_module/): sub-modules declared as
instance attributes in `__init__`, invoked in sequence in `forward()`,
each stage's output feeding the next stage's input.

**Nothing here is hardcoded to sregym, gymact, or any other specific
benchmark/environment** -- same claim as `k8s_signatures.py`, and checked
the same way (see `tests/reasoning/test_k8s_diagnosis_pipeline_chicago.py`).
This module owns no environment materialization, no tool wiring, no
`CapabilityGate` -- it is pure DSPy reasoning composition. A caller that
needs gated, real tool calls (kubectl reads, real actuation) wires those
in separately, the same way `gymact_dspy_react.py` already does for its
own `DiagnoseClusterFault` signature; this pipeline is deliberately a
smaller, composable, tool-free reasoning unit that such a caller can
invoke with already-collected evidence, or extend.

Four real stages, matching the docs' own pattern of sequential dspy.Predict/
dspy.ChainOfThought sub-modules:

1. `summarize` (`SummarizeKubernetesResourceState`) -- raw kubectl JSON
   evidence -> a concise summary relevant to the given symptom.
2. `classify` (`ClassifyKubernetesAnomaly`) -- that summary vs. an
   expected/baseline state -> whether an anomaly is present and its
   category.
3. `diagnose` (`DiagnoseKubernetesFault`, via `dspy.ChainOfThought` --
   the one stage genuinely benefiting from explicit reasoning before its
   answer, per the docs' own RAG example using ChainOfThought for the
   final answer-generation stage) -> root cause, confidence, evidence.
4. `propose_remediation` (`ProposeKubernetesRemediation`) -- the
   diagnosed root cause -> a concrete remediation action and its risk.

Real, direct call chain
------------------------
`summary = self.summarize(...).summary` -> `anomaly = self.classify(
observed_state=summary, ...)` -> `diagnosis = self.diagnose(...,
observed_resource_state=summary)` -> `remediation =
self.propose_remediation(root_cause=diagnosis.root_cause, ...)` -- each
stage's real output is the next stage's real input, never re-derived or
assumed; if an earlier stage's output is empty/unusable, the next real
stage sees exactly that, honestly, not a silently patched-over value.
"""

from __future__ import annotations

import dspy

from autofde_lab.reasoning.k8s_signatures import (
    ClassifyKubernetesAnomaly,
    DiagnoseKubernetesFault,
    ProposeKubernetesRemediation,
    SummarizeKubernetesResourceState,
)

__all__ = ["KubernetesDiagnosisPipeline"]


class KubernetesDiagnosisPipeline(dspy.Module):
    """Real, four-stage DSPy `Module`: summarize -> classify -> diagnose
    -> propose remediation. Construct once, call (`__call__`, never
    `forward()` directly -- see DSPy's own guidance) with real evidence
    for each new investigation."""

    def __init__(self) -> None:
        super().__init__()
        self.summarize = dspy.Predict(SummarizeKubernetesResourceState)
        self.classify = dspy.Predict(ClassifyKubernetesAnomaly)
        self.diagnose = dspy.ChainOfThought(DiagnoseKubernetesFault)
        self.propose_remediation = dspy.Predict(ProposeKubernetesRemediation)

    def forward(
        self,
        *,
        namespace: str,
        symptom_description: str,
        raw_resource_json: str,
        expected_state: str,
    ) -> dspy.Prediction:
        """Run all four real stages in sequence.

        Args:
            namespace: the real Kubernetes namespace under investigation.
            symptom_description: natural-language description of the
                observed symptom driving this investigation.
            raw_resource_json: real, raw `kubectl get ... -o json` output
                (or equivalent) relevant to the symptom.
            expected_state: the expected/baseline state to compare
                against for anomaly classification.

        Returns:
            A real `dspy.Prediction` carrying every stage's real output:
            `summary`, `is_anomalous`, `anomaly_category`,
            `anomaly_rationale`, `root_cause`, `confidence`,
            `supporting_evidence`, `remediation_action`, `risk_assessment`.
        """
        summary = self.summarize(
            raw_resource_json=raw_resource_json,
            question=f"what is the current state relevant to this symptom: {symptom_description}",
        ).summary

        anomaly = self.classify(observed_state=summary, expected_state=expected_state)

        diagnosis = self.diagnose(
            namespace=namespace,
            symptom_description=symptom_description,
            observed_resource_state=summary,
        )

        remediation = self.propose_remediation(
            root_cause=diagnosis.root_cause,
            relevant_resource_spec=raw_resource_json,
        )

        return dspy.Prediction(
            summary=summary,
            is_anomalous=anomaly.is_anomalous,
            anomaly_category=anomaly.anomaly_category,
            anomaly_rationale=anomaly.rationale,
            root_cause=diagnosis.root_cause,
            confidence=diagnosis.confidence,
            supporting_evidence=diagnosis.supporting_evidence,
            remediation_action=remediation.remediation_action,
            risk_assessment=remediation.risk_assessment,
        )
