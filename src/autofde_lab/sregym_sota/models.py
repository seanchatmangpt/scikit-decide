from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class Fact(BaseModel):
    id: str
    source: str
    path: str
    value: str


class Capability(BaseModel):
    id: str
    surface: str
    tool: str
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)


class IncidentOrientation(BaseModel):
    summary: str
    candidate_boundaries: list[str] = Field(default_factory=list)
    direct_anomalies: list[str] = Field(default_factory=list)
    background_noise_candidates: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)


class HypothesisProposal(BaseModel):
    id: str
    claim: str
    mechanism: str
    predictions: list[str] = Field(default_factory=list)
    falsifiers: list[str] = Field(default_factory=list)


class HypothesisRecord(HypothesisProposal):
    state: Literal["SUPPORTED", "REFUTED", "UNKNOWN"] = "UNKNOWN"
    supporting_fact_ids: list[str] = Field(default_factory=list)
    refuting_fact_ids: list[str] = Field(default_factory=list)


class EvidenceLinkProposal(BaseModel):
    hypothesis_id: str
    fact_id: str
    relation: Literal["SUPPORTS", "REFUTES", "IRRELEVANT"]
    explanation: str = ""


class EpistemicObligation(BaseModel):
    id: str
    question: str
    would_support: list[str] = Field(default_factory=list)
    would_refute: list[str] = Field(default_factory=list)


class OutcomePrediction(BaseModel):
    condition: str
    supports: list[str] = Field(default_factory=list)
    refutes: list[str] = Field(default_factory=list)


class ObservationStep(BaseModel):
    id: str
    capability_id: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    after: list[str] = Field(default_factory=list)
    why: str = ""
    discriminates: list[str] = Field(default_factory=list)
    outcomes: list[OutcomePrediction] = Field(default_factory=list)
    repeat_reason: str = ""


class ObservationProcessProposal(BaseModel):
    steps: list[ObservationStep] = Field(default_factory=list)


class RootCause(BaseModel):
    component_refs: list[str] = Field(default_factory=list)
    mechanism: str
    causal_chain: list[str] = Field(default_factory=list)
    evidence_fact_ids: list[str] = Field(default_factory=list)
    hypothesis_ids: list[str] = Field(default_factory=list)


class DiagnosisCandidate(BaseModel):
    root_causes: list[RootCause]
    explanation: str


class MitigationStep(BaseModel):
    id: str
    consequence: Literal["DO", "VERIFY"]
    capability_id: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    after: list[str] = Field(default_factory=list)
    expected_effect: str = ""


class MitigationProcessProposal(BaseModel):
    id: str
    steps: list[MitigationStep]
    reversible: bool = False
    risk: float = Field(ge=0.0, le=1.0, default=0.5)
    rationale: str = ""
