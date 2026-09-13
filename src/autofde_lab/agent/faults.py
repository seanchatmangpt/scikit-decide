# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Deterministic fault matrix: every fault gets exactly one lawful outcome.

Why this exists
---------------
An agent that hits a fault with no classification has no lawful next move. It
then does the one thing that is never safe — it guesses, usually by continuing.
This module makes the guess impossible: :func:`classify` is a **pure, total**
function from a :class:`FaultObservation` to exactly one :class:`FaultOutcome`.
No I/O, no wall clock, no default branch. Same input, same outcome, always.

What this module does **not** do
--------------------------------
Nothing here actuates, admits, retries, or repairs. An outcome is a *label on
a decision* — the same claim ceiling :class:`~autofde_lab.agent.replan.ReplanningMode`
carries. ``REQUEST_NEW_AUTHORITY`` in particular is a request; this repository
never grants authority.

Honesty about mechanism
-----------------------
Three of the eleven faults are classified by **real logic** that inspects real
state and can therefore fail:

* :attr:`FaultKind.TORN_FIRE` — derived from
  :meth:`~autofde_lab.agent.ledger.OccurrenceLedger.outstanding`; see
  :func:`observe_torn_fire`.
* :attr:`FaultKind.DUPLICATE_OBSERVATION` — derived from committed
  :class:`~autofde_lab.powl.identity.OccurrenceKey` membership; see
  :func:`observe_duplicate_observation`.
* :attr:`FaultKind.LABEL_CONTEXT_COLLISION` — derived from ``OccurrenceKey``
  inequality under equal ``activity_sha256``; see
  :func:`observe_label_context_collision`.

Two more carry real arithmetic — :attr:`FaultKind.DOWNSTREAM_TIMEOUT` and
:attr:`FaultKind.EVIDENCE_SINK_UNAVAILABLE` compare ``attempt`` against
``retry_bound`` and flip to ``REFUSE`` once it is spent (:func:`_retry`).

The remaining six (``OUT_OF_ORDER_OBSERVATION``, ``NOTIFICATION_REJECTED``,
``IDENTITY_FORBIDDEN``, ``AUTHORITY_EXPIRED``, ``POPULATION_EXPANDED``,
``POSTCONDITION_UNCONFIRMED``) are a **declared mapping**: a table lookup with
no mechanism behind it yet. They are correct as policy and carry zero evidence
that any component implements the response. Do not read them as ``ALIVE``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable

from autofde_lab.agent.ledger import OccurrenceLedger
from autofde_lab.agent.refusals import AgentRefusalCode
from autofde_lab.powl.identity import OccurrenceKey

__all__ = [
    "FaultKind",
    "FaultOutcome",
    "FaultObservation",
    "FaultClassification",
    "classify",
    "observe_torn_fire",
    "observe_duplicate_observation",
    "observe_label_context_collision",
    "DECLARED_MAPPING_ONLY",
]


class FaultKind(StrEnum):
    """The eleven faults this runtime is required to classify."""

    DUPLICATE_OBSERVATION = "DUPLICATE_OBSERVATION"
    OUT_OF_ORDER_OBSERVATION = "OUT_OF_ORDER_OBSERVATION"
    DOWNSTREAM_TIMEOUT = "DOWNSTREAM_TIMEOUT"
    NOTIFICATION_REJECTED = "NOTIFICATION_REJECTED"
    EVIDENCE_SINK_UNAVAILABLE = "EVIDENCE_SINK_UNAVAILABLE"
    IDENTITY_FORBIDDEN = "IDENTITY_FORBIDDEN"
    AUTHORITY_EXPIRED = "AUTHORITY_EXPIRED"
    POPULATION_EXPANDED = "POPULATION_EXPANDED"
    POSTCONDITION_UNCONFIRMED = "POSTCONDITION_UNCONFIRMED"
    LABEL_CONTEXT_COLLISION = "LABEL_CONTEXT_COLLISION"
    TORN_FIRE = "TORN_FIRE"


class FaultOutcome(StrEnum):
    """The only lawful next moves. Exactly one is assigned per fault."""

    CONTINUE = "continue"
    REPAIR = "repair"
    REPLAN = "replan"
    REQUEST_NEW_AUTHORITY = "request_new_authority"
    RETRY_WITHIN_BOUND = "retry_within_bound"
    REFUSE = "refuse"
    #: Reachable, and never a synonym for "probably fine". An ``UNKNOWN``
    #: outcome means the classifier declines to say, and the caller must not
    #: proceed on its own judgement.
    UNKNOWN = "unknown"


