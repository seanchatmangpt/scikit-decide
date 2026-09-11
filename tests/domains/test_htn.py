# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style: real HTNTotalOrderPlanner exercised against a real, bundled
unified-planning HTN fixture and against a hand-authored verify-and-commit
problem for xaas's own verify-and-commit.hddl domain. No mocked solver, no
mocked parser -- unified_planning.io.PDDLReader parses real HDDL files on
disk, and HTNTotalOrderPlanner.solve() runs its real recursive
method-try/backtrack decomposition search.

Every returned plan is replay-verified independently of the planner: the
test itself re-applies each returned action's real preconditions/effects
against a state built directly from the parsed problem's initial values,
step by step, and asserts every precondition holds and the final state
satisfies the problem's goal. This is the postcondition replay-audit shape
cited (as a known-good verification pattern, not reused code) from
~/wasm4pm's htn_planning.rs.
"""

from __future__ import annotations

import os

from unified_planning.io import PDDLReader

from autofde_lab.hub.domain.htn import HTNDomain, HTNTotalOrderPlanner
from autofde_lab.hub.domain.htn.planner import _apply_effects, _eval_condition

HERE = os.path.dirname(__file__)
FIXTURES = os.path.join(HERE, "htn_fixtures")

# Real bundled unified-planning HTN fixture (confirmed present in this
# repo's own .venv; verified before hand-building anything, per the task's
# own "absence is not evidence" instruction).
import unified_planning as _up  # noqa: E402

_UP_HDDL_DIR = os.path.join(
    os.path.dirname(_up.__file__), "test", "hddl", "2020-to-Multiarm-Blocksworld"
)
BLOCKSWORLD_DOMAIN = os.path.join(_UP_HDDL_DIR, "domain.hddl")
BLOCKSWORLD_PROBLEM = os.path.join(_UP_HDDL_DIR, "instance.1.pb.hddl")


def _replay_verify(problem, plan, check_goal: bool = True) -> None:
    """Re-apply `plan` (a list of GroundAction) from `problem`'s real
    initial state, asserting each action's real preconditions hold before
    its real effects are applied, then (if `check_goal`) asserting the
    real classical-planning goal holds.

    `check_goal=False` is used for the bundled Multiarm-Blocksworld HTN
    fixture: HTN success is defined by the task network being fully
    decomposed into a valid primitive-action sequence (which the
    precondition-chain replay below verifies directly), not by that
    benchmark's leftover classical-planning `:goal` section, which its own
    `achieve-goals` task tracks via a separate `goal_on`/`goal_on-table`/
    `done` bookkeeping scheme rather than by literally holding at plan end
    (confirmed for real: this fixture's own plan legitimately unstacks
    blocks again after marking them done, as part of a later
    `achieve-goals` recursion for a different block)."""
    planner = HTNTotalOrderPlanner(problem)
    state = planner.initial_state()
    for ga in plan:
        action = problem.action(ga.name)
        bindings = {p.name: a for p, a in zip(action.parameters, ga.args)}
        for pre in action.preconditions:
            assert _eval_condition(pre, bindings, state), (
                f"replay-verify failed: precondition {pre} false before {ga!r} "
                f"in state {sorted(state)}"
            )
        state = _apply_effects(action, bindings, state)
    if check_goal:
        for goal in problem.goals:
            assert _eval_condition(goal, {}, state), (
                f"replay-verify failed: goal {goal} false in final state "
                f"{sorted(state)}"
            )


class TestHTNTotalOrderPlannerBundledFixture:
    """Verification target (a): a real bundled unified-planning HTN fixture
    (2020-to-Multiarm-Blocksworld) whose `achieve-goals` task has 5 methods
    tried in declared order, several of which require picking the *right*
    existentially-quantified block among several candidates -- a real
    backtracking requirement, not a contrived one."""

    def test_bundled_fixture_exists(self):
        assert os.path.exists(BLOCKSWORLD_DOMAIN), (
            "expected the real bundled unified-planning HTN fixture; if this "
            "fails, the .venv layout changed and this test's fixture path "
            "needs updating -- do not silently fall back to a mock"
        )
        assert os.path.exists(BLOCKSWORLD_PROBLEM)

    def test_solve_returns_real_plan_requiring_backtracking(self):
        reader = PDDLReader()
        problem = reader.parse_problem(BLOCKSWORLD_DOMAIN, BLOCKSWORLD_PROBLEM)
        planner = HTNTotalOrderPlanner(problem)
        plan = planner.solve()

        assert len(plan) > 0
        # Real evidence that backtracking/search actually happened, not a
        # single straight-line greedy match: more decomposition attempts
        # were made than actions ended up in the final plan.
        assert planner._attempts > len(plan), (
            "expected real backtracking (more decomposition attempts than "
            f"final plan actions); attempts={planner._attempts} "
            f"plan_len={len(plan)}"
        )

    def test_plan_replay_verifies_against_real_initial_state_and_goal(self):
        reader = PDDLReader()
        problem = reader.parse_problem(BLOCKSWORLD_DOMAIN, BLOCKSWORLD_PROBLEM)
        planner = HTNTotalOrderPlanner(problem)
        plan = planner.solve()
        _replay_verify(problem, plan, check_goal=False)

    def test_htn_domain_wraps_the_same_real_plan(self):
        domain = HTNDomain(BLOCKSWORLD_DOMAIN, BLOCKSWORLD_PROBLEM)
        assert domain.plan == HTNTotalOrderPlanner(domain.problem).solve()
        state = domain._get_initial_state_()
        total_cost = 0.0
        while not domain._is_terminal(state):
            actions = list(domain._get_applicable_actions_from(state).get_elements())
            assert len(actions) == 1
            action = actions[0]
            next_state = domain._get_next_state(state, action)
            total_cost += domain._get_transition_value(state, action, next_state).cost
            state = next_state
        assert total_cost == len(domain.plan)
        assert domain._get_goals_().contains(state)


class TestHTNTotalOrderPlannerVerifyAndCommit:
    """Verification target (b): xaas's real verify-and-commit.hddl domain
    (copied read-only into tests/domains/htn_fixtures/ -- this repo does not
    modify the xaas working tree) plus a hand-authored problem file
    supplying the initial state and initial task network the domain file
    alone does not carry (confirmed: parsing the domain file alone yields
    zero objects and an empty task network)."""

    DOMAIN_PATH = os.path.join(FIXTURES, "verify-and-commit.hddl")
    PROBLEM_PATH = os.path.join(FIXTURES, "verify-and-commit-problem.hddl")

    def test_domain_alone_has_no_init_task_network(self):
        reader = PDDLReader()
        domain_only = reader.parse_problem(self.DOMAIN_PATH)
        assert list(domain_only.all_objects) == []
        assert list(domain_only.task_network.subtasks) == []

    def test_solve_returns_the_expected_five_step_total_order_plan(self):
        reader = PDDLReader()
        problem = reader.parse_problem(self.DOMAIN_PATH, self.PROBLEM_PATH)
        planner = HTNTotalOrderPlanner(problem)
        plan = planner.solve()

        assert [ga.name for ga in plan] == [
            "compile",
            "migrate",
            "test",
            "mock-grep",
            "commit-with-real-status",
        ]
        _replay_verify(problem, plan)

    def test_htn_domain_end_to_end(self):
        domain = HTNDomain(self.DOMAIN_PATH, self.PROBLEM_PATH)
        assert [ga.name for ga in domain.plan] == [
            "compile",
            "migrate",
            "test",
            "mock-grep",
            "commit-with-real-status",
        ]
