"""Bounded construction-operations planning domain.

The domain models the coordination skeleton shared by small contractors and
larger field-service/capital-project organizations. It deliberately separates
planner-owned construction from externally observed authority/consequence:

    planner Action -> CONSTRUCT only
    ExternalObservation -> authority or physical-world fact

A planner therefore cannot make a customer approve work, grant a permit,
claim physical completion, pass an inspection, or manufacture payment.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import Enum
from typing import NamedTuple, Optional

from autofde_lab import (
    DeterministicPlanningDomain,
    EnumerableSpace,
    ImplicitSpace,
    Space,
    Value,
)


class FiniteSpace(EnumerableSpace):
    """Dependency-free finite space for the bounded case-study vocabulary."""

    def __init__(self, elements: Sequence[object]):
        self._elements = tuple(elements)

    def get_elements(self) -> Sequence[object]:
        return self._elements


class State(NamedTuple):
    """Admitted state of one contractor job."""

    facts_admitted: bool = False
    estimate_prepared: bool = False
    customer_approved: bool = False
    permit_granted: bool = False
    crew_scheduled: bool = False
    materials_ready: bool = False
    field_packet_prepared: bool = False
    work_completed: bool = False
    inspection_failed: bool = False
    remediation_prepared: bool = False
    inspection_passed: bool = False
    invoice_issued: bool = False
    payment_received: bool = False
    closeout_assembled: bool = False


class Action(Enum):
    """Reversible planner-owned CONSTRUCT transitions."""

    ADMIT_PROJECT_FACTS = "admit_project_facts"
    PREPARE_ESTIMATE = "prepare_estimate"
    SCHEDULE_CREW = "schedule_crew"
    ORDER_MATERIALS = "order_materials"
    PREPARE_FIELD_PACKET = "prepare_field_packet"
    PREPARE_REMEDIATION = "prepare_remediation"
    ISSUE_INVOICE = "issue_invoice"
    ASSEMBLE_CLOSEOUT = "assemble_closeout"


class ExternalObservation(Enum):
    """Facts that must originate outside the planner's action space."""

    CUSTOMER_APPROVED = "customer_approved"
    PERMIT_GRANTED = "permit_granted"
    WORK_COMPLETED = "work_completed"
    INSPECTION_FAILED = "inspection_failed"
    INSPECTION_PASSED = "inspection_passed"
    PAYMENT_RECEIVED = "payment_received"


class TransitionRefused(ValueError):
    """Typed refusal for an inapplicable planner transition."""

    code = "REFUSED:INAPPLICABLE_CONSTRUCTION_ACTION"

    def __init__(self, action: Action):
        super().__init__(f"{self.code}:{action.value}")
        self.action = action


class ObservationRefused(ValueError):
    """Typed refusal for an external fact whose prerequisites are absent."""

    code = "REFUSED:EXTERNAL_OBSERVATION_PRECONDITION"

    def __init__(self, observation: ExternalObservation):
        super().__init__(f"{self.code}:{observation.value}")
        self.observation = observation


class D(DeterministicPlanningDomain):
    T_state = State
    T_observation = T_state
    T_event = Action
    T_value = float
    T_predicate = bool
    T_info = None


