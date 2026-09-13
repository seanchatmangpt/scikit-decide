# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for the Level 4 crown's per-step postconditions and
the real discover<->plan trial loop.

Every collaborator here is real: a real GymAct kernel episode driven through
the real subprocess bridge into ~/gymact's own venv, real CUBE counter
providers, the real registered solver federation, real SQLite receipts, real
OCEL output. No mocks, no monkeypatching -- when gymact is not checked out
the tests report a named skip rather than substituting a fake.
"""

from __future__ import annotations

import pytest

from autofde_lab.hub.domain.gym_procedure.crown_evidence import Level4AliveEvidence
from autofde_lab.hub.domain.gym_procedure.level4_crown import (
    AdvisoryAuthorityRefused,
    ValidatedPlan,
    commit,
    commit_and_execute,
    predict_step_postconditions,
    run_real_trial,
    validate_ocel_referential_integrity,
)
from autofde_lab.hub.domain.gym_procedure.level4_gymact_bridge import skip_reason

pytestmark = pytest.mark.skipif(skip_reason() is not None, reason=str(skip_reason()))


def test_predict_step_postconditions_counter_arithmetic() -> None:
    assert predict_step_postconditions(
        ("increment", "increment", "increment"), "cube_counter", {"counter": 0, "target": 3}
    ) == [
        {"counter": 1, "solved": False},
        {"counter": 2, "solved": False},
        {"counter": 3, "solved": True},
    ]
    assert predict_step_postconditions(
        ("increment_by", "decrement"), "cube_counter", {"counter": 0, "target": 1},
        payloads=[{"value": 2}, {}],
    ) == [{"counter": 2, "solved": False}, {"counter": 1, "solved": True}]

    with pytest.raises(ValueError, match="UNSUPPORTED_PROVIDER_FOR_POSTCONDITION_PREDICTION"):
        predict_step_postconditions(("increment",), "not_a_provider", {"counter": 0})


def test_every_step_of_a_multi_step_plan_is_alive_and_verified(tmp_path) -> None:
    """The repair: broadcasting one terminal expectation made intermediate
    steps REFUSED. Per-step postconditions must leave all three ALIVE."""
    plan = ("increment",) * 3
    expected = predict_step_postconditions(plan, "cube_counter", {"counter": 0, "target": 3})
    commitment = commit(ValidatedPlan(plan=plan, model_digest="d"), "trial-perstep")

    result = commit_and_execute(
        commitment, "cube_counter", {"target": 3}, expected, tmp_path / "perstep"
    )

    assert [t["standing"] for t in result["transitions"]] == ["ALIVE", "ALIVE", "ALIVE"]
    assert [t["verified"] for t in result["transitions"]] == [True, True, True]
    assert result["final_state"]["counter"] == 3
    assert result["final_state"]["solved"] is True
    assert result["independently_verified"] is True
    assert result["ocel_valid"] is True
    assert validate_ocel_referential_integrity(result["ocel"]) == []


def test_single_dict_expected_stays_backward_compatible(tmp_path) -> None:
    plan = ("increment",) * 3
    commitment = commit(ValidatedPlan(plan=plan, model_digest="d"), "trial-compat")

    result = commit_and_execute(
        commitment, "cube_counter", {"target": 3}, {"counter": 3, "solved": True}, tmp_path / "compat"
    )

    assert [t["standing"] for t in result["transitions"]] == ["ALIVE", "ALIVE", "ALIVE"]
    assert result["independently_verified"] is True


def test_advisory_candidate_still_refused_at_the_actuation_boundary(tmp_path) -> None:
    with pytest.raises(AdvisoryAuthorityRefused, match="ADVISORY_AUTHORITY_USED_AS_BEARER"):
        commit_and_execute(("increment",), "cube_counter", {"target": 3}, {}, tmp_path / "refused")


def test_run_real_trial_end_to_end(tmp_path) -> None:
    report = run_real_trial(1, "cube_counter", {"target": 3}, tmp_path)

    assert report.outcome == "EXECUTED"
    assert report.provider == "cube_counter"
    assert report.n_probes > 0
    # Real federation over the real registry, not an assumed planner count.
    assert report.n_supported_solvers > 0
    # One attempt per SUPPORTED registered solver, plus `typed_search`, which
    # is now a federated candidate producer under the same PlannerAttempt
    # contract instead of a direct line to commitment (see
    # `planner_federation.run_typed_search_attempt`).
    assert report.n_planner_attempts == report.n_supported_solvers + 1
    assert len(report.planners_producing_candidates) > 0
    # The continuous `reward` dimension has no sound propositional encoding;
    # it must be RECORDED as a loss, never silently dropped.
    assert report.representation_losses["reward"].startswith("UNREPRESENTABLE:")
    # The real evidence chain (`standing_from_episode`) produced a real
    # `Level4AliveEvidence`: real OCEL schema validity, real conformance, a
    # real valid replay, a real receipted postcondition (`.conformant`), AND
    # a real independently-observed goal-consequence event reporting
    # `passed=True` (`.goal`) -- not a chain of independently-asserted
    # booleans that could drift apart, and not process evidence alone.
    assert isinstance(report.standing, Level4AliveEvidence)
    assert report.standing.conformant.conformance.conformant is True
    assert report.standing.conformant.replay.valid is True
    assert report.standing.conformant.episode_digest
    assert report.standing.conformant.receipt_id
    assert report.standing.goal.passed is True
    assert report.standing.goal.verification_id
    assert report.is_alive() is True
    assert report.verdict() == "ALIVE"
    assert report.ocel_ref_violations == ()
    assert report.replay_mismatches == ()
    assert set(report.step_standings) == {"ALIVE"}
    # Per-trial isolation, exactly like level4_generator.Trial.
    assert report.run_id in report.evidence_dir


def test_two_trials_do_not_share_evidence(tmp_path) -> None:
    a = run_real_trial(2, "cube_counter", {"target": 2}, tmp_path)
    b = run_real_trial(2, "cube_counter", {"target": 2}, tmp_path)

    assert a.run_id != b.run_id
    assert a.evidence_dir != b.evidence_dir
