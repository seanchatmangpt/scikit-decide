# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Single-hop replanning over POWL 2.0 candidate plans.

When the world diverges from what a candidate plan assumed, the agent does not
resume POWL0 — it computes a *new* candidate plan POWL1 and decides, node by
node, what POWL0 already did that POWL1 must not do again. That decision is a
:class:`PreserveMap`.

Nothing in this module actuates, admits, brokers, or issues receipts. "Preserve"
means "seed the next plan's structural marking so this node cannot appear in
:func:`~autofde_lab.powl.executor.enabled` again"; it does not mean the world was
changed, and it carries no admission semantics.

Three things this module deliberately refuses to be clever about
----------------------------------------------------------------

**1. Content addressing alone cannot identify an occurrence.** Two occurrences
of the same activity are content-identical *by construction* —
:func:`~autofde_lab.powl.identity.activity_sha256` covers ``{label, action
identity, bindings}`` and nothing positional. So when POWL0 completed ``n``
occurrences of an activity and POWL1 contains ``m != n`` nodes carrying it,
:func:`infer_preserve_map` leaves those nodes **unmapped** rather than guessing
an alignment. An unmapped node is re-planned, which is safe; a wrongly mapped
node silently skips work that never happened, which is not.

**2. Redo is a legal outcome, not a refusal.** The world moves. A completed
``revoke_sessions`` may need doing again because a new population appeared. Such
a node goes in :attr:`PreserveMap.redo` with a written justification, is *not*
seeded, and fires with a **fresh** occurrence index of ``prior_count`` — the
prior occurrence is never overwritten or reused. That rising index is precisely
why :class:`~autofde_lab.powl.identity.OccurrenceKey` is not a bare content hash.

**3. Preservation is single-hop.** A :class:`PreserveMap` relates epoch ``k`` to
epoch ``k + 1`` and nothing else. Chaining two hops would require a
transitively-composed justification nobody wrote; the map carries its epochs and
:func:`validate_preserve_map` refuses a non-adjacent pair.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Iterator, Mapping

from autofde_lab.powl.algebra import (
    Atom,
    ChoiceGraph,
    End,
    PartialOrder,
    PowlNode,
    Silent,
    Start,
)
from autofde_lab.powl.executor import (
    INITIAL_MARKING,
    Marking,
    NodePath,
    enabled,
    node_at,
)
from autofde_lab.powl.identity import OccurrenceKey, activity_sha256, node_id

__all__ = [
    "ReplanningMode",
    "ReplanRefusal",
    "ReplanError",
    "OccurrenceStatus",
    "LedgerEntry",
    "Ledger",
    "LedgerLike",
    "as_ledger",
    "Epoch",
    "PreserveMap",
    "leaf_paths",
    "activity_of",
    "infer_preserve_map",
    "validate_preserve_map",
    "seed_marking",
    "redo_occurrence_key",
]


class ReplanningMode(StrEnum):
    """What the agent decided to do when the world diverged.

    A mode is a *label on a decision*, not an instruction to anything. Nothing
    in this package acts on one.
    """

    CONTINUE = "Continue"
    REPAIR = "Repair"
    REPLAN = "Replan"
    RESCHEDULE = "Reschedule"
    UPDATE_POLICY = "UpdatePolicy"
    LEARN_MODEL = "LearnModel"
    SPAWN_CHILD = "SpawnChild"
    TERMINATE = "Terminate"
    REFUSE = "Refuse"


class ReplanRefusal(StrEnum):
    """Typed refusal codes for preserve-map validation.

    Distinct from :class:`~autofde_lab.powl.refusals.PowlRefusal`: those describe an
    ill-formed *model*, these describe an ill-formed *reuse claim* about a
    well-formed one.
    """

    NOT_DOWNWARD_CLOSED = "SKD-AGENT-004"
    OCCURRENCE_NOT_IN_LEDGER = "SKD-AGENT-005"
    UNRESUMABLE_TORN_FIRE = "SKD-AGENT-006"
    REDO_WITHOUT_JUSTIFICATION = "SKD-AGENT-007"
    NON_ADJACENT_EPOCH = "SKD-AGENT-008"
    DANGLING_PRESERVED_PATH = "SKD-AGENT-009"


