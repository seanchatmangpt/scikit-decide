# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""UNIT checkpoint (NOT a Chicago/ecosystem test): a second batch of
`GymProcedureDomain` recipes, each transcribed from a real, documented,
ordered procedure found in a real vendored gym -- no fabricated steps -- and
each proven with a real registered `Astar` solver's real `solve()` call. No
`unittest.mock`/`Mock`/`patch`/`monkeypatch` anywhere in this file, per
`.claude/rules/testing-chicago-style.md`.

Per-gym status (assignment: vendor/gyms/agentbench, vendor/gyms/general-agentbench,
vendor/gyms/agentlab):

- agentbench: ALIVE. `data/knowledgegraph/dev.json`'s `qid=4300563004000_grailqa`
  entry carries a real, ordered gold `"actions"` list (a sequence of
  `get_relations`/`get_neighbors`/`intersection` KG-walk operations) leading to a
  documented `"answer"`. Transcribed verbatim into
  `recipes/agentbench_kg_relation_path.json`.
- general-agentbench: ALIVE. `benchmarks/terminal-bench/tasks/openssl-selfsigned-cert`
  carries a real numbered instruction list (`task.yaml`, steps 1-6) with a matching
  real reference `solution.sh`. Transcribed into
  `recipes/general_agentbench_openssl_selfsigned_cert.json`.
- agentlab: BLOCKED:NO_TRANSCRIBABLE_PROCEDURE. AgentLab vendors only the
  BrowserGym-agent *framework* (agents, experiment/study runners, LLM API glue) --
  actual benchmark task definitions (WebArena, MiniWoB, WorkArena, OSWorld, GAIA,
  ...) are external packages installed via `ensure_benchmark(...)`, not vendored in
  this checkout. The closest in-repo candidate, `hint_db.csv`
  (`src/agentlab/agents/tool_use_agent/hint_db.csv`), is a set of free-text UI
  hints tagged by `semantic_keys` (e.g. "drop down menu", "Filling up form"), not
  an ordered step sequence with preconditions/effects -- turning it into Step
  records would require inventing an order and fact structure the source does not
  document. No `solve.sh`/numbered-instructions/gold-trajectory file was found
  anywhere under `vendor/gyms/agentlab` after checking `README.md`, `tutorials/`,
  `src/agentlab/benchmarks/`, and `reproducibility_journal.csv`.
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


def _solve_and_reach_goal(domain: GymProcedureDomain, max_steps: int = 20) -> list[str]:
    Astar = utils.load_registered_solver("Astar")
    with Astar(domain_factory=lambda: domain) as solver:
        solver.solve()
        obs = domain.reset()
        plan: list[str] = []
        for _ in range(max_steps):
            if domain._is_terminal(obs):
                break
            action = solver.sample_action(obs)
            plan.append(action)
            outcome = domain.step(action)
            obs = outcome.observation
        assert domain._is_goal(obs), f"A* did not reach the goal. Plan: {plan}"
        return plan


def test_agentbench_knowledgegraph_relation_path_recipe_reaches_answer():
    """Real gold `actions` trajectory from AgentBench's KG task (dev.json,
    qid=4300563004000_grailqa) drives an A* plan to `answer_found`."""
    domain = GymProcedureDomain.from_json(RECIPES_DIR / "agentbench_kg_relation_path.json")
    plan = _solve_and_reach_goal(domain)
    # the real gold trajectory has 7 actions; our two independent branches
    # (via #0 and via m.0j50kb6) may interleave differently under A*, but both
    # must be exhausted before the final intersection step fires.
    assert len(plan) == 7
    assert plan[-1] == "intersect_positions"
    assert set(plan) == {
        "get_relations_quotation",
        "get_neighbors_quotation_author",
        "get_relations_var0",
        "get_neighbors_var0_position",
        "get_relations_pat_connaughton",
        "get_neighbors_pat_position",
        "intersect_positions",
    }


def test_general_agentbench_openssl_selfsigned_cert_recipe_reaches_verification():
    """Real numbered instructions + reference `solution.sh` from
    general-agentbench's terminal-bench `openssl-selfsigned-cert` task drive an
    A* plan through the documented order to a passing verification script."""
    domain = GymProcedureDomain.from_json(
        RECIPES_DIR / "general_agentbench_openssl_selfsigned_cert.json"
    )
    plan = _solve_and_reach_goal(domain)
    assert plan == [
        "create_ssl_dir",
        "generate_private_key",
        "chmod_private_key",
        "create_selfsigned_cert",
        "create_combined_pem",
        "write_verification_txt",
        "write_check_cert_script",
        "run_check_cert_script",
    ]
