# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""UNIT checkpoint (NOT a Chicago/ecosystem test): three more real recipes for
the generic `GymProcedureDomain` factory (`CLAUDE.md`'s "your gyms" batch 8),
each transcribed directly from a real vendored artifact -- no fabricated
steps, per the task's own instruction:

- ``cube-harness``: ``vendor/gyms/cube-harness``'s ``knows-cube`` task
  ``knows.docs_11_personal_recipe_ocr.1``, whose own
  ``task_metadata.json[...]['abstract_description']`` is itself an explicitly
  ordered ("First, ... Then, ... Finally, ...") procedure.
- ``cube-standard``: a real captured OCEL episode at
  ``docs/papers/evidence/cube-standard/cube-container-counter-episode.ocel.json``
  (materialize -> increment x3 -> decrement -> increment -> teardown), from a
  prior session's real gymact instrumentation run.
- ``qqr``: ``vendor/gyms/qqr``'s ``data/secrespond/ranges/redis-rce/checklist.en.md``
  incident-response benchmark, whose CHK-01..CHK-24 remediation actions
  (grouped into checklist Dimensions 1/2/3/5) are transcribed in the
  checklist's own dimension/CHK-number order.

Each test loads its recipe via ``GymProcedureDomain.from_json(...)`` and
solves it with the real registered ``Astar`` solver -- no
`unittest.mock`/`Mock`/`patch`/`monkeypatch` anywhere in this file, per
`.claude/rules/testing-chicago-style.md`.
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


def _solve_and_reach_goal(recipe_path: Path) -> list[str]:
    domain = GymProcedureDomain.from_json(recipe_path)
    Astar = utils.load_registered_solver("Astar")
    with Astar(domain_factory=lambda: domain) as solver:
        solver.solve()
        obs = domain.reset()
        plan: list[str] = []
        for _ in range(50):
            if domain._is_terminal(obs):
                break
            action = solver.sample_action(obs)
            plan.append(action)
            outcome = domain.step(action)
            obs = outcome.observation
        assert domain._is_goal(obs), f"A* did not reach the goal. Plan: {plan}"
        return plan


def test_astar_solves_cube_harness_knows_recipe_ocr_recipe_in_documented_order():
    """cube-harness: knows-cube docs_11_personal_recipe_ocr.1's own ordered
    ("First, ... Then, ... Finally, ...") abstract_description, transcribed
    verbatim from vendor/gyms/cube-harness/cubes/knows-cube/src/knows_cube/task_metadata.json."""
    plan = _solve_and_reach_goal(RECIPES_DIR / "cube_harness_knows_docs11_recipe.json")
    assert plan == [
        "identify_recipe_name_from_image",
        "replace_recipe_name_in_template",
        "copy_ingredient_list",
        "paste_instructions",
        "get_and_cite_tips",
        "replace_default_image",
        "fill_remaining_template_fields",
        "search_similar_recipes",
        "create_pages_for_similar_recipes",
        "fill_tips_from_online_recipes",
    ]


def test_astar_solves_cube_standard_container_counter_episode_recipe():
    """cube-standard: the real captured gymact OCEL episode trace at
    docs/papers/evidence/cube-standard/cube-container-counter-episode.ocel.json
    (materialize -> increment x3 -> decrement -> increment -> teardown). A*
    finds the minimum-cost plan reaching goal_facts (count reaches 3 already
    after the 3rd increment, so it takes that shortcut rather than replaying
    the full 7-event episode) -- both the shortcut and the full episode are
    real transitions transcribed from the recipe's step table; A*'s job is
    to find *a* shortest path through them, not to replay the episode
    verbatim."""
    plan = _solve_and_reach_goal(RECIPES_DIR / "cube_standard_container_counter.json")
    assert plan == [
        "materialize",
        "increment_1",
        "increment_2",
        "increment_3",
        "teardown",
    ]


def test_astar_solves_qqr_secrespond_redis_rce_remediation_recipe():
    """qqr: the real secrespond redis-rce benchmark's checklist.en.md
    remediation actions (CHK-01..CHK-24), transcribed in the checklist's own
    Dimension/CHK-number order from
    vendor/gyms/qqr/data/secrespond/ranges/redis-rce/checklist.en.md."""
    plan = _solve_and_reach_goal(RECIPES_DIR / "qqr_secrespond_redis_rce.json")
    assert plan == [
        "terminate_mining_process",
        "delete_mining_binary",
        "rebuild_authorized_keys",
        "clean_crontab",
        "harden_redis_bind",
        "set_redis_requirepass",
        "enable_protected_mode",
        "run_redis_as_dedicated_user",
        "rename_dangerous_commands",
        "disable_ssh_root_login",
        "restrict_sudoers_nopasswd",
        "remove_ssh_rc_persistence",
        "remove_initd_persistence",
        "verify_redis_hardening",
        "restrict_port_6379",
        "verify_services_restart",
    ]
