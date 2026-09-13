# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""UNIT checkpoints (NOT Chicago/ecosystem tests): the generic
`GymProcedureDomain` factory proven against recipes transcribed from real
vendored gym tasks in this batch's priority list (`vendor/gyms/crmarena`,
`vendor/gyms/tau2-bench`, `vendor/gyms/mcp-bench`), each solved with a real
registered `Astar` solver's real `solve()` call -- no
`unittest.mock`/`Mock`/`patch`/`monkeypatch` anywhere in this file, per
`.claude/rules/testing-chicago-style.md`.

`vendor/gyms/crmarena` was investigated and found to have no transcribable
ordered procedure: its tasks are loaded dynamically from the
`Salesforce/CRMArena(Pro)` Hugging Face datasets over a live Salesforce org
(`crm_sandbox/data/assets.py`), evaluated by a free-form ReAct/tool-call
agent with no vendored gold action/tool-call trajectory file in the repo
(`run_tasks.py`, `README.md`). No recipe was written for it here; see the
per-gym report in the calling session for the precise
`BLOCKED:NO_TRANSCRIBABLE_PROCEDURE` citation.
"""

from pathlib import Path

import pytest

from autofde_lab import utils
from autofde_lab.hub.domain.gym_procedure import GymProcedureDomain, load_recipe

RECIPES_DIR = (
    Path(__file__).resolve().parents[3]
    / "src"
    / "autofde_lab"
    / "hub"
    / "domain"
    / "gym_procedure"
    / "recipes"
)


def _solve_and_collect_plan(domain, max_steps: int = 20):
    Astar = utils.load_registered_solver("Astar")
    with Astar(domain_factory=lambda: domain) as solver:
        solver.solve()
        obs = domain.reset()
        plan = []
        for _ in range(max_steps):
            if domain._is_terminal(obs):
                break
            action = solver.sample_action(obs)
            plan.append(action)
            outcome = domain.step(action)
            obs = outcome.observation
        return obs, plan


def test_tau2bench_airline_cancel_recipe_reaches_goal_in_documented_action_order():
    """tau2-bench airline domain, task id "7": the recipe transcribes the
    task's own `evaluation_criteria.actions` gold action list (real function
    names + arguments) from
    `vendor/gyms/tau2-bench/data/tau2/domains/airline/tasks.json`."""
    recipe = load_recipe(RECIPES_DIR / "tau2bench_airline_cancel.json")
    assert recipe.gym == "tau2-bench"
    assert len(recipe.steps) == 5

    domain = GymProcedureDomain(recipe)
    obs, plan = _solve_and_collect_plan(domain)

    assert domain._is_goal(obs), f"A* did not reach the goal. Plan: {plan}"
    assert plan == [
        "get_reservation_details_xehm4b",
        "get_reservation_details_59xx6w",
        "upgrade_xehm4b_to_business",
        "cancel_reservation_xehm4b",
        "cancel_reservation_59xx6w",
    ]


def test_mcpbench_openapi_explorer_recipe_reaches_goal_in_documented_step_order():
    """mcp-bench "OpenAPI Explorer" server, task "openapi_explorer_001": the
    recipe transcribes the task's own numbered steps 1-6 (real tool calls
    `getApiOverview`/`getApiOperation`) from
    `vendor/gyms/mcp-bench/tasks/mcpbench_tasks_single_runner_format.json`."""
    recipe = load_recipe(RECIPES_DIR / "mcpbench_openapi_explorer_001.json")
    assert recipe.gym == "mcp-bench"
    assert len(recipe.steps) == 6

    domain = GymProcedureDomain(recipe)
    obs, plan = _solve_and_collect_plan(domain)

    assert domain._is_goal(obs), f"A* did not reach the goal. Plan: {plan}"
    assert plan == [
        "get_openai_overview",
        "get_openai_create_operation_details",
        "get_github_overview",
        "get_github_repos_operation_details",
        "extract_security_schemes",
        "compile_consolidated_report",
    ]
