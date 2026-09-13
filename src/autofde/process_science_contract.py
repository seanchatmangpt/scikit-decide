"""Evidence-only boundary between wasm4pm process science and AutoFDE-Lab.

AutoFDE-Lab may consume process facts, compare hypotheses, and manufacture
candidate interventions. It may not silently promote a local conformance helper
into the authoritative process-science engine, and a planning artifact is never
an execution receipt.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

_ALLOWED_STANDING = {"OBSERVED", "DERIVED", "ADMITTED"}


@dataclass(frozen=True)
class ProcessEvidence:
    subject_id: str
    source: str
    algorithm_id: str
    algorithm_version: str
    configuration_id: str
    input_id: str
    output_id: str
    standing: str
    facts: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.source != "wasm4pm":
            raise ValueError("PROCESS_SCIENCE_SOURCE_REFUSED: source must be wasm4pm")
        if self.standing not in _ALLOWED_STANDING:
            raise ValueError("PROCESS_SCIENCE_STANDING_REFUSED")
        for field_name in (
            "subject_id",
            "algorithm_id",
            "algorithm_version",
            "configuration_id",
            "input_id",
            "output_id",
        ):
            if not getattr(self, field_name).strip():
                raise ValueError(f"PROCESS_SCIENCE_IDENTITY_REFUSED: {field_name}")


@dataclass(frozen=True)
class PlanningEvidence:
    """Candidate-side evidence; deliberately not an execution receipt."""

    subject_id: str
    process_output_id: str
    candidate_id: str
    decision: str

    @property
    def receipt_kind(self) -> str:
        return "planning-evidence"

    @property
    def confers_do_authority(self) -> bool:
        return False


def bind_process_evidence(payload: Mapping[str, Any]) -> ProcessEvidence:
    """Parse a wasm4pm evidence envelope and fail closed on identity gaps."""

    return ProcessEvidence(
        subject_id=str(payload.get("subject_id", "")),
        source=str(payload.get("source", "")),
        algorithm_id=str(payload.get("algorithm_id", "")),
        algorithm_version=str(payload.get("algorithm_version", "")),
        configuration_id=str(payload.get("configuration_id", "")),
        input_id=str(payload.get("input_id", "")),
        output_id=str(payload.get("output_id", "")),
        standing=str(payload.get("standing", "")),
        facts=dict(payload.get("facts", {})),
    )
