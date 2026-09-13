from pathlib import Path
from typing import get_type_hints

import dspy

from autofde_lab.sregym_sota import SIGNATURE_REVISION
from autofde_lab.sregym_sota.models import IncidentOrientation, ObservationStep
from autofde_lab.sregym_sota.signatures import (
    ChallengeDiagnosis,
    CommitDiagnosis,
    ConstructDiscriminationProcess,
    ConstructMitigationProcesses,
    GenerateHypotheses,
    OrientIncident,
    RelateEvidence,
)


def test_signature_revision_is_explicit() -> None:
    assert SIGNATURE_REVISION == "SRE-SIG-003"


def test_exact_signature_surface() -> None:
    signatures = {
        OrientIncident,
        GenerateHypotheses,
        RelateEvidence,
        ConstructDiscriminationProcess,
        CommitDiagnosis,
        ChallengeDiagnosis,
        ConstructMitigationProcesses,
    }
    assert len(signatures) == 7
    assert all(issubclass(signature, dspy.Signature) for signature in signatures)


def test_cognition_source_contains_no_gepa_or_prompt_compiler() -> None:
    package = Path(__file__).parents[2] / "src" / "autofde_lab" / "sregym_sota"
    text = "\n".join(path.read_text() for path in sorted(package.glob("*.py"))).lower()
    assert "dspy.gepa" not in text
    assert "dspy.mipro" not in text
    assert "bootstrapfewshot" not in text


def test_core_contains_no_sregym_problem_ids_or_fault_taxonomy_keys() -> None:
    package = Path(__file__).parents[2] / "src" / "autofde_lab" / "sregym_sota"
    text = "\n".join(path.read_text() for path in sorted(package.glob("*.py")))
    forbidden = (
        "target_port",
        "incorrect_image",
        "network_policy_block",
        "duplicate_pvc",
        "fault_id",
        "fault_type",
    )
    assert not any(token in text for token in forbidden)


def test_orient_returns_typed_noise_aware_orientation() -> None:
    assert get_type_hints(OrientIncident)["orientation"] is IncidentOrientation
    doc = (OrientIncident.__doc__ or "").lower()
    assert "background" in doc
    assert "impact path" in doc


def test_hypothesis_signature_consumes_orientation_and_retired_portfolios() -> None:
    fields = GenerateHypotheses.__annotations__
    assert "orientation_json" in fields
    assert "prior_hypotheses_json" in fields
    doc = (GenerateHypotheses.__doc__ or "").lower()
    assert "causally diverse" in doc
    assert "retired" in doc


def test_discriminator_requires_exact_capability_read_history_and_falsifiers() -> None:
    fields = ConstructDiscriminationProcess.__annotations__
    assert "capabilities_json" in fields
    assert "read_history_json" in fields
    assert "rejections_json" in fields
    doc = ConstructDiscriminationProcess.__doc__ or ""
    assert "capability_id" in doc
    assert "input_schema" in doc
    assert "REFUTE" in doc
    assert "repeat_reason" in doc
    assert "outcomes" in ObservationStep.model_fields
