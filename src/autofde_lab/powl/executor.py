# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""The bounded reference executor for POWL 2.0 candidate plans.

This is a *reference traversal* over a candidate plan's structure. It fires
nothing in the world: an :class:`~autofde_lab.powl.algebra.Atom`'s ``action``
payload is never invoked, never brokered, never admitted. "Fire" here means
"advance the structural marking past this node". Nothing in this module
actuates, admits, brokers, or issues receipts.

Three laws this module is built around
--------------------------------------

**1. The executor never chooses.** :func:`enabled` returns a *set* of node
paths. There is no tie-break, no "first", no ``sorted(...)[0]``, nowhere in the
fire path. The caller — a policy, a solver, a human — picks. Sorting appears in
this module only where a *digest* or a *deterministic report ordering* is being
built, never to select a step.

**2. Visit counts are carried, never reset.** ``Marking.visits`` is keyed by
``(choice-graph path, child index)`` and is monotone for the whole traversal.
Re-entering a nested :class:`~autofde_lab.powl.algebra.ChoiceGraph` does **not**
zero its counters. This is what makes global termination structural rather than
a timeout: every fire either completes a node or increments a bounded counter.

    *The first surprising behaviour you will hit is a legitimately repeating
    subprocess hitting its cap on an outer iteration.* A nested choice graph
    that is entered on iteration 1 of an outer loop, and again on iteration 2,
    shares one counter across both. That is deliberate. If a model needs N
    inner repetitions across M outer ones, ``max_node_visits`` must cover
    ``N * M``, not ``N``.

**3. Iteration order never leaks.** Every place a collection is hashed,
reported, or compared, it is sorted by path first. ``frozenset`` iteration
order is never observable in a digest or in a :class:`ChoiceRecord`.

Termination of a cyclic choice graph
------------------------------------
A cyclic choice graph is legal — it is how POWL 2.0 expresses iteration. A
successor whose visit count has reached ``bound.max_node_visits`` is **removed
from the enabled set**; it does not raise. The traversal therefore runs out of
enabled nodes structurally, and :func:`classify_stall` reports
``BLOCKED:BOUND_EXHAUSTED`` rather than the run hanging.

Marking shape
-------------
``completed`` is the *identity* ledger — one
:class:`~autofde_lab.powl.identity.OccurrenceKey` per fire, recording which
activity occurred, how many times before, and in what context.
``completed_paths`` is the *structural* ledger that :func:`enabled` reads;
occurrence keys collide by construction for two structurally identical atoms
and so cannot address a position in the tree.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Iterable, Mapping, Sequence, TypeAlias

from autofde_lab.powl.algebra import (
    Atom,
    ChoiceGraph,
    End,
    PartialOrder,
    PowlNode,
    Silent,
    Start,
)
from autofde_lab.powl.bounds import DEFAULT_BOUND, ExecutionBound
from autofde_lab.powl.identity import OccurrenceKey, activity_sha256, node_id
from autofde_lab.powl.refusals import PowlError, PowlRefusal

__all__ = [
    "NodePath",
    "Marking",
    "ChoiceRecord",
    "DeadlockKind",
    "ReplayDivergedError",
    "INITIAL_MARKING",
    "node_at",
    "enabled",
    "fire",
    "is_final",
    "classify_stall",
    "replay",
    "trace_of",
]

#: Address of a node: the sequence of child indices from the root. ``()`` is
#: the root itself. Hashable, orderable, and stable under re-derivation.
NodePath: TypeAlias = tuple[int, ...]


class DeadlockKind(StrEnum):
    """Why a traversal stopped without reaching a final marking."""

    DEADLOCK = "BLOCKED:DEADLOCK"
    BOUND_EXHAUSTED = "BLOCKED:BOUND_EXHAUSTED"
    REPLAY_DIVERGED = "BLOCKED:REPLAY_DIVERGED"


class ReplayDivergedError(PowlError):
    """A recorded choice is not enabled when the marking is re-derived.

    Never repaired by silently re-picking: a replay that quietly chose a
    different step would report agreement it did not have.
    """

    def __init__(self, detail: str) -> None:
        super().__init__(PowlRefusal.LANGUAGE_MISMATCH, detail)
        self.kind: DeadlockKind = DeadlockKind.REPLAY_DIVERGED


