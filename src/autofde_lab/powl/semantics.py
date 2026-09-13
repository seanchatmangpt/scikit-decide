# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Denotational semantics for POWL 2.0: the *language* of a node.

Provenance
----------
This module is an **independent Python implementation** of the formal model
specified in ``~/POWL/powl/Semantics/Language.lean`` (namespace
``POWL.Language``). That file defines, over ``Trace α := List α`` and
``Language α := Set (Trace α)``:

- ``epsilon = {[]}`` — silent behaviour;
- ``atom a = {[a]}`` — one observable activity;
- ``choice = ⋃₀`` — nondeterministic choice as set union;
- ``seq L R = {u ++ v | u ∈ L, v ∈ R}`` — sequential composition;
- ``Interleaves : List α → List α → List α → Prop`` — an inductive relation
  with ``nil`` / ``left`` / ``right`` cases, i.e. the *order-preserving*
  shuffle of two traces;
- ``parallel L R = {w | ∃ u ∈ L, ∃ v ∈ R, Interleaves u v w}``;
- ``power body n`` — exact finite iteration, ``power body 0 = epsilon``;
- ``boundedPower body frequency = ⋃ n, ⋃ (frequency.Allows n), power body n``.

No code was copied from ``~/POWL`` (which is AGPL and contains only Lean); the
Lean statements above are the *specification* transcribed here in Python.

Everything here is bounded
--------------------------
The Lean model is over infinite sets. A Python realisation must be finite, so
every entry point takes the bound as an **explicit parameter** — never a
constant buried in a loop:

- ``max_traces`` caps the size of any intermediate or final language;
- ``max_unrolls`` caps how many times a single choice-graph node may be
  revisited in one walk, and stands in for ``max = None`` (unbounded
  :class:`~autofde_lab.powl.frequency.Frequency`).

When a bound is hit this module **raises**
:class:`~autofde_lab.powl.refusals.PowlError` with
:data:`~autofde_lab.powl.refusals.PowlRefusal.BOUND_EXHAUSTED`. It never returns
a truncated language: a partial set presented as complete would silently
falsify every downstream containment check.

