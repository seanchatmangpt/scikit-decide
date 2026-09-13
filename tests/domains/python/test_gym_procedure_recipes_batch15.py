# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""UNIT checkpoints (NOT Chicago/ecosystem tests): three recipes transcribed
from real, documented, ordered procedures in three vendored gyms --
``workarena`` (a real ``cheat()`` method's ordered UI steps),
``assetopsbench`` (a real worked ground-truth trajectory example from that
gym's own guideline doc), and ``r2e-gym`` (a real numbered reproduction
guide) -- each proven against the generic ``GymProcedureDomain`` factory and
a real registered ``Astar`` solver's real ``solve()`` call. No
``unittest.mock``/``Mock``/``patch``/``monkeypatch`` anywhere in this file,
per ``.claude/rules/testing-chicago-style.md``.
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


def _solve_and_reach_goal(recipe_path: Path, expected_plan: list[str]) -> None:
    domain = GymProcedureDomain.from_json(recipe_path)
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


def test_astar_solves_workarena_mark_duplicate_problem_recipe():
    """Transcribed from vendor/gyms/workarena's real
    ``SetProblemAsDuplicateTask.cheat()`` ordered UI steps (search the
    target problem -> open it -> open duplicate mode -> close the popup ->
    fill duplicate_of -> click update)."""
    _solve_and_reach_goal(
        RECIPES_DIR / "workarena_mark_duplicate_problem.json",
        [
            "search_target_problem_by_number",
            "open_target_problem_record",
            "open_duplicate_mode",
            "close_duplicate_popup",
            "fill_duplicate_of_field",
            "click_update",
        ],
    )


def test_astar_solves_assetopsbench_iot_list_assets_recipe():
    """Transcribed from vendor/gyms/assetopsbench's own ground-truth design
    guideline doc, Section 9 'Example 1: Simple Query (Scenario 3)' -- a
    real, fully worked linear execution_steps/execution_links trajectory for
    the utterance "What assets can be found at the MAIN site?"."""
    _solve_and_reach_goal(
        RECIPES_DIR / "assetopsbench_iot_list_assets_main_site.json",
        ["list_assets_for_site_main", "finish_with_asset_list_answer"],
    )


def test_astar_solves_r2e_gym_deepswe_reproduction_recipe():
    """Transcribed from vendor/gyms/r2e-gym's real numbered reproduction
    guide (DEEPSWE_REPRODUCTION.MD): clone+install -> start VLLM server ->
    run agent evaluation -> generate SWE-Bench submission -> run official
    SWE-Bench evaluation harness."""
    _solve_and_reach_goal(
        RECIPES_DIR / "r2e_gym_deepswe_reproduction.json",
        [
            "clone_repo_and_install_dependencies",
            "start_vllm_server",
            "run_agent_evaluation",
            "generate_submission_file",
            "run_official_swebench_evaluation",
        ],
    )
