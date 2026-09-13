# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""UNIT checkpoints (NOT Chicago/ecosystem tests): three more gyms
(`vendor/gyms/agentdojo`, `vendor/gyms/agentgym`, `vendor/gyms/asb`) reduced
to `GymProcedureDomain` recipes, each transcribed from a real, documented,
ordered source in the vendored gym itself (a `ground_truth()` function-call
list, real Minecraft crafting-recipe JSON files plus the env's own
craft/get action semantics, and a `manual_workflow()` method), and solved by
the real registered `Astar` solver -- no `unittest.mock`/`Mock`/`patch`/
`monkeypatch` anywhere in this file, per `.claude/rules/testing-chicago-style.md`.
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


def _solve_and_reach_goal(recipe_path: Path, max_steps: int = 20):
    domain = GymProcedureDomain.from_json(recipe_path)
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
        assert domain._is_goal(obs), f"A* did not reach the goal. Plan: {plan}"
        return domain, plan, obs


def test_astar_solves_agentdojo_banking_pay_bill_ground_truth_order():
    """agentdojo: banking suite UserTask0's own `ground_truth()` -- read the
    bill file, then send_money -- reduced to a two-step recipe."""
    domain, plan, obs = _solve_and_reach_goal(
        RECIPES_DIR / "agentdojo_banking_pay_bill.json"
    )
    assert plan == ["read_bill_file", "send_money_for_bill"]
    assert obs.facts == frozenset({"knows_bill_details", "bill_paid"})


def test_astar_solves_agentgym_textcraft_golden_sword_recipe_chain():
    """agentgym: agentenv-textcraft's real Minecraft recipe files
    (golden_sword.json, stick.json, birch_planks.json) define a real
    crafting dependency chain enforced by TextCraftEnv.step's craft/get
    regex actions; reduced to a five-step recipe."""
    domain, plan, obs = _solve_and_reach_goal(
        RECIPES_DIR / "agentgym_textcraft_golden_sword.json"
    )
    assert set(plan) == {
        "get_gold_ingot",
        "get_birch_log",
        "craft_birch_planks",
        "craft_stick",
        "craft_golden_sword",
    }
    # dependency order must be respected: log before planks before stick,
    # and both gold_ingot and stick must precede the final craft
    assert plan.index("get_birch_log") < plan.index("craft_birch_planks")
    assert plan.index("craft_birch_planks") < plan.index("craft_stick")
    assert plan.index("craft_stick") < plan.index("craft_golden_sword")
    assert plan.index("get_gold_ingot") < plan.index("craft_golden_sword")
    assert domain._is_goal(obs)


def test_astar_solves_asb_financial_analyst_manual_workflow_order():
    """asb: FinancialAnalystAgent.manual_workflow()'s own two ordered steps
    (MarketDataAPI, then PortfolioManager) reduced to a two-step recipe."""
    domain, plan, obs = _solve_and_reach_goal(
        RECIPES_DIR / "asb_financial_analyst_manual_workflow.json"
    )
    assert plan == ["gather_market_data", "postprocess_and_recommend"]
    assert obs.facts == frozenset(
        {"market_data_gathered", "investment_recommendations_provided"}
    )
