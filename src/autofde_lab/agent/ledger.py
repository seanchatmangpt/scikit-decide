# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Two-phase (write-ahead) occurrence ledger.

Why two phases and not one
--------------------------
A single ``record(occurrence)`` written *after* an act cannot distinguish two
crash states that demand opposite recoveries:

* the act happened and the record was lost — resuming re-executes it;
* the act never happened — refusing to resume strands work that was never done.

Guessing either way corrupts the no-re-execution guarantee. So :meth:`intend`
writes an ``INTENDED`` record **before** the act and :meth:`commit` writes
``COMMITTED`` after. An ``INTENDED`` with no matching ``COMMITTED`` is exactly
the unknown state, and the only sound response is to refuse to resume
(``SKD-AGENT-006``) and hand the decision to something with more standing than
this runtime has.

Nothing here actuates or admits. A record is a note about a candidate-plan
traversal, not a receipt for a change to the world.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Iterable, Sequence

from autofde_lab.agent.refusals import AgentRefusal, AgentRefusalCode
from autofde_lab.fabric.canonical import sha256
from autofde_lab.powl.identity import OccurrenceKey

__all__ = [
    "LedgerPhase",
    "IntentToken",
    "LedgerRecord",
    "OccurrenceLedger",
]


class LedgerPhase(StrEnum):
    """The two phases of a write-ahead occurrence record."""

    INTENDED = "INTENDED"
    COMMITTED = "COMMITTED"


#: One qualified object reference: ``(object_id, qualifier)``.
ObjectRef = tuple[str, str]


def _as_objects(objects: Iterable[Sequence[str]] | None) -> tuple[ObjectRef, ...]:
    """Normalize an object-reference iterable, refusing malformed pairs.

    A bare object id is **not** accepted here: an unqualified reference is a
    modelling defect that OCEL only tolerates because the empty string is a
    legal qualifier, and inventing ``""`` on the caller's behalf is exactly the
    kind of silent repair this package refuses elsewhere.
    """
    out: list[ObjectRef] = []
    for ref in objects or ():
        if isinstance(ref, str) or len(tuple(ref)) != 2:
            raise AgentRefusal(
                AgentRefusalCode.UNKNOWN_INTENT_TOKEN,
                "object references must be (object_id, qualifier) pairs",
                details={"got": repr(ref)},
            )
        object_id, qualifier = tuple(ref)
        out.append((str(object_id), str(qualifier)))
    return tuple(out)


@dataclass(frozen=True, slots=True)
class IntentToken:
    """Handle to an ``INTENDED`` record awaiting its ``COMMITTED`` counterpart."""

    token_id: str
    sequence: int
    path: tuple[int, ...]
    context_sha256: str
    objects: tuple[ObjectRef, ...] = ()
    activity: str = ""
    timestamp_ns: int = 0


@dataclass(frozen=True, slots=True)
class LedgerRecord:
    """One append-only ledger line.

    ``activity_sha256`` is the content address occurrences are keyed by;
    ``activity`` is a human-readable label carried alongside it. The two are
    deliberately separate — the label is never hashed into the occurrence key,
    so relabelling an activity cannot silently mint a new occurrence identity.
    """

    sequence: int
    phase: LedgerPhase
    token_id: str
    path: tuple[int, ...]
    context_sha256: str
    activity_sha256: str
    occurrence_index: int | None
    detail: str
    objects: tuple[ObjectRef, ...] = ()
    activity: str = ""
    timestamp_ns: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "phase": self.phase.value,
            "token_id": self.token_id,
            "path": list(self.path),
            "context_sha256": self.context_sha256,
            "activity_sha256": self.activity_sha256,
            "occurrence_index": self.occurrence_index,
            "detail": self.detail,
            "objects": [list(ref) for ref in self.objects],
            "activity": self.activity,
            "timestamp_ns": self.timestamp_ns,
        }


def _token_id(sequence: int, path: tuple[int, ...], context_sha256: str) -> str:
    return sha256(
        {
            "sequence": sequence,
            "path": list(path),
            "context_sha256": context_sha256,
        }
    )


