# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for classical/search solver entries that were
registered in ``pyproject.toml`` but had no real, solve()-exercising test
anywhere in ``tests/domains`` or ``tests/solvers`` as of this session.

Confirmed genuinely untested by grepping ``tests/`` for each entry point
name before writing this file (see the task transcript / commit message):

- ``EHC``        (autofde_lab.hub.solver.ehc:EHC)          -- zero matches
- ``IDAstar``     (autofde_lab.hub.solver.ldfs:IDAstar)      -- zero matches
  for the IDAstar class specifically; ``tests/solvers/cpp/test_ldfs.py``
  only exercises the sibling ``LDFS`` class in the same module.
- ``MCTS``       (autofde_lab.hub.solver.mcts:MCTS, plain)  -- zero matches;
  only the ``UCT`` entry point (same module, different nested class) is
  exercised elsewhere.
- ``SimpleGreedy`` (autofde_lab.hub.solver.simple_greedy:SimpleGreedy) --
  zero matches anywhere in tests/.

Follows the EXACT domain/fixture pattern of
``tests/solvers/cpp/test_cpp_solvers.py`` (GridDomain built on
``DeterministicPlanningDomain``) and the ``get_plan`` helper /
``load_registered_solver`` usage of ``tests/solvers/python/test_python_solvers.py``.
No test doubles: every solver here constructs the real registered solver
class via ``load_registered_solver`` and calls the real ``solve()`` against
a real, concrete grid domain instance, then asserts on the real returned
plan/cost/policy -- not a mock, not an import-only smoke test.
"""

from __future__ import annotations

from enum import Enum
from math import sqrt
from typing import NamedTuple, Optional

import pytest

from autofde_lab import DeterministicPlanningDomain, ImplicitSpace, Space, Value
from autofde_lab.builders.domain import UnrestrictedActions
from autofde_lab.hub.space.gym import EnumSpace, MultiDiscreteSpace
from autofde_lab.utils import load_registered_solver


# Must be defined at module scope so parallel/duplicated domains can pickle it.
class State(NamedTuple):
    x: int
    y: int
    s: int  # step counter, keeps the domain cycle-free


class Action(Enum):
    up = 0
    down = 1
    left = 2
    right = 3


class D(DeterministicPlanningDomain, UnrestrictedActions):
    T_state = State
    T_observation = T_state
    T_event = Action
    T_value = float
    T_predicate = bool
    T_info = None


class GridDomain(D):
    """A small deterministic grid-world with a corner goal.

    Identical in shape to the GridDomain used by
    tests/solvers/cpp/test_cpp_solvers.py and
    tests/solvers/python/test_python_solvers.py -- deliberately reused
    rather than reinvented, per this repo's "nearest working example
    first" convention.
    """

    def __init__(self, num_cols=4, num_rows=4):
        self.num_cols = num_cols
        self.num_rows = num_rows

    def _get_next_state(self, memory, action):
        if action == Action.left:
            next_state = State(max(memory.x - 1, 0), memory.y, memory.s + 1)
        if action == Action.right:
            next_state = State(
                min(memory.x + 1, self.num_cols - 1), memory.y, memory.s + 1
            )
        if action == Action.up:
            next_state = State(memory.x, max(memory.y - 1, 0), memory.s + 1)
        if action == Action.down:
            next_state = State(
                memory.x, min(memory.y + 1, self.num_rows - 1), memory.s + 1
            )
        return next_state

    def _get_transition_value(self, memory, action, next_state=None):
        if next_state.x == memory.x and next_state.y == memory.y:
            cost = 2  # penalty for hitting a wall
        else:
            cost = abs(next_state.x - memory.x) + abs(next_state.y - memory.y)
        return Value(cost=cost)

    def _is_terminal(self, state):
        return self._is_goal(state) or state.s >= 50

    def _get_action_space_(self):
        return EnumSpace(Action)

    def _get_goals_(self):
        return ImplicitSpace(
            lambda state: state.x == (self.num_cols - 1)
            and state.y == (self.num_rows - 1)
        )

    def _get_initial_state_(self):
        return State(x=0, y=0, s=0)

    def _get_observation_space_(self):
        return MultiDiscreteSpace(
            nvec=[self.num_cols, self.num_rows, 100], element_class=State
        )


def manhattan_heuristic(d, s):
    return Value(cost=sqrt((d.num_cols - 1 - s.x) ** 2 + (d.num_rows - 1 - s.y) ** 2))


def get_plan(domain, solver):
    plan = []
    cost = 0
    observation = domain.reset()
    nb_steps = 0
    while (not domain.is_goal(observation)) and nb_steps < 20:
        plan.append(solver.sample_action(observation, domain=domain))
        outcome = domain.step(plan[-1])
        cost += outcome.value.cost
        observation = outcome.observation
        nb_steps += 1
    return plan, cost


# The optimal cost from (0,0) to (3,3) on a 4x4 Manhattan grid is 6.
OPTIMAL_COST = 6
OPTIMAL_LEN = 6


class TestEHCUntested:
    """EHC (Enforced Hill Climbing) -- entry point 'EHC', never tested."""

    def test_check_domain(self):
        EHC = load_registered_solver("EHC")
        dom = GridDomain()
        assert EHC.check_domain(dom)

    def test_solve_reaches_goal(self):
        EHC = load_registered_solver("EHC")
        dom = GridDomain()
        with EHC(
            domain_factory=GridDomain,
            heuristic=manhattan_heuristic,
            verbose=False,
        ) as slv:
            slv.solve()
            plan, cost = get_plan(dom, slv)

        assert len(plan) > 0
        # State-based assertion on the real outcome of following the policy:
        final_obs = dom.reset()
        for a in plan:
            final_obs = dom.step(a).observation
        assert dom.is_goal(final_obs)
        assert cost == OPTIMAL_COST


class TestIDAstarUntested:
    """IDAstar -- entry point 'IDAstar', sibling of the tested LDFS class
    in the same module but never itself exercised."""

    def test_check_domain(self):
        IDAstar = load_registered_solver("IDAstar")
        dom = GridDomain()
        assert IDAstar.check_domain(dom)

    def test_solve_finds_optimal_plan(self):
        IDAstar = load_registered_solver("IDAstar")
        dom = GridDomain()
        with IDAstar(
            domain_factory=GridDomain,
            heuristic=manhattan_heuristic,
            verbose=False,
        ) as slv:
            slv.solve()
            plan, cost = get_plan(dom, slv)

            # get_plan() is IDAstar-specific API (greedy policy trace);
            # assert on its real return value too, not just the
            # sample_action rollout above. Must be called before the
            # solver's `with` block exits -- the C++ solver handle is
            # released on __exit__.
            greedy_plan = slv.get_plan()

        assert len(plan) == OPTIMAL_LEN
        assert cost == OPTIMAL_COST
        assert len(greedy_plan) == OPTIMAL_LEN


class TestMCTSPlainUntested:
    """MCTS (plain, not the UCT specialization) -- entry point 'MCTS',
    never itself exercised; only the sibling 'UCT' nested class in the
    same module has coverage."""

    def test_check_domain(self):
        MCTS = load_registered_solver("MCTS")
        dom = GridDomain()
        assert MCTS.check_domain(dom)

    def test_solve_produces_a_defined_policy(self):
        MCTS = load_registered_solver("MCTS")
        dom = GridDomain()
        with MCTS(
            domain_factory=GridDomain,
            time_budget=2000,
            rollout_budget=200,
            max_depth=10,
            continuous_planning=True,
            verbose=False,
        ) as slv:
            slv.solve()
            plan, cost = get_plan(dom, slv)

        # MCTS is not guaranteed optimal on a tight budget; assert on real
        # observed final state instead of a fixed optimal cost.
        assert len(plan) > 0
        final_obs = dom.reset()
        for a in plan:
            final_obs = dom.step(a).observation
        assert dom.is_goal(final_obs)
        assert cost >= OPTIMAL_COST  # MCTS cannot beat the true optimum


class TestSimpleGreedyUntested:
    """SimpleGreedy -- entry point 'SimpleGreedy', never tested.

    Uses a 1-row corridor variant of GridDomain rather than the full 4x4
    grid: on the 4x4 grid, SimpleGreedy's one-step lookahead has genuine
    reward ties between "up" and "down" once y > 0 (both reduce Manhattan
    distance by the same amount), and Python's ``max()`` breaks ties by
    first-occurrence in ``EnumSpace(Action)`` enumeration order
    (up, down, left, right) -- which here produces a real up/down
    oscillation forever. That is honest, observed SimpleGreedy behavior on
    a tie-heavy domain, not a test bug, but it makes the 2-D grid a poor
    fixture for asserting goal-reaching greedy behavior. A corridor
    (num_rows=1) removes the tie: "right" is always the unique
    distance-reducing action, so the real solver converges.
    """

    class CorridorDomain(GridDomain):
        """Corridor with an asymmetric cost that strictly penalizes
        backward movement, so 'right' is always the unique
        cost-minimizing greedy choice (no left/right tie)."""

        def __init__(self):
            super().__init__(num_cols=4, num_rows=1)

        def _get_transition_value(self, memory, action, next_state=None):
            value = super()._get_transition_value(memory, action, next_state)
            if action == Action.left:
                return Value(cost=value.cost + 10)
            return value

    def corridor_factory(self):
        return TestSimpleGreedyUntested.CorridorDomain()

    def test_check_domain(self):
        SimpleGreedy = load_registered_solver("SimpleGreedy")
        dom = self.corridor_factory()
        assert SimpleGreedy.check_domain(dom)

    def test_solve_and_greedy_rollout(self):
        SimpleGreedy = load_registered_solver("SimpleGreedy")
        dom = self.corridor_factory()
        with SimpleGreedy(domain_factory=self.corridor_factory) as slv:
            slv.solve()
            assert slv.is_policy_defined_for(dom.reset())
            plan, cost = get_plan(dom, slv)

        # On the corridor, greedy's one-step lookahead always picks the
        # unique cost-minimizing "right" move, so it reaches the goal in
        # the real optimal number of steps (3 moves, cost 3).
        assert len(plan) == 3
        assert cost == 3
        final_obs = dom.reset()
        for a in plan:
            final_obs = dom.step(a).observation
        assert dom.is_goal(final_obs)
