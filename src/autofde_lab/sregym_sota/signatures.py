from __future__ import annotations

import dspy

from .models import (
    DiagnosisCandidate,
    EpistemicObligation,
    EvidenceLinkProposal,
    HypothesisProposal,
    IncidentOrientation,
    MitigationProcessProposal,
    ObservationProcessProposal,
)


class OrientIncident(dspy.Signature):
    """Orient to the observed operational system without assuming a fault taxonomy.

    Separate *direct anomalies with an observed impact path* from merely loud or unusual
    background signals. A warning/error/log line is not causal evidence by itself. Keep
    multiple plausible system boundaries open when the facts do not yet localize impact,
    and state the questions that would distinguish those boundaries.
    """

    goal: str = dspy.InputField()
    facts_json: str = dspy.InputField()
    capabilities_json: str = dspy.InputField()
    orientation: IncidentOrientation = dspy.OutputField()


class GenerateHypotheses(dspy.Signature):
    """Manufacture a causally diverse portfolio of falsifiable hypotheses.

    Do not use a predefined benchmark/fault taxonomy. Prefer mechanisms over symptoms and
    distinguish causes from victims. Span materially different relationships/boundaries
    rather than producing variants of one subsystem theory. `prior_hypotheses_json`
    contains earlier or retired portfolios; do not repeat a retired mechanism unless new
    admitted facts specifically change its predictions or falsifiers. Every hypothesis
    must expose predictions and at least one observation that could falsify it.
    """

    goal: str = dspy.InputField()
    orientation_json: str = dspy.InputField()
    facts_json: str = dspy.InputField()
    prior_hypotheses_json: str = dspy.InputField()
    max_hypotheses: int = dspy.InputField()
    hypotheses: list[HypothesisProposal] = dspy.OutputField()


class RelateEvidence(dspy.Signature):
    """Propose mechanism-specific relationships between admitted fact IDs and hypotheses.

    Never assign epistemic standing. Cite only fact IDs present in the input. Mark a fact
    SUPPORTS only when it is a predicted consequence that is materially more specific to
    that hypothesis than to its live competitors. Generic warnings, health symptoms,
    resource existence, and facts equally compatible with multiple causes should be
    IRRELEVANT and should create a discriminating obligation instead of falsely supporting
    a cause. Mark REFUTES when an admitted fact contradicts a stated prediction/mechanism.
    """

    facts_json: str = dspy.InputField()
    hypotheses_json: str = dspy.InputField()
    links: list[EvidenceLinkProposal] = dspy.OutputField()
    obligations: list[EpistemicObligation] = dspy.OutputField()


class ConstructDiscriminationProcess(dspy.Signature):
    """Construct a bounded POWL-compatible process that maximally partitions survivors.

    Each step MUST copy one exact `capability_id` from the supplied capability catalog and
    shape `arguments` according to its input_schema. Never invent a surface, tool name,
    capability ID, argument name, or benchmark fault category. `read_history_json` lists
    already executed reads: do not repeat the same capability+arguments unless a temporal
    repeat is genuinely required, in which case `repeat_reason` must explain what changed
    or why comparison across time is discriminating.

    Every step must name current hypothesis IDs in `discriminates` and provide expected
    `outcomes`; at least one possible outcome must REFUTE a current competitor. Prefer
    reads that split or falsify the largest number of survivors. When prior rounds failed
    to shrink the frontier, deliberately inspect an unexamined relationship or system
    boundary rather than gathering more detail around the current anchor. Do not actuate.
    If prior candidates were refused, obey those typed refusals.
    """

    facts_json: str = dspy.InputField()
    hypotheses_json: str = dspy.InputField()
    obligations_json: str = dspy.InputField()
    capabilities_json: str = dspy.InputField()
    read_history_json: str = dspy.InputField()
    rejections_json: str = dspy.InputField()
    max_steps: int = dspy.InputField()
    process: ObservationProcessProposal = dspy.OutputField()


class CommitDiagnosis(dspy.Signature):
    """Describe the smallest causal explanation justified by externally computed
    epistemic standing. The input is already at causal closure; do not broaden it.
    Reference only supplied hypothesis IDs and admitted fact IDs.
    """

    facts_json: str = dspy.InputField()
    hypotheses_json: str = dspy.InputField()
    diagnosis: DiagnosisCandidate = dspy.OutputField()


class ChallengeDiagnosis(dspy.Signature):
    """Try to falsify the proposed diagnosis and return evidence obligations only.
    Check temporal behavior, victim-versus-cause errors, viable competitors, symptom
    coverage, whether the causal chain reaches the observed impact, and whether removing
    the proposed cause predicts recovery. Do not assign standing.
    """

    diagnosis_json: str = dspy.InputField()
    facts_json: str = dspy.InputField()
    hypotheses_json: str = dspy.InputField()
    obligations: list[EpistemicObligation] = dspy.OutputField()


class ConstructMitigationProcesses(dspy.Signature):
    """Construct multiple lawful POWL-compatible recovery processes for the admitted
    diagnosis. Each step MUST copy one exact `capability_id` from the supplied catalog
    and use only arguments admitted by that capability's input_schema. Consequential
    steps are explicit DO; verification is explicit VERIFY. Prefer reversible causal
    repairs. Never invent a capability, surface, tool name, or benchmark fault category.
    Do not execute.
    """

    diagnosis_json: str = dspy.InputField()
    facts_json: str = dspy.InputField()
    capabilities_json: str = dspy.InputField()
    max_processes: int = dspy.InputField()
    processes: list[MitigationProcessProposal] = dspy.OutputField()
