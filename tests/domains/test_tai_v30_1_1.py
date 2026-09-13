from autofde_lab.hub.domain.tai_v30_1_1 import (
    INITIAL_STATE,
    POSITIVE_PLAN,
    REFUSAL_PLAN,
    RefusalReason,
    TAIForwardDeploymentDomain,
    TaiAction,
    TaiTransitionRefused,
    build_receipt,
    verify_receipt_replay,
)


def _execute(domain, plan):
    state = INITIAL_STATE
    for action in plan:
        applicable = domain.get_applicable_actions(state).get_elements()
        assert action in applicable
        state = domain.get_next_state(state, action)
    return state


def test_positive_path_is_receipted_and_replayable():
    domain = TAIForwardDeploymentDomain()
    final_state = _execute(domain, POSITIVE_PLAN)

    assert domain.is_terminal(final_state)
    assert domain.is_goal(final_state)
    assert final_state.brce_actuated
    assert final_state.receipt_issued
    assert final_state.replay_verified
    assert final_state.standing

    receipt = build_receipt(POSITIVE_PLAN, final_state)
    assert receipt.standing == "ALIVE"
    assert verify_receipt_replay(receipt)
    assert len(receipt.receipt_id) == 64


def test_brce_actuation_requires_runtime_and_authority():
    domain = TAIForwardDeploymentDomain()
    applicable = domain.get_applicable_actions(INITIAL_STATE).get_elements()

    assert TaiAction.brce_actuate not in applicable
    try:
        domain.get_next_state(INITIAL_STATE, TaiAction.brce_actuate)
    except TaiTransitionRefused as error:
        assert error.reason is RefusalReason.RUNTIME_NOT_ADMITTED
    else:
        raise AssertionError("unadmitted BRCE actuation was not refused")


def test_falsified_local_model_terminates_with_typed_refusal_receipt():
    domain = TAIForwardDeploymentDomain(local_conformance=False)
    final_state = _execute(domain, REFUSAL_PLAN)

    assert domain.is_terminal(final_state)
    assert not domain.is_goal(final_state)
    assert not final_state.brce_actuated
    assert final_state.refusal_receipt_issued

    receipt = build_receipt(REFUSAL_PLAN, final_state)
    assert receipt.standing == RefusalReason.LOCAL_CONFORMANCE_FALSIFIED.value
    assert verify_receipt_replay(receipt)