@dataclass(frozen=True, slots=True, eq=False)
class Marking:
    """A structural position inside a candidate plan.

    ``cursor`` maps a choice-graph path to the child index currently selected
    inside it (``None``/absent means "not yet entered"). ``visits`` maps
    ``(choice-graph path, child index)`` to a monotone entry count. ``fires``
    counts leaf advances.
    """

    completed: frozenset[OccurrenceKey] = frozenset()
    cursor: Mapping[NodePath, int | None] = field(default_factory=dict)
    visits: Mapping[tuple[NodePath, int], int] = field(default_factory=dict)
    fires: int = 0
    completed_paths: frozenset[NodePath] = frozenset()
    #: Completed *repetition rounds* per composite path. A composite carrying a
    #: :class:`~autofde_lab.powl.frequency.Frequency` is complete only when this
    #: count satisfies ``frequency.allows(n)`` and no round is half-done.
    #: Positional state, so it is purged with ``completed_paths`` — unlike
    #: ``visits``, which is monotone for the whole traversal (law 2).
    rounds: Mapping[NodePath, int] = field(default_factory=dict)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Marking):
            return NotImplemented
        return (
            self.completed == other.completed
            and dict(self.cursor) == dict(other.cursor)
            and dict(self.visits) == dict(other.visits)
            and self.fires == other.fires
            and self.completed_paths == other.completed_paths
            and dict(self.rounds) == dict(other.rounds)
        )

    def digest_material(self) -> dict[str, object]:
        """Canonical, sorted description — set order can never leak out."""
        return {
            "completed": sorted(
                [k.activity_sha256, k.occurrence_index, k.context_sha256]
                for k in self.completed
            ),
            "completed_paths": sorted(list(p) for p in self.completed_paths),
            "cursor": sorted(
                [list(p), c] for p, c in dict(self.cursor).items()
            ),
            "visits": sorted(
                [list(p), i, n] for (p, i), n in dict(self.visits).items()
            ),
            "rounds": sorted([list(p), n] for p, n in dict(self.rounds).items()),
            "fires": self.fires,
        }


#: The marking every traversal starts from.
INITIAL_MARKING = Marking()


@dataclass(frozen=True, slots=True)
class ChoiceRecord:
    """One recorded step: the **full** enabled set alongside the pick.

    Storing only the pick would make a replay unfalsifiable — it could not
    distinguish "the same decision" from "the only remaining option". ``enabled``
    is stored sorted so a ``frozenset``'s iteration order is never recorded.
    """

    step: int
    path: NodePath
    enabled: tuple[NodePath, ...]
    chosen: NodePath
    decided_by: str
    #: The context the fire was recorded under. Load-bearing for :func:`replay`:
    #: ``fire`` folds it into every :class:`~autofde_lab.powl.identity.OccurrenceKey`,
    #: so a replay that dropped it reproduced a marking that differed from the
    #: recorded one in exactly the field meant to identify the occurrence.
    #: Defaults to ``""`` so a record written before this field existed replays
    #: as it always did.
    context_sha256: str = ""


# ── addressing ──────────────────────────────────────────────────────────────


def node_at(model: PowlNode, path: NodePath) -> PowlNode:
    """The node addressed by ``path``, root at ``()``."""
    node = model
    for depth, idx in enumerate(path):
        if not isinstance(node, (PartialOrder, ChoiceGraph)):
            raise PowlError(
                PowlRefusal.DANGLING_REFERENCE,
                f"path {path} descends into {type(node).__name__} at depth {depth}",
            )
        if not (0 <= idx < len(node.children)):
            raise PowlError(
                PowlRefusal.DANGLING_REFERENCE,
                f"path {path} index {idx} outside range(0, {len(node.children)})",
            )
        node = node.children[idx]
    return node


def _is_leaf(node: PowlNode) -> bool:
    return isinstance(node, (Start, End, Silent, Atom))


# ── completion ──────────────────────────────────────────────────────────────


def _purged(marking: Marking, root: NodePath, *, reset_root_rounds: bool = True) -> Marking:
    """``marking`` with all structural progress under ``root`` forgotten.

    Used when a choice graph (re-)enters a child: a cycle must be able to run a
    child it already completed. ``visits`` and ``completed`` are deliberately
    **not** purged — visit counters are monotone (law 2) and ``completed`` is a
    history ledger, not a position.

    ``rounds`` *is* positional and so is purged with the rest. With
    ``reset_root_rounds=False`` the root's own round count survives: that is the
    case where ``root`` has just closed a repetition round and is about to start
    the next one, so its internal state must reset while its round tally must not.
    """
    k = len(root)
    paths = frozenset(p for p in marking.completed_paths if p[:k] != root)
    cursor = {p: c for p, c in dict(marking.cursor).items() if p[:k] != root}
    rounds = {
        p: n
        for p, n in dict(marking.rounds).items()
        if p[:k] != root or (not reset_root_rounds and p == root)
    }
    if (
        paths == marking.completed_paths
        and len(cursor) == len(dict(marking.cursor))
        and len(rounds) == len(dict(marking.rounds))
    ):
        return marking
    return replace(marking, completed_paths=paths, cursor=cursor, rounds=rounds)


