# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""UNIT checkpoints (NOT Chicago/ecosystem tests): batch 1 of gym-procedure
recipes transcribed from real vendored gym tasks and proven with a real
registered `Astar` solver's real `solve()` call -- no `unittest.mock`/`Mock`/
`patch`/`monkeypatch` anywhere in this file, per
`.claude/rules/testing-chicago-style.md`.

Per-gym status this batch (see task prompt for the full investigation):

- cybench: ALIVE -- a second, distinct real task (not the already-done
  hkcert-ctf/05-motp), `project-sekai-ctf/sekaictf-2023/forensics/eval-me`,
  whose real ordered subtasks/answers/commands live in its own
  `metadata.json`.
- sec-bench: BLOCKED:NO_TRANSCRIBABLE_PROCEDURE -- the repository is a
  benchmark-*generation* tool (seed/report/project preprocessing pipeline
  over the OSV database, then generic Docker-based evaluation commands). No
  single vulnerability instance ships a documented, ordered, per-task solve
  procedure the way cybench's `metadata.json` subtasks or cybergym-e2e's
  per-task scripts do; the README's "steps" are pipeline *stages of the
  tool itself*, not a task-specific procedure to transcribe without
  fabrication. Skipped per the task's explicit no-fabrication instruction.
- cybergym-e2e: ALIVE -- `curl/arvo_66012` has a real, ordered, documented
  four-stage validation procedure (README.md "Validation runs in four
  stages") backed by real per-task scripts (`prepare.sh`, `compile.sh`,
  `run_poc.sh`, `test.sh`) and a real reference `patch.diff`.
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


def _solve_and_check_goal(domain, max_steps: int = 20):
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
        return plan, obs


def test_cybench_evalme_recipe_solves_in_documented_subtask_order():
    """cybench: project-sekai-ctf/sekaictf-2023/forensics/eval-me -- a
    distinct real task from the already-done hkcert-ctf/05-motp, transcribed
    from its own metadata.json subtasks/commands."""
    domain = GymProcedureDomain.from_json(RECIPES_DIR / "cybench_evalme.json")
    plan, obs = _solve_and_check_goal(domain)
    assert plan == [
        "identify_pcap_source",
        "find_xor_key",
        "extract_and_decrypt_flag",
    ]
    assert "flag_captured" in obs.facts


def test_cybergym_e2e_curl_arvo_66012_recipe_solves_documented_four_stage_validation():
    """cybergym-e2e: curl/arvo_66012 -- the real four-stage patch-validation
    procedure documented in README.md, backed by real per-task scripts
    (prepare.sh, compile.sh, run_poc.sh, test.sh) and patch.diff."""
    domain = GymProcedureDomain.from_json(
        RECIPES_DIR / "cybergym_e2e_curl_arvo_66012.json"
    )
    plan, obs = _solve_and_check_goal(domain, max_steps=20)
    assert plan == [
        "prepare_source",
        "compile_fuzzer_vulnerable",
        "poc_crashes_without_patch",
        "apply_patch",
        "compile_fuzzer_patched",
        "poc_no_crash_with_patch",
        "run_test_suite",
        "ground_truth_poc_no_crash_with_patch",
    ]
    assert "patch_validated" in obs.facts
