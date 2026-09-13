# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for `planner_league.policy_instantiation`
(V2030.1.1 required capability 3): `PolicySpec.parameters` becomes a real,
outcome-affecting axis rather than an identity-only string tuple, and an
unlawful `PolicySpec` is refused before any solve attempt.

Real collaborators throughout: the real `Astar` solver's real `heuristic`
constructor parameter (`src/autofde_lab/hub/solver/astar/astar.py`), the
real `Maze` domain from `WORLD_DOMAIN_FACTORIES["generic_enterprise"]`, and
real `solve()`/`get_plan()`. No test doubles of any kind anywhere in this
file.
"""

from __future__ import annotations

import dataclasses

from autofde_lab.core import Value
from autofde_lab.planner_league import LeagueMatch, PolicySpec
from autofde_lab.planner_league.policy_instantiation import (
    instantiate_policy,
    validate_policy_spec,
)
from autofde_lab.planner_league.world_admission import WORLD_DOMAIN_FACTORIES

WORLD_ID = "generic_enterprise"


def _domain():
    return WORLD_DOMAIN_FACTORIES[WORLD_ID]()


def test_two_real_parameterizations_of_astar_both_produce_real_replayed_plans():
    zero_heuristic_spec = PolicySpec.for_role(
        "Astar",
        "plan_constructor",
        parameters={"heuristic": lambda d, s: Value(cost=0)},
    )
    manhattan_heuristic_spec = PolicySpec.for_role(
        "Astar",
        "plan_constructor",
        parameters={
            "heuristic": lambda d, s: Value(
                cost=abs(s.x - d._goal.x) + abs(s.y - d._goal.y)
            )
        },
    )

    explored_states: dict[str, int] = {}
    plans: dict[str, list] = {}
    for label, spec in (
        ("zero", zero_heuristic_spec),
        ("manhattan", manhattan_heuristic_spec),
    ):
        domain = _domain()
        result = instantiate_policy(spec, domain_factory=lambda d=domain: d)
        assert result.status == "INSTANTIATED", result
        assert result.solver is not None
        result.solver.solve()
        plan = list(result.solver.get_plan(domain.get_initial_state()))
        assert plan, "expected a real non-empty plan"
        plans[label] = plan
        explored_states[label] = result.solver.get_nb_explored_states()

    # The adversarial refute pass on this PR found that, on this maze's
    # unique shortest path, both heuristics happen to replay to the SAME
    # final plan -- A* is optimal, so "plan is non-empty" alone does not
    # demonstrate parameters is a real, outcome-affecting axis (a mock
    # `dict(spec.parameters)` that was silently dropped would pass that
    # assertion too). The axis that genuinely differs, real and measured,
    # is search effort: the admissible Manhattan heuristic explores
    # strictly fewer states than the zero heuristic. Assert on THAT real
    # difference, not on an assertion the two configurations would satisfy
    # identically either way.
    assert explored_states["manhattan"] < explored_states["zero"], explored_states
    assert plans["zero"] and plans["manhattan"]


def test_identity_sha256_differs_between_the_two_real_parameterizations():
    def _match_for(heuristic) -> LeagueMatch:
        return LeagueMatch(
            world_id=WORLD_ID,
            left_role_id="plan_constructor",
            left_policy=PolicySpec.for_role(
                "Astar",
                "plan_constructor",
                parameters={"heuristic": heuristic},
            ),
            right_role_id="plan_falsifier",
            right_policy=PolicySpec.for_role("MCTS", "plan_falsifier"),
        )

    zero_match = _match_for("zero")
    manhattan_match = _match_for("manhattan")
    assert zero_match.identity_sha256 != manhattan_match.identity_sha256

    # Confirm the parameters axis really is what moves identity: an
    # otherwise-identical spec with the same parameter value round-trips
    # to the same identity.
    assert zero_match.identity_sha256 == _match_for("zero").identity_sha256


def test_validate_policy_spec_refuses_unknown_planner_via_direct_constructor():
    spec = PolicySpec(
        planner_id="NotAPlanner",
        objective_id="construct_goal_reaching_plan",
        observation_projection_id="full_observation",
        action_projection_id="candidate_plan",
    )
    try:
        validate_policy_spec(spec)
        raised = None
    except ValueError as exc:
        raised = str(exc)
    assert raised == "REFUSED:UNKNOWN_PLANNER:NotAPlanner"


def test_instantiate_policy_refuses_unknown_planner_before_any_solve_attempt():
    spec = PolicySpec(
        planner_id="NotAPlanner",
        objective_id="construct_goal_reaching_plan",
        observation_projection_id="full_observation",
        action_projection_id="candidate_plan",
    )
    domain = _domain()
    try:
        instantiate_policy(spec, domain_factory=lambda: domain)
        raised = None
    except ValueError as exc:
        raised = str(exc)
    assert raised == "REFUSED:UNKNOWN_PLANNER:NotAPlanner"


def test_validate_policy_spec_refuses_unknown_objective_id():
    spec = dataclasses.replace(
        PolicySpec.for_role("Astar", "plan_constructor"),
        objective_id="bogus_objective",
    )
    try:
        validate_policy_spec(spec)
        raised = None
    except ValueError as exc:
        raised = str(exc)
    assert raised == "REFUSED:UNKNOWN_OBJECTIVE:bogus_objective"


def test_validate_policy_spec_refuses_unknown_observation_projection_id():
    spec = dataclasses.replace(
        PolicySpec.for_role("Astar", "plan_constructor"),
        observation_projection_id="bogus_obs",
    )
    try:
        validate_policy_spec(spec)
        raised = None
    except ValueError as exc:
        raised = str(exc)
    assert raised == "REFUSED:UNKNOWN_OBSERVATION_PROJECTION:bogus_obs"


def test_validate_policy_spec_refuses_unknown_action_projection_id():
    spec = dataclasses.replace(
        PolicySpec.for_role("Astar", "plan_constructor"),
        action_projection_id="bogus_action",
    )
    try:
        validate_policy_spec(spec)
        raised = None
    except ValueError as exc:
        raised = str(exc)
    assert raised == "REFUSED:UNKNOWN_ACTION_PROJECTION:bogus_action"


def test_validate_policy_spec_accepts_a_real_lawful_spec():
    spec = PolicySpec.for_role("Astar", "plan_constructor")
    assert validate_policy_spec(spec) is spec
