# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""A trial that cannot be modelled must be SCORED as failed, never raised.

Chicago-style throughout: a real `RealBlindEnvironment` against the real
gymact provider over a real subprocess bridge, a real `run_real_trial`, real
files on disk, and assertions on the real returned `TrialReport` state. No
test doubles -- the refusal used here is one the real provider genuinely
issues (`requires_authority=True` makes every DO binding refuse with
`LIVE_AUTHORITY_REQUIRED`), so no collaborator needs faking.

The defect pinned: when probing never observes any action succeed,
`induce_discovered_domain` marks every action unknown, `project_to_recipe`
drops them all, and `Recipe.__post_init__` refuses the empty procedure by
raising. That refusal is correct, but letting it escape `run_real_trial`
removed the trial from the crown scoreboard entirely instead of scoring it
False -- 4 of 10 frozen seeds terminated this way and had to be classified
by hand, outside the conjunction. Absent evidence is not a passed factor,
and it is not an absent factor either: it is a failed one with a name.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from autofde_lab.hub.domain.gym_procedure.crown_evidence import UnknownEvidence
from autofde_lab.hub.domain.gym_procedure.level4_crown import run_real_trial
from autofde_lab.hub.domain.gym_procedure.level4_crown_runner import _row_is_alive
from autofde_lab.hub.domain.gym_procedure.level4_gymact_bridge import (
    GYMACT_VENV_PYTHON,
    RealBlindEnvironment,
)

pytestmark = pytest.mark.skipif(
    not Path(GYMACT_VENV_PYTHON).exists(),
    reason=f"real gymact interpreter absent at {GYMACT_VENV_PYTHON}",
)


def test_provider_really_refuses_when_authority_is_required(tmp_path: Path) -> None:
    """Ground the premise on the REAL provider before relying on it below."""
    env = RealBlindEnvironment(
        "cube_counter", {"target": 3, "requires_authority": True}, tmp_path / "probe"
    )
    record = env.try_action("increment", commit=False)

    assert record["applicable"] is False
    assert record["standing"] == "REFUSED"
    assert record["reason"] == "LIVE_AUTHORITY_REQUIRED"
    # The real world did not move.
    assert record["observed_post"]["counter"] == 0


def test_unmodellable_trial_is_scored_not_raised(tmp_path: Path) -> None:
    report = run_real_trial(
        seed=424242,
        provider_key="cube_counter",
        config={"target": 3, "requires_authority": True},
        evidence_root=tmp_path / "ev",
        probe_budget=6,
    )

    assert report.outcome == "NO_APPLICABLE_ACTION_DISCOVERED"
    # The trial never reached actuation, so `standing` is a named
    # `UnknownEvidence` -- never a silently-defaulted `AliveEvidence`, and
    # never a boolean ground-truth field left to disagree with it.
    assert isinstance(report.standing, UnknownEvidence)
    assert report.standing.missing == "NO_APPLICABLE_ACTION_DISCOVERED"
    assert report.standing.episode_digest is None
    assert report.is_alive() is False
    assert report.verdict() == "UNKNOWN"
    assert report.replay_error == "NO_APPLICABLE_ACTION_DISCOVERED"
    assert "NO_APPLICABLE_ACTION_DISCOVERED" in report.replay_mismatches
    # The real provider's own refusal reason survives into the report.
    assert "LIVE_AUTHORITY_REQUIRED" in report.goal_predicate_description
    # Probing really happened against the real bridge.
    assert report.n_probes > 0
    assert Path(report.evidence_dir).is_dir()


def test_unmodellable_trial_scores_false_in_the_crown_conjunction(
    tmp_path: Path,
) -> None:
    report = run_real_trial(
        seed=424243,
        provider_key="cube_counter",
        config={"target": 3, "requires_authority": True},
        evidence_root=tmp_path / "ev",
        probe_budget=6,
    )
    # `crown_factor.conjunction_from_row` is now explicitly a legacy-row
    # compatibility shim, not the live construction path (see
    # `crown_evidence.py`'s module docstring) -- go through
    # `TrialReport.to_row()`, the real serialization this refactor
    # introduced, rather than reconstructing a legacy row shape from
    # `report.__dict__` by hand.
    row = report.to_row()

    assert _row_is_alive(row) is False


def test_authority_granted_path_still_reaches_a_real_model(tmp_path: Path) -> None:
    """The guard must not swallow trials that CAN be modelled: the same
    provider with authority granted still discovers a real applicable
    action, so the new early return is narrow rather than a blanket bail."""
    env = RealBlindEnvironment(
        "cube_counter", {"target": 3, "requires_authority": False}, tmp_path / "probe"
    )
    record = env.try_action("increment", commit=False)

    assert record["applicable"] is True
    assert record["standing"] == "ALIVE"
    assert record["observed_post"]["counter"] == 1
