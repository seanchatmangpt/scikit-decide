# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Batch 11 gym-procedure recipes: mcp-universe and rcaeval.

Each recipe is transcribed from a real, ordered, documented procedure found
in the corresponding vendored gym (see each recipe JSON's ``source_ref``),
solved with the real registered ``Astar`` solver over the generic
``GymProcedureDomain`` factory -- no ``unittest.mock``/``Mock``/``patch``/
``monkeypatch`` anywhere in this file, per
``.claude/rules/testing-chicago-style.md``.

``sadservers`` (the third assigned gym, priority 3) was investigated and
found to have NO transcribable ordered procedure: every scenario README
under ``vendor/gyms/sadservers/scenarios/*/README.md`` (verona, paris,
kampot, bilbao, marseille, kilifi, salta, bata, and others sampled) contains
only a problem Description and a goal-verification ``check.sh`` test -- no
numbered steps, fix sequence, or reference solve script anywhere in the
gym. The pre-existing OCEL capture at
``docs/papers/evidence/discovered/sadservers.ocel.json`` was also checked
and contains only lifecycle events (``materialize``/``act``/``teardown``)
with no step-level content to transcribe. Per this task's own instruction,
no recipe was fabricated for sadservers: BLOCKED:NO_TRANSCRIBABLE_PROCEDURE.
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


def _solve_and_check_goal(recipe_path: Path) -> list[str]:
    domain = GymProcedureDomain.from_json(recipe_path)
    Astar = utils.load_registered_solver("Astar")
    with Astar(domain_factory=lambda: domain) as solver:
        solver.solve()
        obs = domain.reset()
        plan: list[str] = []
        for _ in range(20):
            if domain._is_terminal(obs):
                break
            action = solver.sample_action(obs)
            plan.append(action)
            outcome = domain.step(action)
            obs = outcome.observation

        assert domain._is_goal(obs), f"A* did not reach the goal. Plan: {plan}"
        return plan


def test_mcp_universe_employee_onboarding_recipe_solves_to_goal():
    """mcp-universe: Notion 'Employee Onboarding' mcpmark task, transcribed
    from its own numbered ``description.md`` task requirements (1, then
    2 with ordered sub-steps 1-4)."""
    plan = _solve_and_check_goal(RECIPES_DIR / "mcp_universe_employee_onboarding.json")
    assert plan == [
        "create_checklist_database",
        "populate_checklist_entries",
        "create_onboarding_hub_page",
        "embed_checklist_database",
        "add_benefits_overview_section",
        "add_30_day_timeline_section",
        "add_feedback_form_section",
    ]


def test_rcaeval_cartservice_f1_recipe_solves_to_goal():
    """rcaeval: the code-level RCA demo notebook's own numbered procedure
    (# 1. Read available logs, # 2. Parse logs into time series, # 4. Apply
    BARO, then its Summary's root-cause conclusion) for the real injected
    ``cartservice_f1`` fault in the RE3-OB dataset."""
    plan = _solve_and_check_goal(RECIPES_DIR / "rcaeval_cartservice_f1.json")
    assert plan == [
        "read_available_logs",
        "parse_logs_into_time_series",
        "apply_baro",
        "identify_root_cause",
    ]
