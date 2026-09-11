# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Real Chicago-style tests for `verify_throughput_claim` against the
real `logs/throughput-benchmark-2026-08-20.log` this repo already has on
disk. No mocked log content -- both tests read the real file and assert
on the real returned boolean / `ExperimentReceipt` state."""

from __future__ import annotations

from pathlib import Path

from autofde_lab.fabric.verify_throughput_claim import (
    real_logged_solves_per_sec,
    receipt_from_throughput_claim,
    verify_throughput_claim,
)
from autofde_lab.reasoning.laboratory import FalsificationStanding

REAL_LOG_PATH = (
    Path(__file__).resolve().parents[2] / "logs" / "throughput-benchmark-2026-08-20.log"
)


def test_real_log_exists_on_disk() -> None:
    """Guard: if this file is missing, every other assertion below would
    be vacuous -- fail loudly instead of silently passing on absence."""
    assert REAL_LOG_PATH.exists(), f"expected real log at {REAL_LOG_PATH}"


def test_accurate_claim_matching_real_log_survives() -> None:
    """A claim that actually matches the real logged maze throughput
    (199.80 solves/sec, per the real RESULTS_JSON block) survives."""
    real_value = real_logged_solves_per_sec(REAL_LOG_PATH, "maze")
    assert real_value == 199.8032281771983

    accurate_claim = real_value  # the real number itself, not invented
    assert verify_throughput_claim(accurate_claim, REAL_LOG_PATH, "maze") is True

    receipt = receipt_from_throughput_claim(
        "test-accurate-maze-claim", accurate_claim, REAL_LOG_PATH, "maze"
    )
    assert receipt.postconditions_observed == ("throughput-claim-matches-real-log",)
    assert receipt.postconditions_violated == ()


def test_fabricated_claim_not_in_real_log_is_falsified() -> None:
    """A deliberately fabricated throughput number -- one nowhere near
    the real logged 199.80 solves/sec for maze, and not the real 360.53
    solves/sec for blocksworld either -- must be caught."""
    fabricated_claim = 50_000.0  # no real solve loop in this repo hit this

    real_value = real_logged_solves_per_sec(REAL_LOG_PATH, "maze")
    assert abs(fabricated_claim - real_value) / real_value > 0.05  # sanity: really is fabricated

    assert verify_throughput_claim(fabricated_claim, REAL_LOG_PATH, "maze") is False

    receipt = receipt_from_throughput_claim(
        "test-fabricated-maze-claim", fabricated_claim, REAL_LOG_PATH, "maze"
    )
    assert receipt.postconditions_violated == ("throughput-claim-matches-real-log",)
    assert receipt.postconditions_observed == ()

    # And running it through the real falsify_candidate machinery reports
    # a real FALSIFIED standing, not merely a bare bool.
    from autofde_lab.reasoning.laboratory import ArchitectureCandidate, falsify_candidate

    candidate = ArchitectureCandidate(
        candidate_id="fabricated-throughput-claim",
        target_state_assertions=("maze solver achieves 50000 solves/sec",),
        verification_criteria=("throughput-claim-matches-real-log",),
    )
    result = falsify_candidate(candidate, receipts=(receipt,))
    assert result.standing == FalsificationStanding.FALSIFIED


def test_missing_log_file_is_falsified_not_unknown() -> None:
    """A claim checked against a log that doesn't exist is falsified --
    never silently treated as passing."""
    assert verify_throughput_claim(199.8, Path("/nonexistent/no-such.log"), "maze") is False


def test_domain_not_present_in_real_log_is_falsified() -> None:
    """A claim about a domain this real log never actually benchmarked
    is falsified, not fabricated a pass."""
    assert verify_throughput_claim(100.0, REAL_LOG_PATH, "no-such-domain") is False
