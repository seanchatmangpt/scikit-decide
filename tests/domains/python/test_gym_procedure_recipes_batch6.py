# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""UNIT checkpoints (NOT Chicago/ecosystem tests): recipes transcribed from
real vendored gyms' own documented ordered procedures, each proven against
the generic `GymProcedureDomain` factory and a real registered `Astar`
solver's real `solve()` call -- no `unittest.mock`/`Mock`/`patch`/
`monkeypatch` anywhere in this file, per
`.claude/rules/testing-chicago-style.md`.

Batch 6 gyms and outcomes:

- `vendor/gyms/bountytasks/curl/bounties/bounty_0`: real, ordered exploit
  script (`exploit_files/exploit.sh`) for CVE-2023-46219 (HSTS long
  filename clears contents), verified against its own `verify_files/verify.sh`.
- `vendor/gyms/doomarena`: BLOCKED:NO_TRANSCRIBABLE_PROCEDURE -- it is an
  adversarial-agent *testing framework* (TauBench/BrowserGym/OSWorld/
  MailInject integrations) whose attack outcomes depend on live,
  nondeterministic LLM calls (its own intro notebook requires a real
  OpenAI API key and an LLM-driven agent's response to determine attack
  success). No fixed, documented, deterministic ordered walkthrough exists
  to transcribe without fabricating what the LLM would do.
- `vendor/gyms/cloudfoxable/aws/challenges/Search 1`: real, ordered
  cheatsheet (`cheatsheet.md`) walking through `cloudfox aws endpoints`,
  finding an exposed OpenSearch domain, and querying it for the flag --
  a different documented attack path than the already-completed
  cloudgoat/azuregoat/terragoat gyms.
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


def test_astar_solves_bountytasks_curl_hsts_bypass_recipe():
    """CVE-2023-46219: curl HSTS long-filename bug -- real exploit.sh, real
    verify.sh outcome ('the HSTS entry is gone')."""
    domain, plan, obs = _solve_and_reach_goal(
        RECIPES_DIR / "bountytasks_curl_bounty0.json"
    )
    assert plan == [
        "build_curl_from_source",
        "populate_good_hsts_file",
        "copy_to_overlong_filename",
        "curl_with_overlong_hsts_filename",
        "confirm_hsts_bypass",
    ]
    assert "hsts_bypass_confirmed" in obs.facts
    assert sum(domain.describe_step(s).cost for s in plan) == pytest.approx(5.0)


def test_astar_solves_cloudfoxable_search1_recipe():
    """CloudFoxable 'Search 1': exposed OpenSearch domain -> flag, per the
    challenge's own cheatsheet.md and challenge.yml flag."""
    domain, plan, obs = _solve_and_reach_goal(
        RECIPES_DIR / "cloudfoxable_search1.json"
    )
    assert plan == [
        "run_cloudfox_endpoints",
        "find_exposed_opensearch_domain",
        "query_opensearch_for_flag",
    ]
    assert "flag_captured" in obs.facts
    assert sum(domain.describe_step(s).cost for s in plan) == pytest.approx(3.0)