#: Faults whose outcome is a policy table entry with no mechanism behind it.
#: Kept as data so a reader — and a test — can see the honest boundary rather
#: than inferring it from prose.
DECLARED_MAPPING_ONLY: frozenset[FaultKind] = frozenset(
    {
        FaultKind.OUT_OF_ORDER_OBSERVATION,
        FaultKind.NOTIFICATION_REJECTED,
        FaultKind.IDENTITY_FORBIDDEN,
        FaultKind.AUTHORITY_EXPIRED,
        FaultKind.POPULATION_EXPANDED,
        FaultKind.POSTCONDITION_UNCONFIRMED,
    }
)


@dataclass(frozen=True, slots=True)
class FaultObservation:
    """Everything :func:`classify` is allowed to look at.

    Deliberately a value, not a handle: the classifier cannot reach a socket,
    a file, or a clock through it, so it cannot become nondeterministic later
    without the type changing first.
    """

    kind: FaultKind
    #: 1-based attempt number for a retryable fault.
    attempt: int = 1
    #: Ceiling on ``attempt``. ``retry_within_bound`` is not unbounded retry
    #: wearing a different name — once ``attempt >= retry_bound`` the outcome
    #: becomes ``REFUSE``.
    retry_bound: int = 3
    #: True only when the ledger shows an ``INTENDED`` with no ``COMMITTED``.
    torn: bool = False
    #: True when the same occurrence key is already committed.
    already_committed: bool = False
    #: True when two occurrences share ``activity_sha256`` but differ in
    #: ``context_sha256``.
    context_diverged: bool = False
    #: True only when two occurrence keys were actually compared. Without it,
    #: ``context_diverged=False`` is indistinguishable from "nobody looked",
    #: and treating "nobody looked" as ``CONTINUE`` is precisely the silent
    #: guess this module exists to remove.
    keys_compared: bool = False
    detail: str = ""


@dataclass(frozen=True, slots=True)
class FaultClassification:
    """The verdict: one outcome, plus why, plus a refusal code when refusing."""

    kind: FaultKind
    outcome: FaultOutcome
    reason: str
    refusal_code: AgentRefusalCode | None = None
    mechanism_backed: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind.value,
            "outcome": self.outcome.value,
            "reason": self.reason,
            "refusal_code": None if self.refusal_code is None else self.refusal_code.value,
            "mechanism_backed": self.mechanism_backed,
        }


def _retry(obs: FaultObservation, what: str) -> FaultClassification:
    """Bounded retry, or a named refusal once the bound is spent."""
    if obs.attempt >= obs.retry_bound:
        return FaultClassification(
            obs.kind,
            FaultOutcome.REFUSE,
            f"{what}: retry bound {obs.retry_bound} exhausted at attempt {obs.attempt}",
            AgentRefusalCode.BOUND_EXHAUSTED,
            mechanism_backed=True,
        )
    return FaultClassification(
        obs.kind,
        FaultOutcome.RETRY_WITHIN_BOUND,
        f"{what}: attempt {obs.attempt} of {obs.retry_bound}",
        mechanism_backed=True,
    )