class ReplanError(ValueError):
    """A refusal carrying its code, never a bare string."""

    def __init__(self, refusal: ReplanRefusal, detail: str = "") -> None:
        super().__init__(f"{refusal.value}: {detail}" if detail else refusal.value)
        self.refusal = refusal
        self.detail = detail


# ── the ledger ──────────────────────────────────────────────────────────────


class OccurrenceStatus(StrEnum):
    """How far a recorded occurrence actually got.

    ``INTENDED`` is the reason this is not a boolean: an occurrence the agent
    decided on but never observed completing is *not* evidence that it happened,
    and preserving it would seed a marking claiming work that may not exist.
    """

    INTENDED = "INTENDED"
    COMPLETED = "COMPLETED"
    TORN = "TORN"


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    """One recorded occurrence in one epoch.

    ``resumable`` is only meaningful for :attr:`OccurrenceStatus.TORN`: a torn
    fire whose partial effect cannot be reasoned about is unresumable, and
    preserving it is :data:`ReplanRefusal.UNRESUMABLE_TORN_FIRE`.
    """

    key: OccurrenceKey
    path: NodePath
    status: OccurrenceStatus
    epoch: int
    resumable: bool = False


@dataclass(frozen=True, slots=True)
class Ledger:
    """The append-only record of what prior epochs observed.

    This is a **read view**, not a second write-ahead log. The authoritative
    record is :class:`~autofde_lab.agent.ledger.OccurrenceLedger`; this type is
    what a reuse claim is validated against, and
    :meth:`from_occurrence_ledger` is the only sanctioned way to derive one
    from a live session. Constructing entries directly stays available for
    tests and for replaying persisted epochs, but a hand-built ``Ledger`` is
    not evidence of anything the WAL did not record.
    """

    entries: tuple[LedgerEntry, ...] = ()

    @classmethod
    def from_occurrence_ledger(
        cls,
        wal: "OccurrenceLedger",
        *,
        epoch: int = 0,
        committed_only: bool = False,
    ) -> "Ledger":
        """Project the two-phase WAL onto the epoch-scoped view.

        ``COMMITTED`` becomes :attr:`OccurrenceStatus.COMPLETED`. An
        ``INTENDED`` line with no ``COMMITTED`` counterpart becomes
        :attr:`OccurrenceStatus.INTENDED` carrying the occurrence key it
        *would* have taken — so a preserve map naming it is refused by name
        (``SKD-AGENT-005``, "an intention is not an observation") instead of
        merely failing to resolve. ``committed_only=True`` drops those lines
        entirely; either way the claim is rejected, and the two paths are
        tested separately.

        The WAL has no epoch axis, so every projected entry is stamped with
        ``epoch``. Nothing here infers an epoch boundary.
        """
        from autofde_lab.agent.ledger import LedgerPhase  # local: avoid a cycle

        settled = {r.token_id for r in wal.committed()}
        entries: list[LedgerEntry] = []
        for record in wal.records():
            if record.phase is LedgerPhase.COMMITTED:
                entries.append(
                    LedgerEntry(
                        key=OccurrenceKey(
                            record.activity_sha256,
                            int(record.occurrence_index or 0),
                            record.context_sha256,
                        ),
                        path=record.path,
                        status=OccurrenceStatus.COMPLETED,
                        epoch=epoch,
                    )
                )
                continue
            if committed_only or record.token_id in settled:
                continue
            entries.append(
                LedgerEntry(
                    key=OccurrenceKey(
                        record.activity_sha256,
                        wal.provisional_index(record.activity_sha256, record.sequence),
                        record.context_sha256,
                    ),
                    path=record.path,
                    status=OccurrenceStatus.INTENDED,
                    epoch=epoch,
                )
            )
        return cls(tuple(entries))

    def for_epoch(self, epoch: int) -> tuple[LedgerEntry, ...]:
        return tuple(e for e in self.entries if e.epoch == epoch)

    def find(self, key: OccurrenceKey, epoch: int) -> LedgerEntry | None:
        for e in self.entries:
            if e.epoch == epoch and e.key == key:
                return e
        return None

    def completed_count(self, activity: str) -> int:
        """How many times ``activity`` has completed across every epoch.

        This is the ``prior_count`` a redo's fresh occurrence index starts from.
        """
        return sum(
            1
            for e in self.entries
            if e.status is OccurrenceStatus.COMPLETED
            and e.key.activity_sha256 == activity
        )


