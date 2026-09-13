# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""UNIT checkpoint (NOT a Chicago/ecosystem test): batch 4 of gym recipes for
the generic `GymProcedureDomain` factory, transcribed from real vendored
SRE/observability gyms' own documented procedures -- no
`unittest.mock`/`Mock`/`patch`/`monkeypatch` anywhere in this file, per
`.claude/rules/testing-chicago-style.md`.

Assigned gyms and their outcome:

- `vendor/gyms/aiopslab` -- investigated `aiopslab/orchestrator/problems/`
  (60+ problems). Every problem is a generic Detection/Localization/
  Analysis/Mitigation task graded by exact-string/dict match against a
  single expected answer (see `misconfig_app_hotel_res.py`'s `eval()`
  methods); none carries a documented *ordered* step sequence (numbered
  runbook, numbered subtasks, or a reference solve trajectory) anywhere in
  the problem source, `README.md`, or `CLAUDE.md`. BLOCKED:NO_TRANSCRIBABLE_PROCEDURE.

- `vendor/gyms/o11y-bench` -- investigated `tasks-spec/{investigation,
  dashboarding,...}/*.yaml`. Every task is graded by an unordered, weighted
  `rubric` list (or a final-state `checks` list for dashboarding tasks);
  `checks: []` for every investigation task. No task file anywhere encodes a
  numbered/ordered procedure -- only what the *final* answer/dashboard state
  must contain, scored independently per criterion.
  BLOCKED:NO_TRANSCRIBABLE_PROCEDURE.

- `vendor/gyms/sre-bench` -- `scenerio/README.md` documents 17 real,
  numbered incident scenarios. Scenario 0 ("Broken Image ->
  ImagePullBackOff") gives an ordered "Detection Signals > Commands to
  observe" list and a numbered "Mitigation Steps" 1-5 list, and is backed by
  a real manifest (`vendor/gyms/sre-bench/manifests/scenario-0/pod.yaml`,
  which really does reference `nonexistent-registry.io/invalid-image:v1.0`).
  Transcribed verbatim into `recipes/sre_bench_broken_image.json`. ALIVE.
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


def test_sre_bench_broken_image_recipe_loads_from_real_readme():
    recipe = load_recipe(RECIPES_DIR / "sre_bench_broken_image.json")
    assert recipe.gym == "sre-bench"
    assert recipe.task == "scenario-0-broken-image-imagepullbackoff"
    assert len(recipe.steps) == 7
    assert recipe.goal_facts == frozenset({"pod_running"})
    # the real broken image reference transcribed from manifests/scenario-0/pod.yaml
    assert "nonexistent-registry.io/invalid-image:v1.0" in recipe.steps[2].description


def test_astar_solves_real_sre_bench_broken_image_recipe_in_documented_order():
    """A* must recover the README's own Detection Signals -> Mitigation Steps ordering."""
    domain = GymProcedureDomain.from_json(RECIPES_DIR / "sre_bench_broken_image.json")
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
            "observe_pod_status",
            "describe_pod_for_error",
            "identify_incorrect_image_reference",
            "verify_image_exists_in_registry",
            "check_registry_authentication",
            "update_deployment_with_correct_image",
            "verify_pod_starts_successfully",
        ]
        assert sum(domain.describe_step(s).cost for s in plan) == pytest.approx(7.0)
