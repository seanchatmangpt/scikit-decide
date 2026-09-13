"""Minimal Brokered Receipted Consequential Execution (BRCE) experiment kernel.

The kernel is intentionally provider-neutral. It is the only function in this module that calls
an actuator, and it cannot return a successful consequence without independently observing and
verifying the postcondition and manufacturing a content-bound receipt. Lost acknowledgement
after possible actuation is ``UNCERTAIN`` and must be reconciled; it is never blindly retried.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Callable, Mapping


class BrceStanding(str, Enum):
    ALIVE = "ALIVE"
    REFUSED_POLICY = "REFUSED:POLICY"
    REFUSED_AUTHORITY = "REFUSED:AUTHORITY"
    REFUSED_VERIFICATION = "REFUSED:VERIFICATION"
    UNCERTAIN = "UNCERTAIN"
    REPLAY_MATCH = "REPLAY_MATCH"
    REPLAY_DRIFT = "REPLAY_DRIFT"


@dataclass(frozen=True, slots=True)
class ActuationIntent:
    intent_id: str
    subject_id: str
    principal_id: str
    capability: str
    resource: str
    intended_effect: Mapping[str, object]
    idempotency_key: str
    planner_id: str = ""
    environment_id: str = ""
    revision_id: str = ""


@dataclass(frozen=True, slots=True)
class Authority:
    principal_id: str
    capabilities: frozenset[str]
    resources: frozenset[str]


@dataclass(frozen=True, slots=True)
class ActuationResult:
    acknowledgement: str | None
    effect_evidence: Mapping[str, object]
    possibly_actuated: bool = True


@dataclass(frozen=True, slots=True)
class BrceReceipt:
    receipt_id: str
    intent_digest: str
    policy_digest: str
    authority_digest: str
    acknowledgement: str
    effect_digest: str
    postcondition_digest: str
    verifier_digest: str
    standing: BrceStanding


@dataclass(frozen=True, slots=True)
class BrceDecision:
    standing: BrceStanding
    receipt: BrceReceipt | None
    reason: str


def _digest(value: object) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), default=str
    ).encode()
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _authorized(intent: ActuationIntent, authority: Authority) -> bool:
    return (
        intent.principal_id == authority.principal_id
        and intent.capability in authority.capabilities
        and intent.resource in authority.resources
    )


def execute_brce(
    intent: ActuationIntent,
    *,
    authority: Authority,
    policy_id: str,
    policy_admits: Callable[[ActuationIntent], bool],
    actuator: Callable[[ActuationIntent], ActuationResult],
    observer: Callable[[ActuationIntent, ActuationResult], Mapping[str, object]],
    verifier_id: str,
    verifier: Callable[[ActuationIntent, Mapping[str, object]], bool],
) -> BrceDecision:
    """Execute exactly one admitted intent and return its causal receipt.

    ``actuator`` is called at most once. No caller-visible success path exists without a receipt.
    The observer receives the actuator result but must obtain/construct the postcondition view
    independently of the actuator's success assertion; the verifier judges that view.
    """

    if not _authorized(intent, authority):
        return BrceDecision(
            BrceStanding.REFUSED_AUTHORITY,
            None,
            "principal/capability/resource is outside admitted authority",
        )
    if not policy_admits(intent):
        return BrceDecision(
            BrceStanding.REFUSED_POLICY,
            None,
            "autonomous policy refused the admitted principal authority",
        )

    result = actuator(intent)
    if result.acknowledgement is None and result.possibly_actuated:
        return BrceDecision(
            BrceStanding.UNCERTAIN,
            None,
            "actuation may have occurred but acknowledgement was lost; reconcile before retry",
        )
    if result.acknowledgement is None:
        return BrceDecision(
            BrceStanding.REFUSED_VERIFICATION,
            None,
            "actuator produced no acknowledgement or receiptable consequence",
        )

    postcondition = observer(intent, result)
    if not verifier(intent, postcondition):
        return BrceDecision(
            BrceStanding.REFUSED_VERIFICATION,
            None,
            "independent postcondition verifier rejected observed consequence",
        )

    intent_digest = _digest(asdict(intent))
    policy_digest = _digest({"policy_id": policy_id})
    authority_digest = _digest(asdict(authority))
    effect_digest = _digest(dict(result.effect_evidence))
    postcondition_digest = _digest(dict(postcondition))
    verifier_digest = _digest({"verifier_id": verifier_id})
    receipt_payload = {
        "intent": intent_digest,
        "policy": policy_digest,
        "authority": authority_digest,
        "ack": result.acknowledgement,
        "effect": effect_digest,
        "postcondition": postcondition_digest,
        "verifier": verifier_digest,
    }
    receipt = BrceReceipt(
        receipt_id=_digest(receipt_payload),
        intent_digest=intent_digest,
        policy_digest=policy_digest,
        authority_digest=authority_digest,
        acknowledgement=result.acknowledgement,
        effect_digest=effect_digest,
        postcondition_digest=postcondition_digest,
        verifier_digest=verifier_digest,
        standing=BrceStanding.ALIVE,
    )
    return BrceDecision(BrceStanding.ALIVE, receipt, "verified consequence receipted")


def replay_receipt(
    receipt: BrceReceipt,
    intent: ActuationIntent,
    *,
    authority: Authority,
    policy_id: str,
    acknowledgement: str,
    effect_evidence: Mapping[str, object],
    postcondition: Mapping[str, object],
    verifier_id: str,
) -> BrceStanding:
    current = (
        _digest(asdict(intent)),
        _digest({"policy_id": policy_id}),
        _digest(asdict(authority)),
        acknowledgement,
        _digest(dict(effect_evidence)),
        _digest(dict(postcondition)),
        _digest({"verifier_id": verifier_id}),
    )
    expected = (
        receipt.intent_digest,
        receipt.policy_digest,
        receipt.authority_digest,
        receipt.acknowledgement,
        receipt.effect_digest,
        receipt.postcondition_digest,
        receipt.verifier_digest,
    )
    return (
        BrceStanding.REPLAY_MATCH if current == expected else BrceStanding.REPLAY_DRIFT
    )
