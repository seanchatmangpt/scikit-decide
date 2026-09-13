from __future__ import annotations

import pytest

from autofde.process_science_contract import PlanningEvidence, bind_process_evidence


def _valid_payload() -> dict[str, object]:
    return {
        "subject_id": "world:fortune5:episode-001",
        "source": "wasm4pm",
        "algorithm_id": "object-centric-conformance",
        "algorithm_version": "26.8.11",
        "configuration_id": "blake3:config",
        "input_id": "blake3:ocel-before",
        "output_id": "blake3:process-facts",
        "standing": "DERIVED",
        "facts": {"fitness": 1.0, "deviations": []},
    }


def test_wasm4pm_evidence_is_bound_with_exact_identity() -> None:
    evidence = bind_process_evidence(_valid_payload())
    assert evidence.source == "wasm4pm"
    assert evidence.output_id == "blake3:process-facts"


def test_local_process_engine_cannot_self_promote() -> None:
    payload = _valid_payload()
    payload["source"] = "autofde-lab"
    with pytest.raises(ValueError, match="PROCESS_SCIENCE_SOURCE_REFUSED"):
        bind_process_evidence(payload)


def test_missing_algorithm_identity_fails_closed() -> None:
    payload = _valid_payload()
    payload["algorithm_id"] = ""
    with pytest.raises(ValueError, match="PROCESS_SCIENCE_IDENTITY_REFUSED"):
        bind_process_evidence(payload)


def test_planning_evidence_is_never_execution_authority() -> None:
    planning = PlanningEvidence(
        subject_id="world:fortune5:episode-001",
        process_output_id="blake3:process-facts",
        candidate_id="candidate:scale-out",
        decision="admit-for-experiment",
    )
    assert planning.receipt_kind == "planning-evidence"
    assert planning.confers_do_authority is False