class ConstructionDomain(D):
    """Gall-layer contractor process model for falsification and replanning.

    The goal is evidence-complete closeout, not merely a generated plan. The
    domain reaches that goal only after the required external facts have been
    observed and admitted between planning episodes.
    """

    _COSTS = {
        Action.ADMIT_PROJECT_FACTS: 10.0,
        Action.PREPARE_ESTIMATE: 20.0,
        Action.SCHEDULE_CREW: 10.0,
        Action.ORDER_MATERIALS: 10.0,
        Action.PREPARE_FIELD_PACKET: 5.0,
        Action.PREPARE_REMEDIATION: 15.0,
        Action.ISSUE_INVOICE: 5.0,
        Action.ASSEMBLE_CLOSEOUT: 5.0,
    }

    def _get_next_state(
        self,
        memory: D.T_memory[D.T_state],
        action: D.T_agent[D.T_concurrency[D.T_event]],
    ) -> D.T_state:
        if action not in self._applicable_actions(memory):
            raise TransitionRefused(action)

        if action == Action.ADMIT_PROJECT_FACTS:
            return memory._replace(facts_admitted=True)
        if action == Action.PREPARE_ESTIMATE:
            return memory._replace(estimate_prepared=True)
        if action == Action.SCHEDULE_CREW:
            return memory._replace(crew_scheduled=True)
        if action == Action.ORDER_MATERIALS:
            return memory._replace(materials_ready=True)
        if action == Action.PREPARE_FIELD_PACKET:
            return memory._replace(field_packet_prepared=True)
        if action == Action.PREPARE_REMEDIATION:
            return memory._replace(remediation_prepared=True)
        if action == Action.ISSUE_INVOICE:
            return memory._replace(invoice_issued=True)
        if action == Action.ASSEMBLE_CLOSEOUT:
            return memory._replace(closeout_assembled=True)
        raise TransitionRefused(action)

    def _get_transition_value(
        self,
        memory: D.T_memory[D.T_state],
        action: D.T_agent[D.T_concurrency[D.T_event]],
        next_state: Optional[D.T_state] = None,
    ) -> D.T_agent[Value[D.T_value]]:
        return Value(cost=self._COSTS[action])

    def _is_terminal(self, state: D.T_state) -> D.T_agent[D.T_predicate]:
        return state.closeout_assembled

    def _get_action_space_(self) -> D.T_agent[Space[D.T_event]]:
        return FiniteSpace(tuple(Action))

    def _get_applicable_actions_from(
        self, memory: D.T_memory[D.T_state]
    ) -> D.T_agent[Space[D.T_event]]:
        return FiniteSpace(self._applicable_actions(memory))

    def _get_goals_(self) -> D.T_agent[Space[D.T_observation]]:
        return ImplicitSpace(lambda state: state.closeout_assembled)

    def _get_initial_state_(self) -> D.T_state:
        return State()

    def _get_observation_space_(self) -> D.T_agent[Space[D.T_observation]]:
        return ImplicitSpace(lambda state: isinstance(state, State))

    @staticmethod
    def planner_can_emit(event: object) -> bool:
        """Return whether ``event`` belongs to the planner-owned action plane."""

        return isinstance(event, Action)

    def observe(self, state: State, observation: ExternalObservation) -> State:
        """Admit one externally sourced authority/consequence observation.

        This method is intentionally outside the planner action API. It records
        an observed fact after checking the minimum causal prerequisites; it does
        not claim that AutoFDE Lab caused the fact.
        """

        if observation == ExternalObservation.CUSTOMER_APPROVED:
            if not state.estimate_prepared:
                raise ObservationRefused(observation)
            return state._replace(customer_approved=True)

        if observation == ExternalObservation.PERMIT_GRANTED:
            if not state.customer_approved:
                raise ObservationRefused(observation)
            return state._replace(permit_granted=True)

        if observation == ExternalObservation.WORK_COMPLETED:
            if not state.field_packet_prepared:
                raise ObservationRefused(observation)
            return state._replace(work_completed=True)

        if observation == ExternalObservation.INSPECTION_FAILED:
            if not state.work_completed:
                raise ObservationRefused(observation)
            return state._replace(inspection_failed=True, inspection_passed=False)

        if observation == ExternalObservation.INSPECTION_PASSED:
            if not state.work_completed:
                raise ObservationRefused(observation)
            if state.inspection_failed and not state.remediation_prepared:
                raise ObservationRefused(observation)
            return state._replace(inspection_passed=True)

        if observation == ExternalObservation.PAYMENT_RECEIVED:
            if not state.invoice_issued:
                raise ObservationRefused(observation)
            return state._replace(payment_received=True)

        raise ObservationRefused(observation)

    @staticmethod
    def _applicable_actions(state: State) -> tuple[Action, ...]:
        actions: list[Action] = []

        if not state.facts_admitted:
            actions.append(Action.ADMIT_PROJECT_FACTS)
        if state.facts_admitted and not state.estimate_prepared:
            actions.append(Action.PREPARE_ESTIMATE)

        authority_ready = state.customer_approved and state.permit_granted
        if authority_ready and not state.crew_scheduled:
            actions.append(Action.SCHEDULE_CREW)
        if authority_ready and not state.materials_ready:
            actions.append(Action.ORDER_MATERIALS)
        if (
            authority_ready
            and state.crew_scheduled
            and state.materials_ready
            and not state.field_packet_prepared
        ):
            actions.append(Action.PREPARE_FIELD_PACKET)

        if (
            state.work_completed
            and state.inspection_failed
            and not state.inspection_passed
            and not state.remediation_prepared
        ):
            actions.append(Action.PREPARE_REMEDIATION)

        if state.inspection_passed and not state.invoice_issued:
            actions.append(Action.ISSUE_INVOICE)
        if (
            state.invoice_issued
            and state.payment_received
            and not state.closeout_assembled
        ):
            actions.append(Action.ASSEMBLE_CLOSEOUT)

        return tuple(actions)
