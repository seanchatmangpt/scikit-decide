from autofde_lab.fabric.brce import (
    ActuationIntent,
    ActuationResult,
    Authority,
    BrceStanding,
    execute_brce,
    replay_receipt,
)


def intent() -> ActuationIntent:
    return ActuationIntent(
        intent_id="i:1",
        subject_id="subject:1",
        principal_id="principal:1",
        capability="set",
        resource="resource:1",
        intended_effect={"value": 1},
        idempotency_key="idem:1",
    )


def authority() -> Authority:
    return Authority("principal:1", frozenset({"set"}), frozenset({"resource:1"}))


def test_verified_consequence_has_receipt_and_distinct_evidence_states():
    world = {"value": 0}
    calls = []

    def actuator(_):
        calls.append("actuate")
        world["value"] = 1
        return ActuationResult("ack:1", {"requested": 1})

    decision = execute_brce(
        intent(),
        authority=authority(),
        policy_id="policy:v1",
        policy_admits=lambda _: True,
        actuator=actuator,
        observer=lambda _intent, _result: dict(world),
        verifier_id="verifier:v1",
        verifier=lambda _intent, observed: observed["value"] == 1,
    )
    assert decision.standing is BrceStanding.ALIVE
    assert decision.receipt is not None
    assert calls == ["actuate"]
    assert decision.receipt.acknowledgement == "ack:1"
    assert decision.receipt.effect_digest != decision.receipt.postcondition_digest

    assert (
        replay_receipt(
            decision.receipt,
            intent(),
            authority=authority(),
            policy_id="policy:v1",
            acknowledgement="ack:1",
            effect_evidence={"requested": 1},
            postcondition={"value": 1},
            verifier_id="verifier:v1",
        )
        is BrceStanding.REPLAY_MATCH
    )


def test_no_authority_or_policy_means_no_actuation():
    calls = []

    def actuator(_):
        calls.append("actuate")
        return ActuationResult("ack", {})

    wrong = Authority("principal:1", frozenset(), frozenset({"resource:1"}))
    assert (
        execute_brce(
            intent(),
            authority=wrong,
            policy_id="p",
            policy_admits=lambda _: True,
            actuator=actuator,
            observer=lambda *_: {},
            verifier_id="v",
            verifier=lambda *_: True,
        ).standing
        is BrceStanding.REFUSED_AUTHORITY
    )
    assert calls == []
    assert (
        execute_brce(
            intent(),
            authority=authority(),
            policy_id="p",
            policy_admits=lambda _: False,
            actuator=actuator,
            observer=lambda *_: {},
            verifier_id="v",
            verifier=lambda *_: True,
        ).standing
        is BrceStanding.REFUSED_POLICY
    )
    assert calls == []


def test_lost_ack_after_possible_actuation_is_uncertain_not_retry():
    calls = []

    def actuator(_):
        calls.append("actuate")
        return ActuationResult(None, {"possible": True}, possibly_actuated=True)

    decision = execute_brce(
        intent(),
        authority=authority(),
        policy_id="p",
        policy_admits=lambda _: True,
        actuator=actuator,
        observer=lambda *_: {"value": 1},
        verifier_id="v",
        verifier=lambda *_: True,
    )
    assert decision.standing is BrceStanding.UNCERTAIN
    assert decision.receipt is None
    assert calls == ["actuate"]


def test_failed_independent_postcondition_never_returns_success_receipt():
    decision = execute_brce(
        intent(),
        authority=authority(),
        policy_id="p",
        policy_admits=lambda _: True,
        actuator=lambda _: ActuationResult("ack", {"claimed": "ok"}),
        observer=lambda *_: {"value": 0},
        verifier_id="v",
        verifier=lambda _intent, observed: observed["value"] == 1,
    )
    assert decision.standing is BrceStanding.REFUSED_VERIFICATION
    assert decision.receipt is None


def test_replay_detects_policy_or_environment_evidence_drift():
    decision = execute_brce(
        intent(),
        authority=authority(),
        policy_id="p:v1",
        policy_admits=lambda _: True,
        actuator=lambda _: ActuationResult("ack", {"requested": 1}),
        observer=lambda *_: {"value": 1},
        verifier_id="v:v1",
        verifier=lambda *_: True,
    )
    assert decision.receipt is not None
    assert (
        replay_receipt(
            decision.receipt,
            intent(),
            authority=authority(),
            policy_id="p:v2",
            acknowledgement="ack",
            effect_evidence={"requested": 1},
            postcondition={"value": 1},
            verifier_id="v:v1",
        )
        is BrceStanding.REPLAY_DRIFT
    )