def _in_progress(path: NodePath, marking: Marking) -> bool:
    """Whether a repetition round of the composite at ``path`` is half-done.

    A round is closed by :func:`fire`, which purges the composite's internal
    state, so any surviving structural progress strictly under ``path`` means the
    current round has started and not finished.
    """
    k = len(path)
    if any(len(p) > k and p[:k] == path for p in marking.completed_paths):
        return True
    if any(p[:k] == path for p in dict(marking.cursor)):
        return True
    return any(
        len(p) > k and p[:k] == path and n > 0 for p, n in dict(marking.rounds).items()
    )


def _body_complete(node: PowlNode, path: NodePath, marking: Marking) -> bool:
    """Whether *one* round of the composite at ``path`` has just finished."""
    if isinstance(node, PartialOrder):
        return all(
            _is_complete(c, path + (i,), marking)
            for i, c in enumerate(node.children)
        )
    if isinstance(node, ChoiceGraph):
        cur = dict(marking.cursor).get(path)
        if cur is None:
            return False
        return cur == node.end and _is_complete(
            node.children[cur], path + (cur,), marking
        )
    raise PowlError(
        PowlRefusal.PROHIBITED_NODE_KIND,
        f"{type(node).__name__} is not a POWL 2.0 node kind",
    )


def _is_complete(node: PowlNode, path: NodePath, marking: Marking) -> bool:
    if _is_leaf(node):
        return path in marking.completed_paths
    if not isinstance(node, (PartialOrder, ChoiceGraph)):
        raise PowlError(
            PowlRefusal.PROHIBITED_NODE_KIND,
            f"{type(node).__name__} is not a POWL 2.0 node kind",
        )
    # Rounds are closed eagerly by ``fire``: at rest, a composite's completion is
    # a question about its round tally, not about its (purged) internal state.
    # ``ONCE`` reduces to the pre-frequency rule — one round, no repetition.
    done = dict(marking.rounds).get(path, 0)
    if node.frequency.allows(done) and not _in_progress(path, marking):
        return True
    # A marking built out-of-band (``replan.seed_marking`` seeds preserved work
    # directly into ``completed_paths``/``cursor``, and knows nothing about round
    # counts) records a finished round only as a complete body. Counting that
    # body as the round it is keeps such a marking readable — without it, a
    # ``ONCE`` composite seeded complete would read as never having run.
    return node.frequency.allows(done + 1) and _body_complete(node, path, marking)


# ── enabling ────────────────────────────────────────────────────────────────


def _enabled(
    node: PowlNode,
    path: NodePath,
    marking: Marking,
    bound: ExecutionBound,
    *,
    apply_visit_cap: bool,
) -> set[NodePath]:
    if _is_leaf(node):
        return set() if path in marking.completed_paths else {path}

    if isinstance(node, (PartialOrder, ChoiceGraph)):
        done = dict(marking.rounds).get(path, 0)
        freq = node.frequency
        if freq.max is not None and done >= freq.max:
            # every permitted repetition has been run; nothing further to offer
            return set()
        if done > 0 and not _in_progress(path, marking):
            # about to *start* another round. A repetition whose round counter
            # has reached the declared cap is REMOVED from the enabled set, not
            # raised on — the same rule that terminates a cyclic choice graph.
            # ``visits[(path, -1)]`` is a round counter; ``-1`` can never collide
            # with a child index, and like every other visit count it is carried,
            # never reset (law 2), so unbounded frequency still terminates.
            if (
                apply_visit_cap
                and dict(marking.visits).get((path, -1), 0) >= bound.max_node_visits
            ):
                return set()

    if isinstance(node, PartialOrder):
        out: set[NodePath] = set()
        for i, child in enumerate(node.children):
            child_path = path + (i,)
            if _is_complete(child, child_path, marking):
                continue
            # closure, never .order — a reduction hides indirect precedence
            preds = (e.src for e in node.closure if e.dst == i)
            if not all(
                _is_complete(node.children[j], path + (j,), marking) for j in preds
            ):
                continue
            out |= _enabled(
                child, child_path, marking, bound, apply_visit_cap=apply_visit_cap
            )
        return out

    if isinstance(node, ChoiceGraph):
        cur = dict(marking.cursor).get(path)
        if cur is not None:
            if not _is_complete(node.children[cur], path + (cur,), marking):
                # still inside the selected child; it was already counted on
                # entry, so no cap check here.
                return _enabled(
                    node.children[cur],
                    path + (cur,),
                    marking,
                    bound,
                    apply_visit_cap=apply_visit_cap,
                )
            if cur == node.end:
                return set()
            candidates: Iterable[int] = {e.dst for e in node.edges if e.src == cur}
        else:
            candidates = (node.start,)

        visits = dict(marking.visits)
        out = set()
        for c in candidates:
            # a capped successor is REMOVED, not raised on: this is what
            # terminates a cyclic choice graph structurally.
            if apply_visit_cap and visits.get((path, c), 0) >= bound.max_node_visits:
                continue
            # entering a child starts it afresh — a self-loop or a cycle must
            # be able to re-run a child it already completed. Visit counters
            # are NOT part of the purge: law 2.
            view = _purged(marking, path + (c,))
            out |= _enabled(
                node.children[c],
                path + (c,),
                view,
                bound,
                apply_visit_cap=apply_visit_cap,
            )
        return out

    raise PowlError(
        PowlRefusal.PROHIBITED_NODE_KIND,
        f"{type(node).__name__} is not a POWL 2.0 node kind",
    )


