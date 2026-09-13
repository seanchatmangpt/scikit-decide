# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Real, reusable DSPy `Signature` classes for the SRE troubleshooting
cognition graph: orient, normalize (O -> O*), hypothesize, propose a
discriminating probe, commit a diagnosis, construct a mitigation.

**Nothing here is hardcoded to sregym, gymact, or any other specific
benchmark/environment** -- same discipline as `k8s_signatures.py`. Every
field is plain troubleshooting vocabulary; problem-specific values
(`problem_id`, a namespace, a conductor endpoint) are call-site data a
caller folds into the input fields' text, never a dedicated signature field.

The architectural law these signatures encode
--------------------------------------------------
Per direct instruction, this module and its companion pipeline
(`sre_troubleshooting_pipeline.py`) implement ONLY the "reason over
evidence, construct candidates" half of the SRE troubleshooting graph:

    DSPy            = reason over evidence + construct candidates (never actuates)
    GymAct/BRCE     = observe + admit + DO + receipt
    SREGym harness  = inject fault + hold oracle + grade + reset (hidden)

No signature here has an output field that is itself an actuation -- every
"do this" output is an INTENT (`mitigation_intent`, `probe_intent`) that a
caller must route through the real, gated `environment.actuate(...)`
surface (`gymact_dspy_react.py`'s `build_gated_react_tools`/
`GymActReActDiagnoser`) to become a real action. This mirrors
`DiagnoseKubernetesFault`'s own contract in `k8s_signatures.py`: a
`Signature` is a typed reasoning contract, never a tool and never a loop.
"""

from __future__ import annotations

import dspy

__all__ = [
    "CommitSreDiagnosis",
    "ConstructSreMitigation",
    "HypothesizeSreCauses",
    "NormalizeSreEvidence",
    "OrientSreIncident",
    "ProposeDiscriminatingObservation",
]


class OrientSreIncident(dspy.Signature):
    """Bound the system under investigation and propose an initial
    evidence-gathering plan, WITHOUT prematurely selecting a root cause.
    Orienting is scoping, not diagnosing -- never conclude a cause here."""

    episode_goal: str = dspy.InputField(
        desc="the benchmark-visible troubleshooting goal -- never a hidden fault or oracle value"
    )
    system_context: str = dspy.InputField(
        desc="what is currently known about the system (app topology, recent changes, symptoms reported)"
    )
    capability_catalog: str = dspy.InputField(
        desc="the real, admitted READ/DO capability names available to investigate/act with"
    )
    system_boundary: str = dspy.OutputField(
        desc="the bounded scope of what this investigation will consider (which components, which timeframe)"
    )
    initial_observation_plan: str = dspy.OutputField(
        desc="a real, honest first evidence-gathering plan using only the given capability_catalog"
    )


class NormalizeSreEvidence(dspy.Signature):
    """Transform raw, real observations into explicit admitted facts (O ->
    O*), preserving contradictions and unknowns rather than silently
    resolving them. Every admitted fact must trace to something present in
    raw_evidence -- never invent a fact raw_evidence does not support."""

    raw_evidence: str = dspy.InputField(desc="real, raw observation/tool output collected so far")
    prior_facts: str = dspy.InputField(
        desc="facts already admitted from earlier normalization rounds, or 'none' on the first round"
    )
    admitted_facts: str = dspy.OutputField(
        desc="the real facts raw_evidence supports, each traceable to a specific piece of raw_evidence"
    )
    contradictions: str = dspy.OutputField(
        desc="any real observations that conflict with prior_facts or each other -- kept explicit, "
        "never silently resolved; 'none' when genuinely absent"
    )
    evidence_sufficient: bool = dspy.OutputField(
        desc="True only if admitted_facts genuinely supports advancing to hypothesis-forming"
    )


class HypothesizeSreCauses(dspy.Signature):
    """Given the currently admitted facts, maintain a REAL portfolio of
    plausible causes -- explicitly distinguishing which are supported,
    refuted, or still unknown given the evidence. Never collapse to a
    single cause before the evidence actually discriminates between
    candidates."""

    admitted_facts: str = dspy.InputField(desc="the current, real O* facts")
    prior_hypotheses: str = dspy.InputField(
        desc="the hypothesis portfolio from the previous round, or 'none' on the first round"
    )
    hypothesis_portfolio: str = dspy.OutputField(
        desc="every plausible cause considered, each labeled supported/refuted/unknown with the "
        "specific admitted_facts entries that justify the label"
    )
    dominant_uncertainty: str = dspy.OutputField(
        desc="the single highest-value unresolved question that, if answered, would most reduce "
        "the hypothesis portfolio's uncertainty"
    )


class ProposeDiscriminatingObservation(dspy.Signature):
    """Construct ONE candidate real observation (a READ, never a DO) whose
    real purpose is discriminating between the current hypothesis
    portfolio's surviving candidates -- an observation that would return
    the same result under every hypothesis provides no real information
    and should not be proposed. This produces an INTENT, not an actuation;
    a caller must route probe_intent through the real, gated capability
    surface to actually execute it."""

    admitted_facts: str = dspy.InputField(desc="the current, real O* facts")
    hypothesis_portfolio: str = dspy.InputField(desc="the current, real hypothesis portfolio")
    capability_catalog: str = dspy.InputField(desc="the real, admitted READ capability names available")
    probe_intent: str = dspy.OutputField(
        desc="one concrete, real observation request, precise enough to translate into exactly one "
        "real READ capability call -- never a DO, never vague"
    )
    expected_information_gain: float = dspy.OutputField(
        desc="0.0-1.0, an honest estimate of how much this probe would narrow hypothesis_portfolio, "
        "grounded in which hypotheses it could actually distinguish -- not a generic confidence score"
    )
    estimated_cost: float = dspy.OutputField(
        desc="a real, honest, non-negative estimate of this probe's execution cost/time/risk relative "
        "to other plausible probes -- never a constant placeholder"
    )


class CommitSreDiagnosis(dspy.Signature):
    """Commit to a single diagnosis -- symptom, causal mechanism, root
    cause, and the specific evidence that supports it -- ONLY once the
    evidence genuinely discriminates a winning hypothesis. `confidence`
    must reflect actual evidentiary support, never generic certainty."""

    admitted_facts: str = dspy.InputField(desc="the current, real O* facts")
    hypothesis_portfolio: str = dspy.InputField(desc="the current, real hypothesis portfolio")
    symptom: str = dspy.OutputField(desc="the real, observed symptom this diagnosis explains")
    mechanism: str = dspy.OutputField(desc="the real causal mechanism connecting root_cause to symptom")
    root_cause: str = dspy.OutputField(desc="the committed root cause, grounded in admitted_facts")
    evidence_refs: str = dspy.OutputField(
        desc="the specific admitted_facts entries that justify root_cause over every other surviving hypothesis"
    )
    confidence: int = dspy.OutputField(
        desc="0-100, must reflect actual evidentiary support in evidence_refs, not general confidence",
        ge=0,
        le=100,
    )


class ConstructSreMitigation(dspy.Signature):
    """Construct the smallest, safest, most reversible real mitigation for
    an already-committed diagnosis. This produces an INTENT, never an
    actuation -- `safe_to_actuate=True` marks eligibility for separate,
    real admission through the gated capability surface; it never itself
    performs the DO."""

    root_cause: str = dspy.InputField(desc="the committed, real root cause to mitigate")
    relevant_resource_spec: str = dspy.InputField(
        desc="the current real spec/state of the resource(s) the mitigation would change"
    )
    capability_catalog: str = dspy.InputField(desc="the real, admitted DO capability names available")
    mitigation_intent: str = dspy.OutputField(
        desc="a concrete, real mitigation request, precise enough to translate into exactly one real "
        "DO capability call -- never vague, never a placeholder"
    )
    expected_consequence: str = dspy.OutputField(
        desc="the real, honest expected effect of applying mitigation_intent, including side effects"
    )
    rollback_plan: str = dspy.OutputField(
        desc="a real, concrete way to reverse mitigation_intent if it makes things worse"
    )
    safe_to_actuate: bool = dspy.OutputField(
        desc="True only if mitigation_intent is genuinely small, reversible, and grounded in "
        "relevant_resource_spec -- an honest False is a legitimate answer"
    )
