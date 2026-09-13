# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Structural well-formedness checking for POWL 2.0 models.

This module answers exactly one question: *is this object graph a legal POWL
2.0 model?* It says nothing about what the model would do if executed.

Anti-self-attestation
---------------------
**This module must never import** :mod:`autofde_lab.powl.executor` or
:mod:`autofde_lab.powl.semantics`, now or ever — not directly, not transitively,
not inside a function body, not under ``TYPE_CHECKING``. A validator that
shares a code path with the machinery that produced (or interprets) the model
is not an independent check: it would attest to its own output. The two halves
of the pair are kept apart by construction, and
``tests/powl/test_import_separation.py`` enforces the separation in a fresh
subprocess so an accidental re-coupling fails a test rather than passing
silently.

Redundancy with construction is deliberate
------------------------------------------
:mod:`autofde_lab.powl.algebra` already refuses most of these conditions at
construction time. A model can nevertheless reach this function without having
passed through those constructors — deserialized from a wire form, rebuilt by
``object.__setattr__``, or produced by a future builder. The validator
therefore re-derives every structural property from the stored fields instead
of trusting any cached value.

Cycles in a choice graph are legal
----------------------------------
A cycle in a :class:`~autofde_lab.powl.algebra.ChoiceGraph` is how POWL 2.0
expresses iteration and is **never** a refusal. Only a cycle in a
:class:`~autofde_lab.powl.algebra.PartialOrder` is.

