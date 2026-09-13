# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Real, reusable DSPy `Signature` classes for Kubernetes operational
reasoning -- gather, summarize, diagnose, propose, report.

**Nothing here is hardcoded to sregym, gymact, or any other specific
benchmark/environment.** Every field description is written in plain
Kubernetes vocabulary (namespace, resource kind, manifest, event) with no
reference to a benchmark problem id, a conductor API, a submission
protocol, or any other caller-specific concept. This is deliberate: these
signatures are meant to be reusable across `gymact_dspy_react.py` (sregym),
a future non-sregym k8s environment, or a standalone k8s-reasoning CLI --
none of which should need to know about each other.

What a `dspy.Signature` is and is not
--------------------------------------
A `Signature` declares the typed input/output CONTRACT for one LLM
reasoning step (what goes in, what must come out) -- it is not a tool, not
a loop, and it makes no network/API call by itself. Binding one to a real
`dspy.Predict`/`dspy.ChainOfThought`/`dspy.ReAct` module and calling it is
what makes an actual LM call; constructing or inspecting a `Signature`
class never does. `tests/reasoning/test_k8s_signatures_chicago.py` proves
this split: real, no-LLM-call structural tests for every signature here,
plus one named, `GROQ_API_KEY`-gated live test exercising a real LM call
end to end, never a mock.

The five reasoning steps modeled here
---------------------------------------
1. `SummarizeKubernetesResourceState` -- turn raw kubectl JSON output into
   a concise natural-language summary answering a specific question.
2. `DiagnoseKubernetesFault` -- given observed resource state and symptoms,
   propose a root-cause hypothesis grounded in the given evidence.
3. `ClassifyKubernetesAnomaly` -- given an observed vs. expected/baseline
   resource state, classify what kind of anomaly (if any) is present, from
   an open, LLM-chosen category, not a fixed taxonomy this module would
   otherwise have to hardcode and keep in sync with a caller's domain.
4. `ProposeKubernetesRemediation` -- given a root-cause diagnosis, propose
   a concrete remediation action (a kubectl command or a manifest patch)
   and an honest assessment of its risk.
5. `DecideNextKubernetesInvestigationStep` -- given the evidence gathered
   so far and what remains unknown, decide the single next real
   investigation action to take (the "think" step of a ReAct-style loop),
   generic enough to drive any tool surface a caller wires up.
"""

from __future__ import annotations

import dspy

__all__ = [
    "SummarizeKubernetesResourceState",
    "DiagnoseKubernetesFault",
    "ClassifyKubernetesAnomaly",
    "ProposeKubernetesRemediation",
    "DecideNextKubernetesInvestigationStep",
]


class SummarizeKubernetesResourceState(dspy.Signature):
    """Summarize raw Kubernetes resource state (as returned by a real
    `kubectl get ... -o json` call) into a concise, accurate natural-
    language answer to a specific question. Never invent a resource,
    field, or status value not present in the given raw state."""

    raw_resource_json: str = dspy.InputField(
        desc="raw JSON text from a real `kubectl get`/`describe` call (any resource kind)"
    )
    question: str = dspy.InputField(
        desc="the specific question this summary must answer, e.g. "
        "'which pods are not Ready and why?'"
    )
    summary: str = dspy.OutputField(
        desc="concise natural-language answer, citing only fields actually "
        "present in raw_resource_json"
    )


class DiagnoseKubernetesFault(dspy.Signature):
    """Diagnose the likely root cause of a Kubernetes application fault,
    grounded strictly in the given observed evidence. Never conclude a
    root cause the evidence does not support -- state uncertainty
    explicitly in `confidence` rather than guessing."""

    namespace: str = dspy.InputField(desc="the Kubernetes namespace under investigation")
    symptom_description: str = dspy.InputField(
        desc="a natural-language description of the observed symptom(s), "
        "e.g. 'checkout requests intermittently return 503'"
    )
    observed_resource_state: str = dspy.InputField(
        desc="real, raw or summarized Kubernetes resource state relevant to the symptom "
        "(deployments, pods, services, events, logs -- whatever was actually collected)"
    )
    root_cause: str = dspy.OutputField(
        desc="free-text root-cause hypothesis, grounded in observed_resource_state"
    )
    confidence: float = dspy.OutputField(
        desc="0.0-1.0, must reflect actual evidentiary support in observed_resource_state, "
        "not the model's general confidence in its own reasoning"
    )
    supporting_evidence: str = dspy.OutputField(
        desc="the specific fields/values from observed_resource_state that support root_cause"
    )


class ClassifyKubernetesAnomaly(dspy.Signature):
    """Classify whether a Kubernetes resource's observed state represents
    an anomaly relative to its expected/baseline state, and if so, what
    kind. The category is open-ended (the model's own words), not
    constrained to a fixed enum this signature would otherwise have to
    hardcode -- callers that need a closed taxonomy should validate/map
    `anomaly_category` themselves."""

    observed_state: str = dspy.InputField(desc="the real, currently-observed resource state")
    expected_state: str = dspy.InputField(
        desc="the expected/baseline resource state to compare against "
        "(a known-good manifest, a prior healthy snapshot, or a stated invariant)"
    )
    is_anomalous: bool = dspy.OutputField(
        desc="True only if observed_state genuinely deviates from expected_state "
        "in a way that matters operationally"
    )
    anomaly_category: str = dspy.OutputField(
        desc="a short, free-text category label for the anomaly (e.g. "
        "'image-baseline-mismatch', 'scaled-to-zero', 'missing-env-var'), "
        "or 'none' when is_anomalous is False"
    )
    rationale: str = dspy.OutputField(desc="why observed_state was judged (an)omalous or not")


class ProposeKubernetesRemediation(dspy.Signature):
    """Propose a concrete remediation for a diagnosed Kubernetes fault.
    The proposal must be a real, executable action (a kubectl command or a
    manifest patch) -- never a vague description like 'fix the
    configuration'. Also state the real risk of applying it."""

    root_cause: str = dspy.InputField(desc="the diagnosed root cause to remediate")
    relevant_resource_spec: str = dspy.InputField(
        desc="the current spec/state of the resource(s) the remediation would change"
    )
    remediation_action: str = dspy.OutputField(
        desc="a concrete, executable remediation: either a real kubectl command "
        "(e.g. 'kubectl scale deployment/frontend --replicas=3 -n prod') or a "
        "manifest patch (a real JSON/YAML patch document)"
    )
    risk_assessment: str = dspy.OutputField(
        desc="an honest assessment of what could go wrong if remediation_action is applied, "
        "including 'low risk' as a legitimate honest answer when genuinely low"
    )


class DecideNextKubernetesInvestigationStep(dspy.Signature):
    """Decide the single next real investigation action to take, given the
    evidence gathered so far and what remains unknown. This is the
    "think" step of a ReAct-style loop -- generic enough to drive any real
    tool surface a caller wires up (kubectl reads, log queries, metric
    queries, etc.); this signature names WHAT to investigate next, never
    which specific tool implementation to call."""

    evidence_so_far: str = dspy.InputField(
        desc="a summary of everything real observed/collected so far this investigation"
    )
    open_questions: str = dspy.InputField(
        desc="what remains unknown or unconfirmed that would change the diagnosis"
    )
    next_action: str = dspy.OutputField(
        desc="the single next real investigation action to take, described precisely "
        "enough that a caller could translate it into one real tool call "
        "(e.g. 'read the last 50 events in namespace prod sorted by timestamp')"
    )
    rationale: str = dspy.OutputField(
        desc="why next_action, specifically, is the most useful next real step "
        "given evidence_so_far and open_questions"
    )
