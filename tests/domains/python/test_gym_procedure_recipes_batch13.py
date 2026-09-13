# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""UNIT checkpoints (NOT Chicago/ecosystem tests): the generic
`GymProcedureDomain` factory proven against three more real recipes, each
transcribed from a real vendored gym's own documented procedure (an
instruction + reference solve script, a scenario's own milestone tool-trace
list, or a task's own numbered steps + checkpoints), and a real registered
`Astar` solver's real `solve()` call -- no `unittest.mock`/`Mock`/`patch`/
`monkeypatch` anywhere in this file, per `.claude/rules/testing-chicago-style.md`.

Gyms covered (priority order from the assignment):

- terminal-bench-pro / cmake-build-for-cpp-console-app: instruction.md's
  numbered requirements + solution/solve.sh's literal CMakeLists.txt heredoc
  + tests/test_outputs.py's own build/verify command order.
- toolsandbox / multiple_tool_call_scenarios.remove_contact_by_phone: the
  scenario's own ordered `Milestone` list (search_contacts -> remove_contact
  -> reply), transcribed directly from the tool_trace JSON each milestone
  asserts.
- the-agent-company / admin-check-employees-budget-and-reply: task.md's own
  numbered steps (1, 2, 3), cross-checked against checkpoints.md's per-step
  verification criteria.

vendor/gyms/the-agent-company as a whole has no reference solve script or
gold tool-call trace for any task (verified by listing every file under
several task directories: only Dockerfile/Makefile/task.md/checkpoints.md/
evaluator.py, no solution/ directory anywhere) -- this one task's own task.md
numbering was used because it is itself the real, ordered, documented
procedure, not a fabrication.
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
        return plan, obs


def test_terminal_bench_pro_cmake_build_recipe_loads_from_real_json():
    recipe = load_recipe(RECIPES_DIR / "terminal_bench_pro_cmake_build.json")
    assert recipe.gym == "terminal-bench-pro"
    assert recipe.task == "cmake-build-for-cpp-console-app"
    assert len(recipe.steps) == 4
    assert recipe.goal_facts == frozenset({"app_output_verified"})


def test_astar_solves_terminal_bench_pro_cmake_build_recipe_in_documented_order():
    """A* must recover instruction.md's write -> configure -> build -> run/verify order."""
    domain = GymProcedureDomain.from_json(RECIPES_DIR / "terminal_bench_pro_cmake_build.json")
    plan, obs = _solve_and_collect_plan(domain)

    assert domain._is_goal(obs), f"A* did not reach the goal. Plan: {plan}"
    assert plan == [
        "write_cmakelists",
        "run_cmake_configure",
        "run_make_build",
        "run_and_verify_output",
    ]
    assert sum(domain.describe_step(s).cost for s in plan) == pytest.approx(4.0)


def test_toolsandbox_remove_contact_by_phone_recipe_loads_from_real_json():
    recipe = load_recipe(RECIPES_DIR / "toolsandbox_remove_contact_by_phone.json")
    assert recipe.gym == "toolsandbox"
    assert recipe.task == "multiple_tool_call_scenarios.remove_contact_by_phone"
    assert len(recipe.steps) == 3
    assert recipe.goal_facts == frozenset({"user_notified_removed"})
    # the real tool_name transcribed from the scenario's first milestone
    assert "search_contacts" in recipe.steps[0].description


def test_astar_solves_toolsandbox_remove_contact_by_phone_recipe_in_milestone_order():
    """A* must recover the scenario's own Milestone ordering: search -> remove -> reply."""
    domain = GymProcedureDomain.from_json(RECIPES_DIR / "toolsandbox_remove_contact_by_phone.json")
    plan, obs = _solve_and_collect_plan(domain)

    assert domain._is_goal(obs), f"A* did not reach the goal. Plan: {plan}"
    assert plan == [
        "search_contacts_by_phone",
        "remove_contact",
        "reply_to_user",
    ]
    assert sum(domain.describe_step(s).cost for s in plan) == pytest.approx(3.0)


def test_the_agent_company_check_employees_budget_recipe_loads_from_real_json():
    recipe = load_recipe(RECIPES_DIR / "the_agent_company_check_employees_budget.json")
    assert recipe.gym == "the-agent-company"
    assert recipe.task == "admin-check-employees-budget-and-reply"
    assert len(recipe.steps) == 3
    assert recipe.goal_facts == frozenset({"replied_with_budget_answer"})


def test_astar_solves_the_agent_company_check_employees_budget_recipe_in_task_md_order():
    """A* must recover task.md's own numbered step order: collect -> retrieve -> reply."""
    domain = GymProcedureDomain.from_json(
        RECIPES_DIR / "the_agent_company_check_employees_budget.json"
    )
    plan, obs = _solve_and_collect_plan(domain)

    assert domain._is_goal(obs), f"A* did not reach the goal. Plan: {plan}"
    assert plan == [
        "collect_equipment_requests",
        "retrieve_equipment_prices",
        "reply_with_budget_answer",
    ]
    assert sum(domain.describe_step(s).cost for s in plan) == pytest.approx(3.0)
