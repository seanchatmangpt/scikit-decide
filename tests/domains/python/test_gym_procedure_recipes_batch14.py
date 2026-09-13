# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""UNIT checkpoint (NOT a Chicago/ecosystem test): batch-14 recipes for the
generic `GymProcedureDomain` factory, transcribed from real vendored gym
tasks -- no `unittest.mock`/`Mock`/`patch`/`monkeypatch` anywhere in this
file, per `.claude/rules/testing-chicago-style.md`.

Assigned gyms and outcome, investigated for real this session:

- `vendor/gyms/tua-bench` -- ALIVE. Task `108-create-mail-folders` ships a
  real, ordered `solution/solve.sh` (kill Thunderbird -> resolve profile dir
  -> create the `Local Folders` root -> create COMPANY -> create UNIVERSITY)
  transcribed verbatim below.
- `vendor/gyms/webarena` -- BLOCKED:NO_TRANSCRIBABLE_PROCEDURE. Its 812
  tasks (`config_files/test.raw.json`) are single-intent QA/goal tasks
  evaluated by final-state matching (`string_match`/`program_html`), not an
  ordered step sequence. The only step-level artifacts (human trajectories,
  Playwright traces, execution renders) are external Google Drive links in
  `resources/README.md`, not vendored in this checkout -- transcribing a
  procedure would mean fabricating one.
- `vendor/gyms/wonderbread` -- BLOCKED:NO_TRANSCRIBABLE_PROCEDURE. Its
  `data/metadata.json`/`data/df_valid.csv` reference per-demo
  `trace.json`/`sop.txt` files under `data/demos/`, which do not exist in
  this checkout (`ls data/demos` -> no such directory) -- the underlying
  demonstrations live only on Zenodo/Google Drive. The vendored
  `data/Process Mining Task Demonstrations.xlsx` "Gold SOP" column likewise
  holds only Google Drive links, not inline ordered step text.
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


def test_astar_solves_real_tua_bench_create_mail_folders_recipe():
    """A* must recover the real solve.sh's own ordering to create both local folders."""
    domain = GymProcedureDomain.from_json(RECIPES_DIR / "tua_bench_create_mail_folders.json")
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
            "kill_thunderbird",
            "locate_profile_dir",
            "create_local_folders_root",
            "create_company_folder",
            "create_university_folder",
        ]
