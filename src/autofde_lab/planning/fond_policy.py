"""Finite-state checks for candidate FOND policies.

This module is deliberately authority-free. It checks graph properties of a
candidate policy produced by a planner; it does not authorize or execute any
action. Strong and strong-cyclic follow the standard FOND distinction: strong
policies reach a goal for every outcome without cycles; strong-cyclic policies
may cycle but every reachable state retains a path to a goal under fairness.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Mapping

StateId = str
ActionId = str


class PolicySemantics(str, Enum):
    STRONG = "strong"
    STRONG_CYCLIC = "strong_cyclic"


@dataclass(frozen=True)
class FONDProblem:
    """A finite, fully observable nondeterministic transition relation."""

    initial_state: StateId
    goal_states: frozenset[StateId]
    transitions: Mapping[tuple[StateId, ActionId], frozenset[StateId]]

    def outcomes(self, state: StateId, action: ActionId) -> frozenset[StateId]:
        return self.transitions.get((state, action), frozenset())


@dataclass(frozen=True)
class CandidatePolicy:
    """Planner-produced state-to-action mapping. Carries no DO authority."""

    actions: Mapping[StateId, ActionId]


@dataclass(frozen=True)
class PolicyCheck:
    semantics: PolicySemantics
    valid: bool
    reachable_states: frozenset[StateId]
    missing_policy_states: frozenset[StateId]
    dead_end_states: frozenset[StateId]
    non_goal_cycle_states: frozenset[StateId]
    cannot_reach_goal_states: frozenset[StateId]
    claim_ceiling: str = "candidate_policy_only"


def _reachable(
    problem: FONDProblem, policy: CandidatePolicy
) -> tuple[set[StateId], set[StateId], set[StateId]]:
    reachable: set[StateId] = set()
    missing: set[StateId] = set()
    dead_ends: set[StateId] = set()
    queue: deque[StateId] = deque([problem.initial_state])

    while queue:
        state = queue.popleft()
        if state in reachable:
            continue
        reachable.add(state)
        if state in problem.goal_states:
            continue

        action = policy.actions.get(state)
        if action is None:
            missing.add(state)
            continue
        outcomes = problem.outcomes(state, action)
        if not outcomes:
            dead_ends.add(state)
            continue
        queue.extend(outcomes - reachable)

    return reachable, missing, dead_ends


def _non_goal_cycle_states(
    problem: FONDProblem, policy: CandidatePolicy, reachable: set[StateId]
) -> set[StateId]:
    graph: dict[StateId, set[StateId]] = {}
    for state in reachable - problem.goal_states:
        action = policy.actions.get(state)
        if action is None:
            graph[state] = set()
            continue
        graph[state] = set(problem.outcomes(state, action)) & (
            reachable - problem.goal_states
        )

    index = 0
    stack: list[StateId] = []
    on_stack: set[StateId] = set()
    indices: dict[StateId, int] = {}
    lowlink: dict[StateId, int] = {}
    cyclic: set[StateId] = set()

    def visit(state: StateId) -> None:
        nonlocal index
        indices[state] = index
        lowlink[state] = index
        index += 1
        stack.append(state)
        on_stack.add(state)

        for nxt in graph.get(state, set()):
            if nxt not in indices:
                visit(nxt)
                lowlink[state] = min(lowlink[state], lowlink[nxt])
            elif nxt in on_stack:
                lowlink[state] = min(lowlink[state], indices[nxt])

        if lowlink[state] != indices[state]:
            return

        component: set[StateId] = set()
        while stack:
            member = stack.pop()
            on_stack.remove(member)
            component.add(member)
            if member == state:
                break

        if len(component) > 1:
            cyclic.update(component)
        elif state in graph.get(state, set()):
            cyclic.add(state)

    for state in graph:
        if state not in indices:
            visit(state)
    return cyclic


def _cannot_reach_goal(
    problem: FONDProblem, policy: CandidatePolicy, reachable: set[StateId]
) -> set[StateId]:
    reverse: dict[StateId, set[StateId]] = {}
    for state in reachable - problem.goal_states:
        action = policy.actions.get(state)
        if action is None:
            continue
        for nxt in problem.outcomes(state, action):
            if nxt in reachable:
                reverse.setdefault(nxt, set()).add(state)

    can_reach = set(problem.goal_states & reachable)
    queue: deque[StateId] = deque(can_reach)
    while queue:
        state = queue.popleft()
        for parent in reverse.get(state, set()):
            if parent not in can_reach:
                can_reach.add(parent)
                queue.append(parent)
    return reachable - can_reach


def check_candidate_policy(
    problem: FONDProblem,
    policy: CandidatePolicy,
    *,
    semantics: PolicySemantics,
) -> PolicyCheck:
    """Check a finite candidate policy without promoting its standing."""

    reachable, missing, dead_ends = _reachable(problem, policy)
    cycles = _non_goal_cycle_states(problem, policy, reachable)
    cannot_reach_goal = _cannot_reach_goal(problem, policy, reachable)

    if semantics is PolicySemantics.STRONG:
        valid = not missing and not dead_ends and not cycles and not cannot_reach_goal
    else:
        valid = not missing and not dead_ends and not cannot_reach_goal

    return PolicyCheck(
        semantics=semantics,
        valid=valid,
        reachable_states=frozenset(reachable),
        missing_policy_states=frozenset(missing),
        dead_end_states=frozenset(dead_ends),
        non_goal_cycle_states=frozenset(cycles),
        cannot_reach_goal_states=frozenset(cannot_reach_goal),
    )
