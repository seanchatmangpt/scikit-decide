"""The one broker shape kept from mfw's multiple parallel Broker lineages (per the
ERRC grid's Eliminate row): ``crates/pcp/mfw-pcp-broker``'s generic
``Broker<A: Actuator, V: PostconditionVerifier>`` — chosen because it is the cleanest,
ontology-free implementation, and because its two-trait split (the thing that acts and
the thing that checks are never the same code path) is mfw's single highest-leverage
discipline per this session's exploration ("the executor must not mint its own
authority").

Method names (``open``, ``actuate``, ``close``) match the Rust source 1:1 on purpose —
this is the part of the ERRC grid's "Create" row that is meant to survive verbatim into
a future Rust rewrite; only the digest algorithm and the generic-type machinery were
reduced away.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

from .cert import Certificate
from .core import Digest


class BrokerError(RuntimeError):
    """Base for every broker refusal. Subclasses name the exact reason, mirroring
    mfw-pcp-broker's ``BrokerError`` variants (``TokenAlreadyConsumed``,
    ``ConcurrentOpenUnsupported``, ...)."""


class TokenAlreadyConsumed(BrokerError):
    pass


class ConcurrentOpenUnsupported(BrokerError):
    pass


class UnknownToken(BrokerError):
    pass


class ColludingRoles(BrokerError):
    """Refused at construction: ``actuator`` and ``verifier`` are the same object.
    A single object wired into both roles can lie about verification with nothing
    in ``actuate``/``replay.verify`` able to catch it after the fact — the digest
    chain only proves the receipt wasn't tampered with post-issuance, not that the
    verifier's ``bool`` was honest. This is a real, adversarially-confirmed gap
    (see ``tests/test_broker_receipt_replay.py::test_colluding_actuator_and_verifier_is_refused``
    and the docstring note below); refusing identical objects at construction closes
    the cheap, no-effort version of the attack. It does NOT close the harder case of
    two *distinct* objects that collude out-of-band (e.g. sharing a closure over
    mutable state) -- that is out of scope for an identity check and is not claimed
    to be fixed here."""


class EffectOutcome(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class Actuator(Protocol):
    """Sole effect interface. Exactly one ``Actuator`` implementation is ever wired
    into a ``Broker`` — it is not the ``Broker``'s job to guess which one, and it is
    not the ``Actuator``'s job to also verify its own effect (see
    ``PostconditionVerifier``)."""

    def actuate(self, action: dict) -> dict:
        """Perform the action, return evidence (a plain dict). May raise — the
        ``Broker`` converts an exception into a receipted ``FAILED`` outcome rather
        than letting it propagate unreceipted."""
        ...

    def adapter_digest(self) -> str:
        ...


class PostconditionVerifier(Protocol):
    """Structurally separate from ``Actuator`` on purpose: a compromised/buggy
    actuator cannot self-certify its own effect. Called independently, even when the
    actuator raised."""

    def verify(self, action: dict, evidence: dict | None) -> bool:
        ...

    def verifier_digest(self) -> str:
        ...


@dataclass(frozen=True)
class ActionToken:
    value: str


@dataclass(frozen=True)
class OpenedAction:
    token: ActionToken
    receipt: Certificate


@dataclass(frozen=True)
class ClosedAction:
    outcome: EffectOutcome
    postcondition_satisfied: bool
    receipt: Certificate


@dataclass
class _OpenSlot:
    action: dict
    open_receipt_digest: str
    opened_at_ms: int


def _now_ms() -> int:
    return int(time.time() * 1000)


@dataclass
class Broker:
    """``Broker<A, V>`` reduced to plain composition (Python has no generics
    ceremony worth paying for here): holds exactly one ``Actuator`` and one
    ``PostconditionVerifier``, enforces single in-flight transaction, single-use
    tokens, and a mandatory close receipt on every branch."""

    actuator: Actuator
    verifier: PostconditionVerifier
    _open: dict[str, _OpenSlot] = field(default_factory=dict)
    _consumed: set[str] = field(default_factory=set)
    _sequence: int = 0
    _previous_receipt_digest: str = field(default_factory=lambda: str(Digest.genesis()))

    def __post_init__(self) -> None:
        if self.actuator is self.verifier:
            raise ColludingRoles(
                "actuator and verifier must not be the same object: a colluding "
                "object could actuate an action and then silently rubber-stamp its "
                "own effect, defeating the whole point of a separate verifier"
            )

    def open(self, action: dict) -> OpenedAction:
        if self._open:
            raise ConcurrentOpenUnsupported(
                "a transaction is already open; close it before opening another"
            )
        self._sequence += 1
        token = ActionToken(value=f"tok-{self._sequence}-{_now_ms()}")
        body = {
            "sequence": self._sequence,
            "action": action,
            "previous_receipt_digest": self._previous_receipt_digest,
            "opened_at_ms": _now_ms(),
        }
        receipt = Certificate(kind="open", body=body, issued_at_ms=body["opened_at_ms"])
        digest = str(receipt.certificate_digest())
        self._open[token.value] = _OpenSlot(
            action=action, open_receipt_digest=digest, opened_at_ms=body["opened_at_ms"]
        )
        self._previous_receipt_digest = digest
        return OpenedAction(token=token, receipt=receipt)

    def actuate(self, token: ActionToken) -> ClosedAction:
        if token.value in self._consumed:
            raise TokenAlreadyConsumed(f"token {token.value!r} already consumed")
        slot = self._open.pop(token.value, None)
        if slot is None:
            raise UnknownToken(f"token {token.value!r} is not open")
        self._consumed.add(token.value)

        evidence: dict | None
        try:
            evidence = self.actuator.actuate(slot.action)
            outcome = EffectOutcome.SUCCEEDED
        except Exception as exc:  # noqa: BLE001 - deliberately broad: must still receipt
            evidence = {"error": str(exc)}
            outcome = EffectOutcome.FAILED

        postcondition_satisfied = False
        if outcome == EffectOutcome.SUCCEEDED:
            postcondition_satisfied = bool(
                self.verifier.verify(slot.action, evidence)
            )

        body = {
            "sequence": self._sequence,
            "action": slot.action,
            "open_receipt_digest": slot.open_receipt_digest,
            "previous_receipt_digest": slot.open_receipt_digest,
            "outcome": outcome.value,
            "postcondition_satisfied": postcondition_satisfied,
            "evidence": evidence,
            "closed_at_ms": _now_ms(),
        }
        receipt = Certificate(kind="close", body=body, issued_at_ms=body["closed_at_ms"])
        self._previous_receipt_digest = str(receipt.certificate_digest())
        return ClosedAction(
            outcome=outcome,
            postcondition_satisfied=postcondition_satisfied,
            receipt=receipt,
        )
