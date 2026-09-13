# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Deterministic planning domain over a real git repository, recovering a
commit lost to a detached-HEAD checkout.

terminal-bench (vendored at ``vendor/gyms/terminal-bench``, task
``fix-git``) drops the agent in a real git repository where a commit was
made while `HEAD` was detached and is unreachable from `master` except by
its raw hash. The task's own documented success condition
(``fix-git/tests/test_outputs.py``) is that two patched files
(``_includes/about.md``, ``_layouts/default.html``) on `master` match a
known-good copy on disk, and the task's own reference solution
(``fix-git/solution/solve.sh``) is exactly three git commands:

```
git checkout -b recovery-branch <hash>
git checkout master
git merge -X theirs recovery-branch
```

This domain models the *sequencing* of those three real git operations as a
deterministic planning problem over ``(current_branch, recovery_branch_exists,
merged)`` state:

* **state**: ``(current_branch, recovery_branch_exists, merged)`` -- the
  initial value is observed from the real repository via
  ``git branch --show-current``; subsequent transitions are computed
  symbolically (see note below).
* **action**: one of ``checkout_recovery``, ``checkout_master``,
  ``merge_recovery`` -- each corresponds 1:1 to one real ``git`` subprocess
  command against the repository at ``self.repo_dir``.
* **goal**: on `master`, with the recovery merge complete.

**Why ``_get_next_state`` does not itself run ``git``**: forward search
solvers such as Astar explore the state graph, including branches that are
not on the final plan, and may revisit a state. If ``_get_next_state``
executed the real ``git`` mutation on every expansion, search exploration
would corrupt the one real repository on disk (e.g. attempting
``checkout -b recovery-branch`` a second time once the branch already
exists from a different explored path) -- a domain cannot safely alias
"exploring a state" with "actuating a state" against a real mutable
resource. So planning here is over a pure, symbolic model of the same three
transitions; :meth:`execute_action` (not part of the solved graph) is what
actually runs the corresponding real ``git`` command, and is used to replay
a solved plan against the real repository and verify real resulting state
-- domains compute candidate plans, they do not actuate (see
``src/autofde_lab/CLAUDE.md``); the caller replaying the plan for real is
the actuation step, kept explicit and separate.

Discovering *which* commit hash needs recovering (the task's own solution
greps ``.git/logs/HEAD``) is a search step over reflog text, not a planning
concern, so the target hash is supplied at construction -- the same
division TerraGoatRemediation draws between parsing findings (construction
time, not a planning concern) and remediating them (the planning problem).
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import NamedTuple, Optional

from autofde_lab import D, DeterministicPlanningDomain, Space, Value
from autofde_lab.hub.space.gym import ListSpace

RECOVERY_BRANCH = "recovery-branch"

CHECKOUT_RECOVERY = "checkout_recovery"
CHECKOUT_MASTER = "checkout_master"
MERGE_RECOVERY = "merge_recovery"

ALL_ACTIONS = (CHECKOUT_RECOVERY, CHECKOUT_MASTER, MERGE_RECOVERY)


class State(NamedTuple):
    current_branch: str
    recovery_branch_exists: bool
    merged: bool


class D_(
    DeterministicPlanningDomain,
):
    T_state = State
    T_observation = T_state
    T_event = str  # one of ALL_ACTIONS
    T_value = float
    T_predicate = bool
    T_info = None