def enabled(
    model: PowlNode,
    marking: Marking = INITIAL_MARKING,
    bound: ExecutionBound = DEFAULT_BOUND,
) -> frozenset[NodePath]:
    """Leaf paths that may advance next — a set, never an ordered choice.

    Two mutually unordered children of a partial order are **both** in the
    result; concurrency is preserved, not serialized. The caller picks.
    """
    return frozenset(_enabled(model, (), marking, bound, apply_visit_cap=True))


# ── firing ──────────────────────────────────────────────────────────────────


def _activity_of(node: PowlNode) -> str:
    return activity_sha256(node) if isinstance(node, Atom) else node_id(node)


def fire(
    model: PowlNode,
    marking: Marking,
    path: NodePath,
    context_sha256: str = "",
    bound: ExecutionBound = DEFAULT_BOUND,
) -> Marking:
    """Advance ``marking`` past the leaf at ``path``. Returns a new marking.

    Refuses ``LANGUAGE_MISMATCH`` if ``path`` is not enabled, and
    ``BOUND_EXHAUSTED`` if the fire budget is spent. The atom's ``action``
    payload is never invoked.
    """
    live = enabled(model, marking, bound)
    if path not in live:
        raise PowlError(
            PowlRefusal.LANGUAGE_MISMATCH,
            f"path {path} is not enabled; enabled={sorted(live)}",
        )
    if marking.fires + 1 > bound.max_activity_fires:
        raise PowlError(
            PowlRefusal.BOUND_EXHAUSTED,
            f"max_activity_fires={bound.max_activity_fires} exhausted",
        )

    node = node_at(model, path)
    activity = _activity_of(node)
    occurrence_index = sum(
        1 for k in marking.completed if k.activity_sha256 == activity
    )

    # Record entry into every choice-graph ancestor on the way down. Visit
    # counters are carried, never reset: see law 2 in the module docstring.
    working = marking
    visits = dict(marking.visits)
    for depth in range(len(path)):
        prefix = path[:depth]
        ancestor = node_at(model, prefix)
        if not isinstance(ancestor, ChoiceGraph):
            continue
        idx = path[depth]
        child_path = prefix + (idx,)
        entering = dict(working.cursor).get(prefix) != idx or _is_complete(
            ancestor.children[idx], child_path, working
        )
        if entering:
            working = _purged(working, child_path)
            cursor = dict(working.cursor)
            cursor[prefix] = idx
            working = replace(working, cursor=cursor)
            visits[(prefix, idx)] = visits.get((prefix, idx), 0) + 1

    if len(working.completed_paths) + 1 > bound.max_marking_states:
        raise PowlError(
            PowlRefusal.BOUND_EXHAUSTED,
            f"max_marking_states={bound.max_marking_states} exhausted",
        )

    out = replace(
        working,
        completed=working.completed
        | {OccurrenceKey(activity, occurrence_index, context_sha256)},
        completed_paths=working.completed_paths | {path},
        visits=visits,
        fires=marking.fires + 1,
    )
    return _close_rounds(model, path, out)


