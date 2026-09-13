# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""UNIT checkpoint (NOT a Chicago/ecosystem test): batch 9 of gym recipes for the
generic ``GymProcedureDomain`` factory (see
``src/autofde_lab/hub/domain/gym_procedure/gym_procedure.py``), one test per gym:

- devops-gym (``vendor/gyms/devops-gym``): the real ordered "Run Manually" 5-step
  procedure transcribed from
  ``tasks/end_to_end/gogs__cpu-usage/README.md``.
- itbench (``vendor/gyms/itbench``): the real ordered solution steps transcribed
  from ``scenarios/sre/library/indexes/scenarios/1.json``'s own
  ``solutions[0][0].steps``.
- enterprisebench (``vendor/gyms/enterprisebench``): the real recorded ground-truth
  tool-call trajectory (``get_product`` then ``update_product``) transcribed from
  ``Task_Generation/tasks.json[0]``.

Each recipe is loaded via ``GymProcedureDomain.from_json`` and solved with the
real registered ``Astar`` solver -- no ``unittest.mock``/``Mock``/``patch``/
``monkeypatch`` anywhere in this file, per
``.claude/rules/testing-chicago-style.md``.
"""

from pathlib import Path

from autofde_lab import utils
from autofde_lab.hub.domain.gym_procedure import GymProcedureDomain

RECIPES_DIR = (
    Path(__file__).resolve().parents[3]
    / "src"
    / "autofde_lab"
    / "hub"
    / "domain"
    / "gym_procedure"
    / "recipes"
)


def _solve_and_assert_goal(recipe_filename: str, expected_plan: list[str]) -> None:
    domain = GymProcedureDomain.from_json(RECIPES_DIR / recipe_filename)
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
        assert plan == expected_plan


def test_astar_solves_devopsgym_gogs_cpu_usage_recipe_in_readme_order():
    """devops-gym: the real 5-step "Run Manually" procedure from
    tasks/end_to_end/gogs__cpu-usage/README.md."""
    _solve_and_assert_goal(
        "devopsgym_gogs_cpu_usage.json",
        [
            "set_env_vars",
            "start_services",
            "watch_client_log",
            "start_server",
            "run_tests",
        ],
    )


def test_astar_solves_itbench_sre_scenario1_recipe_in_documented_solution_order():
    """itbench: the real 2-step solution from
    scenarios/sre/library/indexes/scenarios/1.json's own solutions[0][0].steps."""
    _solve_and_assert_goal(
        "itbench_sre_scenario1.json",
        ["disable_feature_flag", "restart_deployments"],
    )


def test_astar_solves_enterprisebench_sales_update_product_price_recipe_in_trajectory_order():
    """enterprisebench: the real recorded ground-truth tool-call trajectory from
    Task_Generation/tasks.json[0] (get_product then update_product)."""
    _solve_and_assert_goal(
        "enterprisebench_sales_update_product_price.json",
        ["get_product", "update_product"],
    )