Nothing in this module actuates, admits, brokers, or issues receipts.
"""

from __future__ import annotations

from autofde_lab.powl.algebra import (
    MAX_POWL_DEPTH,
    Atom,
    ChoiceGraph,
    ChoiceGraphEdge,
    End,
    Guard,
    OrderEdge,
    PartialOrder,
    PowlNode,
    Silent,
    Start,
    transitive_reduction,
)
from autofde_lab.powl.frequency import Frequency
from autofde_lab.powl.refusals import PowlError, PowlRefusal

__all__ = ["validate_model"]

_LEAF_KINDS = (Start, End, Atom, Silent)


def validate_model(node: PowlNode) -> None:
    """Validate ``node`` and every descendant, structurally.

    Returns ``None`` when the model is well formed; otherwise raises
    :class:`~autofde_lab.powl.refusals.PowlError` carrying the specific
    :class:`~autofde_lab.powl.refusals.PowlRefusal` that was violated.
    """
    _validate(node, depth=1)


# ── recursion ───────────────────────────────────────────────────────────────


def _validate(node: PowlNode, depth: int) -> None:
    if depth > MAX_POWL_DEPTH:
        raise PowlError(
            PowlRefusal.DEPTH_EXCEEDED,
            f"nesting depth {depth} exceeds MAX_POWL_DEPTH={MAX_POWL_DEPTH}",
        )
    if isinstance(node, _LEAF_KINDS):
        return
    if isinstance(node, PartialOrder):
        _validate_partial_order(node)
    elif isinstance(node, ChoiceGraph):
        _validate_choice_graph(node)
    else:
        raise PowlError(
            PowlRefusal.PROHIBITED_NODE_KIND,
            f"{type(node).__name__} is not a POWL 2.0 node kind",
        )
    for child in node.children:
        _validate(child, depth + 1)


# ── shared checks ───────────────────────────────────────────────────────────


def _validate_frequency(freq: object, where: str) -> None:
    if not isinstance(freq, Frequency):
        raise PowlError(
            PowlRefusal.INVALID_FREQUENCY,
            f"{where}: frequency must be a Frequency, got {type(freq).__name__}",
        )
    if not isinstance(freq.min, int) or isinstance(freq.min, bool) or freq.min < 0:
        raise PowlError(
            PowlRefusal.INVALID_FREQUENCY, f"{where}: min={freq.min!r} is not a natural number"
        )
    if freq.max is not None:
        if not isinstance(freq.max, int) or isinstance(freq.max, bool):
            raise PowlError(
                PowlRefusal.INVALID_FREQUENCY,
                f"{where}: max={freq.max!r} is neither int nor None",
            )
        if freq.max < freq.min:
            raise PowlError(
                PowlRefusal.INVALID_FREQUENCY, f"{where}: max={freq.max} < min={freq.min}"
            )


def _check_endpoints(edges: frozenset, n: int, expected: type, where: str) -> None:
    for e in edges:
        if not isinstance(e, expected):
            raise PowlError(
                PowlRefusal.EDGE_TYPE_MISMATCH,
                f"{where}: expected {expected.__name__}, got {type(e).__name__}",
            )
        if not (0 <= e.src < n) or not (0 <= e.dst < n):
            raise PowlError(
                PowlRefusal.DANGLING_REFERENCE,
                f"{where}: edge {e.src}->{e.dst} outside range(0, {n})",
            )


# ── PartialOrder ────────────────────────────────────────────────────────────


def _validate_partial_order(node: PartialOrder) -> None:
    n = len(node.children)
    if n < 2:
        raise PowlError(
            PowlRefusal.INVALID_PARTIAL_ORDER_ARITY,
            f"PartialOrder requires n >= 2 children, got {n}",
        )
    _validate_frequency(node.frequency, "PartialOrder")
    order = frozenset(node.order)
    _check_endpoints(order, n, OrderEdge, "PartialOrder.order")

    for e in order:
        if e.src == e.dst:
            raise PowlError(
                PowlRefusal.CYCLIC_PARTIAL_ORDER,
                f"PartialOrder.order is not irreflexive: self-loop at index {e.src}",
            )

    # Acyclicity, recomputed from the stored reduction — never from a cache.
    # transitive_reduction raises CYCLIC_PARTIAL_ORDER on a cyclic relation.
    reduction = transitive_reduction(order, n)
    if reduction != order:
        raise PowlError(
            PowlRefusal.NOT_TRANSITIVELY_REDUCED,
            f"PartialOrder.order holds {len(order)} edges but its transitive "
            f"reduction holds {len(reduction)}; canonical storage is the reduction",
        )

    _validate_closure(node, n)


def _validate_closure(node: PartialOrder, n: int) -> None:
    closure = frozenset(node.closure)
    _check_endpoints(closure, n, OrderEdge, "PartialOrder.closure")
    pairs = {(e.src, e.dst) for e in closure}
    for i, j in pairs:
        if i == j:
            raise PowlError(
                PowlRefusal.CYCLIC_PARTIAL_ORDER,
                f"PartialOrder.closure is not irreflexive: self-loop at index {i}",
            )
        if (j, i) in pairs:
            raise PowlError(
                PowlRefusal.CYCLIC_PARTIAL_ORDER,
                f"PartialOrder.closure is not antisymmetric: {i}<->{j}",
            )
    for i, j in pairs:
        for k in range(n):
            if (j, k) in pairs and (i, k) not in pairs:
                raise PowlError(
                    PowlRefusal.NOT_TRANSITIVELY_REDUCED,
                    f"PartialOrder.closure is not transitive: {i}->{j}->{k} "
                    f"present but {i}->{k} missing",
                )


# ── ChoiceGraph ─────────────────────────────────────────────────────────────


def _validate_choice_graph(node: ChoiceGraph) -> None:
    n = len(node.children)
    if n < 2:
        raise PowlError(
            PowlRefusal.INVALID_CHOICE_ARITY,
            f"ChoiceGraph requires n >= 2 children, got {n} (required_min=2)",
        )
    _validate_frequency(node.frequency, "ChoiceGraph")
    edges = frozenset(node.edges)
    _check_endpoints(edges, n, ChoiceGraphEdge, "ChoiceGraph.edges")

    for name, idx in (("start", node.start), ("end", node.end)):
        if not isinstance(idx, int) or isinstance(idx, bool) or not (0 <= idx < n):
            raise PowlError(
                PowlRefusal.DANGLING_REFERENCE,
                f"ChoiceGraph.{name}={idx!r} outside range(0, {n})",
            )
    if node.start == node.end:
        raise PowlError(
            PowlRefusal.MULTI_BOUNDARY_CHOICE_GRAPH,
            f"ChoiceGraph start and end coincide at index {node.start}",
        )
    for e in edges:
        if e.dst == node.start:
            raise PowlError(
                PowlRefusal.MULTI_BOUNDARY_CHOICE_GRAPH,
                f"ChoiceGraph start index {node.start} has an incoming edge from {e.src}",
            )
        if e.src == node.end:
            raise PowlError(
                PowlRefusal.MULTI_BOUNDARY_CHOICE_GRAPH,
                f"ChoiceGraph end index {node.end} has an outgoing edge to {e.dst}",
            )

    _validate_guard_exclusivity(edges, n)

    # Cycles are LEGAL here — iteration in POWL 2.0 is a cyclic choice graph.
    # Only reachability and co-reachability are required.
    succ: dict[int, set[int]] = {i: set() for i in range(n)}
    pred: dict[int, set[int]] = {i: set() for i in range(n)}
    for e in edges:
        succ[e.src].add(e.dst)
        pred[e.dst].add(e.src)

    forward = _traverse(node.start, succ)
    backward = _traverse(node.end, pred)
    for i in range(n):
        if i not in forward:
            raise PowlError(
                PowlRefusal.CHOICE_GRAPH_DISCONNECTED,
                f"ChoiceGraph node index {i} is not reachable from start={node.start}",
            )
        if i not in backward:
            raise PowlError(
                PowlRefusal.CHOICE_GRAPH_DISCONNECTED,
                f"ChoiceGraph node index {i} does not co-reach end={node.end}",
            )


def _validate_guard_exclusivity(edges: frozenset[ChoiceGraphEdge], n: int) -> None:
    """For every source node with more than one outgoing edge WHERE AT LEAST
    ONE outgoing edge carries a guard: no two outgoing edges may carry the
    identical guard (a real, checkable structural duplicate — the executor
    would have no principled way to choose between two edges guarded by the
    same predicate), and at most one outgoing edge may be unguarded (a real
    "else" edge) — two or more unguarded edges alongside a guarded one is a
    genuine ambiguity an executor cannot resolve without guessing.

    Nodes with NO guarded outgoing edges at all are untouched by this rule —
    a ChoiceGraph with several unguarded outgoing edges from one node is
    POWL 2.0's own pre-existing, legal free-choice/nondeterministic-branch
    shape (real fixtures predating this session's guard vocabulary rely on
    it); this rule only fires once a caller has introduced at least one real
    guard at that node, at which point leaving other branches ambiguously
    unguarded is far more likely a real authoring mistake than an
    intentional nondeterministic fallback.

    This does not (cannot, without evaluating predicates) prove semantic
    mutual exclusivity of distinct guard predicates -- it is the structural
    half of that requirement, matching this module's own stated scope
    ("is this object graph a legal POWL 2.0 model?").
    """
    by_src: dict[int, list[ChoiceGraphEdge]] = {i: [] for i in range(n)}
    for e in edges:
        by_src[e.src].append(e)

    for src, outgoing in by_src.items():
        if len(outgoing) < 2:
            continue
        guarded = [e for e in outgoing if e.guard is not None]
        if not guarded:
            continue
        unguarded = [e for e in outgoing if e.guard is None]
        if len(unguarded) > 1:
            raise PowlError(
                PowlRefusal.AMBIGUOUS_CHOICE_GUARD,
                f"ChoiceGraph node index {src} has {len(unguarded)} unguarded "
                "outgoing edges alongside a guarded edge -- at most one "
                "unguarded 'else' edge is allowed once guards are in use",
            )
        guard_keys: dict[str, int] = {}
        for e in outgoing:
            if e.guard is None:
                continue
            if not isinstance(e.guard, Guard):
                raise PowlError(
                    PowlRefusal.AMBIGUOUS_CHOICE_GUARD,
                    f"ChoiceGraph node index {src}: edge guard is {type(e.guard).__name__}, not Guard",
                )
            if e.guard.key in guard_keys:
                raise PowlError(
                    PowlRefusal.AMBIGUOUS_CHOICE_GUARD,
                    f"ChoiceGraph node index {src} has two outgoing edges sharing "
                    f"the identical guard {e.guard.predicate_name!r} -- an executor "
                    "cannot choose between them",
                )
            guard_keys[e.guard.key] = e.dst


def _traverse(origin: int, adj: dict[int, set[int]]) -> set[int]:
    """Nodes reachable from ``origin`` following ``adj``; cycle-safe."""
    seen = {origin}
    stack = [origin]
    while stack:
        cur = stack.pop()
        for nxt in adj[cur]:
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return seen
