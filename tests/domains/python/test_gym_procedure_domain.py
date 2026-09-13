# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""UNIT checkpoint (NOT a Chicago/ecosystem test): the generic
`GymProcedureDomain` factory, proven against a real recipe transcribed from
a real vendored gym task (`vendor/gyms/cybench`'s `hkcert-ctf/05-motp`
challenge, whose real ordered subtasks/answers/commands live in that task's
own `metadata.json`) and a real registered `Astar` solver's real `solve()`
call -- no `unittest.mock`/`Mock`/`patch`/`monkeypatch` anywhere in this
file, per `.claude/rules/testing-chicago-style.md`.

A second, synthetic recipe exercises the `removes` effect (state facts a
step retracts, not just adds) to prove the factory is genuinely generic and
not merely reshaped around the one real recipe it ships with.
"""

from pathlib import Path

import pytest

from autofde_lab import utils
from autofde_lab.hub.domain.gym_procedure import GymProcedureDomain, Recipe, Step, load_recipe

RECIPES_DIR = Path(__file__).resolve().parents[3] / "src" / "autofde_lab" / "hub" / "domain" / "gym_procedure" / "recipes"


def test_load_recipe_reads_real_cybench_motp_json():
    recipe = load_recipe(RECIPES_DIR / "cybench_motp.json")
    assert recipe.gym == "cybench"
    assert recipe.task == "hkcert-ctf/CTF-2022/05-motp"
    assert len(recipe.steps) == 5
    assert recipe.goal_facts == frozenset({"flag_captured"})
    # the real command transcribed from metadata.json subtasks[4].commands[0]
    assert "curl" in recipe.steps[-1].description


def test_astar_solves_real_cybench_motp_recipe_in_documented_subtask_order():
    """A* must recover the metadata.json's own subtask ordering to capture the flag."""
    domain = GymProcedureDomain.from_json(RECIPES_DIR / "cybench_motp.json")
    Astar = utils.load_registered_solver("Astar")
    with Astar(domain_factory=lambda: domain) as solver:
        solver.solve()
        obs = domain.reset()
        plan = []
        for _ in range(20):
            if domain._is_terminal(obs):
                break
            action = solver.sample_action(obs)
            plan.append(action)
            outcome = domain.step(action)
            obs = outcome.observation

        assert domain._is_goal(obs), f"A* did not reach the goal. Plan: {plan}"
        assert plan == [
            "identify_credentials_file",
            "identify_otp_bypass_file",
            "identify_vulnerable_operator",
            "determine_bypass_type",
            "retrieve_flag",
        ]
        assert sum(domain.describe_step(s).cost for s in plan) == pytest.approx(5.0)


def test_generic_factory_honors_removes_effect_not_just_establishes():
    """A synthetic recipe (not the shipped cybench one) proving genericity: a
    step that both establishes a new fact and removes a stale one -- the
    factory must not silently ignore `removes`."""
    recipe = Recipe(
        gym="synthetic",
        task="removes-effect-check",
        source_ref="test_gym_procedure_domain.py",
        initial_facts=frozenset({"door_locked"}),
        goal_facts=frozenset({"door_open"}),
        steps=(
            Step(
                id="unlock_door",
                description="unlock the door",
                preconditions=frozenset({"door_locked"}),
                establishes=frozenset({"door_unlocked"}),
                removes=frozenset({"door_locked"}),
            ),
            Step(
                id="open_door",
                description="open the unlocked door",
                preconditions=frozenset({"door_unlocked"}),
                establishes=frozenset({"door_open"}),
            ),
        ),
    )
    domain = GymProcedureDomain(recipe)
    Astar = utils.load_registered_solver("Astar")
    with Astar(domain_factory=lambda: domain) as solver:
        solver.solve()
        obs = domain.reset()
        plan = []
        for _ in range(10):
            if domain._is_terminal(obs):
                break
            action = solver.sample_action(obs)
            plan.append(action)
            outcome = domain.step(action)
            obs = outcome.observation

        assert domain._is_goal(obs)
        assert plan == ["unlock_door", "open_door"]
        # the removes effect actually fired: door_locked is gone from the goal state
        assert "door_locked" not in obs.facts
        assert obs.facts == frozenset({"door_unlocked", "door_open"})
