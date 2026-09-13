# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Project the agent's occurrence ledger into an OCEL 2.0 log.

What this is
------------
A **one-way projection**: ledger lines in, :class:`~autofde_lab.ocel.log.OcelLog`
out. The ledger stays the authoritative record; the OCEL log is a rendering of
it in a standard interchange shape, and re-reading the log back is not a way to
learn anything the ledger did not already say.

What this is emphatically not
-----------------------------
Emitting an OCEL log is **not evidence that anything ran, was admitted, was
actuated, or was verified**. It is the same class of act as
``fabric/powl.py``'s Turtle projection: it manufactures a document. A document
is not an execution.

The direction of the dependency is load-bearing
-----------------------------------------------
This module imports :mod:`autofde_lab.ocel`; :mod:`autofde_lab.ocel` must never
import this module. ``OcelLog.validate()`` and ``validate_locality()`` are the
laws a projection is judged *against*, and a validator that knew about its
one producer could be shaped -- deliberately or by drift -- to admit exactly
what that producer emits. That is self-attestation: the thing being checked
supplying the check. ``tests/ocel/test_no_self_attestation.py`` asserts the
absence of the back-edge mechanically, because a convention nobody can execute
is not a control.

Refusal over repair
-------------------
An OCEL event must carry at least one qualified object reference (OCPQ
Definition 2, p. 6 -- see :meth:`~autofde_lab.ocel.log.OcelLog.validate` law 1).
A ``COMMITTED`` ledger record with no objects therefore cannot become a
conformant event. This module **refuses** it by name
(:data:`SinkRefusal.COMMITTED_RECORD_HAS_NO_OBJECTS`) rather than inventing a
placeholder object to get past ``validate()``. Inventing one would produce a
log that passes every structural law while asserting a relationship nobody
recorded -- a false statement with a green check next to it, which is worse
than a refusal.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Iterable, Mapping, Sequence

from autofde_lab.agent.ledger import (
    LedgerPhase,
    LedgerRecord,
    ObjectRef,
    OccurrenceLedger,
)
from autofde_lab.ocel.log import OcelLog
from autofde_lab.ocel.model import OcelAttributeValue, OcelObject

__all__ = [
    "LifecyclePhase",
    "SinkRefusal",
    "OcelSinkError",
    "OcelSink",
]


class LifecyclePhase(StrEnum):
    """The agent-lifecycle phases an OCEL event may record.

    Two of these -- ``INTENDED`` and ``COMMITTED`` -- come straight from the
    write-ahead ledger. The rest describe decisions the ledger does not model,
    and must be supplied explicitly by whoever made them: this module never
    infers that something was refused, superseded, replanned, or granted
    authority.
    """

    INTENDED = "intended"
    COMMITTED = "committed"
    REFUSED = "refused"
    SUPERSEDED = "superseded"
    REPLANNED = "replanned"
    AUTHORITY_REQUESTED = "authority-requested"
    AUTHORITY_GRANTED = "authority-granted"
    AUTHORITY_REFUSED = "authority-refused"


class SinkRefusal(StrEnum):
    """Named refusals. Every one of them is a refusal to fabricate."""

    #: A ``COMMITTED`` record referenced no object, so no conformant event
    #: exists for it. Never repaired by minting a placeholder object.
    COMMITTED_RECORD_HAS_NO_OBJECTS = "SKD-SINK-001"

    #: An object was referenced whose OCEL type the caller never declared.
    #: An object type is time-stable under OCPQ Definition 2; guessing one
    #: would fix a value that nothing can later correct.
    UNDECLARED_OBJECT_TYPE = "SKD-SINK-002"

    #: Two events would carry the same id, making ``E`` a multiset.
    DUPLICATE_EVENT_ID = "SKD-SINK-003"

    #: A phase event carried no object references at all.
    PHASE_EVENT_HAS_NO_OBJECTS = "SKD-SINK-004"


class OcelSinkError(ValueError):
    """A sink refusal carrying its code, never a bare string."""

    def __init__(self, refusal: SinkRefusal, detail: str = "") -> None:
        super().__init__(f"{refusal.value}: {detail}" if detail else refusal.value)
        self.refusal = refusal
        self.detail = detail


def _attrs(
    *,
    phase: LifecyclePhase,
    decision_epoch: int,
    commitment_digest: str,
    context_sha256: str,
    occurrence_index: int | None,
) -> dict[str, OcelAttributeValue]:
    """The four facts every projected event carries, plus its phase."""
    attributes = {
        "phase": OcelAttributeValue.string(phase.value),
        "decisionEpoch": OcelAttributeValue.integer(int(decision_epoch)),
        "commitmentDigest": OcelAttributeValue.string(commitment_digest),
        "contextDigest": OcelAttributeValue.string(context_sha256),
    }
    attributes["occurrenceIndex"] = (
        OcelAttributeValue.integer(int(occurrence_index))
        if occurrence_index is not None
        else OcelAttributeValue.null()
    )
    return attributes


