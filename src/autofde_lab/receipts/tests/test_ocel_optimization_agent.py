"""Chicago-style test: an agent uses real OCEL data for optimization/performance
decisions between candidate plan runs.

Two REAL candidate trajectories over the same maze (reused from
``test_real_rollout.py``), both produced by actually stepping the domain — no
mocking, no fabricated numbers:

  - "astar-optimal": Astar's real solve (4 steps, cost 4 — an efficient path).
  - "naive-worse": a real, hand-driven action sequence that bumps into a wall once
    before recovering (5 steps, cost 6 — reaches the same goal, but worse).

Both are converted to real ``OcelLog``s via ``ocel_adapter.trajectory_to_ocel_log``,
and ``optimization_agent.PlanPerformanceAgent`` — the deterministic decision core an
LLM-driven agent's tool-call would invoke — picks between them using only the OCEL
event data. Assertions are state-based on the real computed scores/decision, not on
whether any particular method was called (no ``unittest.mock`` anywhere in this
package, verified by grep after every change this session).
"""

from __future__ import annotations

from enum import Enum
from typing import Any, NamedTuple, Optional

import pytest

from autofde_lab import DeterministicPlanningDomain, Space, Value
from autofde_lab.builders.domain import UnrestrictedActions
from autofde_lab.hub.solver.p_astar import Astar
from autofde_lab.hub.space.gym import EnumSpace, ListSpace
from autofde_lab.receipts.ocel_adapter import trajectory_to_ocel_log
from autofde_lab.receipts.optimization_agent import PlanPerformanceAgent
from autofde_lab.receipts.planning_types import PlanStepOutcome
from autofde_lab.standing import Blocked
from autofde_lab.utils import rollout


class State(NamedTuple):
    x: int
    y: int


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


MAZE_STR = """
.....
. . .
. . .
.   .
.....
""".strip()


class MazeDomain(D):
    def __init__(self, start: State, end: State):
        self.start = start
        self.end = end
        self.maze = MAZE_STR.splitlines()

    def _get_next_state(self, memory: D.T_state, action: D.T_event) -> D.T_state:
        next_x, next_y = memory.x, memory.y
        if action == Action.up:
            next_x -= 1
        if action == Action.down:
            next_x += 1
        if action == Action.left:
            next_y -= 1
        if action == Action.right:
            next_y += 1
        if not (0 <= next_x < len(self.maze) and 0 <= next_y < len(self.maze[0])):
            return memory
        return State(next_x, next_y) if self.maze[next_x][next_y] != "." else memory

    def _get_transition_value(
        self,
        memory: D.T_state,
        action: D.T_event,
        next_state: Optional[D.T_state] = None,
    ) -> Value[D.T_value]:
        return Value(cost=1 if next_state != memory else 2)

    def _get_initial_state_(self) -> D.T_state:
        return self.start

    def _get_goals_(self) -> Space[D.T_observation]:
        return ListSpace([self.end])

    def _is_terminal(self, state: D.T_state) -> Any:
        return self._is_goal(state)

    def _get_action_space_(self) -> Space[D.T_event]:
        return EnumSpace(Action)

    def _get_observation_space_(self) -> Space[D.T_observation]:
        pass


START = State(1, 1)
END = State(3, 3)


def _domain_factory() -> MazeDomain:
    return MazeDomain(START, END)


def _steps_from_episode(observations, actions, values) -> list[PlanStepOutcome]:
    return [
        PlanStepOutcome(
            observation=str(observations[i + 1]),
            action=str(action),
            reward=value.reward,
            cost=value.cost,
            termination=(observations[i + 1] == END),
            step_index=i,
        )
        for i, (action, value) in enumerate(zip(actions, values))
    ]


def _astar_optimal_steps() -> list[PlanStepOutcome]:
    """The real, efficient candidate: Astar's actual solve."""
    with Astar(domain_factory=_domain_factory) as solver:
        solver.solve()
        domain = _domain_factory()
        observations, actions, values = rollout(
            domain, solver, from_memory=START, max_steps=20, render=False,
            verbose=False, return_episodes=True,
        )[0]
    return _steps_from_episode(observations, actions, values)


def _naive_worse_steps() -> list[PlanStepOutcome]:
    """The real, worse candidate: a hand-driven action sequence that bumps into a
    wall once (right from (1,1) hits a wall, cost 2, stays put) before recovering
    via the same route Astar takes — genuinely stepped through the real domain, not
    fabricated numbers."""
    domain = _domain_factory()
    domain.reset()
    action_sequence = [Action.right, Action.down, Action.down, Action.right, Action.right]
    observations = [START]
    values = []
    for action in action_sequence:
        outcome = domain.step(action)
        observations.append(outcome.observation)
        values.append(outcome.value)
    return _steps_from_episode(observations, action_sequence, values)


def test_astar_candidate_is_real_and_cheaper_than_naive_candidate() -> None:
    astar_steps = _astar_optimal_steps()
    naive_steps = _naive_worse_steps()
    astar_cost = sum(s.cost for s in astar_steps)
    naive_cost = sum(s.cost for s in naive_steps)
    # Sanity: both real trajectories actually reach the goal.
    assert astar_steps[-1].termination
    assert naive_steps[-1].termination
    assert astar_cost < naive_cost
    assert astar_cost == 4  # 4 clean moves
    assert naive_cost == 6  # 1 wall bump (cost 2) + 4 clean moves


def test_agent_selects_the_cheaper_real_candidate_via_ocel() -> None:
    astar_steps = _astar_optimal_steps()
    naive_steps = _naive_worse_steps()

    candidates = {
        "astar-optimal": trajectory_to_ocel_log(astar_steps, run_id="astar-optimal"),
        "naive-worse": trajectory_to_ocel_log(naive_steps, run_id="naive-worse"),
    }

    agent = PlanPerformanceAgent()
    decision = agent.select_best(candidates)

    assert decision.winner_run_id == "astar-optimal"
    assert "astar-optimal" in decision.reason
    by_id = {s.run_id: s for s in decision.scores}
    assert by_id["astar-optimal"].total_cost == 4
    assert by_id["astar-optimal"].step_count == 4
    assert by_id["astar-optimal"].reached_goal
    assert by_id["naive-worse"].total_cost == 6
    assert by_id["naive-worse"].step_count == 5
    assert by_id["naive-worse"].reached_goal


def test_agent_refuses_to_optimize_over_a_run_that_never_reaches_the_goal() -> None:
    stuck_step = PlanStepOutcome(
        observation=str(State(1, 1)),
        action=str(Action.up),  # bumps into the outer wall, never reaches END
        reward=-2.0,
        cost=2.0,
        termination=False,
        step_index=0,
    )
    candidates = {
        "stuck": trajectory_to_ocel_log([stuck_step], run_id="stuck"),
    }
    with pytest.raises(Blocked, match="no candidate reached the goal"):
        PlanPerformanceAgent().select_best(candidates)


def test_agent_refuses_an_empty_candidate_set_with_a_named_reason() -> None:
    with pytest.raises(Blocked, match="no candidate OCEL logs"):
        PlanPerformanceAgent().select_best({})
