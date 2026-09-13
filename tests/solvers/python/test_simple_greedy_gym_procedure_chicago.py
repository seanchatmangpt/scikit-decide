# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style test: real `SimpleGreedy` over a real `GymProcedureDomain`.

No test doubles at all. A real recipe is loaded from disk, two real
`GymProcedureDomain` instances are constructed (one for the solver factory, one
for the rollout -- `Solver.__init__` mutates whatever the factory returns via
`autocast_all`, so sharing a single instance would roll out on a solver-mutated
object), `solve()` is run for real, and the assertions are on real final state:
the actual actions returned, the actual facts in the reached state, and the
domain's own goal predicate.

Regression covered: `GymProcedureDomain.State` is a `NamedTuple`, so the
`(Memory, Union)` autocast rule unwraps it by `obj[0]`. `SimpleGreedy` applying
that cast a second time on top of the one `Solver.__init__` already applied
handed `_get_applicable_actions_from` the state's first field -- a `frozenset` --
producing `AttributeError: 'frozenset' object has no attribute 'facts'`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from autofde_lab.hub.domain.gym_procedure.gym_procedure import (
    GymProcedureDomain,
    load_recipe,
)
from autofde_lab.hub.solver.simple_greedy.simple_greedy import SimpleGreedy

RECIPES = (
    Path(__file__).resolve().parents[3]
    / "src/autofde_lab/hub/domain/gym_procedure/recipes"
)


@pytest.fixture(scope="module")
def recipe():
    return load_recipe(RECIPES / "agentbench_kg_relation_path.json")


def test_check_domain_accepts_gym_procedure_domain(recipe):
    assert SimpleGreedy.check_domain(GymProcedureDomain(recipe)) is True


def test_simple_greedy_rolls_out_on_real_gym_procedure_domain(recipe):
    """The regression: a real rollout used to raise AttributeError mid-flight."""
    rollout_domain = GymProcedureDomain(recipe)
    step_bound = len(recipe.steps) + 2

    with SimpleGreedy(domain_factory=lambda: GymProcedureDomain(recipe)) as solver:
        solver.solve()

        observation = rollout_domain.reset()
        plan: list[str] = []
        for _ in range(step_bound):
            if rollout_domain._is_terminal(observation):
                break
            action = solver.sample_action(observation)
            legal = rollout_domain._get_applicable_actions_from(
                observation
            ).get_elements()
            # Real assertion on real state: every action the greedy policy
            # proposed was actually applicable where it was proposed.
            assert action in legal, f"{action!r} not in {sorted(legal)}"
            plan.append(action)
            observation = rollout_domain.step(action).observation

    # Final-state assertions, not interaction assertions.
    assert plan, "solver produced no actions at all"
    assert len(plan) == len(set(plan)), f"repeated step in plan: {plan}"
    assert set(recipe.goal_facts) <= set(observation.facts)
    assert rollout_domain._is_goal(observation)


def test_get_next_action_with_explicit_domain_argument(recipe):
    """The other branch of `_get_next_action`: caller supplies the domain.

    This path applies the autocast itself (the solve-time domain is already
    cast); it must reach the same first action as the implicit-domain path.
    """
    external_domain = GymProcedureDomain(recipe)
    observation = external_domain.reset()

    with SimpleGreedy(domain_factory=lambda: GymProcedureDomain(recipe)) as solver:
        solver.solve()
        implicit = solver.get_next_action(observation)
        explicit = solver.get_next_action(observation, domain=external_domain)

    assert implicit == explicit
    assert implicit in external_domain._get_applicable_actions_from(
        observation
    ).get_elements()