@dataclass(frozen=True, slots=True)
class OcelSink:
    """An accumulating, immutable projection of ledger lines into OCEL.

    ``object_types`` must declare an OCEL type for every object id the ledger
    references. It is required rather than inferred: a ledger object reference
    is ``(object_id, qualifier)`` and carries no type, and an object's type is
    time-stable, so a guess made once could never be corrected.
    """

    object_types: Mapping[str, str]
    decision_epoch: int = 0
    commitment_digest: str = ""
    log: OcelLog = field(default_factory=OcelLog)

    # ── objects ────────────────────────────────────────────────────────────

    def _declare(self, log: OcelLog, refs: Sequence[ObjectRef]) -> OcelLog:
        known = {o.id for o in log.objects}
        fresh: list[OcelObject] = []
        for object_id, _qualifier in refs:
            if object_id in known:
                continue
            object_type = self.object_types.get(object_id)
            if object_type is None:
                raise OcelSinkError(
                    SinkRefusal.UNDECLARED_OBJECT_TYPE,
                    f"object {object_id!r} has no declared OCEL type; "
                    "the sink never guesses one",
                )
            known.add(object_id)
            fresh.append(OcelObject(object_id, object_type))
        return log.with_objects(*fresh) if fresh else log

    # ── ledger projection ──────────────────────────────────────────────────

    def absorb(
        self, ledger: OccurrenceLedger, *, include_intended: bool = False
    ) -> "OcelSink":
        """Project a ledger. Every ``COMMITTED`` record becomes one event.

        ``include_intended`` also emits the outstanding ``INTENDED`` lines, on
        a distinct ``#INTENDED`` event id so an intent can never be mistaken
        for the commit that may not have followed it. Off by default: a log of
        what an agent *decided* and a log of what it *recorded completing* are
        different claims, and the second is the default one.
        """
        log = self.log
        seen = {e.id for e in log.events}
        settled = {r.token_id for r in ledger.committed()}

        for record in ledger.records():
            if record.phase is LedgerPhase.COMMITTED:
                log = self._append_record(log, record, record.token_id, seen)
            elif include_intended and record.token_id not in settled:
                log = self._append_record(
                    log, record, f"{record.token_id}#INTENDED", seen
                )
        return replace(self, log=log)

    def _append_record(
        self, log: OcelLog, record: LedgerRecord, event_id: str, seen: set[str]
    ) -> OcelLog:
        phase = (
            LifecyclePhase.COMMITTED
            if record.phase is LedgerPhase.COMMITTED
            else LifecyclePhase.INTENDED
        )
        if not record.objects:
            refusal = (
                SinkRefusal.COMMITTED_RECORD_HAS_NO_OBJECTS
                if phase is LifecyclePhase.COMMITTED
                else SinkRefusal.PHASE_EVENT_HAS_NO_OBJECTS
            )
            raise OcelSinkError(
                refusal,
                f"ledger record {record.sequence} ({record.phase.value}) at path "
                f"{list(record.path)} references no object; an OCEL event needs "
                "at least one qualified reference and the sink will not mint one",
            )
        if event_id in seen:
            raise OcelSinkError(
                SinkRefusal.DUPLICATE_EVENT_ID,
                f"event id {event_id!r} already in the log",
            )
        seen.add(event_id)
        log = self._declare(log, record.objects)
        return log.append_event(
            event_id,
            record.activity or record.activity_sha256,
            list(record.objects),
            timestamp_ns=record.timestamp_ns,
            attributes=_attrs(
                phase=phase,
                decision_epoch=self.decision_epoch,
                commitment_digest=self.commitment_digest,
                context_sha256=record.context_sha256,
                occurrence_index=record.occurrence_index,
            ),
        )

    # ── phases the ledger does not model ───────────────────────────────────

    def note(
        self,
        phase: LifecyclePhase,
        event_id: str,
        activity: str,
        objects: Iterable[ObjectRef],
        *,
        timestamp_ns: int = 0,
        context_sha256: str = "",
        occurrence_index: int | None = None,
    ) -> "OcelSink":
        """Record a lifecycle phase the write-ahead ledger has no line for.

        Refusals, supersessions, replans and the three authority phases are
        decisions made *about* a traversal rather than steps within one. They
        are recorded here only because a caller states them; nothing in this
        module infers one.
        """
        refs = tuple((str(o), str(q)) for o, q in objects)
        if not refs:
            raise OcelSinkError(
                SinkRefusal.PHASE_EVENT_HAS_NO_OBJECTS,
                f"{phase.value} event {event_id!r} references no object",
            )
        if event_id in {e.id for e in self.log.events}:
            raise OcelSinkError(
                SinkRefusal.DUPLICATE_EVENT_ID,
                f"event id {event_id!r} already in the log",
            )
        log = self._declare(self.log, refs)
        log = log.append_event(
            event_id,
            activity,
            list(refs),
            timestamp_ns=timestamp_ns,
            attributes=_attrs(
                phase=phase,
                decision_epoch=self.decision_epoch,
                commitment_digest=self.commitment_digest,
                context_sha256=context_sha256,
                occurrence_index=occurrence_index,
            ),
        )
        return replace(self, log=log)

    # ── output ─────────────────────────────────────────────────────────────

    def validated(self, *, strict_qualifiers: bool = True) -> OcelLog:
        """The log, checked against the OCEL laws it did not author.

        ``strict_qualifiers`` defaults to **on** here although
        :meth:`~autofde_lab.ocel.log.OcelLog.validate` defaults it off: the ledger
        always carries a qualifier per reference, so an unqualified one coming
        out of this sink is a defect in this module, not a conformant third
        party log being rejected.
        """
        return self.log.validate(strict_qualifiers=strict_qualifiers)

    def activities(self) -> tuple[str, ...]:
        """Event activities in log order -- the history the OCEL log asserts."""
        return tuple(e.activity for e in self.log.events)
