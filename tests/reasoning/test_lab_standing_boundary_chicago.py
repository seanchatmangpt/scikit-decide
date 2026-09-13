"""Chicago-style tests for the lab/production standing boundary
(`V2030.1.1-PRD-ARD.md` capability 9; falsifier "if benchmark success
grants production actuation").

Every collaborator is real: the real `falsify_candidate` over a real
`ArchitectureCandidate` and real `ExperimentReceipt`s, the real
`derive_enterprise_standing` over the real `AuthorityModel` parsed from the
same committed Turtle fixture `tests/ecosystem/test_enterprise_standing_chicago.py`
uses. Assertions are on returned state only.
"""

from __future__ import annotations

from dataclasses import fields
from pathlib import Path

import pytest

from autofde_lab.fabric.enterprise_standing import derive_enterprise_standing
from autofde_lab.fabric.fde import parse_authority_turtle
from autofde_lab.reasoning.lab_standing import (
    PRODUCTION_CLAIM_REFUSAL,
    GraduationPacket,
    LabResultStanding,
    graduation_packet,
    production_technical_claim,
)
from autofde_lab.reasoning.laboratory import (
    ArchitectureCandidate,
    ExperimentIntent,
    ExperimentReceipt,
    FalsificationResult,
    FalsificationStanding,
    falsify_candidate,
)

FIXTURES = Path(__file__).resolve().parents[1] / "ecosystem" / "fixtures" / "fde"
BASE = FIXTURES / "customer-authority.ttl"


def _real_surviving_result() -> FalsificationResult:
    candidate = ArchitectureCandidate(
        candidate_id="cand-1", target_state_assertions=("p95<250ms",)
    )
    intent = ExperimentIntent(
        candidate_id="cand-1",
        target_world_ref="world:checkout",
        initial_state_evidence_ref="obs-1",
        proposed_actions=("scale_out_api_instances",),
        expected_postconditions=("p95_reduced",),
    )
    receipt = ExperimentReceipt(
        intent_id=intent.intent_id,
        observed_outcome_refs=("outcome-1",),
        standing="ALIVE",
        postconditions_observed=("p95_reduced",),
    )
    result = falsify_candidate(candidate, receipts=(receipt,))
    assert result.standing == FalsificationStanding.SURVIVES
    return result


def _real_falsified_result() -> FalsificationResult:
    candidate = ArchitectureCandidate(
        candidate_id="cand-2", target_state_assertions=("p95<250ms",)
    )
    receipt = ExperimentReceipt(
        intent_id="intent-2",
        observed_outcome_refs=("outcome-2",),
        standing="ALIVE",
        postconditions_violated=("cost_ceiling_exceeded",),
    )
    result = falsify_candidate(candidate, receipts=(receipt,))
    assert result.standing == FalsificationStanding.FALSIFIED
    return result


def _lab(result: FalsificationResult) -> LabResultStanding:
    return LabResultStanding(
        candidate_id=result.candidate_id,
        falsification=result,
        world_ref_digest="blake3:" + "c" * 64,
        receipt_refs=result.receipt_refs,
    )


def test_surviving_lab_result_never_yields_a_production_alive_claim() -> None:
    lab = _lab(_real_surviving_result())

    assert lab.scope == "LAB"
    assert lab.lab_standing == FalsificationStanding.SURVIVES
    claim = production_technical_claim(lab)
    assert claim == PRODUCTION_CLAIM_REFUSAL
    assert claim.startswith("UNKNOWN:")
    assert claim != "ALIVE"


def test_falsified_lab_result_yields_the_same_scope_based_refusal() -> None:
    lab = _lab(_real_falsified_result())

    assert production_technical_claim(lab) == PRODUCTION_CLAIM_REFUSAL


def test_forwarding_the_refusal_into_enterprise_standing_fails_closed() -> None:
    model = parse_authority_turtle(BASE.read_text(encoding="utf-8"))
    claim = production_technical_claim(_lab(_real_surviving_result()))

    standing = derive_enterprise_standing(model, technical_standing=claim)

    assert standing.technical_standing == claim
    assert standing.enterprise_standing == "UNKNOWN"
    assert standing.organizational_standing == "UNKNOWN"