class OccurrenceLedger:
    """Append-only, two-phase ledger of traversal occurrences."""

    __slots__ = ("_records", "_last_ns")

    def __init__(self, records: Sequence[LedgerRecord] = ()) -> None:
        self._records: list[LedgerRecord] = list(records)
        self._last_ns: int = max((r.timestamp_ns for r in self._records), default=0)

    # ── time ───────────────────────────────────────────────────────────────

    def _stamp(self, proposed: int | None) -> int:
        """A strictly increasing timestamp.

        Monotone by construction rather than by trusting the clock: a wall
        clock can go backwards, and a ledger whose timestamps do would make a
        derived OCEL log's event order disagree with its own append order.

        The **default is a logical clock**, not ``time.time_ns()``. Wall time
        is not usable as a default here because :meth:`sha256` folds every
        field: a real clock would make two identical traversals produce
        different ledger digests, which would then propagate into the epoch
        receipt digest and destroy the reproducibility that digest exists to
        assert. A caller with a real timeline passes ``timestamp_ns``
        explicitly and accepts that consequence knowingly.
        """
        candidate = self._last_ns + 1 if proposed is None else int(proposed)
        stamp = max(candidate, self._last_ns + 1)
        self._last_ns = stamp
        return stamp

    @staticmethod
    def wall_clock_ns() -> int:
        """Wall time, for a caller that wants it. Never used as a default."""
        return time.time_ns()

    # ── phase 1 ────────────────────────────────────────────────────────────

    def intend(
        self,
        path: tuple[int, ...],
        context_sha256: str = "",
        *,
        activity_sha256: str = "",
        activity: str = "",
        objects: Iterable[Sequence[str]] = (),
        timestamp_ns: int | None = None,
        detail: str = "",
    ) -> IntentToken:
        """Write the ``INTENDED`` record. Must precede the act it describes."""
        outstanding = self.outstanding()
        if outstanding:
            raise AgentRefusal(
                AgentRefusalCode.INTENT_ALREADY_OUTSTANDING,
                "an intent is already outstanding; commit it before intending again",
                details={"outstanding": [t.token_id for t in outstanding]},
            )
        sequence = len(self._records)
        path = tuple(int(i) for i in path)
        refs = _as_objects(objects)
        stamp = self._stamp(timestamp_ns)
        token = IntentToken(
            token_id=_token_id(sequence, path, context_sha256),
            sequence=sequence,
            path=path,
            context_sha256=context_sha256,
            objects=refs,
            activity=activity,
            timestamp_ns=stamp,
        )
        self._records.append(
            LedgerRecord(
                sequence=sequence,
                phase=LedgerPhase.INTENDED,
                token_id=token.token_id,
                path=path,
                context_sha256=context_sha256,
                activity_sha256=activity_sha256,
                occurrence_index=None,
                detail=detail,
                objects=refs,
                activity=activity,
                timestamp_ns=stamp,
            )
        )
        return token

    # ── phase 2 ────────────────────────────────────────────────────────────

    def commit(
        self,
        token: IntentToken,
        outcome: Any = None,
        *,
        activity_sha256: str | None = None,
        activity: str | None = None,
        objects: Iterable[Sequence[str]] | None = None,
        timestamp_ns: int | None = None,
        detail: str = "",
    ) -> OccurrenceKey:
        """Write the ``COMMITTED`` record for ``token`` and return its key.

        ``activity_sha256`` is supplied by the caller because the ledger does not
        hold the model. When absent it falls back to a structural stand-in
        derived from the path, and the record says so in ``detail``.
        """
        if token.token_id not in {t.token_id for t in self.outstanding()}:
            raise AgentRefusal(
                AgentRefusalCode.UNKNOWN_INTENT_TOKEN,
                "commit() for a token that is not outstanding",
                details={"token_id": token.token_id},
            )
        intended = self._by_token(token.token_id, LedgerPhase.INTENDED)
        if activity_sha256 is None:
            activity_sha256 = intended.activity_sha256 or sha256(
                {"path": list(token.path)}
            )
            if not intended.activity_sha256:
                detail = (detail + " ACTIVITY_FROM_PATH").strip()
        label = intended.activity if activity is None else activity
        refs = intended.objects if objects is None else _as_objects(objects)
        occurrence_index = sum(
            1
            for r in self._records
            if r.phase is LedgerPhase.COMMITTED and r.activity_sha256 == activity_sha256
        )
        if outcome is not None:
            detail = (detail + f" outcome={outcome!s}").strip()
        self._records.append(
            LedgerRecord(
                sequence=len(self._records),
                phase=LedgerPhase.COMMITTED,
                token_id=token.token_id,
                path=token.path,
                context_sha256=token.context_sha256,
                activity_sha256=activity_sha256,
                occurrence_index=occurrence_index,
                detail=detail,
                objects=refs,
                activity=label,
                timestamp_ns=self._stamp(timestamp_ns),
            )
        )
        return OccurrenceKey(activity_sha256, occurrence_index, token.context_sha256)

    # ── reads ──────────────────────────────────────────────────────────────

    def _by_token(self, token_id: str, phase: LedgerPhase) -> LedgerRecord:
        for record in self._records:
            if record.token_id == token_id and record.phase is phase:
                return record
        raise AgentRefusal(
            AgentRefusalCode.UNKNOWN_INTENT_TOKEN,
            f"no {phase.value} record for token",
            details={"token_id": token_id},
        )

    def records(self) -> tuple[LedgerRecord, ...]:
        """Every line, in append order."""
        return tuple(self._records)

    def outstanding(self) -> tuple[IntentToken, ...]:
        """Tokens with an ``INTENDED`` record and no ``COMMITTED`` counterpart."""
        committed = {
            r.token_id for r in self._records if r.phase is LedgerPhase.COMMITTED
        }
        return tuple(
            IntentToken(
                r.token_id,
                r.sequence,
                r.path,
                r.context_sha256,
                r.objects,
                r.activity,
                r.timestamp_ns,
            )
            for r in self._records
            if r.phase is LedgerPhase.INTENDED and r.token_id not in committed
        )

    def committed(self) -> tuple[LedgerRecord, ...]:
        """Only the ``COMMITTED`` lines — the view a reuse claim may rest on.

        An ``INTENDED`` line is a decision, not an observation, so anything
        that must not preserve unobserved work reads through here.
        """
        return tuple(r for r in self._records if r.phase is LedgerPhase.COMMITTED)

    def provisional_index(self, activity_sha256: str, before_sequence: int) -> int:
        """The occurrence index an activity would take at ``before_sequence``.

        Used to give an ``INTENDED`` line a projected key so a preserve map
        naming it can be *recognised and refused* rather than merely missed.
        """
        return sum(
            1
            for r in self._records
            if r.phase is LedgerPhase.COMMITTED
            and r.activity_sha256 == activity_sha256
            and r.sequence < before_sequence
        )

    def occurrences(self) -> tuple[OccurrenceKey, ...]:
        """Committed occurrences, in commit order. Intents are never included."""
        return tuple(
            OccurrenceKey(
                r.activity_sha256,
                int(r.occurrence_index or 0),
                r.context_sha256,
            )
            for r in self._records
            if r.phase is LedgerPhase.COMMITTED
        )

    def is_resumable(self) -> bool:
        """False when any intent is unresolved — i.e. recovery state is UNKNOWN."""
        return not self.outstanding()

    def assert_resumable(self) -> None:
        """Refuse ``SKD-AGENT-006`` when an ``INTENDED`` has no ``COMMITTED``.

        Never repaired by assuming either outcome: "acted, did not record" and
        "did not act" are indistinguishable from here, and both repairs are
        wrong half the time.
        """
        outstanding = self.outstanding()
        if outstanding:
            raise AgentRefusal(
                AgentRefusalCode.LEDGER_UNRESUMABLE,
                "ledger has INTENDED records with no COMMITTED counterpart; "
                "recovery state is UNKNOWN and the session refuses to resume",
                details={
                    "outstanding": [
                        {"token_id": t.token_id, "path": list(t.path)}
                        for t in outstanding
                    ]
                },
            )

    def sha256(self) -> str:
        """Content hash over every line."""
        return sha256([r.as_dict() for r in self._records])

    @classmethod
    def from_records(cls, records: Iterable[LedgerRecord]) -> OccurrenceLedger:
        """Rehydrate from persisted lines (does **not** validate resumability)."""
        return cls(list(records))

    def __len__(self) -> int:
        return len(self._records)
