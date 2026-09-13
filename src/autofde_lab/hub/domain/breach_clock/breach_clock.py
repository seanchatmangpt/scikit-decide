# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Breach Clock — a SIMULATED incident-response planning domain.

Everything here is simulation. The domain touches no cloud provider, no
identity system, no workload, and no notification channel; it imports nothing
outside ``autofde_lab``. ``revoke_sessions`` moves an enum in a
:class:`State` tuple and does nothing else. It computes a **candidate** plan —
it does not actuate, admit, broker, or issue receipts, and no action name in
this file should be read as evidence that the named operation is reachable from
this repository.

Two structural properties are deliberate, because a domain that lacked them
would make the POWL 2.0 operators it is meant to exercise vacuous:

**Real concurrency.** ``triage``, ``collect_evidence`` and ``compute_scope``
share **no** precondition with each other. All three are applicable in the
initial state and none enables another, so a partial order over them expresses
genuine unorderedness rather than a serialization the domain forced anyway.

**A real 3-way exclusive choice.** ``revoke_sessions``, ``isolate_workload`` and
``preserve_evidence_only`` are each applicable exactly when containment has not
been decided, and each one closes the other two out. The exclusivity is in the
precondition (``containment is Containment.NONE``), not in a solver heuristic.

The divergence hook
-------------------
:meth:`BreachClockDomain.observe_divergence` is the observation that forces a
replan: population ``B`` turns out to be affected after the scope was already
computed. It widens the affected set and knocks scope back to ``PARTIAL``, so a
plan that had already drafted a notification for population ``A`` alone no
longer reaches the goal. The hook is a pure function of a state — it is not
triggered by the solver and never fires on its own.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, FrozenSet, NamedTuple, Optional

from autofde_lab import DeterministicPlanningDomain, ImplicitSpace, Space, Value
from autofde_lab.builders.domain import Renderable
from autofde_lab.hub.space.gym import ListSpace


class Scope(Enum):
    """How well the incident's blast radius is understood."""

    UNKNOWN = 0
    PARTIAL = 1
    KNOWN = 2


class Containment(Enum):
    """Which containment posture was chosen. ``NONE`` means undecided."""

    NONE = 0
    SESSIONS_REVOKED = 1
    WORKLOAD_ISOLATED = 2
    EVIDENCE_ONLY = 3


class Notification(Enum):
    """How far regulator/subject notification has progressed."""

    NONE = 0
    DRAFTED = 1
    DELIVERED = 2


class Action(Enum):
    """The eight simulated incident-response steps."""

    triage = 0
    collect_evidence = 1
    compute_scope = 2
    revoke_sessions = 3
    isolate_workload = 4
    preserve_evidence_only = 5
    draft_notification = 6
    deliver_notification = 7


#: Containment postures, and the action that selects each. Exactly one may be
#: taken — the exclusivity lives in the precondition, see the module docstring.
CONTAINMENT_CHOICE: dict[Action, Containment] = {
    Action.revoke_sessions: Containment.SESSIONS_REVOKED,
    Action.isolate_workload: Containment.WORKLOAD_ISOLATED,
    Action.preserve_evidence_only: Containment.EVIDENCE_ONLY,
}

#: The three steps with no precondition on each other.
INDEPENDENT_ACTIONS: tuple[Action, ...] = (
    Action.triage,
    Action.collect_evidence,
    Action.compute_scope,
)

DEFAULT_INITIAL_POPULATIONS: FrozenSet[str] = frozenset({"A"})

#: The population the divergence hook reveals.
DIVERGENCE_POPULATION: str = "B"


class State(NamedTuple):
    """Incident state. Hashable — frozensets and enums only."""

    scope: Scope
    populations: FrozenSet[str]
    containment: Containment
    triaged: bool
    evidence: bool
    notification: Notification
    #: Populations the drafted notification covers. Empty until drafted.
    notified_populations: FrozenSet[str] = frozenset()


class D(DeterministicPlanningDomain, Renderable):
    T_state = State
    T_observation = T_state
    T_event = Action
    T_value = float
    T_predicate = bool
    T_info = None


