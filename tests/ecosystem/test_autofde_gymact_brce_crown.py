"""Chicago crown: cached AutoFDE POWL -> GymAct BRCE -> real consequence."""

from __future__ import annotations

from dataclasses import replace

import pytest
from gymact.action_contract import (
    ActionDefinition,
    ExecutionGrant,
    ExpectedEffect,
    SubjectRef,
    VerificationKind,
    VerificationStrategy,
    construct_prepared_action,
)
from gymact.authority import AllowListAuthorityResolver
from gymact.brce import BRCEBroker, BrokerRequest
from gymact.models import MaterializationIntent, Standing
from gymact.providers import MemoryProvider
from gymact.runtime import ProductionGymAct

from autofde_lab.agent.continuous_planning import (
    PlanApplicability,
    PlanArtifact,
    PlanningContext,
)
from autofde_lab.fabric.powl import parse_powl_turtle, project_plan_to_powl
from autofde_lab.gymact.brce_plan import AdmittedActuationSession
from autofde_lab.powl.algebra import Atom
from autofde_lab.powl.turtle_bridge import powl_model_to_node

BASE = "urn:autofde-lab:test:brce-plan"
AUTHORITY = f"{BASE}:authority"
SET_ACTION = f"{BASE}/set"
INCREMENT_ACTION = f"{BASE}/increment"
SET_CAPABILITY = "urn:gymact:memory:capability:set"
INCREMENT_CAPABILITY = "urn:gymact:memory:capability:increment"
PLAN_LINES = ("(set counter ten)", "(increment counter five)")
PLAN_GOAL = "restore-counter"
PLAN_FACT = "counter-world-materialized"


def _request(
    *,
    episode_id: str,
    action_ref: str,
    capability_ref: str,
    payload: dict[str, object],
    expected: dict[str, object],
    key: str,
    scope_refs: tuple[str, ...] | None = None,
) -> BrokerRequest:
    effect = ExpectedEffect(predicate="state", parameters=expected)
    action = ActionDefinition(
        semantic_id=action_ref,
        provider_ref="urn:gymact:provider:memory",
        capability_ref=capability_ref,
        subject_type="schema:Thing",
        input_schema={"type": "object"},
        expected_effects=(effect,),
        verification=VerificationStrategy(
            kind=VerificationKind.EXACT_STATE,
            observer_ref="urn:gymact:observer:memory",
            expected=expected,
        ),
    )
    subject = SubjectRef(
        semantic_id=f"urn:gymact:episode:{episode_id}",
        provider_ref="memory",
    )
    bound_scope_refs = (subject.semantic_id,) if scope_refs is None else scope_refs
    prepared = construct_prepared_action(
        action,
        episode_id=episode_id,
        subject=subject,
        payload=payload,
        admission_digest=f"admitted:{key}",
        idempotency_key=key,
    )
    grant = ExecutionGrant(
        principal="urn:autofde-lab:test:principal",
        action_ref=action.semantic_id,
        subject=subject,
        capability_ref=capability_ref,
        authority_ref=AUTHORITY,
        policy_revision="autofde-test-policy-v1",
        admitted_observation_ref=f"urn:autofde-lab:test:observation:{key}",
        intended_effects=action.expected_effects,
        scope_refs=bound_scope_refs,
        nonce=f"nonce:{key}",
    )
    return BrokerRequest(
        action=action,
        prepared=prepared,
        grant=grant,
        expected=expected,
    )


async def _runtime_and_episode() -> tuple[ProductionGymAct, str]:
    runtime = ProductionGymAct(
        validate_profile=False,
        authority_resolver=AllowListAuthorityResolver({AUTHORITY}),
    )
    runtime.register_provider(MemoryProvider())
    materialized = await runtime.materialize(
        MaterializationIntent(
            provider="memory",
            config={"requires_authority": True},
            idempotency_key="autofde-brce-materialize",
        )
    )
    assert materialized.episode is not None
    return runtime, materialized.episode.episode_id


def _episode_scope(episode_id: str) -> str:
    """Exact Chicago test-world authority scope: this materialized episode only."""
    return f"urn:gymact:episode:{episode_id}"


def _authorized_bundle(episode_id: str) -> dict[str, BrokerRequest]:
    return {
        SET_ACTION: _request(
            episode_id=episode_id,
            action_ref=SET_ACTION,
            capability_ref=SET_CAPABILITY,
            payload={"key": "counter", "value": 10},
            expected={"counter": 10},
            key="autofde-brce-set",
        ),
        INCREMENT_ACTION: _request(
            episode_id=episode_id,
            action_ref=INCREMENT_ACTION,
            capability_ref=INCREMENT_CAPABILITY,
            payload={"key": "counter", "amount": 5},
            expected={"counter": 15},
            key="autofde-brce-increment",
        ),
    }


def _cached_plan() -> PlanArtifact:
    turtle = project_plan_to_powl(
        PLAN_LINES,
        BASE,
        planner_run="run-autofde-lab-autonomous-brce",
    )
    tree = powl_model_to_node(parse_powl_turtle(turtle))
    return PlanArtifact(
        model=tree,
        applicability=PlanApplicability(
            goal=PLAN_GOAL,
            required_facts=frozenset({PLAN_FACT}),
            required_capabilities=frozenset({SET_CAPABILITY, INCREMENT_CAPABILITY}),
            constraint_digest="autofde-test-policy-v1",
            semantic_revision="gymact-brce-plan-v1",
        ),
        planner="autofde-lab-powl",
        family_id="counter-recovery",
        version=1,
        required_authority_classes=("bounded-episode-operator",),
    )


