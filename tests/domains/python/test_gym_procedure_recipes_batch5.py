# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""UNIT checkpoints (NOT Chicago/ecosystem tests): the generic
`GymProcedureDomain` factory proven against real recipes transcribed from
two of this session's three assigned gyms (`vendor/gyms/androidworld`,
`vendor/gyms/browsergym`) via a real registered `Astar` solver's real
`solve()` call -- no `unittest.mock`/`Mock`/`patch`/`monkeypatch` anywhere
in this file, per `.claude/rules/testing-chicago-style.md`.

`vendor/gyms/osworld` is BLOCKED:NO_TRANSCRIBABLE_PROCEDURE and has no
test here: its task JSONs under `evaluation_examples/examples/**/*.json`
carry a `"trajectory"` field pointing at a `trajectories/<uuid>/` directory
that does not exist anywhere in the vendored checkout (verified with
`find vendor/gyms/osworld -type d -iname 'trajector*'` -- zero results),
and every `config` block present is environment *setup* (download/open a
seed file), not a solution -- the `evaluator` blocks only check final
state (e.g. `compare_table` against an expected output file), never an
ordered gold action list. Transcribing steps here would mean fabricating
an order the gym itself does not document, which `CLAUDE.md`'s standing
law forbids.
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


def _solve_and_collect_plan(domain: GymProcedureDomain, solver) -> list[str]:
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


def test_androidworld_markor_create_note_and_sms_recipe_solves_in_documented_order():
    """androidworld's MarkorCreateNoteAndSms composite task: its own template
    ("Create a new note ... and then ... Share the entire content ... via
    SMS") documents the order -- note creation must precede the SMS share.
    """
    recipe = load_recipe(RECIPES_DIR / "androidworld_markor_create_note_and_sms.json")
    assert recipe.gym == "androidworld"
    assert len(recipe.steps) == 2

    domain = GymProcedureDomain(recipe)
    Astar = utils.load_registered_solver("Astar")
    with Astar(domain_factory=lambda: domain) as solver:
        plan = _solve_and_collect_plan(domain, solver)

    assert plan == ["create_markor_note", "share_note_via_sms"]


def test_browsergym_miniwob_click_menu_2_recipe_solves_in_documented_order():
    """browsergym's own `tests/miniwob/test_click-menu-2.py` "cheat" test is
    a real reference solution: click Menu, then (for a Playback-submenu
    item such as "Play") click Playback, then click the target item.
    """
    recipe = load_recipe(RECIPES_DIR / "browsergym_miniwob_click_menu_2.json")
    assert recipe.gym == "browsergym"
    assert len(recipe.steps) == 3

    domain = GymProcedureDomain(recipe)
    Astar = utils.load_registered_solver("Astar")
    with Astar(domain_factory=lambda: domain) as solver:
        plan = _solve_and_collect_plan(domain, solver)

    assert plan == ["click_menu_button", "click_playback_submenu", "click_target_item"]


def test_osworld_has_no_vendored_gold_trajectories_directory():
    """Documents BLOCKED:NO_TRANSCRIBABLE_PROCEDURE for osworld as a real,
    checked fact rather than an assertion: no `trajectories/` directory
    exists anywhere in the vendored osworld checkout, even though task
    JSONs reference one by relative path.
    """
    osworld_root = Path(__file__).resolve().parents[3] / "vendor" / "gyms" / "osworld"
    assert osworld_root.is_dir(), f"expected vendored osworld checkout at {osworld_root}"
    trajectory_dirs = [p for p in osworld_root.rglob("trajector*") if p.is_dir()]
    assert trajectory_dirs == []