def test_lab_vocabulary_is_rejected_by_production_standing() -> None:
    model = parse_authority_turtle(BASE.read_text(encoding="utf-8"))

    with pytest.raises(ValueError, match="UNKNOWN_STANDING:SURVIVES"):
        derive_enterprise_standing(
            model, technical_standing=FalsificationStanding.SURVIVES.value
        )


def test_graduation_packet_carries_identities_and_no_standing() -> None:
    lab = _lab(_real_surviving_result())

    packet = graduation_packet(
        lab,
        benchmark_refs=("bench:checkout-2026-09",),
        falsifier_refs=("falsifier:cost-ceiling",),
        limits=("simulated world only",),
    )

    assert isinstance(packet, GraduationPacket)
    assert hasattr(packet, "standing") is False
    assert hasattr(packet, "alive") is False
    assert packet.required_downstream_admission == "autofde"
    assert packet.candidate_id == "cand-1"
    # The verdict is a query over the very object falsify_candidate returned,
    # not a copied token that could drift from it.
    assert packet.falsification is lab.falsification
    assert packet.lab_falsification_standing == "SURVIVES"
    assert "lab_falsification_standing" not in {f.name for f in fields(packet)}
    assert packet.world_ref_digest == lab.world_ref_digest
    assert packet.receipt_refs == lab.receipt_refs + lab.falsification.receipt_refs
    assert packet.benchmark_refs == ("bench:checkout-2026-09",)
    assert packet.falsifier_refs == ("falsifier:cost-ceiling",)
    assert packet.limits == ("simulated world only",)


def test_graduation_packet_refuses_a_different_downstream_admitter() -> None:
    lab = _lab(_real_surviving_result())
    packet = graduation_packet(lab)

    with pytest.raises(ValueError, match="GRADUATION_REQUIRES_AUTOFDE_ADMISSION"):
        GraduationPacket(
            candidate_id=packet.candidate_id,
            falsification=packet.falsification,
            world_ref_digest=packet.world_ref_digest,
            receipt_refs=packet.receipt_refs,
            benchmark_refs=(),
            falsifier_refs=(),
            limits=(),
            required_downstream_admission="autofde-lab",  # type: ignore[arg-type]
        )


def test_graduation_packet_refuses_a_verdict_that_is_not_its_candidates() -> None:
    packet = graduation_packet(_lab(_real_surviving_result()))

    with pytest.raises(ValueError, match="GRADUATION_PACKET_CANDIDATE_MISMATCH"):
        GraduationPacket(
            candidate_id="someone-else",
            falsification=packet.falsification,
            world_ref_digest=packet.world_ref_digest,
            receipt_refs=packet.receipt_refs,
            benchmark_refs=(),
            falsifier_refs=(),
            limits=(),
        )

    with pytest.raises(
        TypeError, match="GRADUATION_PACKET_REQUIRES_REAL_FALSIFICATION_RESULT"
    ):
        GraduationPacket(
            candidate_id="cand-1",
            falsification="SURVIVES",  # type: ignore[arg-type]
            world_ref_digest=packet.world_ref_digest,
            receipt_refs=(),
            benchmark_refs=(),
            falsifier_refs=(),
            limits=(),
        )


def test_lab_standing_is_constructible_only_from_a_real_falsification_result() -> None:
    with pytest.raises(
        TypeError, match="LAB_STANDING_REQUIRES_REAL_FALSIFICATION_RESULT"
    ):
        LabResultStanding(
            candidate_id="cand-1",
            falsification="SURVIVES",  # type: ignore[arg-type]
            world_ref_digest="blake3:" + "c" * 64,
        )

    with pytest.raises(ValueError, match="LAB_STANDING_CANDIDATE_MISMATCH"):
        LabResultStanding(
            candidate_id="someone-else",
            falsification=_real_surviving_result(),
            world_ref_digest="blake3:" + "c" * 64,
        )