#: What the validation entry points accept: the view, or the WAL it derives from.
LedgerLike = "Ledger | OccurrenceLedger"


def as_ledger(ledger: object, *, epoch: int = 0, committed_only: bool = False) -> Ledger:
    """Normalize a WAL or a view into the view. The single reconciliation point."""
    from autofde_lab.agent.ledger import OccurrenceLedger  # local: avoid a cycle

    if isinstance(ledger, OccurrenceLedger):
        return Ledger.from_occurrence_ledger(
            ledger, epoch=epoch, committed_only=committed_only
        )
    if isinstance(ledger, Ledger):
        return ledger
    raise TypeError(f"expected Ledger or OccurrenceLedger, got {type(ledger).__name__}")


@dataclass(frozen=True, slots=True)
class Epoch:
    """A planning epoch: an index and the candidate plan it planned over."""

    index: int
    model: PowlNode


# ── addressing helpers ──────────────────────────────────────────────────────


def leaf_paths(model: PowlNode, prefix: NodePath = ()) -> Iterator[NodePath]:
    """Every leaf path in ``model``, in depth-first child order."""
    if isinstance(model, (Start, End, Silent, Atom)):
        yield prefix
        return
    for i, child in enumerate(model.children):
        yield from leaf_paths(child, prefix + (i,))


def activity_of(node: PowlNode) -> str:
    """The content address a fire records for ``node``.

    Same rule the executor's ``_activity_of`` uses — an :class:`Atom` hashes to
    its activity, anything else to its structural node id. Kept in agreement
    deliberately: a preserve map that addressed occurrences differently from the
    executor would seed keys the executor never produces.
    """
    return activity_sha256(node) if isinstance(node, Atom) else node_id(node)


def _covers_completion(model: PowlNode, path: NodePath, preserved: frozenset[NodePath]) -> bool:
    """Whether ``preserved`` implies the subtree at ``path`` is complete.

    Mirrors the executor's ``_is_complete``: every child of a partial order, but
    only the ``end`` child of a choice graph — a choice graph completes when its
    cursor reaches ``end``, so preserving some other branch proves nothing.
    """
    node = node_at(model, path)
    if isinstance(node, (Start, End, Silent, Atom)):
        return path in preserved
    if isinstance(node, PartialOrder):
        return all(
            _covers_completion(model, path + (i,), preserved)
            for i in range(len(node.children))
        )
    if isinstance(node, ChoiceGraph):
        return _covers_completion(model, path + (node.end,), preserved)
    return False


# ── inference ───────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class PreserveMap:
    """What POWL1 may reuse from POWL0, and what it must deliberately redo.

    ``entries`` maps a POWL1 leaf path to the prior occurrence it stands for.
    ``redo`` names POWL1 leaf paths whose prior occurrence exists but must run
    again anyway; every one of them needs a written justification — an
    unjustified redo is :data:`ReplanRefusal.REDO_WITHOUT_JUSTIFICATION`, not a
    silent default.
    """

    entries: Mapping[NodePath, OccurrenceKey] = field(default_factory=dict)
    redo: frozenset[NodePath] = frozenset()
    redo_justification: Mapping[NodePath, str] = field(default_factory=dict)
    from_epoch: int = 0
    to_epoch: int = 1


