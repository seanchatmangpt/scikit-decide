from __future__ import annotations

import pytest

from autofde_lab.autofde.failure_to_fix_crown import (
    REQUIRED_STAGES,
    StageObservation,
    verify_failure_to_fix_crown,
)


def observations(*, subject: str = "subject:1", elapsed_ms: float = 10.0):
    return tuple(StageObservation(stage, elapsed_ms, subject) for stage in REQUIRED_STAGES)


def test_crown_is_alive_only_with_complete_same_subject_under_budget() -> None:
    result = verify_failure_to_fix_crown("run:1", observations())
    assert result.standing == "ALIVE"
    assert result.elapsed_ms == 80.0
    assert result.missing_stages == ()
    assert result.subject_digest == "subject:1"


def test_partial_evidence_cannot_be_promoted_to_crown() -> None:
    result = verify_failure_to_fix_crown("run:1", observations()[:-1])
    assert result.standing == "PARTIAL_ALIVE"
    assert result.missing_stages == ("recovery_generation",)


def test_cross_subject_timings_are_refused() -> None:
    mixed = list(observations())
    mixed[-1] = StageObservation("recovery_generation", 10.0, "subject:other")
    result = verify_failure_to_fix_crown("run:1", tuple(mixed))
    assert result.standing == "REFUSED"
    assert result.subject_digest is None


def test_over_budget_complete_run_is_not_alive() -> None:
    result = verify_failure_to_fix_crown("run:1", observations(elapsed_ms=200.0))
    assert result.standing == "BUILD_BROKEN"
    assert result.elapsed_ms == 1600.0


def test_duplicate_stage_is_refused() -> None:
    duplicate = observations() + (StageObservation("delta", 1.0, "subject:1"),)
    with pytest.raises(ValueError, match="DUPLICATE_CROWN_STAGE_REFUSED"):
        verify_failure_to_fix_crown("run:1", duplicate)