def _planning_context(*, include_required_fact: bool = True) -> PlanningContext:
    facts = frozenset({PLAN_FACT}) if include_required_fact else frozenset()
    return PlanningContext(
        goal=PLAN_GOAL,
        facts=facts,
        capabilities=frozenset({SET_CAPABILITY, INCREMENT_CAPABILITY}),
        constraint_digest="autofde-test-policy-v1",
        semantic_revision="gymact-brce-plan-v1",
    )


@pytest.mark.asyncio
async def test_cached_plan_autonomously_actuates_complete_plan_only_via_brce() -> None:
    runtime, episode_id = await _runtime_and_episode()
    session = AdmittedActuationSession(
        broker=BRCEBroker(runtime),
        request_binding=_authorized_bundle(episode_id),
        scope_ref=_episode_scope(episode_id),
    )
    cached_plan = _cached_plan()

    execution = session.run(
        PLAN_LINES,
        base_iri=BASE,
        plan_artifact=cached_plan,
        planning_context=_planning_context(),
    )

    assert execution.alive is True
    assert [transition.standing for transition in execution.transitions] == [
        Standing.ALIVE,
        Standing.ALIVE,
    ]
    assert len(execution.plan_binding_digests) == 2
    assert len(set(execution.plan_binding_digests)) == 2
    assert all(
        transition.receipt.planning_provenance_digest is not None
        for transition in execution.transitions
    )
    assert (
        len(
            {
                transition.receipt.planning_provenance_digest
                for transition in execution.transitions
            }
        )
        == 2
    )
    assert all(
        transition.receipt.principal == "urn:autofde-lab:test:principal"
        for transition in execution.transitions
    )
    assert all(
        session.scope_ref in request.grant.scope_refs
        for request in session.request_binding.values()
    )
    assert not hasattr(session, "act")
    assert (
        "mfwp:implementsAction <urn:autofde-lab:test:brce-plan/set>"
        in execution.powl_turtle
    )
    assert (
        "mfwp:implementsAction <urn:autofde-lab:test:brce-plan/increment>"
        in execution.powl_turtle
    )
    assert len(execution.ocel_log.events) == 2
    assert (await runtime.observe(episode_id)).state == {"counter": 15}
    assert runtime.verify_evidence_chain()


@pytest.mark.asyncio
async def test_cached_plan_model_drift_is_refused_before_first_do() -> None:
    runtime, episode_id = await _runtime_and_episode()
    session = AdmittedActuationSession(
        broker=BRCEBroker(runtime),
        request_binding=_authorized_bundle(episode_id),
        scope_ref=_episode_scope(episode_id),
    )
    stale_plan = replace(_cached_plan(), model=Atom("stale-cached-plan"))

    with pytest.raises(ValueError, match="REFUSED:PLAN_MODEL_IDENTITY_DRIFT"):
        session.run(
            PLAN_LINES,
            base_iri=BASE,
            plan_artifact=stale_plan,
            planning_context=_planning_context(),
        )

    assert (await runtime.observe(episode_id)).state == {}


@pytest.mark.asyncio
async def test_cached_plan_applicability_is_refused_before_first_do() -> None:
    runtime, episode_id = await _runtime_and_episode()
    session = AdmittedActuationSession(
        broker=BRCEBroker(runtime),
        request_binding=_authorized_bundle(episode_id),
        scope_ref=_episode_scope(episode_id),
    )

    with pytest.raises(PermissionError, match="REFUSED:PLAN_APPLICABILITY"):
        session.run(
            PLAN_LINES,
            base_iri=BASE,
            plan_artifact=_cached_plan(),
            planning_context=_planning_context(include_required_fact=False),
        )

    assert (await runtime.observe(episode_id)).state == {}


@pytest.mark.asyncio
async def test_chicago_preflight_refuses_identity_drift_before_first_do() -> None:
    runtime, episode_id = await _runtime_and_episode()
    bundle = _authorized_bundle(episode_id)
    bundle[INCREMENT_ACTION] = _request(
        episode_id=episode_id,
        action_ref=f"{BASE}/wrong-increment",
        capability_ref=INCREMENT_CAPABILITY,
        payload={"key": "counter", "amount": 5},
        expected={"counter": 15},
        key="autofde-brce-wrong-increment",
    )
    session = AdmittedActuationSession(
        broker=BRCEBroker(runtime),
        request_binding=bundle,
        scope_ref=_episode_scope(episode_id),
    )

    with pytest.raises(
        ValueError, match="REFUSED:BROKER_REQUEST_ACTION_IDENTITY_DRIFT"
    ):
        session.run(PLAN_LINES, base_iri=BASE)

    assert (await runtime.observe(episode_id)).state == {}


@pytest.mark.asyncio
async def test_chicago_preflight_refuses_out_of_scope_bundle_before_first_do() -> None:
    runtime, episode_id = await _runtime_and_episode()
    bundle = _authorized_bundle(episode_id)
    bundle[INCREMENT_ACTION] = _request(
        episode_id=episode_id,
        action_ref=INCREMENT_ACTION,
        capability_ref=INCREMENT_CAPABILITY,
        payload={"key": "counter", "amount": 5},
        expected={"counter": 15},
        key="autofde-brce-out-of-scope",
        # Provider scope is independently valid in GymAct, but intentionally
        # broader than this session's exact episode scope. AutoFDE must refuse it.
        scope_refs=("memory",),
    )
    session = AdmittedActuationSession(
        broker=BRCEBroker(runtime),
        request_binding=bundle,
        scope_ref=_episode_scope(episode_id),
    )

    with pytest.raises(PermissionError, match="REFUSED:ACTUATION_SCOPE_MISMATCH"):
        session.run(PLAN_LINES, base_iri=BASE)

    assert (await runtime.observe(episode_id)).state == {}
