# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Independent language membership for POWL 2.0 models.

**This module must never import** :mod:`autofde_lab.powl.executor`, and it does
not. It exists to answer "is this trace genuinely in the language of this
model?" by a *different algorithm* than the one that produced the trace. If it
shared the executor's code path it would only prove that the executor agrees
with itself, which is not a check at all. Its only intra-package imports are
:mod:`autofde_lab.powl.algebra`, :mod:`autofde_lab.powl.identity` and
:mod:`autofde_lab.powl.refusals`.

Algorithm — no enumeration
--------------------------
Membership is decided structurally, not by generating the language:

* :class:`~autofde_lab.powl.algebra.PartialOrder` — the trace's label multiset
  must equal the children's, occurrences are assigned to children by a
  canonical topological-order-stable rule, and for every ``(i, j)`` in the
  **closed** order the last position assigned to child ``i`` must precede the
  first position assigned to child ``j``. That is ``O(n^2 + len(trace))``.
* :class:`~autofde_lab.powl.algebra.ChoiceGraph` — every child consumes a fixed,
  statically-known number of labels, so the trace is matched against a
  ``start -> end`` walk in ``edges`` by reachability over
  ``(trace position, child index)`` states, with a visited set so a cyclic
  choice graph (legal, and how POWL 2.0 expresses iteration) terminates.
* :class:`~autofde_lab.powl.algebra.Atom` — the trace is exactly its label.
* :class:`~autofde_lab.powl.algebra.Start`, ``End``, ``Silent`` — the empty trace.

Composite children are recursed into on their projected subtrace.

Documented limitation
---------------------
A composite carrying a :class:`~autofde_lab.powl.frequency.Frequency` other than
``ONCE`` makes the label multiset of the model non-static, and this check is
static by construction. Such a model raises
:data:`~autofde_lab.powl.refusals.PowlRefusal.IRREDUCIBLE_PROJECTION` rather than
silently returning a verdict it cannot justify.