def classify(obs: FaultObservation) -> FaultClassification:
    """Pure, total fault -> outcome. No I/O, no clock, no default branch.

    The ``match`` below enumerates every :class:`FaultKind` member explicitly.
    Adding a member without a case falls through to the final ``case _``, which
    raises rather than returning ``CONTINUE`` — an unclassified fault must be
    loud, not benign.
    """
    if not isinstance(obs, FaultObservation):  # pragma: no cover - type guard
        raise TypeError(f"classify expects FaultObservation, got {type(obs).__name__}")

    match obs.kind:
        case FaultKind.TORN_FIRE:
            # The one state recovery cannot resolve. "Acted, did not record"
            # and "did not act" are indistinguishable from here; assuming
            # either loses an action or double-fires one. So: refuse.
            return FaultClassification(
                obs.kind,
                FaultOutcome.REFUSE,
                "INTENDED with no COMMITTED; recovery state is UNKNOWN and "
                "the session refuses to resume",
                AgentRefusalCode.LEDGER_UNRESUMABLE,
                mechanism_backed=True,
            )

        case FaultKind.DUPLICATE_OBSERVATION:
            # Only lawful because the occurrence key is already committed —
            # this is the single place `continue` is allowed, and it is
            # allowed by evidence, not by optimism.
            if not obs.already_committed:
                return FaultClassification(
                    obs.kind,
                    FaultOutcome.UNKNOWN,
                    "claimed duplicate, but no committed occurrence supports it",
                    mechanism_backed=True,
                )
            return FaultClassification(
                obs.kind,
                FaultOutcome.CONTINUE,
                "occurrence key already committed; the observation adds nothing",
                mechanism_backed=True,
            )

        case FaultKind.LABEL_CONTEXT_COLLISION:
            # Same label, same bindings, different world state. The occurrence
            # keys differ in context_sha256, so they are two occurrences and a
            # plan decided against the older context no longer holds.
            if not obs.keys_compared:
                return FaultClassification(
                    obs.kind,
                    FaultOutcome.UNKNOWN,
                    "collision claimed without comparing occurrence keys; "
                    "'nobody looked' is not evidence of sameness",
                    mechanism_backed=True,
                )
            if not obs.context_diverged:
                return FaultClassification(
                    obs.kind,
                    FaultOutcome.CONTINUE,
                    "same activity and same context: genuinely one occurrence",
                    mechanism_backed=True,
                )
            return FaultClassification(
                obs.kind,
                FaultOutcome.REPLAN,
                "identical activity_sha256 with divergent context_sha256: two "
                "distinct occurrences, decided against different world states",
                mechanism_backed=True,
            )

        case FaultKind.DOWNSTREAM_TIMEOUT:
            return _retry(obs, "downstream call timed out")

        case FaultKind.EVIDENCE_SINK_UNAVAILABLE:
            return _retry(obs, "evidence sink unavailable")

        case FaultKind.OUT_OF_ORDER_OBSERVATION:
            return FaultClassification(
                obs.kind,
                FaultOutcome.REPAIR,
                "observation order violates append order; the log is "
                "reorderable without changing what happened",
            )

        case FaultKind.NOTIFICATION_REJECTED:
            return FaultClassification(
                obs.kind,
                FaultOutcome.REPAIR,
                "capture rejected the payload; the payload is reformable "
                "without changing the decision",
            )

        case FaultKind.IDENTITY_FORBIDDEN:
            return FaultClassification(
                obs.kind,
                FaultOutcome.REQUEST_NEW_AUTHORITY,
                "identity received 403; this runtime requests authority and "
                "never grants it",
            )

        case FaultKind.AUTHORITY_EXPIRED:
            return FaultClassification(
                obs.kind,
                FaultOutcome.REQUEST_NEW_AUTHORITY,
                "authority expired before delivery; a fresh grant must come "
                "from a broker, not from here",
            )

        case FaultKind.POPULATION_EXPANDED:
            return FaultClassification(
                obs.kind,
                FaultOutcome.REPLAN,
                "population expanded after containment; the plan's scope "
                "premise no longer holds",
            )

        case FaultKind.POSTCONDITION_UNCONFIRMED:
            return FaultClassification(
                obs.kind,
                FaultOutcome.UNKNOWN,
                "containment postcondition could not be confirmed; observation "
                "is insufficient to classify and this is not 'probably fine'",
            )

        case _:  # pragma: no cover - reached only by an unclassified new member
            raise ValueError(
                f"unclassified FaultKind: {obs.kind!r}; every member must have "
                "an explicit case in classify()"
            )


# ── derivations: the three faults with real state behind them ───────────────


def observe_torn_fire(ledger: OccurrenceLedger) -> FaultObservation | None:
    """A ``TORN_FIRE`` observation, or ``None`` when the ledger is resumable."""
    outstanding = ledger.outstanding()
    if not outstanding:
        return None
    return FaultObservation(
        FaultKind.TORN_FIRE,
        torn=True,
        detail=f"outstanding={[t.token_id for t in outstanding]}",
    )


def observe_duplicate_observation(
    committed: Iterable[OccurrenceKey], key: OccurrenceKey
) -> FaultObservation:
    """A ``DUPLICATE_OBSERVATION`` observation keyed on real committed state."""
    return FaultObservation(
        FaultKind.DUPLICATE_OBSERVATION,
        already_committed=key in set(committed),
        detail=str(key),
    )


def observe_label_context_collision(
    left: OccurrenceKey, right: OccurrenceKey
) -> FaultObservation:
    """Detect same-content/different-meaning between two occurrence keys.

    ``activity_sha256`` cannot separate them — only ``context_sha256`` can.
    """
    return FaultObservation(
        FaultKind.LABEL_CONTEXT_COLLISION,
        keys_compared=True,
        context_diverged=(
            left.activity_sha256 == right.activity_sha256
            and left.context_sha256 != right.context_sha256
        ),
        detail=f"{left} vs {right}",
    )
