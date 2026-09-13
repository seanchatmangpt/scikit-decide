# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""UNIT checkpoint (NOT a Chicago/ecosystem test): three new `GymProcedureDomain`
recipes, one per gym assigned this batch (`vendor/gyms/harbor`,
`vendor/gyms/inspect-evals`, `vendor/gyms/mcpmark`), each transcribed from that
gym's own real documented ordered procedure and solved with the real
registered `Astar` solver's real `solve()` call -- no `unittest.mock`/`Mock`/
`patch`/`monkeypatch` anywhere in this file, per
`.claude/rules/testing-chicago-style.md`.

Per-gym provenance:

- harbor: `vendor/gyms/harbor/examples/tasks/hello-multi-step-advanced/task.toml`'s
  own `[[steps]]` list (scaffold -> implement -> document), each with its own
  `instruction.md`.
- mcpmark: `vendor/gyms/mcpmark/tasks/github/easy/mcpmark-cicd/issue_lint_guard/
  description.md`'s numbered Requirements, cross-checked against that task's own
  `verify.py` step-ordering assertion.
- inspect_evals: `vendor/gyms/inspect-evals/src/inspect_evals/gdm_in_house_ctf/
  challenges/pw_reuse/README.md`'s five ordered bullets.

`vendor/gyms/mcpmark` and `vendor/gyms/inspect-evals` are large multi-task
corpora with mostly single-shot or reasoning-only tasks; each recipe here was
selected specifically because it had a real, ordered, non-fabricated procedure
to transcribe (see the task-level report for gyms/tasks considered and
rejected).
"""

from pathlib import Path

import pytest

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


def _solve_and_reach_goal(recipe_filename: str, expected_plan: list[str]) -> None:
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


def test_astar_solves_harbor_hello_multi_step_advanced_recipe():
    """harbor: task.toml's own scaffold -> implement -> document step ordering."""
    _solve_and_reach_goal(
        "harbor_hello_multi_step_advanced.json",
        [
            "scaffold_greet_script",
            "implement_named_greeting",
            "document_readme",
        ],
    )


def test_astar_solves_mcpmark_issue_lint_guard_recipe():
    """mcpmark: description.md's numbered Requirements 1-4 for github/easy/
    mcpmark-cicd/issue_lint_guard."""
    _solve_and_reach_goal(
        "mcpmark_issue_lint_guard.json",
        [
            "create_branch",
            "add_workflow_file",
            "open_pr_and_merge",
            "trigger_issue_and_wait_for_success",
        ],
    )


def test_astar_solves_inspect_evals_gdm_pw_reuse_recipe():
    """inspect_evals: gdm_in_house_ctf's pw_reuse challenge README's five
    ordered bullets."""
    _solve_and_reach_goal(
        "inspect_evals_gdm_pw_reuse.json",
        [
            "scan_hosts",
            "login_db_and_list_hashes",
            "crack_user_hash",
            "ssh_login_with_cracked_credentials",
            "list_flag_file",
        ],
    )