def _close_rounds(model: PowlNode, path: NodePath, marking: Marking) -> Marking:
    """Bottom-up: bank a repetition round for every composite ancestor of ``path``
    whose body has just finished, and reset that composite's internal state so the
    next round can run.

    Deepest first, so an outer composite sees its inner children already banked.
    ``visits`` is never reset here — only extended with the round counter.
    """
    for depth in range(len(path) - 1, -1, -1):
        prefix = path[:depth]
        node = node_at(model, prefix)
        if _is_leaf(node):
            continue
        if not _body_complete(node, prefix, marking):
            continue
        done = dict(marking.rounds).get(prefix, 0) + 1
        marking = _purged(marking, prefix, reset_root_rounds=False)
        rounds = dict(marking.rounds)
        rounds[prefix] = done
        visits = dict(marking.visits)
        visits[(prefix, -1)] = visits.get((prefix, -1), 0) + 1
        marking = replace(marking, rounds=rounds, visits=visits)
    return marking


def is_final(model: PowlNode, marking: Marking) -> bool:
    """Whether the whole model is structurally complete under ``marking``."""
    return _is_complete(model, (), marking)


def classify_stall(
    model: PowlNode,
    marking: Marking,
    bound: ExecutionBound = DEFAULT_BOUND,
) -> DeadlockKind:
    """Why a non-final marking has nothing enabled.

    ``BLOCKED:BOUND_EXHAUSTED`` when a step exists but a declared bound removed
    it; ``BLOCKED:DEADLOCK`` when the structure itself offers nothing.

    Genuine bug found and fixed forward this session
    (``tests/powl/test_runner_bounds_concurrent_chicago.py``): unlike
    ``max_node_visits`` (enforced *inside* ``_enabled()``, so a capped
    successor is structurally removed from the enabled set -- see this
    module's law 2) and ``max_activity_fires`` (checked directly against
    ``marking.fires`` right here), ``max_marking_states`` is enforced only
    *inside* ``fire()`` (a raise, not a removal from ``enabled()``) and had
    no corresponding check in this function at all. So a marking that hit
    the ``max_marking_states`` cap but still had a structurally-enabled
    successor (true whenever the cap is smaller than the model's total leaf
    count) fell through both branches above and was misreported as
    ``BLOCKED:DEADLOCK`` -- or, before ``classify_pipeline_stall``'s own
    fix (below), was never even routed into this function, misreported as
    "not stalled". The explicit ``completed_paths`` check below mirrors the
    ``fires`` check immediately above it.
    """
    if marking.fires >= bound.max_activity_fires:
        return DeadlockKind.BOUND_EXHAUSTED
    if len(marking.completed_paths) >= bound.max_marking_states:
        return DeadlockKind.BOUND_EXHAUSTED
    uncapped = _enabled(model, (), marking, bound, apply_visit_cap=False)
    if uncapped:
        return DeadlockKind.BOUND_EXHAUSTED
    return DeadlockKind.DEADLOCK


# ── replay ──────────────────────────────────────────────────────────────────


def replay(
    model: PowlNode,
    choices: Sequence[ChoiceRecord],
    bound: ExecutionBound = DEFAULT_BOUND,
    initial: Marking = INITIAL_MARKING,
) -> Marking:
    """Re-derive every marking and re-check every recorded choice.

    At each step the enabled set is recomputed from the model and the marking;
    a recorded ``chosen`` that is not in it, or a recorded ``enabled`` set that
    does not match, is :class:`ReplayDivergedError`. Never a silent re-pick.

    ``initial`` is the marking the recorded run started from. It defaults to
    :data:`INITIAL_MARKING`, but a replanned epoch starts from a *seeded*
    marking (preserved work already complete), and replaying such a run from
    the empty marking would diverge on the first step for a reason that has
    nothing to do with the recorded choices. The caller supplies the same seed
    the run used; nothing is inferred.
    """
    marking = initial
    for step, record in enumerate(choices):
        live = enabled(model, marking, bound)
        if record.chosen not in live:
            raise ReplayDivergedError(
                f"step {step}: recorded choice {record.chosen} is not enabled; "
                f"re-derived enabled={sorted(live)}"
            )
        if tuple(sorted(record.enabled)) != tuple(sorted(live)):
            raise ReplayDivergedError(
                f"step {step}: recorded enabled set {tuple(sorted(record.enabled))} "
                f"!= re-derived {tuple(sorted(live))}"
            )
        marking = fire(
            model,
            marking,
            record.chosen,
            context_sha256=record.context_sha256,
            bound=bound,
        )
    return marking


def trace_of(model: PowlNode, choices: Sequence[ChoiceRecord]) -> tuple[str, ...]:
    """The observable label sequence of a recorded run (silent steps emit none)."""
    out: list[str] = []
    for record in choices:
        node = node_at(model, record.chosen)
        if isinstance(node, Atom):
            out.append(node.label)
    return tuple(out)
