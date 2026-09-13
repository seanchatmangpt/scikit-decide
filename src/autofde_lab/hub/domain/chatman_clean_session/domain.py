# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from __future__ import annotations

from dataclasses import replace
from typing import Generic, Sequence, TypeVar

from autofde_lab import (
    DeterministicPlanningDomain,
    EnumerableSpace,
    ImplicitSpace,
    Space,
    Value,
)

from .model import (
    ActionKind,
    ActuationIntent,
    RouteEvidence,
    RouteOutcome,
    RouteSpec,
    SessionAction,
    SessionState,
    Stage,
    TaskEnvelope,
)

T = TypeVar("T")


class FiniteSpace(EnumerableSpace[T], Generic[T]):
    """Small dependency-free enumerable space for Chatman domain values."""

    def __init__(self, elements: Sequence[T]):
        self._elements = tuple(elements)

    def get_elements(self) -> Sequence[T]:
        return self._elements


class D(DeterministicPlanningDomain):
    T_state = SessionState
    T_observation = T_state
    T_event = SessionAction
    T_value = float
    T_predicate = bool
    T_info = dict


class ChatmanCleanSessionDomain(D):
    """Deterministic planning model for the Clean-Session Environment Prime.

    The domain is deliberately side-effect free. ``ACTUATE`` is a modeled DO
    edge. Real execution is only performed by :func:`execute_actions`, which
    requires a broker and emits a receipt for every broker attempt.
    """

    def __init__(self, task: TaskEnvelope, routes: Sequence[RouteSpec]):
        self.task = task
        self.routes = tuple(routes)
        if not self.routes:
            raise ValueError(
                "at least one environment-manufacturing route is required"
            )
        route_names = [route.name for route in self.routes]
        if len(route_names) != len(set(route_names)):
            raise ValueError("route names must be unique")
        self._route_by_name = {route.name: route for route in self.routes}
        self._action_space = FiniteSpace(
            (
                SessionAction(ActionKind.PARSE),
                *(
                    SessionAction(ActionKind.TRY_ROUTE, route.name)
                    for route in self.routes
                ),
                SessionAction(ActionKind.CLASSIFY_EXHAUSTION),
                SessionAction(ActionKind.ADMIT),
                SessionAction(ActionKind.DIAGNOSE_OR_REPAIR),
                SessionAction(ActionKind.CONSTRUCT),
                SessionAction(ActionKind.ACTUATE),
                SessionAction(ActionKind.OBSERVE_CONSEQUENCE),
                SessionAction(ActionKind.VERIFY),
                SessionAction(ActionKind.RECEIPT),
                SessionAction(ActionKind.REPLAY_OR_HOOK),
            )
        )

    def initial_state(self) -> SessionState:
        return SessionState(task_identity=self.task.identity)

    def to_task_document(self) -> dict[str, object]:
        """Return the language-neutral task and route exchange document."""

        return {**self.task.to_dict(), "routes": [r.to_dict() for r in self.routes]}

    def applicable_actions(self, state: SessionState) -> tuple[SessionAction, ...]:
        if state.task_identity != self.task.identity:
            return ()
        if state.stage is Stage.PARSE:
            return (SessionAction(ActionKind.PARSE),)
        if state.stage is Stage.ROUTE:
            remaining = tuple(
                SessionAction(ActionKind.TRY_ROUTE, route.name)
                for route in self.routes
                if route.name not in state.attempted_routes
            )
            return remaining or (SessionAction(ActionKind.CLASSIFY_EXHAUSTION),)
        mapping = {
            Stage.ADMIT: ActionKind.ADMIT,
            Stage.DIAGNOSE: ActionKind.DIAGNOSE_OR_REPAIR,
            Stage.CONSTRUCT: ActionKind.CONSTRUCT,
            Stage.ACTUATE: ActionKind.ACTUATE,
            Stage.OBSERVE: ActionKind.OBSERVE_CONSEQUENCE,
            Stage.VERIFY: ActionKind.VERIFY,
            Stage.RECEIPT: ActionKind.RECEIPT,
            Stage.REPLAY_OR_HOOK: ActionKind.REPLAY_OR_HOOK,
        }
        kind = mapping.get(state.stage)
        return () if kind is None else (SessionAction(kind),)

    def transition(self, state: SessionState, action: SessionAction) -> SessionState:
        if action not in self.applicable_actions(state):
            raise ValueError(
                f"action {action} is not applicable at stage {state.stage.value}"
            )
        if action.kind is ActionKind.PARSE:
            return replace(state, stage=Stage.ROUTE)
        if action.kind is ActionKind.TRY_ROUTE:
            route = self._route_by_name[action.route or ""]
            evidence = RouteEvidence(route.name, route.outcome, route.reason)
            attempted = (*state.attempted_routes, route.name)
            evidence_set = (*state.route_evidence, evidence)
            if route.outcome is RouteOutcome.SUCCESS:
                return replace(
                    state,
                    stage=Stage.ADMIT,
                    attempted_routes=attempted,
                    route_evidence=evidence_set,
                    selected_route=route.name,
                )
            return replace(
                state,
                attempted_routes=attempted,
                route_evidence=evidence_set,
            )
        if action.kind is ActionKind.CLASSIFY_EXHAUSTION:
            standing, reason = self._classify_exhaustion(state.route_evidence)
            return replace(
                state,
                stage=Stage.STANDING,
                standing=standing,
                reason=reason,
            )
        next_stage = {
            ActionKind.ADMIT: Stage.DIAGNOSE,
            ActionKind.DIAGNOSE_OR_REPAIR: Stage.CONSTRUCT,
            ActionKind.CONSTRUCT: Stage.ACTUATE,
            ActionKind.ACTUATE: Stage.OBSERVE,
            ActionKind.OBSERVE_CONSEQUENCE: Stage.VERIFY,
            ActionKind.VERIFY: Stage.RECEIPT,
            ActionKind.RECEIPT: Stage.REPLAY_OR_HOOK,
            ActionKind.REPLAY_OR_HOOK: Stage.STANDING,
        }[action.kind]
        if next_stage is Stage.STANDING:
            return replace(state, stage=next_stage, standing="ALIVE")
        return replace(state, stage=next_stage)

    def canonical_completion_plan(self) -> tuple[SessionAction, ...]:
        """Return the lowest-cost known successful route plus canonical closure."""

        successful = sorted(
            (route for route in self.routes if route.outcome is RouteOutcome.SUCCESS),
            key=lambda route: (route.cost, route.name),
        )
        if successful:
            route_actions = (
                SessionAction(ActionKind.TRY_ROUTE, successful[0].name),
            )
        else:
            route_actions = tuple(
                SessionAction(ActionKind.TRY_ROUTE, route.name)
                for route in sorted(
                    self.routes, key=lambda route: (route.cost, route.name)
                )
            ) + (SessionAction(ActionKind.CLASSIFY_EXHAUSTION),)
        if not successful:
            return (SessionAction(ActionKind.PARSE), *route_actions)
        return (
            SessionAction(ActionKind.PARSE),
            *route_actions,
            SessionAction(ActionKind.ADMIT),
            SessionAction(ActionKind.DIAGNOSE_OR_REPAIR),
            SessionAction(ActionKind.CONSTRUCT),
            SessionAction(ActionKind.ACTUATE),
            SessionAction(ActionKind.OBSERVE_CONSEQUENCE),
            SessionAction(ActionKind.VERIFY),
            SessionAction(ActionKind.RECEIPT),
            SessionAction(ActionKind.REPLAY_OR_HOOK),
        )

    def make_actuation_intent(
        self, state: SessionState, replay_of: str | None = None
    ) -> ActuationIntent:
        if state.stage is not Stage.ACTUATE or not state.selected_route:
            raise ValueError("actuation intent may only be constructed at ACTUATE")
        return ActuationIntent(
            task_identity=self.task.identity,
            route=state.selected_route,
            action="execute admitted task through BRCE",
            payload={
                "repo": self.task.repo,
                "base": self.task.base,
                "task": self.task.task,
                "acceptance": self.task.acceptance,
                "constraints": list(self.task.constraints),
                "authority": self.task.authority,
            },
            replay_of=replay_of,
        )

    @staticmethod
    def _classify_exhaustion(
        evidence: Sequence[RouteEvidence],
    ) -> tuple[str, str]:
        if not evidence:
            return "UNKNOWN", "no route was observed"
        outcomes = {item.outcome for item in evidence}
        reasons = "; ".join(
            f"{item.route}:{item.outcome.value}:{item.reason or ''}"
            for item in evidence
        )
        if RouteOutcome.BUILD_BROKEN in outcomes:
            return "BUILD_BROKEN", reasons
        if RouteOutcome.BLOCKED in outcomes:
            return "BLOCKED", reasons
        if outcomes == {RouteOutcome.UNSUPPORTED}:
            return "UNSUPPORTED", reasons
        if outcomes == {RouteOutcome.REFUSED}:
            typed_reason = next(
                (item.reason for item in evidence if item.reason), "POLICY"
            )
            return f"REFUSED:{typed_reason}", reasons
        return "PARTIAL_ALIVE", reasons

    # scikit-decide implementation points
    def _get_initial_state_(self) -> D.T_state:
        return self.initial_state()

    def _get_next_state(
        self,
        memory: D.T_memory[D.T_state],
        action: D.T_agent[D.T_concurrency[D.T_event]],
    ) -> D.T_state:
        return self.transition(memory, action)

    def _get_transition_value(
        self,
        memory: D.T_memory[D.T_state],
        action: D.T_agent[D.T_concurrency[D.T_event]],
        next_state: D.T_state | None = None,
    ) -> D.T_agent[Value[D.T_value]]:
        if action.kind is ActionKind.TRY_ROUTE:
            return Value(cost=self._route_by_name[action.route or ""].cost)
        return Value(cost=1.0)

    def _is_terminal(self, state: D.T_state) -> D.T_agent[D.T_predicate]:
        return state.stage is Stage.STANDING

    def _get_action_space_(self) -> D.T_agent[Space[D.T_event]]:
        return self._action_space

    def _get_applicable_actions_from(
        self, memory: D.T_memory[D.T_state]
    ) -> D.T_agent[Space[D.T_event]]:
        return FiniteSpace(self.applicable_actions(memory))

    def _get_goals_(self) -> D.T_agent[Space[D.T_observation]]:
        return ImplicitSpace(
            lambda state: isinstance(state, SessionState)
            and state.task_identity == self.task.identity
            and state.standing == "ALIVE"
        )

    def _get_observation_space_(self) -> D.T_agent[Space[D.T_observation]]:
        return ImplicitSpace(
            lambda state: isinstance(state, SessionState)
            and state.task_identity == self.task.identity
        )
