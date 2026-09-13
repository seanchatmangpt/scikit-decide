"""Recursive blocked-parent bootstrap orchestration without ambient execution authority.

The controller is a deterministic state machine over externally produced receipts.  It never
runs planners, manufacturers, verifiers, brokers, or deployment tools directly.  Each transition
requires the receipt from the component that owns that authority, preserving the rule that hooks
and orchestration manufacture intents while BRCE remains the exclusive DO path.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum


class BootstrapPhase(str, Enum):
    BLOCKED = "BLOCKED"
    CHILD_PLANNED = "CHILD_PLANNED"
    CHILD_ADMITTED = "CHILD_ADMITTED"
    CHILD_EXECUTED = "CHILD_EXECUTED"
    CHILD_VERIFIED = "CHILD_VERIFIED"
    CAPABILITY_ADMITTED = "CAPABILITY_ADMITTED"
    PARENT_RESUMED = "PARENT_RESUMED"


class BootstrapStanding(str, Enum):
    ADVANCED = "ADVANCED"
    REFUSED_WRONG_PHASE = "REFUSED:WRONG_PHASE"
    REFUSED_MISSING_RECEIPT = "REFUSED:MISSING_RECEIPT"
    REFUSED_SUBJECT_MISMATCH = "REFUSED:SUBJECT_MISMATCH"
    REFUSED_UNVERIFIED = "REFUSED:UNVERIFIED"


@dataclass(frozen=True, slots=True)
class TransitionReceipt:
    receipt_id: str
    subject_id: str
    issuer: str
    verified: bool = True


@dataclass(frozen=True, slots=True)
class BootstrapState:
    parent_id: str
    missing_capability_id: str
    child_id: str
    phase: BootstrapPhase = BootstrapPhase.BLOCKED
    receipt_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BootstrapDecision:
    standing: BootstrapStanding
    state: BootstrapState
    reason: str


_EXPECTED = {
    BootstrapPhase.BLOCKED: (BootstrapPhase.CHILD_PLANNED, "planner"),
    BootstrapPhase.CHILD_PLANNED: (BootstrapPhase.CHILD_ADMITTED, "admission"),
    BootstrapPhase.CHILD_ADMITTED: (BootstrapPhase.CHILD_EXECUTED, "broker"),
    BootstrapPhase.CHILD_EXECUTED: (BootstrapPhase.CHILD_VERIFIED, "verifier"),
    BootstrapPhase.CHILD_VERIFIED: (
        BootstrapPhase.CAPABILITY_ADMITTED,
        "capability-admission",
    ),
    BootstrapPhase.CAPABILITY_ADMITTED: (
        BootstrapPhase.PARENT_RESUMED,
        "parent-controller",
    ),
}


def advance_bootstrap(
    state: BootstrapState,
    *,
    target: BootstrapPhase,
    receipt: TransitionReceipt | None,
) -> BootstrapDecision:
    expected = _EXPECTED.get(state.phase)
    if expected is None or expected[0] is not target:
        return BootstrapDecision(
            BootstrapStanding.REFUSED_WRONG_PHASE,
            state,
            f"{state.phase.value} cannot transition directly to {target.value}",
        )
    if receipt is None or not receipt.receipt_id.strip() or not receipt.issuer.strip():
        return BootstrapDecision(
            BootstrapStanding.REFUSED_MISSING_RECEIPT,
            state,
            "transition requires a receipt from the authority-owning component",
        )

    expected_subject = (
        state.parent_id if target is BootstrapPhase.PARENT_RESUMED else state.child_id
    )
    if receipt.subject_id != expected_subject:
        return BootstrapDecision(
            BootstrapStanding.REFUSED_SUBJECT_MISMATCH,
            state,
            f"receipt subject {receipt.subject_id!r} does not bind {expected_subject!r}",
        )
    if not receipt.verified:
        return BootstrapDecision(
            BootstrapStanding.REFUSED_UNVERIFIED,
            state,
            "unverified receipt cannot advance bootstrap standing",
        )

    next_state = replace(
        state,
        phase=target,
        receipt_ids=state.receipt_ids + (receipt.receipt_id,),
    )
    return BootstrapDecision(
        BootstrapStanding.ADVANCED,
        next_state,
        f"advanced by {expected[1]} receipt; no actuation performed by controller",
    )
