from autofde_lab.autofde.bootstrap import (
    BootstrapPhase,
    BootstrapStanding,
    BootstrapState,
    TransitionReceipt,
    advance_bootstrap,
)


def receipt(subject: str, n: int, *, verified: bool = True) -> TransitionReceipt:
    return TransitionReceipt(
        receipt_id=f"r:{n}",
        subject_id=subject,
        issuer=f"issuer:{n}",
        verified=verified,
    )


def test_recursive_bootstrap_requires_receipt_at_every_transition():
    state = BootstrapState("parent", "capability:x", "child")
    phases = (
        BootstrapPhase.CHILD_PLANNED,
        BootstrapPhase.CHILD_ADMITTED,
        BootstrapPhase.CHILD_EXECUTED,
        BootstrapPhase.CHILD_VERIFIED,
        BootstrapPhase.CAPABILITY_ADMITTED,
        BootstrapPhase.PARENT_RESUMED,
    )
    for n, phase in enumerate(phases, start=1):
        subject = "parent" if phase is BootstrapPhase.PARENT_RESUMED else "child"
        decision = advance_bootstrap(state, target=phase, receipt=receipt(subject, n))
        assert decision.standing is BootstrapStanding.ADVANCED
        state = decision.state
    assert state.phase is BootstrapPhase.PARENT_RESUMED
    assert state.receipt_ids == tuple(f"r:{n}" for n in range(1, 7))


def test_missing_receipt_cannot_advance():
    state = BootstrapState("parent", "capability:x", "child")
    decision = advance_bootstrap(
        state, target=BootstrapPhase.CHILD_PLANNED, receipt=None
    )
    assert decision.standing is BootstrapStanding.REFUSED_MISSING_RECEIPT
    assert decision.state is state


def test_unverified_or_wrong_subject_receipt_cannot_advance():
    state = BootstrapState("parent", "capability:x", "child")
    assert (
        advance_bootstrap(
            state,
            target=BootstrapPhase.CHILD_PLANNED,
            receipt=receipt("wrong", 1),
        ).standing
        is BootstrapStanding.REFUSED_SUBJECT_MISMATCH
    )
    assert (
        advance_bootstrap(
            state,
            target=BootstrapPhase.CHILD_PLANNED,
            receipt=receipt("child", 1, verified=False),
        ).standing
        is BootstrapStanding.REFUSED_UNVERIFIED
    )


def test_controller_cannot_skip_brokered_execution():
    state = BootstrapState(
        "parent", "capability:x", "child", phase=BootstrapPhase.CHILD_ADMITTED
    )
    decision = advance_bootstrap(
        state,
        target=BootstrapPhase.CHILD_VERIFIED,
        receipt=receipt("child", 3),
    )
    assert decision.standing is BootstrapStanding.REFUSED_WRONG_PHASE