def infer_preserve_map(
    prior_epoch: Epoch,
    ledger: Ledger | object,
    model1: PowlNode,
) -> PreserveMap:
    """Content-address prior completions onto ``model1``, greedy by index.

    An activity completed ``n`` times in ``prior_epoch`` is mapped onto
    ``model1``'s nodes carrying that activity **only when there are exactly
    ``n`` of them**. Otherwise the alignment is ambiguous and every such node is
    left unmapped — see law 1 in the module docstring. Nothing here fabricates a
    correspondence that the content addresses cannot support.
    """
    ledger = as_ledger(ledger, epoch=prior_epoch.index)
    completed = [
        e
        for e in ledger.for_epoch(prior_epoch.index)
        if e.status is OccurrenceStatus.COMPLETED
    ]

    by_activity: dict[str, list[LedgerEntry]] = {}
    for e in completed:
        by_activity.setdefault(e.key.activity_sha256, []).append(e)

    new_by_activity: dict[str, list[NodePath]] = {}
    for p in leaf_paths(model1):
        new_by_activity.setdefault(activity_of(node_at(model1, p)), []).append(p)

    entries: dict[NodePath, OccurrenceKey] = {}
    for activity, prior in by_activity.items():
        new_paths = sorted(new_by_activity.get(activity, []))
        if len(new_paths) != len(prior):
            # ambiguous: n prior occurrences, m != n candidate nodes. Leave
            # unmapped rather than guess. Re-planning a node is safe; skipping
            # one that never ran is not.
            continue
        for path, entry in zip(new_paths, sorted(prior, key=lambda e: e.key.occurrence_index)):
            entries[path] = entry.key

    return PreserveMap(
        entries=entries,
        redo=frozenset(),
        redo_justification={},
        from_epoch=prior_epoch.index,
        to_epoch=prior_epoch.index + 1,
    )


# ── validation ──────────────────────────────────────────────────────────────


def validate_preserve_map(
    model1: PowlNode, pm: PreserveMap, ledger: Ledger | object
) -> None:
    """Refuse a preserve map that would seed a marking outside POWL1's language.

    Raises :class:`ReplanError`; returns ``None`` when the map is admissible as
    a *reuse claim*. Admissible here means structurally consistent — it is not
    an admission, an authorization, or a standing verdict.
    """
    ledger = as_ledger(ledger, epoch=pm.from_epoch)
    if pm.to_epoch != pm.from_epoch + 1:
        raise ReplanError(
            ReplanRefusal.NON_ADJACENT_EPOCH,
            f"preservation is single-hop; got from_epoch={pm.from_epoch} "
            f"to_epoch={pm.to_epoch}",
        )

    preserved = frozenset(pm.entries)

    # every preserved path must address a real leaf of model1
    real_leaves = frozenset(leaf_paths(model1))
    for path in sorted(preserved | pm.redo):
        if path not in real_leaves:
            raise ReplanError(
                ReplanRefusal.DANGLING_PRESERVED_PATH,
                f"{path} is not a leaf path of model1",
            )

    # a redo must not also be preserved, and must carry a written reason
    for path in sorted(pm.redo):
        justification = dict(pm.redo_justification).get(path, "")
        if not justification.strip():
            raise ReplanError(
                ReplanRefusal.REDO_WITHOUT_JUSTIFICATION,
                f"redo of {path} carries no justification",
            )
        if path in preserved:
            raise ReplanError(
                ReplanRefusal.REDO_WITHOUT_JUSTIFICATION,
                f"{path} is both preserved and marked redo",
            )

    # SKD-AGENT-005 / SKD-AGENT-006: the ledger must actually support the claim
    for path, key in sorted(pm.entries.items()):
        entry = ledger.find(key, pm.from_epoch)
        if entry is None:
            raise ReplanError(
                ReplanRefusal.OCCURRENCE_NOT_IN_LEDGER,
                f"{path} preserves occurrence {key} absent from epoch "
                f"{pm.from_epoch} of the ledger",
            )
        if entry.status is OccurrenceStatus.INTENDED:
            raise ReplanError(
                ReplanRefusal.OCCURRENCE_NOT_IN_LEDGER,
                f"{path} preserves occurrence {key} recorded only as INTENDED; "
                "an intention is not an observation",
            )
        if entry.status is OccurrenceStatus.TORN and not entry.resumable:
            raise ReplanError(
                ReplanRefusal.UNRESUMABLE_TORN_FIRE,
                f"{path} preserves a torn, unresumable fire {key}",
            )

    # SKD-AGENT-004: downward closure against model1's CLOSED order. A preserved
    # node whose predecessor never ran would seed a marking whose trace is not
    # in model1's language — the executor would then happily continue from a
    # position the model never reaches.
    for path in sorted(preserved):
        for depth in range(len(path)):
            parent = node_at(model1, path[:depth])
            if not isinstance(parent, PartialOrder):
                continue
            i = path[depth]
            for edge in sorted(parent.closure):
                if edge.dst != i:
                    continue
                pred_path = path[:depth] + (edge.src,)
                if not _covers_completion(model1, pred_path, preserved):
                    raise ReplanError(
                        ReplanRefusal.NOT_DOWNWARD_CLOSED,
                        f"{path} is preserved but its closed-order predecessor "
                        f"subtree {pred_path} is not",
                    )


