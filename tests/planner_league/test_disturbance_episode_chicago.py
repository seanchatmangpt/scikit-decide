# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for `planner_league.disturbance_episode` -- the real
`red_disturbance` adversarial episode (V2030.1.1 required capability 6).

Real collaborators throughout: the real `Maze` resolved through
`WORLD_DOMAIN_FACTORIES["generic_enterprise"]`, the real installed `Astar`
solver loaded through the same `PlannerLeague`/`load_registered_solver`
path `test_world_admission_chicago.py` already exercises, the domain's own
`get_initial_state()`/`get_next_state()`/`is_goal()`, and a real
`PayoffHypergraph`. No `unittest.mock` / `Mock` / `MagicMock` / `patch` /
`monkeypatch` anywhere in this file.

Maze geometry the disturbances rely on (read from `DEFAULT_MAZE`, not
assumed): the goal `x` is at `(11, 20)`; the cell directly above it,
`(11, 19)`, is open; the constructor plan's final three actions are
`right, right, down` from `(9, 19)`; `(1, 19)` is an open cell whose
southern neighbour `(1, 20)` is a wall.
"""

from __future__ import annotations

from autofde_lab.hub.domain.maze.maze import State
from autofde_lab.planner_league import PayoffHypergraph, PlannerLeague
from autofde_lab.planner_league.catalog import ROLE_SPECS
from autofde_lab.planner_league.disturbance_episode import (
    Disturbance,
    DisturbanceEpisodeResult,
    DisturbanceStanding,
    disturbance_result_to_payoff,
    run_disturbance_episode,
)
from autofde_lab.planner_league.world_admission import WORLD_DOMAIN_FACTORIES

WORLD_ID = "generic_enterprise"
CONSTRUCTOR = "Astar"
GOAL_ADJACENT = State(11, 19)
BEHIND_WALL = State(1, 19)


def _plan_length(constructor: str = CONSTRUCTOR) -> int:
    # A disturbance with at_step beyond the plan is UNKNOWN; derive the real
    # plan length from a real run so the tests below never guess it.
    probe = run_disturbance_episode(
        WORLD_ID, constructor, Disturbance("identity", 0, lambda s: s)
    )
    assert probe.standing is DisturbanceStanding.SURVIVES, probe.reason
    return probe.plan_length


def _relocate(target: State):
    return lambda _state: target


def test_relocation_adjacent_to_goal_survives_with_replayed_trajectory() -> None:
    domain = WORLD_DOMAIN_FACTORIES[WORLD_ID]()
    assert domain.is_goal(State(11, 20))
    assert not domain.is_goal(GOAL_ADJACENT)
    at_step = _plan_length() - 3
    result = run_disturbance_episode(
        WORLD_ID,
        CONSTRUCTOR,
        Disturbance("relocate-adjacent-to-goal", at_step, _relocate(GOAL_ADJACENT)),
    )
    assert isinstance(result, DisturbanceEpisodeResult)
    assert result.standing is DisturbanceStanding.SURVIVES, result.reason
    assert result.failed_at_step is None
    assert result.counterexample_state is None
    assert len(result.trajectory) > at_step
    # The perturbation really relocated the agent: the state replayed at
    # at_step is the disturbed one, not the one the plan walked into.
    assert result.trajectory[at_step][0] == GOAL_ADJACENT
    assert result.trajectory[at_step - 1][0] != GOAL_ADJACENT
    assert domain.is_goal(result.trajectory[-1][0])
    assert result.trajectory[-1][1] is None


def test_relocation_behind_wall_is_falsified_at_the_disturbance_step() -> None:
    domain = WORLD_DOMAIN_FACTORIES[WORLD_ID]()
    at_step = _plan_length() - 1
    result = run_disturbance_episode(
        WORLD_ID,
        CONSTRUCTOR,
        Disturbance("relocate-behind-wall", at_step, _relocate(BEHIND_WALL)),
    )
    assert result.standing is DisturbanceStanding.FALSIFIED, result.reason
    assert result.failed_at_step == at_step
    assert result.counterexample_state is not None
    assert result.counterexample_state == BEHIND_WALL
    # The remaining action (down) really walks into a wall: the domain's own
    # transition returns the same state.
    state, action = result.trajectory[at_step]
    assert state == BEHIND_WALL
    assert domain.get_next_state(state, action) == BEHIND_WALL
    assert not domain.is_goal(result.trajectory[-1][0])


def test_unregistered_planner_is_unknown_and_yields_no_payoff() -> None:
    league = PlannerLeague()
    result = run_disturbance_episode(
        WORLD_ID,
        "NotARegisteredPlanner",
        Disturbance("relocate-adjacent-to-goal", 0, _relocate(GOAL_ADJACENT)),
        league=league,
    )
    assert result.standing is DisturbanceStanding.UNKNOWN
    assert result.reason == "UNKNOWN:UNSUPPORTED:UNKNOWN_PLANNER"
    assert result.trajectory == ()
    observation, reason = disturbance_result_to_payoff(
        result,
        league=league,
        disturbance_planner_id="Astar",
        receipt_id="court-receipt-1",
    )
    assert observation is None
    assert reason.startswith("REFUSED:UNKNOWN_STANDING_HAS_NO_PAYOFF")


def test_at_step_beyond_plan_is_unknown_never_coerced() -> None:
    result = run_disturbance_episode(
        WORLD_ID, CONSTRUCTOR, Disturbance("too-late", 10_000, _relocate(GOAL_ADJACENT))
    )
    assert result.standing is DisturbanceStanding.UNKNOWN
    assert result.reason.startswith("UNKNOWN:AT_STEP_BEYOND_PLAN")


def test_payoff_requires_external_receipt_and_admits_into_real_hypergraph() -> None:
    league = PlannerLeague()
    at_step = _plan_length() - 3
    result = run_disturbance_episode(
        WORLD_ID,
        CONSTRUCTOR,
        Disturbance("relocate-adjacent-to-goal", at_step, _relocate(GOAL_ADJACENT)),
        league=league,
    )
    assert result.standing is DisturbanceStanding.SURVIVES

    refused, reason = disturbance_result_to_payoff(
        result, league=league, disturbance_planner_id="Astar", receipt_id=""
    )
    assert refused is None
    assert "UNRECEIPTED" in reason
    # The evidence identity is never promoted to a receipt on the caller's behalf.
    assert result.trajectory_digest not in reason

    observation, reason = disturbance_result_to_payoff(
        result,
        league=league,
        disturbance_planner_id="Astar",
        receipt_id="gymact-court-receipt-7f3a",
    )
    assert observation is not None, reason
    assert reason == "ALIVE:DISTURBANCE_PAYOFF:SURVIVES"
    assert observation.receipt_id == "gymact-court-receipt-7f3a"
    assert observation.left_score == 1.0 and observation.right_score == 0.0
    match = observation.match
    assert match.world_id == WORLD_ID
    assert match.left_role_id == "plan_constructor"
    assert match.right_role_id == "red_disturbance"
    assert match.left_policy.objective_id == ROLE_SPECS["plan_constructor"]["objective"]
    assert (
        match.right_policy.action_projection_id
        == ROLE_SPECS["red_disturbance"]["action_projection"]
    )
    assert (
        "disturbance_identity",
        "relocate-adjacent-to-goal",
    ) in match.right_policy.parameters
    assert len(match.identity_sha256) == 64

    hypergraph = PayoffHypergraph()
    hypergraph.add(observation)
    assert hypergraph.observations == [observation]
    assert hypergraph._scores(
        planner_id="Astar",
        role_id="plan_constructor",
        opponent_id="Astar",
        opponent_role_id="red_disturbance",
        world_id=WORLD_ID,
        observation_projection_id="full_observation",
        budget_id="balanced",
    ) == [1.0]


def test_falsified_result_scores_as_a_disturbance_win() -> None:
    league = PlannerLeague()
    at_step = _plan_length() - 1
    result = run_disturbance_episode(
        WORLD_ID,
        CONSTRUCTOR,
        Disturbance("relocate-behind-wall", at_step, _relocate(BEHIND_WALL)),
        league=league,
    )
    observation, reason = disturbance_result_to_payoff(
        result,
        league=league,
        disturbance_planner_id="Astar",
        receipt_id="gymact-court-receipt-9c",
    )
    assert observation is not None, reason
    assert (observation.left_score, observation.right_score) == (0.0, 1.0)


def test_trajectory_digest_is_deterministic_and_sensitive_to_at_step() -> None:
    plan_length = _plan_length()
    first = run_disturbance_episode(
        WORLD_ID,
        CONSTRUCTOR,
        Disturbance(
            "relocate-adjacent-to-goal", plan_length - 3, _relocate(GOAL_ADJACENT)
        ),
    )
    second = run_disturbance_episode(
        WORLD_ID,
        CONSTRUCTOR,
        Disturbance(
            "relocate-adjacent-to-goal", plan_length - 3, _relocate(GOAL_ADJACENT)
        ),
    )
    shifted = run_disturbance_episode(
        WORLD_ID,
        CONSTRUCTOR,
        Disturbance(
            "relocate-adjacent-to-goal", plan_length - 4, _relocate(GOAL_ADJACENT)
        ),
    )
    assert first.trajectory == second.trajectory
    assert first.trajectory_digest == second.trajectory_digest
    assert len(first.trajectory_digest) == 64
    assert shifted.trajectory_digest != first.trajectory_digest


# The adversarial refute pass found the bare-`Action` plan shape (IDAstar,
# LRTAstar) crashing this module where the (state, action, value) shape
# (Astar) did not. Both shapes are real registered solvers on the same
# admitted world, so both must yield a verdict -- or a typed UNKNOWN.
BARE_ACTION_CONSTRUCTOR = "IDAstar"


def test_bare_action_plan_shape_is_replayed_not_crashed() -> None:
    plan_length = _plan_length(BARE_ACTION_CONSTRUCTOR)
    assert plan_length > 0
    survived = run_disturbance_episode(
        WORLD_ID,
        BARE_ACTION_CONSTRUCTOR,
        Disturbance(
            "relocate-adjacent-to-goal", plan_length - 3, _relocate(GOAL_ADJACENT)
        ),
    )
    assert survived.standing is DisturbanceStanding.SURVIVES, survived.reason
    falsified = run_disturbance_episode(
        WORLD_ID,
        BARE_ACTION_CONSTRUCTOR,
        Disturbance("relocate-behind-wall", plan_length - 1, _relocate(BEHIND_WALL)),
    )
    assert falsified.standing is DisturbanceStanding.FALSIFIED, falsified.reason
    # Localisation comes from the domain's own undisturbed replay, so the
    # failing step is still pinned exactly for a planner that claims no states.
    assert falsified.failed_at_step == plan_length - 1
    assert falsified.counterexample_state == BEHIND_WALL


def test_disturbance_that_cannot_be_applied_is_unknown_never_a_verdict() -> None:
    def explode(_state):
        raise RuntimeError("transform exploded")

    class Bogus:
        pass

    exploded = run_disturbance_episode(
        WORLD_ID, CONSTRUCTOR, Disturbance("explode", 0, explode)
    )
    assert exploded.standing is DisturbanceStanding.UNKNOWN
    assert exploded.reason == "UNKNOWN:DISTURBANCE_TRANSFORM_FAILED:RuntimeError"
    assert exploded.trajectory == ()

    rejected = run_disturbance_episode(
        WORLD_ID, CONSTRUCTOR, Disturbance("bogus-state", 0, lambda _s: Bogus())
    )
    assert rejected.standing is DisturbanceStanding.UNKNOWN
    assert rejected.reason.startswith("UNKNOWN:DISTURBED_STATE_REJECTED_BY_DOMAIN:")
    assert rejected.trajectory == ()