class GitRecoveryDomain(D_):
    """Plan the real git commands that recover a detached-HEAD commit onto
    the base branch, matching terminal-bench's ``fix-git`` task."""

    def __init__(
        self,
        repo_dir: Path,
        target_commit: str,
        base_branch: str = "master",
    ) -> None:
        """
        # Parameters
        repo_dir: path to a real, already-initialized git repository (e.g.
            terminal-bench's ``fix-git`` task fixture, replicated locally).
        target_commit: the commit-ish (hash) of the detached-HEAD commit to
            recover onto ``base_branch``.
        base_branch: the branch the recovered commit should be merged into.
            Defaults to ``"master"``, matching the vendored task.
        """
        self.repo_dir = Path(repo_dir)
        self.target_commit = target_commit
        self.base_branch = base_branch
        if not (self.repo_dir / ".git").exists():
            raise ValueError(f"{self.repo_dir} is not a git repository (no .git dir)")

    def _run_git(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", *args],
            cwd=self.repo_dir,
            check=True,
            capture_output=True,
            text=True,
        )

    def _current_branch(self) -> str:
        result = self._run_git("branch", "--show-current")
        return result.stdout.strip()

    def _get_next_state(
        self,
        memory: D.T_memory[D.T_state],
        action: D.T_agent[D.T_concurrency[D.T_event]],
    ) -> D.T_state:
        """Pure symbolic transition -- no real git subprocess call. See the
        module docstring for why: search exploration must not mutate the
        one real repository on disk. Use :meth:`execute_action` to actually
        run the corresponding real git command."""
        if action == CHECKOUT_RECOVERY:
            return State(
                current_branch=RECOVERY_BRANCH,
                recovery_branch_exists=True,
                merged=memory.merged,
            )
        if action == CHECKOUT_MASTER:
            return State(
                current_branch=self.base_branch,
                recovery_branch_exists=memory.recovery_branch_exists,
                merged=memory.merged,
            )
        if action == MERGE_RECOVERY:
            return State(
                current_branch=memory.current_branch,
                recovery_branch_exists=memory.recovery_branch_exists,
                merged=True,
            )
        raise ValueError(f"unknown action {action!r}")

    def execute_action(self, action: str) -> State:
        """Actually run the real git subprocess command corresponding to
        ``action`` against ``self.repo_dir``, and return the real resulting
        state observed from the repository. Not part of the domain's
        planning graph (see module docstring) -- for replaying a solved
        plan against the real repository."""
        if action == CHECKOUT_RECOVERY:
            self._run_git("checkout", "-b", RECOVERY_BRANCH, self.target_commit)
        elif action == CHECKOUT_MASTER:
            self._run_git("checkout", self.base_branch)
        elif action == MERGE_RECOVERY:
            self._run_git(
                "merge",
                "-m",
                "Merge recovery-branch into master",
                "-X",
                "theirs",
                RECOVERY_BRANCH,
            )
        else:
            raise ValueError(f"unknown action {action!r}")
        return State(
            current_branch=self._current_branch(),
            recovery_branch_exists=self.recovery_branch_exists_on_disk(),
            merged=self._merged_on_disk(),
        )

    def recovery_branch_exists_on_disk(self) -> bool:
        result = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", RECOVERY_BRANCH],
            cwd=self.repo_dir,
            capture_output=True,
            text=True,
        )
        return result.returncode == 0

    def _merged_on_disk(self) -> bool:
        if not self.recovery_branch_exists_on_disk():
            return False
        result = subprocess.run(
            ["git", "merge-base", "--is-ancestor", self.target_commit, self.base_branch],
            cwd=self.repo_dir,
            capture_output=True,
            text=True,
        )
        return result.returncode == 0

    def _get_transition_value(
        self,
        memory: D.T_memory[D.T_state],
        action: D.T_agent[D.T_concurrency[D.T_event]],
        next_state: Optional[D.T_state] = None,
    ) -> D.T_agent[Value[D.T_value]]:
        return Value(cost=1.0)

    def _is_terminal(self, state: D.T_state) -> D.T_agent[D.T_predicate]:
        return self._is_goal(state)

    def _get_action_space_(self) -> D.T_agent[Space[D.T_event]]:
        return ListSpace(list(ALL_ACTIONS))

    def _get_applicable_actions_from(
        self, memory: D.T_memory[D.T_state]
    ) -> D.T_agent[Space[D.T_event]]:
        actions: list[str] = []
        if not memory.recovery_branch_exists:
            actions.append(CHECKOUT_RECOVERY)
        if memory.current_branch != self.base_branch:
            actions.append(CHECKOUT_MASTER)
        if (
            memory.current_branch == self.base_branch
            and memory.recovery_branch_exists
            and not memory.merged
        ):
            actions.append(MERGE_RECOVERY)
        return ListSpace(actions)

    def _get_goals_(self) -> D.T_agent[Space[D.T_observation]]:
        return ListSpace(
            [
                State(
                    current_branch=self.base_branch,
                    recovery_branch_exists=True,
                    merged=True,
                )
            ]
        )

    def _get_initial_state_(self) -> D.T_state:
        return State(
            current_branch=self._current_branch(),
            recovery_branch_exists=False,
            merged=False,
        )

    def _get_observation_space_(self) -> D.T_agent[Space[D.T_observation]]:
        return ListSpace(
            [
                State(
                    current_branch=self.base_branch,
                    recovery_branch_exists=True,
                    merged=True,
                )
            ]
        )
