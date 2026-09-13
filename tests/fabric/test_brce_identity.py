from dataclasses import replace

from autofde_lab.fabric.brce import (
    ActuationIntent,
    ActuationResult,
    Authority,
    BrceStanding,
    execute_brce,
    replay_receipt,
)


def test_replay_detects_planner_environment_and_revision_drift():
    intent = ActuationIntent(
        intent_id="i",
        subject_id="s",
        principal_id="p",
        capability="set",
        resource="r",
        intended_effect={"value": 1},
        idempotency_key="idem",
        planner_id="planner:v1",
        environment_id="env:sha256:aaa",
        revision_id="git:abc",
    )
    authority = Authority("p", frozenset({"set"}), frozenset({"r"}))
    decision = execute_brce(
        intent,
        authority=authority,
        policy_id="policy:v1",
        policy_admits=lambda _: True,
        actuator=lambda _: ActuationResult("ack", {"requested": 1}),
        observer=lambda *_: {"value": 1},
        verifier_id="verifier:v1",
        verifier=lambda *_: True,
    )
    assert decision.receipt is not None

    for changed in (
        replace(intent, planner_id="planner:v2"),
        replace(intent, environment_id="env:sha256:bbb"),
        replace(intent, revision_id="git:def"),
    ):
        assert (
            replay_receipt(
                decision.receipt,
                changed,
                authority=authority,
                policy_id="policy:v1",
                acknowledgement="ack",
                effect_evidence={"requested": 1},
                postcondition={"value": 1},
                verifier_id="verifier:v1",
            )
            is BrceStanding.REPLAY_DRIFT
        )