Nothing here actuates, admits, brokers, or issues receipts.
"""

from __future__ import annotations

from collections import Counter, deque
from itertools import product
from typing import Sequence

from autofde_lab.powl.algebra import (
    Atom,
    ChoiceGraph,
    End,
    PartialOrder,
    PowlNode,
    Silent,
    Start,
)
from autofde_lab.powl.frequency import ONCE
from autofde_lab.powl.refusals import PowlError, PowlRefusal

__all__ = ["trace_in_language", "explain", "static_labels", "label_options"]

#: Ceiling on how many alternative label sequences a subtree may contribute
#: before this checker declines to decide. A refusal to decide is reported as a
#: rejection reason, never as a silent ``False`` dressed up as a verdict.
MAX_LABEL_OPTIONS = 512


class _TooManyOptions(Exception):
    """Internal: the option set for a subtree exceeded ``MAX_LABEL_OPTIONS``."""


def label_options(node: PowlNode) -> tuple[tuple[str, ...], ...] | None:
    """Every label sequence a single traversal of ``node`` can emit.

    Returns ``None`` when the set is larger than :data:`MAX_LABEL_OPTIONS`.

    This is what lets a :class:`~autofde_lab.powl.algebra.ChoiceGraph` nested
    inside a :class:`~autofde_lab.powl.algebra.PartialOrder` be decided at all:
    ``static_labels`` cannot name one label footprint for a branching subtree,
    but the *set* of footprints is finite and small for real models, and the
    enclosing partial order can be checked against each in turn.

    Documented limitation, narrower than the one it replaces: a choice graph is
    enumerated over its **simple** ``start -> end`` walks, so a trace that goes
    round a cycle more than once is not enumerated here. The root-level choice
    graph check is a reachability search and does handle cycles; only the
    nested-in-a-partial-order case is bounded this way.
    """
    try:
        return _label_options(node)
    except _TooManyOptions:
        return None


def _label_options(node: PowlNode) -> tuple[tuple[str, ...], ...]:
    if isinstance(node, Atom):
        return ((node.label,),)
    if isinstance(node, (Start, End, Silent)):
        return ((),)
    if isinstance(node, PartialOrder):
        _require_once(node)
        acc: list[tuple[str, ...]] = [()]
        for child in node.children:
            opts = _label_options(child)
            nxt: list[tuple[str, ...]] = []
            for prefix in acc:
                for opt in opts:
                    nxt.append(prefix + opt)
                    if len(nxt) > MAX_LABEL_OPTIONS:
                        raise _TooManyOptions
            acc = nxt
        return tuple(dict.fromkeys(acc))
    if isinstance(node, ChoiceGraph):
        _require_once(node)
        succs: dict[int, list[int]] = {}
        for e in sorted(node.edges):
            succs.setdefault(e.src, []).append(e.dst)
        out: list[tuple[str, ...]] = []

        def walk(cur: int, visited: frozenset, prefixes: list) -> None:
            opts = _label_options(node.children[cur])
            here = [p + o for p in prefixes for o in opts]
            if len(here) > MAX_LABEL_OPTIONS:
                raise _TooManyOptions
            if cur == node.end:
                out.extend(here)
                if len(out) > MAX_LABEL_OPTIONS:
                    raise _TooManyOptions
                return
            for d in succs.get(cur, []):
                if d in visited:
                    continue  # simple walks only; see the docstring
                walk(d, visited | {d}, here)

        walk(node.start, frozenset({node.start}), [()])
        return tuple(dict.fromkeys(out))
    raise PowlError(
        PowlRefusal.PROHIBITED_NODE_KIND,
        f"{type(node).__name__} is not a POWL 2.0 node kind",
    )


# ── static label footprint ──────────────────────────────────────────────────


def _require_once(node: PowlNode) -> None:
    freq = getattr(node, "frequency", ONCE)
    if freq != ONCE:
        raise PowlError(
            PowlRefusal.IRREDUCIBLE_PROJECTION,
            f"{type(node).__name__} carries frequency "
            f"(min={freq.min}, max={freq.max}); the static membership check "
            "decides only frequency ONCE models",
        )


def static_labels(node: PowlNode) -> tuple[str, ...]:
    """Labels a single traversal of ``node`` must emit, in child order.

    Raises ``IRREDUCIBLE_PROJECTION`` if any composite in the subtree carries a
    frequency other than ``ONCE``, and ``PROHIBITED_NODE_KIND`` for a
    non-POWL-2.0 node.
    """
    if isinstance(node, Atom):
        return (node.label,)
    if isinstance(node, (Start, End, Silent)):
        return ()
    if isinstance(node, PartialOrder):
        _require_once(node)
        out: list[str] = []
        for child in node.children:
            out.extend(static_labels(child))
        return tuple(out)
    if isinstance(node, ChoiceGraph):
        _require_once(node)
        for child in node.children:
            static_labels(child)  # validate subtree eagerly
        return ()  # length is branch-dependent; see _choice_lengths
    raise PowlError(
        PowlRefusal.PROHIBITED_NODE_KIND,
        f"{type(node).__name__} is not a POWL 2.0 node kind",
    )


def _fixed_length(node: PowlNode) -> int | None:
    """Number of labels ``node`` emits, or ``None`` if branch-dependent.

    Derived from :func:`label_options` rather than from child arity. An earlier
    version returned the *child* length for a choice graph whose children all
    had the same length, which is wrong: a choice graph emits one label sequence
    per ``start -> end`` walk, and the walks differ in length.
    """
    opts = label_options(node)
    if opts is None:
        return None
    lengths = {len(o) for o in opts}
    return lengths.pop() if len(lengths) == 1 else None


# ── partial order ───────────────────────────────────────────────────────────


def _topological_order(node: PartialOrder) -> list[int]:
    """Deterministic topological order of ``node``'s child indices."""
    n = len(node.children)
    preds = [0] * n
    succs: list[list[int]] = [[] for _ in range(n)]
    for e in sorted(node.order):
        preds[e.dst] += 1
        succs[e.src].append(e.dst)
    ready = deque(sorted(i for i in range(n) if preds[i] == 0))
    order: list[int] = []
    while ready:
        i = ready.popleft()
        order.append(i)
        for j in sorted(succs[i]):
            preds[j] -= 1
            if preds[j] == 0:
                ready.append(j)
    return order


def _assign_positions(
    node: PartialOrder, trace: Sequence[str], child_labels: list
) -> list[list[int]] | str:
    """Assign each trace position to a child, or return a failure reason."""
    n = len(node.children)

    expected = Counter(lbl for labels in child_labels for lbl in labels)
    seen = Counter(trace)
    if expected != seen:
        missing = expected - seen
        extra = seen - expected
        parts = []
        if missing:
            parts.append(f"missing occurrence(s) {dict(sorted(missing.items()))}")
        if extra:
            parts.append(f"unexpected/duplicate occurrence(s) {dict(sorted(extra.items()))}")
        return "multiset mismatch: " + "; ".join(parts)

    # Slots for each label, ordered by a topological order of the children, so
    # a label shared by two ordered children is assigned consistently with the
    # precedence relation rather than by tuple position.
    slots: dict[str, deque[int]] = {}
    for i in _topological_order(node):
        for lbl in child_labels[i]:
            slots.setdefault(lbl, deque()).append(i)

    positions: list[list[int]] = [[] for _ in range(n)]
    for p, lbl in enumerate(trace):
        positions[slots[lbl].popleft()].append(p)
    return positions


