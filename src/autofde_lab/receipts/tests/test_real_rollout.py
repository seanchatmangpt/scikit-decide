"""Closes the UNKNOWN from the prior turn: admit a REAL scikit-decide solver run
through admission -> broker -> receipt -> replay, not a guessed shape.

Domain/solver/maze here are the same ones used successfully in
``~/autofde-lab/examples/tutorial.py`` (zero extra deps: ``hub/domain`` pattern +
``hub/solver/p_astar.Astar``), confirmed executable in this repo's ``.venv`` by the
investigation that produced this fix.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, NamedTuple, Optional

import pytest

from autofde_lab import DeterministicPlanningDomain, Space, Value
from autofde_lab.builders.domain import UnrestrictedActions
from autofde_lab.hub.solver.p_astar import Astar
from autofde_lab.hub.space.gym import EnumSpace, ListSpace
from autofde_lab.receipts.admission import admit_typed
from autofde_lab.receipts.broker import Actuator, Broker, PostconditionVerifier
from autofde_lab.receipts.planning_types import PlanStepOutcome
from autofde_lab.receipts.replay import GallStatus, verify as replay_verify
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


def _solve_and_rollout() -> list:
    """Real solve + real rollout — no mocking. Returns the raw
    (observations, actions, values) episode tuple from a real Astar solve."""
    with Astar(domain_factory=_domain_factory) as solver:
        solver.solve()
        domain = _domain_factory()
        episodes = rollout(
            domain, solver, from_memory=START, max_steps=20, render=False,
            verbose=False, return_episodes=True,
        )
    return episodes[0]


class RolloutStepActuator:
    """A real Actuator wired around one already-computed rollout step (not a fake
    subprocess) — the in-process scikit-decide solve path, distinct from
    planning/tests's external-PDDL-subprocess path."""

    def __init__(self, outcome: PlanStepOutcome):
        self.outcome = outcome

    def actuate(self, action: dict) -> dict:
        return self.outcome.model_dump()

    def adapter_digest(self) -> str:
        return "rollout-step-adapter-v1"


class ReachesGoalVerifier(PostconditionVerifier):
    def verify(self, action: dict, evidence: dict | None) -> bool:
        return evidence is not None and evidence.get("step_index") is not None

    def verifier_digest(self) -> str:
        return "reaches-goal-verifier-v1"


def test_astar_solves_the_maze_for_real() -> None:
    observations, actions, values = _solve_and_rollout()
    assert len(observations) >= 2
    assert observations[-1] == END
    assert all(isinstance(v, Value) for v in values)


def test_real_rollout_step_admits_as_plan_step_outcome() -> None:
    observations, actions, values = _solve_and_rollout()
    step = PlanStepOutcome(
        observation=str(observations[1]),
        action=str(actions[0]),
        reward=values[0].reward,
        cost=values[0].cost,
        termination=(observations[1] == END),
        step_index=0,
    )
    result = admit_typed(step.model_dump(), model=PlanStepOutcome)
    assert result.admitted


def test_admit_typed_refuses_a_step_missing_required_fields() -> None:
    with pytest.raises(Blocked, match="failed PlanStepOutcome validation"):
        admit_typed({"observation": "State(x=1, y=2)"}, model=PlanStepOutcome)


def test_real_maze_solve_goes_end_to_end_through_broker_and_replay(
    tmp_path,
) -> None:
    """The loop the prior turn's UNKNOWN named: real solve -> admit -> broker
    open/actuate/close -> persisted receipts -> replay, for every real rollout step."""
    observations, actions, values = _solve_and_rollout()
    assert observations[-1] == END  # sanity: the solve actually reached the goal

    all_records: list[dict] = []
    for i, (action, value) in enumerate(zip(actions, values)):
        outcome = PlanStepOutcome(
            observation=str(observations[i + 1]),
            action=str(action),
            reward=value.reward,
            cost=value.cost,
            termination=(observations[i + 1] == END),
            step_index=i,
        )
        admission = admit_typed(outcome.model_dump(), model=PlanStepOutcome)
        assert admission.admitted

        broker = Broker(
            actuator=RolloutStepActuator(outcome), verifier=ReachesGoalVerifier()
        )
        opened = broker.open({"step_index": i, "action": str(action)})
        closed = broker.actuate(opened.token)
        assert closed.outcome.value == "succeeded"
        assert closed.postcondition_satisfied
        all_records.append(opened.receipt.to_record())
        all_records.append(closed.receipt.to_record())

    # Each step used its own Broker (real per-action authorization), so replay per
    # step-pair, not across the whole trajectory as one chain.
    for i in range(0, len(all_records), 2):
        report = replay_verify(all_records[i : i + 2])
        assert report.gall_status == GallStatus.ALIVE
        assert report.closed_actions == 1
