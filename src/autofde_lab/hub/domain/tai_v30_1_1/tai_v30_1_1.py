# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""scikit-decide adapter for the TAI v30.1.1 case-study transition model."""

from __future__ import annotations

import random
from collections import deque
from collections.abc import Iterable, Sequence
from typing import Optional, TypeVar

from autofde_lab import (
    DeterministicPlanningDomain,
    EnumerableSpace,
    SamplableSpace,
    Space,
    Value,
)

from .model import (
    INITIAL_STATE,
    POSITIVE_PLAN,
    TaiAction,
    TaiState,
    applicable_actions,
    is_terminal,
    replay_plan,
    transition,
)

_SpaceT = TypeVar("_SpaceT")


class _TupleSpace(EnumerableSpace[_SpaceT], SamplableSpace[_SpaceT]):
    """Dependency-free finite space backed by an immutable tuple."""

    def __init__(self, elements: Iterable[_SpaceT]):
        self._elements = tuple(elements)

    def get_elements(self) -> Sequence[_SpaceT]:
        return self._elements

    def __getitem__(self, index):
        return self._elements[index]

    def __len__(self) -> int:
        return len(self._elements)

    def sample(self) -> _SpaceT:
        return random.choice(self._elements)


class D(DeterministicPlanningDomain):
    T_state = TaiState
    T_observation = T_state
    T_event = TaiAction
    T_value = float
    T_predicate = bool
    T_info = None


class TAIForwardDeploymentDomain(D):
    """Deterministic planner for manufacturing and activating the TAI case study.

    The domain models planning intents only. In particular, ``brce_actuate`` and
    ``brce_replay`` do not perform external side effects; a production adapter
    must submit the selected intent to BRCE and bind the returned receipt.
    """

    def __init__(self, *, local_conformance: bool = True):
        self.local_conformance = local_conformance
        self._states = self._enumerate_reachable_states()
        self._goal = replay_plan(POSITIVE_PLAN)

    def _get_next_state(
        self,
        memory: D.T_memory[D.T_state],
        action: D.T_agent[D.T_concurrency[D.T_event]],
    ) -> D.T_state:
        return transition(memory, action, local_conformance=self.local_conformance)

    def _get_transition_value(
        self,
        memory: D.T_memory[D.T_state],
        action: D.T_agent[D.T_concurrency[D.T_event]],
        next_state: Optional[D.T_state] = None,
    ) -> D.T_agent[Value[D.T_value]]:
        return Value(cost=1.0)

    def _is_terminal(self, state: D.T_state) -> D.T_agent[D.T_predicate]:
        return is_terminal(state)

    def _get_action_space_(self) -> D.T_agent[Space[D.T_event]]:
        return _TupleSpace(TaiAction)

    def _get_applicable_actions_from(
        self, memory: D.T_memory[D.T_state]
    ) -> D.T_agent[Space[D.T_event]]:
        return _TupleSpace(
            applicable_actions(memory, local_conformance=self.local_conformance)
        )

    def _get_goals_(self) -> D.T_agent[Space[D.T_observation]]:
        return _TupleSpace((self._goal,))

    def _get_initial_state_(self) -> D.T_state:
        return INITIAL_STATE

    def _get_observation_space_(self) -> D.T_agent[Space[D.T_observation]]:
        return _TupleSpace(self._states)

    def _enumerate_reachable_states(self) -> tuple[TaiState, ...]:
        seen = {INITIAL_STATE}
        pending = deque([INITIAL_STATE])
        while pending:
            state = pending.popleft()
            for action in applicable_actions(
                state, local_conformance=self.local_conformance
            ):
                next_state = transition(
                    state,
                    action,
                    local_conformance=self.local_conformance,
                )
                if next_state not in seen:
                    seen.add(next_state)
                    pending.append(next_state)
        return tuple(sorted(seen, key=tuple))
