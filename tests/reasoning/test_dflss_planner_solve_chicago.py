# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for `dflss_planner_solve` -- the real drive of each
planner's own dedicated DMEDI-curriculum PDDL problem file through that
exact planner, closing the gap where `dflss_planner_problems.
problem_file_for_planner` had zero real callers outside its own test.

Real collaborators throughout: the real, on-disk per-planner PDDL problem
files, a real `PDDLDomain`, and the real, installed `Astar`/`LRTAstar`/
`CIDual` solver entry points' real `check_domain()`/`solve()`. No
`unittest.mock` / `Mock` / `MagicMock` / `patch` / `monkeypatch` anywhere
in this file.

`Astar` and `LRTAstar` are confirmed live (this session, real end-to-end
rollouts) to both real-solve the DMEDI curriculum problem to the real goal
in exactly 52 real actions; `CIDual` is confirmed live to be
`REFUSED:DOMAIN_CONTRACT_MISMATCH` against this same real PDDL domain.
"""

from __future__ import annotations

from autofde_lab.reasoning.dflss_planner_solve import (
    PlannerSolveOutcome,
    attempt_solve_dflss_curriculum,
)


def test_astar_really_solves_its_own_dedicated_problem_file() -> None:
    outcome = attempt_solve_dflss_curriculum("Astar")
    assert isinstance(outcome, PlannerSolveOutcome)
    assert outcome.planner_id == "Astar"
    assert outcome.standing == "ALIVE"
    assert outcome.reason == "ALIVE:GOAL_REACHED"
    assert outcome.alive
    # Matches the real, established plan length from
    # test_dflss_dmedi_plan_chicago.py's own shared-problem rollout -- same
    # domain, same empty :init, same goal, only the problem *name* differs
    # across per-planner files.
    assert outcome.plan_length == 52


def test_a_second_real_planner_lrtastar_also_solves_its_own_problem_file() -> None:
    """Confirms this module is real and general over planners, not a
    single-planner special case wearing a generic-looking signature."""
    outcome = attempt_solve_dflss_curriculum("LRTAstar")
    assert outcome.standing == "ALIVE"
    assert outcome.plan_length == 52


def test_domain_incompatible_planner_refuses_cleanly() -> None:
    outcome = attempt_solve_dflss_curriculum("CIDual")
    assert outcome.standing == "REFUSED"
    assert outcome.reason == "REFUSED:DOMAIN_CONTRACT_MISMATCH"
    assert not outcome.alive
    assert outcome.plan_length is None


def test_unknown_planner_id_refuses_cleanly_never_raises() -> None:
    outcome = attempt_solve_dflss_curriculum("NotARealPlanner")
    assert outcome.standing == "REFUSED"
    assert outcome.reason == "REFUSED:UNKNOWN_PLANNER:NotARealPlanner"
    assert not outcome.alive


def test_every_real_solve_outcome_carries_the_requested_planner_id() -> None:
    for planner_id in ("Astar", "LRTAstar", "CIDual", "NotARealPlanner"):
        outcome = attempt_solve_dflss_curriculum(planner_id)
        assert outcome.planner_id == planner_id
