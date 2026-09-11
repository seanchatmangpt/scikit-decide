# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for `planner_league.league_solve` -- two materially
different real planners run against the same admitted world through the
league's own `LeagueMatch` path (V2030.1.1 required capability 1).

Real collaborators throughout: the real `Maze` resolved through
`WORLD_DOMAIN_FACTORIES["generic_enterprise"]`, the real installed `Astar`
(optimal search; `(state, action, value)` plan tuples) and `LRTAstar`
(online heuristic; bare-`Action` plan) solvers loaded through the same
`PlannerLeague`/`load_registered_solver` path, real `solve()` under a real
`concurrent.futures` wall-clock bound, and the domain's own
`get_initial_state()`/`get_next_state()`/`is_goal()`. No test doubles of
any kind anywhere in this file.
"""

from __future__ import annotations

import dataclasses
import sys

from autofde_lab.planner_league import LeagueMatch, PlannerLeague, PolicySpec
from autofde_lab.planner_league.league_solve import (
    LeagueSolveOutcome,
    solve_league_match,
)
from autofde_lab.planner_league.world_admission import WORLD_DOMAIN_FACTORIES

WORLD_ID = "generic_enterprise"


def _match(left_planner: str, right_planner: str) -> LeagueMatch:
    return LeagueMatch(
        world_id=WORLD_ID,
        left_role_id="plan_constructor",
        left_policy=PolicySpec.for_role(left_planner, "plan_constructor"),
        right_role_id="plan_falsifier",
        right_policy=PolicySpec.for_role(right_planner, "plan_falsifier"),
    )


def test_two_materially_different_planners_both_produce_replayed_candidates():
    left, right = solve_league_match(
        _match("Astar", "LRTAstar"), league=PlannerLeague()
    )
    for outcome in (left, right):
        assert outcome.status == "PLAN_CANDIDATE", outcome
        assert isinstance(outcome.actions, tuple) and outcome.actions
        assert outcome.plan_length == len(outcome.actions)
        assert outcome.goal_reached is True
        assert outcome.wall_s > 0
        assert outcome.world_id == WORLD_ID
    assert (left.planner_id, left.role_id) == ("Astar", "plan_constructor")
    assert (right.planner_id, right.role_id) == ("LRTAstar", "plan_falsifier")

    # Independent replay of the LRTAstar side (the bare-Action plan shape)
    # through a fresh real domain: goal_reached is the domain's verdict.
    domain = WORLD_DOMAIN_FACTORIES[WORLD_ID]()
    state = domain.get_initial_state()
    for action in right.actions:
        state = domain.get_next_state(state, action)
    assert domain.is_goal(state)


def test_unloadable_rl_side_is_typed_unsupported_while_other_side_still_solves():
    # `ray` is absent in this venv: RayRLlib cannot be loaded. That is a
    # typed UNSUPPORTED:* outcome on its side, not an exception, and the
    # comparison pair is still returned with the other side solved.
    left, right = solve_league_match(
        _match("Astar", "RayRLlib"), league=PlannerLeague()
    )
    assert left.status == "PLAN_CANDIDATE"
    assert right.status.startswith("UNSUPPORTED:"), right
    assert right.actions == () and right.goal_reached is None
    assert right.reason


def test_llm_novelty_oracle_is_refused_per_side_without_loading_it():
    before = set(sys.modules)
    match = LeagueMatch(
        world_id=WORLD_ID,
        left_role_id="plan_constructor",
        left_policy=PolicySpec(planner_id="DSPyPolicy"),
        right_role_id="plan_falsifier",
        right_policy=PolicySpec.for_role("LRTAstar", "plan_falsifier"),
    )
    left, right = solve_league_match(match, league=PlannerLeague())
    assert left.status == "REFUSED:LLM_NOVELTY_BOUNDARY"
    assert left.goal_reached is None and left.actions == ()
    assert "dspy" not in sys.modules
    assert not any(m.startswith("dspy") for m in set(sys.modules) - before)
    assert right.status == "PLAN_CANDIDATE"


def test_tiny_timeout_yields_timeout_not_a_verdict():
    left, _right = solve_league_match(
        _match("Astar", "LRTAstar"), league=PlannerLeague(), timeout_s=1e-6
    )
    assert left.status == "TIMEOUT", left
    assert left.goal_reached is None and left.actions == ()


def test_outcome_carries_no_receipt_or_standing_field():
    names = {f.name for f in dataclasses.fields(LeagueSolveOutcome)}
    assert not names & {"receipt_id", "standing", "alive"}, names
    assert {"planner_id", "role_id", "world_id", "status", "actions"} <= names
