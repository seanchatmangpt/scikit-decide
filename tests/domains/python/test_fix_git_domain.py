# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style test: GitRecoveryDomain solved end to end by Astar over a
real, local git repository replicating vendor/gyms/terminal-bench's
`fix-git` task.

No mocks. This test:

  1. Builds a real git repository on disk (pytest ``tmp_path``), replaying
     the exact sequence of real git operations that
     `vendor/gyms/terminal-bench/fix-git/environment/setup.sh` performs
     against its cloned fixture repo (commit on the base branch, then a
     second commit made while HEAD is detached so it becomes unreachable
     from master except by hash) -- using the task's own real patch files
     for content instead of the upstream network clone (no internet access
     in this test run; the git *mechanics* under test are identical, and
     that mechanic -- not the specific upstream repo history -- is what
     GitRecoveryDomain plans over).
  2. Constructs the real GitRecoveryDomain against that real repo.
  3. Runs the real registered Astar solver's solve() and replays the
     resulting plan against the real domain via real subprocess git calls.
  4. Asserts, exactly as the vendored task's own
     `fix-git/tests/test_outputs.py` does, that the two patched files on
     master now match the known-good copies byte for byte.

SCOPE WARNING: this exercises one domain/solver pair against a locally
replicated fixture of one terminal-bench task's git mechanics. It says
nothing about running the real terminal-bench harness, its Docker image,
or any other vendored task.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from autofde_lab import utils
from autofde_lab.hub.domain.fix_git import GitRecoveryDomain
from autofde_lab.hub.domain.fix_git.git_recovery import State

FIX_GIT_TASK_DIR = (
    Path(__file__).resolve().parents[3]
    / "vendor"
    / "gyms"
    / "terminal-bench"
    / "fix-git"
)
PATCH_FILES_DIR = FIX_GIT_TASK_DIR / "environment" / "resources" / "patch_files"

pytestmark = pytest.mark.skipif(
    not PATCH_FILES_DIR.is_dir(),
    reason=(
        "vendor/gyms/terminal-bench submodule not initialized "
        "(git submodule update --init vendor/gyms/terminal-bench)"
    ),
)


def _run_git(repo_dir: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=repo_dir,
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def fix_git_repo(tmp_path: Path) -> tuple[Path, str]:
    """Real local git repo replicating fix-git's detached-commit scenario.

    Uses the task's own real patch files
    (`environment/resources/patch_files/{about.md,default.html}`) so the
    goal condition below (files match those exact bytes) is the task's own
    real success criterion, not a fabricated stand-in.
    """
    repo_dir = tmp_path / "personal-site"
    repo_dir.mkdir()
    _run_git(repo_dir, "init", "-b", "master")
    _run_git(repo_dir, "config", "user.email", "test@example.com")
    _run_git(repo_dir, "config", "user.name", "Test User")

    (repo_dir / "_includes").mkdir()
    (repo_dir / "_layouts").mkdir()
    (repo_dir / "_includes" / "about.md").write_text("original about\n")
    (repo_dir / "_layouts" / "default.html").write_text("<html>original</html>\n")
    _run_git(repo_dir, "add", "-A")
    _run_git(repo_dir, "commit", "-m", "Initial site")

    # Detach HEAD (as setup.sh's `git checkout HEAD~1`-then-reset dance
    # does) and commit the real patched files while unreachable from any
    # branch -- this is the exact "lost commit" scenario the task models.
    _run_git(repo_dir, "checkout", "--detach", "HEAD")
    about_patch = (PATCH_FILES_DIR / "about.md").read_text()
    layout_patch = (PATCH_FILES_DIR / "default.html").read_text()
    (repo_dir / "_includes" / "about.md").write_text(about_patch)
    (repo_dir / "_layouts" / "default.html").write_text(layout_patch)
    _run_git(repo_dir, "add", "-A")
    _run_git(repo_dir, "commit", "-m", "Move to Stanford")
    lost_commit = _run_git(repo_dir, "rev-parse", "HEAD").stdout.strip()

    # Back to master, where the commit above is now unreachable except by
    # its raw hash -- exactly the state the vendored task's agent wakes up
    # in.
    _run_git(repo_dir, "checkout", "master")

    return repo_dir, lost_commit


def test_astar_recovers_lost_commit_onto_master(fix_git_repo):
    repo_dir, lost_commit = fix_git_repo
    domain = GitRecoveryDomain(repo_dir=repo_dir, target_commit=lost_commit)

    # Sanity: before any plan is executed, master genuinely does not have
    # the patched content (the "problem" is real, not vacuous).
    about_before = (repo_dir / "_includes" / "about.md").read_text()
    assert about_before == "original about\n"

    Astar = utils.load_registered_solver("Astar")
    assert Astar is not None, "Astar did not load from the registry"
    assert Astar.check_domain(domain)

    with Astar(domain_factory=lambda: domain) as solver:
        solver.solve()
        obs = domain._get_initial_state_()
        plan: list[str] = []
        for _ in range(10):
            if domain._is_terminal(obs):
                break
            action = solver.sample_action(obs)
            plan.append(action)
            obs = domain._get_next_state(obs, action)

    # (a) the solver's symbolic plan reaches the domain's own goal predicate
    assert domain._is_goal(obs), f"Astar did not reach the goal. Plan: {plan}"
    assert obs == State(current_branch="master", recovery_branch_exists=True, merged=True)

    # (b) it found the same 3-step shape as the task's own solution.sh
    assert plan == ["checkout_recovery", "checkout_master", "merge_recovery"]

    # (c) replay the solved plan for real against the real repository --
    # actual execution, kept explicit and separate from planning (see
    # GitRecoveryDomain's module docstring).
    real_state = None
    for action in plan:
        real_state = domain.execute_action(action)
    assert real_state == State(current_branch="master", recovery_branch_exists=True, merged=True)

    # (d) real state, real filesystem: master's working tree now matches
    # the task's own documented success condition byte for byte -- the
    # same comparison fix-git/tests/test_outputs.py makes.
    about_after = (repo_dir / "_includes" / "about.md").read_text()
    layout_after = (repo_dir / "_layouts" / "default.html").read_text()
    assert about_after == (PATCH_FILES_DIR / "about.md").read_text()
    assert layout_after == (PATCH_FILES_DIR / "default.html").read_text()

    # (e) the recovered commit really is reachable from master now
    merge_base = _run_git(repo_dir, "merge-base", "--is-ancestor", lost_commit, "master")
    assert merge_base.returncode == 0