class BreachClockDomain(D):
    """Simulated incident response under a notification deadline.

    The goal is a delivered notification covering every affected population.
    Reaching it requires the three independent facts (triage, evidence, scope),
    one of three mutually exclusive containment postures, then a draft and a
    delivery.
    """

    def __init__(
        self,
        initial_populations: FrozenSet[str] = DEFAULT_INITIAL_POPULATIONS,
        step_cost: float = 1.0,
    ) -> None:
        self._initial_populations = frozenset(initial_populations)
        self._step_cost = float(step_cost)

    # ── transitions ─────────────────────────────────────────────────────────

    def _get_next_state(
        self,
        memory: D.T_memory[D.T_state],
        action: D.T_agent[D.T_concurrency[D.T_event]],
    ) -> D.T_state:
        s = memory
        if action is Action.triage:
            return s._replace(triaged=True)
        if action is Action.collect_evidence:
            return s._replace(evidence=True)
        if action is Action.compute_scope:
            return s._replace(scope=Scope.KNOWN)
        if action in CONTAINMENT_CHOICE:
            return s._replace(containment=CONTAINMENT_CHOICE[action])
        if action is Action.draft_notification:
            return s._replace(
                notification=Notification.DRAFTED,
                notified_populations=s.populations,
            )
        if action is Action.deliver_notification:
            return s._replace(notification=Notification.DELIVERED)
        # An action outside the enum is never applicable; leave the domain
        # merely blocked rather than raising.
        return s

    def _get_transition_value(
        self,
        memory: D.T_memory[D.T_state],
        action: D.T_agent[D.T_concurrency[D.T_event]],
        next_state: Optional[D.T_state] = None,
    ) -> D.T_agent[Value[D.T_value]]:
        return Value(cost=self._step_cost)

    def _is_terminal(self, state: D.T_state) -> D.T_agent[D.T_predicate]:
        return self._is_goal(state)

    # ── applicability ───────────────────────────────────────────────────────

    def applicable(self, state: State, action: Action) -> bool:
        """Whether ``action`` is applicable in ``state``.

        Public because the independence and exclusivity properties above are
        claims about *this predicate*, and a test asserting them should read the
        same function the solver does rather than a restatement of it.
        """
        if action is Action.triage:
            return not state.triaged
        if action is Action.collect_evidence:
            return not state.evidence
        if action is Action.compute_scope:
            return state.scope is not Scope.KNOWN
        if action in CONTAINMENT_CHOICE:
            # the exclusive 3-way choice: undecided, and triage has landed
            return state.triaged and state.containment is Containment.NONE
        if action is Action.draft_notification:
            return (
                state.scope is Scope.KNOWN
                and state.evidence
                and state.containment is not Containment.NONE
                and state.notified_populations != state.populations
            )
        if action is Action.deliver_notification:
            return (
                state.notification is Notification.DRAFTED
                and state.notified_populations == state.populations
            )
        return False

    def _get_applicable_actions_from(
        self, memory: D.T_memory[D.T_state]
    ) -> D.T_agent[Space[D.T_event]]:
        return ListSpace([a for a in Action if self.applicable(memory, a)])

    def _get_action_space_(self) -> D.T_agent[Space[D.T_event]]:
        return ListSpace(list(Action))

    # ── goal / initial ──────────────────────────────────────────────────────

    def _get_goals_(self) -> D.T_agent[Space[D.T_observation]]:
        def is_goal_state(state: State) -> bool:
            return (
                state.notification is Notification.DELIVERED
                and state.notified_populations == state.populations
            )

        return ImplicitSpace(is_goal_state)

    def _get_initial_state_(self) -> D.T_state:
        return State(
            scope=Scope.UNKNOWN,
            populations=self._initial_populations,
            containment=Containment.NONE,
            triaged=False,
            evidence=False,
            notification=Notification.NONE,
            notified_populations=frozenset(),
        )

    def _get_observation_space_(self) -> D.T_agent[Space[D.T_observation]]:
        return ImplicitSpace(lambda state: isinstance(state, State))

    # ── divergence hook ─────────────────────────────────────────────────────

    def observe_divergence(
        self, state: State, population: str = DIVERGENCE_POPULATION
    ) -> State:
        """The observation that forces a replan: another population is affected.

        Pure — returns a new state and mutates nothing. Scope falls back to
        ``PARTIAL`` because the previously computed blast radius is now known to
        be incomplete, so a plan that already drafted for the narrower set no
        longer reaches the goal.
        """
        if population in state.populations:
            return state
        return state._replace(
            populations=state.populations | {population},
            scope=Scope.PARTIAL,
        )

    def _render_from(self, memory: D.T_memory[D.T_state], **kwargs: Any) -> Any:
        return (
            f"scope={memory.scope.name} populations={sorted(memory.populations)} "
            f"containment={memory.containment.name} triaged={memory.triaged} "
            f"evidence={memory.evidence} notification={memory.notification.name}"
        )