# ── seeding ─────────────────────────────────────────────────────────────────


def redo_occurrence_key(
    model1: PowlNode,
    ledger: Ledger | object,
    path: NodePath,
    context_sha256: str = "",
) -> OccurrenceKey:
    """The fresh key a redo of ``path`` will carry: index ``prior_count``.

    The prior occurrence is never overwritten. This is the same index the
    executor derives when firing against a marking seeded by
    :func:`seed_marking`, because that marking carries the prior keys.
    """
    ledger = as_ledger(ledger)
    activity = activity_of(node_at(model1, path))
    return OccurrenceKey(activity, ledger.completed_count(activity), context_sha256)


def seed_marking(model1: PowlNode, pm: PreserveMap) -> Marking:
    """POWL1's initial marking, with every preserved node already complete.

    The exclusion is **structural, not a check**: a preserved path is placed in
    ``Marking.completed_paths``, and the executor's leaf rule is ``return set()
    if path in marking.completed_paths`` — so a preserved node cannot enter
    :func:`~autofde_lab.powl.executor.enabled` at all. There is no guard for a
    caller to skip.

    Choice-graph cursors on the way to a preserved leaf are seeded too;
    otherwise the executor would treat the branch as un-entered and re-purge it.
    Prior :class:`~autofde_lab.powl.identity.OccurrenceKey`\\ s are seeded into
    ``completed`` so a redo's occurrence index continues rising.
    """
    preserved = frozenset(pm.entries)
    cursor: dict[NodePath, int | None] = {}
    visits: dict[tuple[NodePath, int], int] = {}
    for path in sorted(preserved):
        for depth in range(len(path)):
            prefix = path[:depth]
            if isinstance(node_at(model1, prefix), ChoiceGraph):
                idx = path[depth]
                if cursor.get(prefix) != idx:
                    cursor[prefix] = idx
                    visits[(prefix, idx)] = visits.get((prefix, idx), 0) + 1

    marking = Marking(
        completed=frozenset(pm.entries.values()),
        cursor=cursor,
        visits=visits,
        fires=len(preserved),
        completed_paths=preserved,
    )

    # Construction-time consistency, not a runtime gate the executor consults:
    # if a preserved path could still be enabled the seeding rule above is
    # broken, and that is a defect in this function, not in the caller.
    live = enabled(model1, marking)
    overlap = preserved & live
    if overlap:
        raise ReplanError(
            ReplanRefusal.NOT_DOWNWARD_CLOSED,
            f"seeded marking still enables preserved paths {sorted(overlap)}",
        )
    return marking


#: The marking a replan with nothing preserved starts from.
EMPTY_SEED: Marking = INITIAL_MARKING
