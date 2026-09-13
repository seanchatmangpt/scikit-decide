from __future__ import annotations

import json
from dataclasses import dataclass, field

import pytest

from autofde_lab.hub.domain.chatman_clean_session import (
    ActionKind,
    ActuationIntent,
    BrokerReceipt,
    ChatmanCleanSessionDomain,
    ExecutionReceipt,
    RouteOutcome,
    RouteSpec,
    SessionAction,
    Stage,
    TaskEnvelope,
    digest,
    execute_actions,
    replay_execution,
)


@dataclass
class RecordingBroker:
    standing: str = "ALIVE"
    intents: list[ActuationIntent] = field(default_factory=list)

    def actuate(self, intent: ActuationIntent) -> BrokerReceipt:
        self.intents.append(intent)
        return BrokerReceipt.issue(
            intent,
            standing=self.standing,
            consequence={"attempt": len(self.intents), "route": intent.route},
            reason=None if self.standing == "ALIVE" else "POLICY_DENIED",
        )


def make_domain(*routes: RouteSpec) -> ChatmanCleanSessionDomain:
    return ChatmanCleanSessionDomain(
        TaskEnvelope(
            repo="seanchatmangpt/scikit-decide",
            base="0f32a25500262047539166a98facc29211e54d01",
            task="prove Clean-Session Environment Prime interoperability",
            acceptance="public domain API plus broker-bound execution and replay",
            constraints=("zero unreceipted actuation",),
            authority="repository owner",
        ),
        routes=routes
        or (
            RouteSpec(
                "exact_sha_sparse_tree", cost=1.0, outcome=RouteOutcome.SUCCESS
            ),
        ),
    )


def test_scikit_decide_public_domain_contract() -> None:
    domain = make_domain()
    state = domain.reset()
    assert state.stage is Stage.PARSE

    parse = domain.get_applicable_actions(state).get_elements()[0]
    routed = domain.get_next_state(state, parse)
    assert routed.stage is Stage.ROUTE
    assert parse in domain.get_action_space()
    assert domain.get_transition_value(state, parse, routed).cost == 1.0
    assert not domain.is_terminal(routed)


def test_failed_edge_is_topology_when_another_route_closes() -> None:
    domain = make_domain(
        RouteSpec(
            "container_dns",
            cost=0.1,
            outcome=RouteOutcome.BLOCKED,
            reason="DNS unavailable",
        ),
        RouteSpec("github_object_graph", cost=1.0, outcome=RouteOutcome.SUCCESS),
    )
    actions = (
        SessionAction(ActionKind.PARSE),
        SessionAction(ActionKind.TRY_ROUTE, "container_dns"),
        SessionAction(ActionKind.TRY_ROUTE, "github_object_graph"),
        SessionAction(ActionKind.ADMIT),
        SessionAction(ActionKind.DIAGNOSE_OR_REPAIR),
        SessionAction(ActionKind.CONSTRUCT),
        SessionAction(ActionKind.ACTUATE),
        SessionAction(ActionKind.OBSERVE_CONSEQUENCE),
        SessionAction(ActionKind.VERIFY),
        SessionAction(ActionKind.RECEIPT),
        SessionAction(ActionKind.REPLAY_OR_HOOK),
    )
    broker = RecordingBroker()
    receipt = execute_actions(domain, actions, broker)

    assert receipt.standing == "ALIVE"
    assert len(receipt.broker_receipts) == 1
    assert broker.intents[0].route == "github_object_graph"


def test_zero_unreceipted_actuation() -> None:
    domain = make_domain()
    receipt = execute_actions(
        domain, domain.canonical_completion_plan(), broker=None
    )

    assert receipt.standing == "REFUSED:MISSING_BRCE_BROKER"
    assert not receipt.broker_receipts
    assert receipt.actions[-1].kind is ActionKind.ACTUATE


def test_every_broker_failure_is_receipted_and_typed() -> None:
    domain = make_domain()
    broker = RecordingBroker(standing="REFUSED:AUTHORITY_DENIED")
    receipt = execute_actions(domain, domain.canonical_completion_plan(), broker)

    assert receipt.standing == "REFUSED:AUTHORITY_DENIED"
    assert len(receipt.broker_receipts) == 1
    assert receipt.broker_receipts[0].reason == "POLICY_DENIED"


def test_replay_reenters_broker_with_prior_receipt_identity() -> None:
    domain = make_domain()
    broker = RecordingBroker()
    first = execute_actions(domain, domain.canonical_completion_plan(), broker)
    replay = replay_execution(domain, first, broker)

    assert replay.standing == "ALIVE"
    assert replay.replay_of == first.receipt_id
    assert len(broker.intents) == 2
    assert broker.intents[1].replay_of == first.receipt_id
    assert broker.intents[0].intent_id != broker.intents[1].intent_id


