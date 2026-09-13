"""Chicago-style tests for the construction Fortune-500 case-study domain."""

from __future__ import annotations

import pytest

from autofde_lab.hub.domain.construction import (
    Action,
    ConstructionDomain,
    ExternalObservation,
    ObservationRefused,
    TransitionRefused,
)


def applicable(domain: ConstructionDomain, state) -> set[Action]:
    return set(domain.get_applicable_actions(state).get_elements())


def construct(domain: ConstructionDomain, state, action: Action):
    return domain.get_next_state(state, action)


def prepare_estimate(domain: ConstructionDomain):
    state = domain.get_initial_state()
    state = construct(domain, state, Action.ADMIT_PROJECT_FACTS)
    return construct(domain, state, Action.PREPARE_ESTIMATE)


def admit_field_authority(domain: ConstructionDomain, state):
    state = domain.observe(state, ExternalObservation.CUSTOMER_APPROVED)
    return domain.observe(state, ExternalObservation.PERMIT_GRANTED)


def prepare_field_packet(domain: ConstructionDomain, state):
    state = construct(domain, state, Action.SCHEDULE_CREW)
    state = construct(domain, state, Action.ORDER_MATERIALS)
    return construct(domain, state, Action.PREPARE_FIELD_PACKET)


class TestAuthorityBoundary:
    def test_planner_action_plane_excludes_external_authority(self):
        domain = ConstructionDomain()

        assert all(
            domain.planner_can_emit(action)
            for action in domain.get_action_space().get_elements()
        )
        assert not domain.planner_can_emit(ExternalObservation.CUSTOMER_APPROVED)
        assert not domain.planner_can_emit(ExternalObservation.PERMIT_GRANTED)
        assert not domain.planner_can_emit(ExternalObservation.INSPECTION_PASSED)
        assert not domain.planner_can_emit(ExternalObservation.PAYMENT_RECEIVED)

    def test_customer_and_permit_cannot_be_manufactured_by_planning(self):
        domain = ConstructionDomain()
        state = prepare_estimate(domain)

        assert applicable(domain, state) == set()
        with pytest.raises(TransitionRefused) as exc:
            construct(domain, state, Action.SCHEDULE_CREW)
        assert exc.value.code == "REFUSED:INAPPLICABLE_CONSTRUCTION_ACTION"
        assert state.customer_approved is False
        assert state.permit_granted is False

    def test_external_observation_requires_causal_precondition(self):
        domain = ConstructionDomain()
        state = domain.get_initial_state()

        with pytest.raises(ObservationRefused) as exc:
            domain.observe(state, ExternalObservation.CUSTOMER_APPROVED)
        assert exc.value.code == "REFUSED:EXTERNAL_OBSERVATION_PRECONDITION"

        state = prepare_estimate(domain)
        with pytest.raises(ObservationRefused):
            domain.observe(state, ExternalObservation.PERMIT_GRANTED)


class TestPartialOrderCoordination:
    def test_crew_and_materials_commute_after_authority_is_observed(self):
        domain = ConstructionDomain()
        authorized = admit_field_authority(domain, prepare_estimate(domain))

        assert applicable(domain, authorized) == {
            Action.SCHEDULE_CREW,
            Action.ORDER_MATERIALS,
        }

        crew_first = construct(domain, authorized, Action.SCHEDULE_CREW)
        crew_first = construct(domain, crew_first, Action.ORDER_MATERIALS)

        materials_first = construct(domain, authorized, Action.ORDER_MATERIALS)
        materials_first = construct(domain, materials_first, Action.SCHEDULE_CREW)

        assert crew_first == materials_first
        assert applicable(domain, crew_first) == {Action.PREPARE_FIELD_PACKET}

    def test_field_packet_is_constructed_but_does_not_claim_physical_work(self):
        domain = ConstructionDomain()
        state = admit_field_authority(domain, prepare_estimate(domain))
        state = prepare_field_packet(domain, state)

        assert state.field_packet_prepared is True
        assert state.work_completed is False
        assert state.inspection_passed is False
        assert applicable(domain, state) == set()

        observed = domain.observe(state, ExternalObservation.WORK_COMPLETED)
        assert observed.work_completed is True


class TestInspectionAndReplanning:
    def test_failed_inspection_forces_remediation_before_pass_observation(self):
        domain = ConstructionDomain()
        state = admit_field_authority(domain, prepare_estimate(domain))
        state = prepare_field_packet(domain, state)
        state = domain.observe(state, ExternalObservation.WORK_COMPLETED)
        state = domain.observe(state, ExternalObservation.INSPECTION_FAILED)

        assert applicable(domain, state) == {Action.PREPARE_REMEDIATION}
        with pytest.raises(ObservationRefused):
            domain.observe(state, ExternalObservation.INSPECTION_PASSED)

        state = construct(domain, state, Action.PREPARE_REMEDIATION)
        state = domain.observe(state, ExternalObservation.INSPECTION_PASSED)
        assert state.inspection_passed is True
        assert applicable(domain, state) == {Action.ISSUE_INVOICE}


class TestEvidenceCompleteCloseout:
    def test_real_domain_episode_requires_external_payment_before_goal(self):
        domain = ConstructionDomain()
        state = admit_field_authority(domain, prepare_estimate(domain))
        state = prepare_field_packet(domain, state)
        state = domain.observe(state, ExternalObservation.WORK_COMPLETED)
        state = domain.observe(state, ExternalObservation.INSPECTION_PASSED)
        state = construct(domain, state, Action.ISSUE_INVOICE)

        assert domain.is_goal(state) is False
        assert applicable(domain, state) == set()
        with pytest.raises(TransitionRefused):
            construct(domain, state, Action.ASSEMBLE_CLOSEOUT)

        state = domain.observe(state, ExternalObservation.PAYMENT_RECEIVED)
        assert applicable(domain, state) == {Action.ASSEMBLE_CLOSEOUT}
        state = construct(domain, state, Action.ASSEMBLE_CLOSEOUT)

        assert domain.is_goal(state) is True
        assert domain.is_terminal(state) is True

    def test_coordination_cost_is_explicit_and_positive(self):
        domain = ConstructionDomain()
        state = domain.get_initial_state()
        next_state = construct(domain, state, Action.ADMIT_PROJECT_FACTS)

        value = domain.get_transition_value(
            state,
            Action.ADMIT_PROJECT_FACTS,
            next_state,
        )
        assert value.cost == 10.0
        assert value.cost > 0