This module computes the language of a *candidate* plan. It never actuates,
admits, brokers, or issues receipts.
"""

from __future__ import annotations

from collections import Counter
from itertools import product
from typing import Iterable, Iterator, TypeAlias

from autofde_lab.powl.algebra import (
    Atom,
    ChoiceGraph,
    End,
    PartialOrder,
    PowlNode,
    Silent,
    Start,
)
from autofde_lab.powl.frequency import Frequency
from autofde_lab.powl.refusals import PowlError, PowlRefusal

__all__ = [
    "Trace",
    "Language",
    "interleavings",
    "language",
    "enabled_labels",
]

#: A finite sequence of observable activity labels. ``Silent``, ``Start`` and
#: ``End`` contribute nothing, so they denote the empty trace.
Trace: TypeAlias = tuple[str, ...]

#: A set of traces — the Python realisation of Lean's ``Language α``.
Language: TypeAlias = frozenset[Trace]

_EPSILON: Language = frozenset({()})


# ── bound enforcement ───────────────────────────────────────────────────────


def _guard(size: int, max_traces: int, what: str) -> None:
    if size > max_traces:
        raise PowlError(
            PowlRefusal.BOUND_EXHAUSTED,
            f"{what} reached {size} traces, exceeding max_traces={max_traces}",
        )


def _check_bounds(max_traces: int, max_unrolls: int) -> None:
    if max_traces < 1:
        raise PowlError(
            PowlRefusal.BOUND_EXHAUSTED, f"max_traces={max_traces} must be >= 1"
        )
    if max_unrolls < 1:
        raise PowlError(
            PowlRefusal.BOUND_EXHAUSTED, f"max_unrolls={max_unrolls} must be >= 1"
        )


# ── Lean: Interleaves ───────────────────────────────────────────────────────


def interleavings(u: Trace, v: Trace) -> Iterator[Trace]:
    """Yield every order-preserving shuffle of ``u`` and ``v``.

    Direct transcription of the ``Interleaves`` inductive in
    ``Language.lean``: the ``nil`` case (both exhausted), the ``left`` case
    (take the head of ``u``) and the ``right`` case (take the head of ``v``).
    Traces may repeat in the output when ``u`` and ``v`` share symbols; Lean's
    ``Set`` collapses them, and so does :func:`language`.
    """
    acc: list[str] = []

    def rec(i: int, j: int) -> Iterator[Trace]:
        if i == len(u) and j == len(v):
            yield tuple(acc)
            return
        if i < len(u):
            acc.append(u[i])
            yield from rec(i + 1, j)
            acc.pop()
        if j < len(v):
            acc.append(v[j])
            yield from rec(i, j + 1)
            acc.pop()

    yield from rec(0, 0)


# ── Lean: seq / power / boundedPower ────────────────────────────────────────


def _seq(left: Iterable[Trace], right: Language, max_traces: int) -> Language:
    """``seq L R = {u ++ v | u ∈ L, v ∈ R}``."""
    out: set[Trace] = set()
    for u in left:
        for v in right:
            out.add(u + v)
            _guard(len(out), max_traces, "seq")
    return frozenset(out)


def _bounded_power(body: Language, freq: Frequency, max_traces: int, max_unrolls: int) -> Language:
    """``boundedPower body frequency``, with ``max = None`` capped at ``max_unrolls``.

    A finite explicit upper bound greater than ``max_unrolls`` is a refusal
    rather than a silent truncation.
    """
    if freq.max is None:
        hi = max_unrolls
    else:
        hi = freq.max
        if hi > max_unrolls:
            raise PowlError(
                PowlRefusal.BOUND_EXHAUSTED,
                f"frequency max={hi} exceeds max_unrolls={max_unrolls}",
            )
    lo = freq.min
    if lo > hi:
        raise PowlError(
            PowlRefusal.BOUND_EXHAUSTED,
            f"frequency min={lo} exceeds the unroll cap {hi}",
        )
    out: set[Trace] = set()
    current: Language = _EPSILON  # power body 0
    for n in range(0, hi + 1):
        if n > 0:
            current = _seq(current, body, max_traces)
        if freq.allows(n):
            out |= current
            _guard(len(out), max_traces, "boundedPower")
    return frozenset(out)


# ── PartialOrder: symbol-level merge respecting the closure ─────────────────


def _merges(traces: tuple[Trace, ...], preds: tuple[frozenset[int], ...]) -> Iterator[Trace]:
    """Yield every merge of ``traces`` in which each child's symbols stay in
    order and, for every closure edge ``p -> i``, child ``p`` is *fully*
    consumed before any symbol of child ``i`` is emitted.

    This is ``parallel`` (Lean's ``Interleaves``, generalised to n operands)
    restricted by the precedence relation — concatenating whole child
    languages in a linear extension would be strictly weaker, since two
    mutually unordered children must be free to interleave symbol by symbol.
    """
    n = len(traces)
    total = sum(len(t) for t in traces)
    pos = [0] * n
    acc: list[str] = []

    def rec() -> Iterator[Trace]:
        if len(acc) == total:
            yield tuple(acc)
            return
        for i in range(n):
            if pos[i] >= len(traces[i]):
                continue
            if any(pos[p] < len(traces[p]) for p in preds[i]):
                continue
            acc.append(traces[i][pos[i]])
            pos[i] += 1
            yield from rec()
            pos[i] -= 1
            acc.pop()

    yield from rec()


def _partial_order_body(node: PartialOrder, max_traces: int, max_unrolls: int) -> Language:
    n = len(node.children)
    preds = tuple(
        frozenset(e.src for e in node.closure if e.dst == i) for i in range(n)
    )
    child_langs = [
        sorted(language(c, max_traces=max_traces, max_unrolls=max_unrolls))
        for c in node.children
    ]
    out: set[Trace] = set()
    for combo in product(*child_langs):
        for merged in _merges(combo, preds):
            out.add(merged)
            _guard(len(out), max_traces, "PartialOrder")
    return frozenset(out)


# ── ChoiceGraph: bounded start->end walks ───────────────────────────────────


def _walks(node: ChoiceGraph, max_unrolls: int) -> Iterator[tuple[int, ...]]:
    """Yield every ``start -> end`` walk visiting each node at most
    ``max_unrolls`` times. Cycles are legal — that is how POWL 2.0 expresses
    iteration — and are terminated by the visit cap, never rejected."""
    succ: dict[int, list[int]] = {}
    for e in node.edges:
        succ.setdefault(e.src, []).append(e.dst)
    for v in succ.values():
        v.sort()
    counts: Counter[int] = Counter()
    path: list[int] = []

    def rec(cur: int) -> Iterator[tuple[int, ...]]:
        if counts[cur] >= max_unrolls:
            return
        counts[cur] += 1
        path.append(cur)
        if cur == node.end:
            yield tuple(path)
        else:
            for nxt in succ.get(cur, ()):
                yield from rec(nxt)
        path.pop()
        counts[cur] -= 1

    yield from rec(node.start)


def _choice_graph_body(node: ChoiceGraph, max_traces: int, max_unrolls: int) -> Language:
    child_langs = [
        language(c, max_traces=max_traces, max_unrolls=max_unrolls) for c in node.children
    ]
    out: set[Trace] = set()
    for walk in _walks(node, max_unrolls):
        acc: Language = _EPSILON
        for idx in walk:
            acc = _seq(acc, child_langs[idx], max_traces)
        out |= acc
        _guard(len(out), max_traces, "ChoiceGraph")
    return frozenset(out)


# ── the entry point ─────────────────────────────────────────────────────────


def language(node: PowlNode, *, max_traces: int, max_unrolls: int) -> Language:
    """The bounded language of ``node``.

    ``Atom(label)`` denotes ``{(label,)}``; :class:`Silent`, :class:`Start`
    and :class:`End` denote ``{()}`` (Lean's ``epsilon``). Composites denote
    their body language under ``boundedPower`` of their
    :class:`~autofde_lab.powl.frequency.Frequency`.

    Raises :class:`~autofde_lab.powl.refusals.PowlError` with
    ``BOUND_EXHAUSTED`` if either bound is hit, and with
    ``PROHIBITED_NODE_KIND`` for anything outside the six legal kinds.
    """
    _check_bounds(max_traces, max_unrolls)
    if isinstance(node, Atom):
        return frozenset({(node.label,)})
    if isinstance(node, (Silent, Start, End)):
        return _EPSILON
    if isinstance(node, PartialOrder):
        body = _partial_order_body(node, max_traces, max_unrolls)
    elif isinstance(node, ChoiceGraph):
        body = _choice_graph_body(node, max_traces, max_unrolls)
    else:
        raise PowlError(
            PowlRefusal.PROHIBITED_NODE_KIND,
            f"{type(node).__name__} is not a POWL 2.0 node kind",
        )
    out = _bounded_power(body, node.frequency, max_traces, max_unrolls)
    _guard(len(out), max_traces, type(node).__name__)
    return out


# ── enabled labels (structural, unbounded-safe) ─────────────────────────────


def _nullable(node: PowlNode) -> bool:
    """Whether ``node`` can produce the empty trace."""
    if isinstance(node, Atom):
        return False
    if isinstance(node, (Silent, Start, End)):
        return True
    if isinstance(node, PartialOrder):
        if node.frequency.is_skippable:
            return True
        return all(_nullable(c) for c in node.children)
    if isinstance(node, ChoiceGraph):
        if node.frequency.is_skippable:
            return True
        return _has_nullable_walk(node)
    raise PowlError(
        PowlRefusal.PROHIBITED_NODE_KIND,
        f"{type(node).__name__} is not a POWL 2.0 node kind",
    )


def _has_nullable_walk(node: ChoiceGraph) -> bool:
    succ: dict[int, list[int]] = {}
    for e in node.edges:
        succ.setdefault(e.src, []).append(e.dst)
    seen: set[int] = set()

    def rec(cur: int) -> bool:
        if cur in seen or not _nullable(node.children[cur]):
            return False
        if cur == node.end:
            return True
        seen.add(cur)
        return any(rec(n) for n in succ.get(cur, ()))

    return rec(node.start)


def enabled_labels(node: PowlNode) -> frozenset[str]:
    """Labels that can occur *first* in some trace of ``node``.

    Computed structurally, so it needs no bounds: a child is reachable-first
    inside a partial order exactly when every closure predecessor of it is
    nullable, and inside a choice graph exactly when it lies on a prefix of
    nullable nodes from ``start``.
    """
    if isinstance(node, Atom):
        return frozenset({node.label})
    if isinstance(node, (Silent, Start, End)):
        return frozenset()
    if isinstance(node, PartialOrder):
        if node.frequency.max == 0:
            return frozenset()
        n = len(node.children)
        preds = [
            frozenset(e.src for e in node.closure if e.dst == i) for i in range(n)
        ]
        out: set[str] = set()
        for i in range(n):
            if all(_nullable(node.children[p]) for p in preds[i]):
                out |= enabled_labels(node.children[i])
        return frozenset(out)
    if isinstance(node, ChoiceGraph):
        if node.frequency.max == 0:
            return frozenset()
        succ: dict[int, list[int]] = {}
        for e in node.edges:
            succ.setdefault(e.src, []).append(e.dst)
        out = set()
        seen: set[int] = set()
        stack = [node.start]
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            out |= enabled_labels(node.children[cur])
            if _nullable(node.children[cur]):
                stack.extend(succ.get(cur, ()))
        return frozenset(out)
    raise PowlError(
        PowlRefusal.PROHIBITED_NODE_KIND,
        f"{type(node).__name__} is not a POWL 2.0 node kind",
    )