def test_exhausted_routes_classify_only_after_all_attempts() -> None:
    domain = make_domain(
        RouteSpec(
            "native_binary",
            outcome=RouteOutcome.UNSUPPORTED,
            reason="binary absent",
        ),
        RouteSpec(
            "shared_library",
            outcome=RouteOutcome.UNSUPPORTED,
            reason="library absent",
        ),
    )
    receipt = execute_actions(domain, domain.canonical_completion_plan(), broker=None)
    assert receipt.standing == "UNSUPPORTED"
    assert not receipt.broker_receipts


def test_generic_route_failure_remains_partial_not_blocked() -> None:
    domain = make_domain(
        RouteSpec(
            "unclassified_transport",
            outcome=RouteOutcome.FAILED,
            reason="transport returned a non-terminal failure",
        )
    )
    receipt = execute_actions(
        domain, domain.canonical_completion_plan(), broker=None
    )
    assert receipt.standing == "PARTIAL_ALIVE"


def test_unknown_broker_observation_is_not_admitted_as_truth() -> None:
    domain = make_domain()
    broker = RecordingBroker(standing="UNKNOWN")
    receipt = execute_actions(domain, domain.canonical_completion_plan(), broker)

    assert receipt.standing == "PARTIAL_ALIVE"
    assert receipt.broker_receipts[0].standing == "UNKNOWN"


def test_interop_documents_are_json_serializable() -> None:
    domain = make_domain()
    receipt = execute_actions(
        domain, domain.canonical_completion_plan(), RecordingBroker()
    )

    task_document = domain.to_task_document()
    receipt_document = receipt.to_dict()

    assert json.loads(json.dumps(task_document)) == task_document
    assert json.loads(json.dumps(receipt_document)) == receipt_document
    broker_document = receipt_document["broker_receipts"][0]
    assert digest(receipt_document["task"]) == receipt_document["task_identity"]
    assert digest(receipt_document["state"]) == receipt_document["state_digest"]
    assert digest(broker_document["intent"]) == broker_document["intent_id"]
    assert receipt_document["state"]["selected_route"] == "exact_sha_sparse_tree"
    assert receipt_document["state"]["route_evidence"]
    assert any(action["lane"] == "DO" for action in receipt_document["actions"])
    assert ExecutionReceipt.from_mapping(receipt_document).to_dict() == receipt_document


@dataclass
class MismatchedBroker:
    def actuate(self, intent: ActuationIntent) -> BrokerReceipt:
        other = ActuationIntent(
            task_identity=intent.task_identity,
            route=intent.route,
            action=intent.action + " altered",
            payload=intent.payload,
        )
        return BrokerReceipt.issue(other, "ALIVE", {"executed": True})


def test_mismatched_broker_receipt_is_refused_and_receipted() -> None:
    domain = make_domain()
    receipt = execute_actions(
        domain, domain.canonical_completion_plan(), MismatchedBroker()
    )

    assert receipt.standing == "REFUSED:BROKER_RECEIPT_IDENTITY_MISMATCH"
    assert len(receipt.broker_receipts) == 1
    assert receipt.broker_receipts[0].intent_id


@dataclass
class ExplodingBroker:
    def actuate(self, intent: ActuationIntent) -> BrokerReceipt:
        raise TimeoutError("bounded broker call timed out")


def test_broker_exception_is_typed_and_receipted() -> None:
    domain = make_domain()
    receipt = execute_actions(
        domain, domain.canonical_completion_plan(), ExplodingBroker()
    )

    assert receipt.standing == "PARTIAL_ALIVE"
    assert receipt.broker_receipts[0].reason == "BROKER_TIMEOUT"
    assert receipt.broker_receipts[0].consequence["exception_type"] == "TimeoutError"


def test_tampered_execution_state_is_refused() -> None:
    domain = make_domain()
    receipt = execute_actions(
        domain, domain.canonical_completion_plan(), RecordingBroker()
    )
    document = receipt.to_dict()
    document["state"]["standing"] = "BLOCKED"

    with pytest.raises(ValueError, match="state document"):
        ExecutionReceipt.from_mapping(document)


def test_tampered_broker_intent_is_refused() -> None:
    domain = make_domain()
    receipt = execute_actions(
        domain, domain.canonical_completion_plan(), RecordingBroker()
    )
    document = receipt.to_dict()
    document["broker_receipts"][0]["intent"]["route"] = "forged_route"

    with pytest.raises(ValueError, match="intent document"):
        ExecutionReceipt.from_mapping(document)