def _check_partial_order(node: PartialOrder, trace: Sequence[str]) -> str | None:
    """Decide ``trace`` against ``node``, trying every branch combination.

    A child whose label footprint is branch-dependent (a nested choice graph)
    contributes one option per branch; the partial order is checked against each
    combination and accepted if any one holds. Without this, a genuinely
    in-language trace over a nested choice graph was rejected on a multiset
    mismatch.
    """
    per_child: list = []
    for i, child in enumerate(node.children):
        opts = label_options(child)
        if opts is None:
            return (
                f"child {i} contributes more than {MAX_LABEL_OPTIONS} alternative "
                "label sequences; membership is not statically decidable here"
            )
        per_child.append(opts)

    first_reason = None
    for count, combo in enumerate(product(*per_child)):
        if count >= MAX_LABEL_OPTIONS:
            return (
                f"more than {MAX_LABEL_OPTIONS} branch combinations; "
                "membership is not statically decidable here"
            )
        reason = _check_partial_order_fixed(node, trace, [list(o) for o in combo])
        if reason is None:
            return None
        if first_reason is None:
            first_reason = reason
    return first_reason or "partial order admits no label assignment"


def _check_partial_order_fixed(
    node: PartialOrder, trace: Sequence[str], child_labels: list
) -> str | None:
    assigned = _assign_positions(node, trace, child_labels)
    if isinstance(assigned, str):
        return assigned

    for e in sorted(node.closure):
        src, dst = assigned[e.src], assigned[e.dst]
        if not src or not dst:
            continue
        if max(src) >= min(dst):
            return (
                f"precedence violated: child {e.src} "
                f"({tuple(child_labels[e.src])}) must complete before "
                f"child {e.dst} ({tuple(child_labels[e.dst])}), but "
                f"last position {max(src)} is not before first position "
                f"{min(dst)}"
            )

    for i, child in enumerate(node.children):
        sub = tuple(trace[p] for p in assigned[i])
        reason = _check(child, sub)
        if reason is not None:
            return f"child {i}: {reason}"
    return None


# ── choice graph ────────────────────────────────────────────────────────────


def _check_choice_graph(node: ChoiceGraph, trace: Sequence[str]) -> str | None:
    n = len(node.children)
    lengths = [_fixed_length(c) for c in node.children]
    if any(length is None for length in lengths):
        return (
            "choice graph has a child whose label count is branch-dependent; "
            "membership is not statically decidable for this model"
        )
    succs: list[list[int]] = [[] for _ in range(n)]
    for e in sorted(node.edges):
        succs[e.src].append(e.dst)

    total = len(trace)
    # (position before matching child c, c)
    start_state = (0, node.start)
    seen_states = {start_state}
    frontier = deque([start_state])
    while frontier:
        pos, c = frontier.popleft()
        length = lengths[c]
        assert length is not None
        nxt = pos + length
        if nxt > total:
            continue
        if _check(node.children[c], tuple(trace[pos:nxt])) is not None:
            continue
        if c == node.end:
            if nxt == total:
                return None
            continue
        for d in succs[c]:
            state = (nxt, d)
            if state not in seen_states:
                seen_states.add(state)
                frontier.append(state)
    return (
        f"no start->end walk in the choice graph (start={node.start}, "
        f"end={node.end}) matches trace {tuple(trace)!r}"
    )


# ── dispatch ────────────────────────────────────────────────────────────────


def _check(node: PowlNode, trace: Sequence[str]) -> str | None:
    if isinstance(node, Atom):
        if tuple(trace) == (node.label,):
            return None
        return f"atom {node.label!r} expects exactly ({node.label!r},), got {tuple(trace)!r}"
    if isinstance(node, (Start, End, Silent)):
        if len(trace) == 0:
            return None
        return f"{type(node).__name__} emits no label, got {tuple(trace)!r}"
    if isinstance(node, PartialOrder):
        _require_once(node)
        return _check_partial_order(node, trace)
    if isinstance(node, ChoiceGraph):
        _require_once(node)
        return _check_choice_graph(node, trace)
    raise PowlError(
        PowlRefusal.PROHIBITED_NODE_KIND,
        f"{type(node).__name__} is not a POWL 2.0 node kind",
    )


def trace_in_language(node: PowlNode, trace: Sequence[str]) -> bool:
    """Whether ``trace`` is in the language of ``node``.

    Decided structurally, never by enumerating the language. See the module
    docstring for the algorithm and its one documented limitation.
    """
    return _check(node, trace) is None


def explain(node: PowlNode, trace: Sequence[str]) -> str:
    """Why ``trace`` is or is not in the language of ``node``.

    A bare ``False`` is not actionable, so every rejection names the specific
    structural law that was broken.
    """
    reason = _check(node, trace)
    if reason is None:
        return f"accepted: {tuple(trace)!r} is in the language of the model"
    return f"rejected: {reason}"
