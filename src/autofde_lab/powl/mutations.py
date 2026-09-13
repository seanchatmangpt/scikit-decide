# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""A real, mechanical, LLM-free POWL 2.0 mutation algebra.

Why this exists
----------------
This session's own live GEPA (LLM-based prompt optimization) tests were hard
disabled over real API cost concerns. Process *structure* optimization does
not need an LLM call per candidate: mutate a real, already-admitted
:mod:`autofde_lab.powl.algebra` tree with a pure, deterministic function,
re-validate with :func:`autofde_lab.powl.validate.validate_model`, score the
result against a real objective, and repeat -- thousands of times, at the
cost of Python function calls, not tokens. This module is the mutation half
of that loop; scoring and search order are a caller's concern, not this
module's.

Every function here operates on the real, frozen dataclasses defined in
``algebra.py`` (:class:`~autofde_lab.powl.algebra.PartialOrder`,
:class:`~autofde_lab.powl.algebra.ChoiceGraph`,
:class:`~autofde_lab.powl.algebra.Atom`, ...), and every mutation's own
output is re-validated by ``validate_model`` before this module returns it --
never a silently-broken graph. See ``algebra.py``, ``validate.py`` and
``guard_executor.py`` for the node/edge shapes and the arena/index convention
this module reuses.

Path addressing
----------------
A node inside a tree is addressed by a **path**: a tuple of 0-based child
indices from the root, e.g. ``()`` is the root itself, ``(2,)`` is the root's
third child, ``(2, 0)`` is that child's first child. This is exactly the same
arena/index convention ``algebra.py``'s own module docstring describes
("a composite node owns its children in a tuple ... edges reference those
children by 0-based index into that same tuple") and that
``guard_executor.py``'s topological walk (`_walk_partial_order`,
`_walk_choice_graph`) already uses when it iterates
``range(len(node.children))`` -- this module does not invent a new addressing
scheme, it names the one already implicit in the executor's own walk.

A path resolves through zero or more composite nodes (``PartialOrder`` or
``ChoiceGraph``) down to a *parent* whose ``children`` tuple is the thing
being mutated. ``parent_path`` in every function below names that composite;
the mutation itself acts on ``parent_path``'s direct children by index.

Purity
------
Every ``algebra.py`` dataclass is ``frozen=True``. Every function in this
module therefore returns a genuinely new node built via full reconstruction
(rebuilding parents at every level from the root down to the mutated node,
since a frozen tree cannot be mutated in place) -- it never calls
``object.__setattr__`` and never mutates its input. The root-to-leaf rebuild
is unavoidable structural sharing: only the nodes on the path to the mutation
are reconstructed, every sibling subtree is reused by reference (safe, since
those subtrees are themselves immutable).

Explicitly out of scope (named, not silently skipped)
-------------------------------------------------------
- **Choice-graph structural mutations beyond guards** (adding/removing a
  ``ChoiceGraphEdge`` itself, adding/removing a whole branch node) are not
  implemented here. Guard-only mutation
  (:func:`add_guard`/:func:`relax_guard`) is safe because it can never change
  reachability/co-reachability (``_validate_choice_graph``'s dominant
  refusal surface); editing the edge set itself risks
  ``CHOICE_GRAPH_DISCONNECTED`` or ``MULTI_BOUNDARY_CHOICE_GRAPH`` failures
  that need a real reachability-repair strategy, which is a genuinely
  separate piece of infrastructure from the arithmetic here. Left for a
  follow-up module rather than a half-safe implementation in this one.
- **Frequency mutation** (changing a composite's ``Frequency``) is not
  implemented -- it is a real, valid POWL 2.0 axis but orthogonal to the
  seven structural mutations named in this module's task, and folding it in
  would blur "structural mutation algebra" into "every mutable field".
- **Cross-subtree moves** (relocating a node from one parent to a different
  parent) are not implemented. Every mutation here acts within a single
  named ``parent_path``'s direct children; a real move operation would need
  to reconcile two different local index spaces and two different
  ``order``/``edges`` relations simultaneously, which is compositionally
  ``delete_node`` at the source followed by ``insert_atom`` (or an
  equivalent) at the destination -- callers can already compose those two
  primitives themselves.

Nothing in this module actuates, admits, brokers, or issues receipts.
"""

from __future__ import annotations

from typing import Tuple

from autofde_lab.powl.algebra import (
    Atom,
    ChoiceGraph,
    ChoiceGraphEdge,
    Guard,
    NodeId,
    OrderEdge,
    PartialOrder,
    PowlNode,
)
from autofde_lab.powl.refusals import PowlError, PowlRefusal
from autofde_lab.powl.validate import validate_model

__all__ = [
    "NodePath",
    "insert_atom",
    "delete_node",
    "reorder",
    "parallelize",
    "serialize",
    "add_guard",
    "relax_guard",
]

#: A node's address from the root: a tuple of 0-based child indices.
#: ``()`` is the root. ``(2, 0)`` is the root's 3rd child's 1st child.
NodePath = Tuple[int, ...]


# ── path resolution / rebuild machinery ────────────────────────────────────


def _resolve(root: PowlNode, path: NodePath) -> PowlNode:
    """Walk ``path`` from ``root`` and return the node it addresses."""
    node = root
    for step, idx in enumerate(path):
        if not isinstance(node, (PartialOrder, ChoiceGraph)):
            raise PowlError(
                PowlRefusal.DANGLING_REFERENCE,
                f"path {path}: index {step} names a composite child, but "
                f"{type(node).__name__} at that depth has no children",
            )
        if not (0 <= idx < len(node.children)):
            raise PowlError(
                PowlRefusal.DANGLING_REFERENCE,
                f"path {path}: index {idx} at depth {step} outside "
                f"range(0, {len(node.children)})",
            )
        node = node.children[idx]
    return node


def _rebuild_with_child_replaced(
    root: PowlNode, parent_path: NodePath, new_children: tuple, **composite_kwargs
) -> PowlNode:
    """Return a new tree identical to ``root`` except the composite node at
    ``parent_path`` is reconstructed with ``new_children`` (and any extra
    composite-specific kwargs, e.g. a rebuilt ``order``/``edges``), and every
    ancestor on the path down to it is rebuilt to point at the new node.

    Pure: never mutates ``root``. Structural sharing: every subtree not on
    ``parent_path`` is reused by reference.
    """
    parent = _resolve(root, parent_path)
    if not isinstance(parent, (PartialOrder, ChoiceGraph)):
        raise PowlError(
            PowlRefusal.DANGLING_REFERENCE,
            f"parent_path {parent_path} resolves to {type(parent).__name__}, "
            "which has no children to mutate",
        )
    if isinstance(parent, PartialOrder):
        new_parent: PowlNode = PartialOrder(
            children=new_children,
            order=composite_kwargs.get("order", frozenset()),
            frequency=parent.frequency,
        )
    else:
        new_parent = ChoiceGraph(
            children=new_children,
            edges=composite_kwargs.get("edges", frozenset()),
            start=composite_kwargs.get("start", parent.start),
            end=composite_kwargs.get("end", parent.end),
            frequency=parent.frequency,
        )
    return _replace_at_path(root, parent_path, new_parent)


def _replace_at_path(root: PowlNode, path: NodePath, replacement: PowlNode) -> PowlNode:
    """Return a new tree identical to ``root`` except the node at ``path`` is
    ``replacement``. Rebuilds every composite ancestor on ``path``."""
    if not path:
        return replacement
    idx = path[0]
    if not isinstance(root, (PartialOrder, ChoiceGraph)):
        raise PowlError(
            PowlRefusal.DANGLING_REFERENCE,
            f"path {path}: cannot descend into leaf node {type(root).__name__}",
        )
    if not (0 <= idx < len(root.children)):
        raise PowlError(
            PowlRefusal.DANGLING_REFERENCE,
            f"path {path}: index {idx} outside range(0, {len(root.children)})",
        )
    new_child = _replace_at_path(root.children[idx], path[1:], replacement)
    new_children = tuple(
        new_child if i == idx else c for i, c in enumerate(root.children)
    )
    if isinstance(root, PartialOrder):
        rebuilt: PowlNode = PartialOrder(
            children=new_children, order=root.order, frequency=root.frequency
        )
    else:
        rebuilt = ChoiceGraph(
            children=new_children,
            edges=root.edges,
            start=root.start,
            end=root.end,
            frequency=root.frequency,
        )
    return rebuilt


def _require_partial_order(root: PowlNode, path: NodePath) -> PartialOrder:
    node = _resolve(root, path)
    if not isinstance(node, PartialOrder):
        raise PowlError(
            PowlRefusal.PROHIBITED_NODE_KIND,
            f"parent_path {path} resolves to {type(node).__name__}, expected PartialOrder",
        )
    return node


def _require_choice_graph(root: PowlNode, path: NodePath) -> ChoiceGraph:
    node = _resolve(root, path)
    if not isinstance(node, ChoiceGraph):
        raise PowlError(
            PowlRefusal.PROHIBITED_NODE_KIND,
            f"choice_graph_path {path} resolves to {type(node).__name__}, expected ChoiceGraph",
        )
    return node


def _remap_order_edges(
    order: frozenset[OrderEdge], remap: dict[int, int]
) -> frozenset[OrderEdge]:
    """Rebuild ``order`` under an index remap; edges touching a dropped index
    (not present in ``remap``) are dropped."""
    out = set()
    for e in order:
        if e.src not in remap or e.dst not in remap:
            continue
        out.add(OrderEdge(NodeId(remap[e.src]), NodeId(remap[e.dst])))
    return frozenset(out)


def _remap_choice_edges(
    edges: frozenset[ChoiceGraphEdge], remap: dict[int, int]
) -> frozenset[ChoiceGraphEdge]:
    out = set()
    for e in edges:
        if e.src not in remap or e.dst not in remap:
            continue
        out.add(ChoiceGraphEdge(NodeId(remap[e.src]), NodeId(remap[e.dst]), guard=e.guard))
    return frozenset(out)


# ── mutations ────────────────────────────────────────────────────────────


def insert_atom(node: PowlNode, *, parent_path: NodePath, index: int, atom: Atom) -> PowlNode:
    """Insert ``atom`` as a new child of the ``PartialOrder`` at
    ``parent_path``, at position ``index`` (0-based, may equal
    ``len(children)`` to append). The new atom is inserted with no order
    edges to any sibling (i.e. it starts fully parallel to everything else);
    all existing ``order`` edges are remapped to the shifted indices.
    """
    parent = _require_partial_order(node, parent_path)
    n = len(parent.children)
    if not (0 <= index <= n):
        raise PowlError(
            PowlRefusal.DANGLING_REFERENCE, f"insert index {index} outside range(0, {n + 1})"
        )
    new_children = parent.children[:index] + (atom,) + parent.children[index:]

    # remap: old index i -> new index (i if i < index else i + 1)
    remap = {i: (i if i < index else i + 1) for i in range(n)}
    new_order = _remap_order_edges(parent.order, remap)

    result = _rebuild_with_child_replaced(node, parent_path, new_children, order=new_order)
    validate_model(result)
    return result


def delete_node(node: PowlNode, *, path: NodePath) -> PowlNode:
    """Remove the node addressed by ``path`` from its parent composite.

    The parent must have at least 3 children before deletion (so at least 2
    remain, satisfying each composite's own minimum arity). Edges/precedence
    touching the removed index are dropped, never left dangling; remaining
    indices are remapped down to stay contiguous.
    """
    if not path:
        raise PowlError(
            PowlRefusal.DANGLING_REFERENCE, "delete_node: cannot delete the root node"
        )
    parent_path, idx = path[:-1], path[-1]
    parent = _resolve(node, parent_path)
    if not isinstance(parent, (PartialOrder, ChoiceGraph)):
        raise PowlError(
            PowlRefusal.PROHIBITED_NODE_KIND,
            f"parent at {parent_path} is {type(parent).__name__}, has no children",
        )
    n = len(parent.children)
    if not (0 <= idx < n):
        raise PowlError(PowlRefusal.DANGLING_REFERENCE, f"index {idx} outside range(0, {n})")
    if n - 1 < 2:
        raise PowlError(
            PowlRefusal.INVALID_PARTIAL_ORDER_ARITY
            if isinstance(parent, PartialOrder)
            else PowlRefusal.INVALID_CHOICE_ARITY,
            f"deleting index {idx} would leave {n - 1} children, below the minimum of 2",
        )

    new_children = tuple(c for i, c in enumerate(parent.children) if i != idx)
    # remap: surviving old index -> new contiguous index; removed index absent
    remap: dict[int, int] = {}
    cursor = 0
    for i in range(n):
        if i == idx:
            continue
        remap[i] = cursor
        cursor += 1

    if isinstance(parent, PartialOrder):
        new_order = _remap_order_edges(parent.order, remap)
        result = _rebuild_with_child_replaced(node, parent_path, new_children, order=new_order)
    else:
        if idx == parent.start or idx == parent.end:
            raise PowlError(
                PowlRefusal.MULTI_BOUNDARY_CHOICE_GRAPH,
                f"cannot delete index {idx}: it is the ChoiceGraph start or end boundary",
            )
        new_edges = _remap_choice_edges(parent.edges, remap)
        result = _rebuild_with_child_replaced(
            node,
            parent_path,
            new_children,
            edges=new_edges,
            start=remap[parent.start],
            end=remap[parent.end],
        )
    validate_model(result)
    return result


def reorder(node: PowlNode, *, parent_path: NodePath, index_a: int, index_b: int) -> PowlNode:
    """Swap the positions of children ``index_a`` and ``index_b`` inside the
    ``PartialOrder`` at ``parent_path``.

    Refused if an existing order edge directly relates ``a`` and ``b``
    (swapping positions of two nodes with a direct precedence edge between
    them would silently invert that precedence, which is a
    ``serialize``/``parallelize`` concern, not a ``reorder`` concern). Every
    order edge's endpoints are remapped so precedence relative to *other*
    siblings survives the position swap intact.
    """
    parent = _require_partial_order(node, parent_path)
    n = len(parent.children)
    for label, idx in (("index_a", index_a), ("index_b", index_b)):
        if not (0 <= idx < n):
            raise PowlError(PowlRefusal.DANGLING_REFERENCE, f"{label}={idx} outside range(0, {n})")
    if index_a == index_b:
        raise PowlError(
            PowlRefusal.DANGLING_REFERENCE, "reorder requires index_a != index_b"
        )

    direct = {(e.src, e.dst) for e in parent.order}
    if (index_a, index_b) in direct or (index_b, index_a) in direct:
        raise PowlError(
            PowlRefusal.NOT_TRANSITIVELY_REDUCED,
            f"indices {index_a} and {index_b} are directly ordered; reorder refuses to "
            "invert an existing precedence edge -- use serialize/parallelize instead",
        )

    new_children = list(parent.children)
    new_children[index_a], new_children[index_b] = new_children[index_b], new_children[index_a]

    remap = {i: i for i in range(n)}
    remap[index_a], remap[index_b] = index_b, index_a
    new_order = _remap_order_edges(parent.order, remap)

    result = _rebuild_with_child_replaced(
        node, parent_path, tuple(new_children), order=new_order
    )
    validate_model(result)
    return result


def parallelize(node: PowlNode, *, parent_path: NodePath, index_a: int, index_b: int) -> PowlNode:
    """Remove the direct order edge between ``index_a`` and ``index_b`` in
    the ``PartialOrder`` at ``parent_path``, so they run in parallel.

    Refuses if no *direct* order edge exists between them (nothing to
    remove) -- this is a real structural precondition, not a courtesy: since
    ``PartialOrder.order`` stores the transitive reduction, an *indirect*
    precedence (``a`` before ``c`` before ``b``) is not represented as an
    ``a -> b`` edge at all, so there would be nothing to remove and no
    parallelization would actually occur.
    """
    parent = _require_partial_order(node, parent_path)
    n = len(parent.children)
    for label, idx in (("index_a", index_a), ("index_b", index_b)):
        if not (0 <= idx < n):
            raise PowlError(PowlRefusal.DANGLING_REFERENCE, f"{label}={idx} outside range(0, {n})")

    forward = OrderEdge(NodeId(index_a), NodeId(index_b))
    backward = OrderEdge(NodeId(index_b), NodeId(index_a))
    if forward in parent.order:
        removed = forward
    elif backward in parent.order:
        removed = backward
    else:
        raise PowlError(
            PowlRefusal.DANGLING_REFERENCE,
            f"no direct order edge between {index_a} and {index_b} to remove",
        )

    new_order = frozenset(e for e in parent.order if e != removed)
    result = _rebuild_with_child_replaced(node, parent_path, parent.children, order=new_order)
    validate_model(result)
    return result


def serialize(node: PowlNode, *, parent_path: NodePath, index_a: int, index_b: int) -> PowlNode:
    """Add a real order edge ``index_a -> index_b`` in the ``PartialOrder``
    at ``parent_path``, making two currently-parallel children sequential.

    Refuses if the two are already related (directly or transitively, in
    either direction) -- nothing to serialize. ``validate_model``
    (via ``PartialOrder``'s own construction-time ``transitive_closure``
    call) is the final authority on whether the new edge introduces a cycle.
    """
    parent = _require_partial_order(node, parent_path)
    n = len(parent.children)
    for label, idx in (("index_a", index_a), ("index_b", index_b)):
        if not (0 <= idx < n):
            raise PowlError(PowlRefusal.DANGLING_REFERENCE, f"{label}={idx} outside range(0, {n})")
    if index_a == index_b:
        raise PowlError(PowlRefusal.DANGLING_REFERENCE, "serialize requires index_a != index_b")

    closure_pairs = {(e.src, e.dst) for e in parent.closure}
    if (index_a, index_b) in closure_pairs or (index_b, index_a) in closure_pairs:
        raise PowlError(
            PowlRefusal.NOT_TRANSITIVELY_REDUCED,
            f"{index_a} and {index_b} are already ordered (directly or transitively); "
            "nothing to serialize",
        )

    new_order = frozenset(parent.order) | {OrderEdge(NodeId(index_a), NodeId(index_b))}
    result = _rebuild_with_child_replaced(node, parent_path, parent.children, order=new_order)
    validate_model(result)
    return result


def add_guard(
    node: PowlNode,
    *,
    choice_graph_path: NodePath,
    edge_src: int,
    edge_dst: int,
    guard: Guard,
) -> PowlNode:
    """Attach ``guard`` to the existing unguarded ``ChoiceGraphEdge``
    ``edge_src -> edge_dst`` inside the ``ChoiceGraph`` at
    ``choice_graph_path``.

    Refuses if no such unguarded edge exists (nothing to guard) -- a guarded
    edge with a *different* guard is a distinct edge, not the same edge with
    a new guard, so callers must ``relax_guard`` first if they want to
    replace one guard with another.
    """
    parent = _require_choice_graph(node, choice_graph_path)
    target = ChoiceGraphEdge(NodeId(edge_src), NodeId(edge_dst), guard=None)
    if target not in parent.edges:
        raise PowlError(
            PowlRefusal.DANGLING_REFERENCE,
            f"no unguarded edge {edge_src}->{edge_dst} exists to attach a guard to",
        )
    new_edges = frozenset(e for e in parent.edges if e != target) | {
        ChoiceGraphEdge(NodeId(edge_src), NodeId(edge_dst), guard=guard)
    }
    result = _rebuild_with_child_replaced(
        node,
        choice_graph_path,
        parent.children,
        edges=new_edges,
        start=parent.start,
        end=parent.end,
    )
    validate_model(result)
    return result


def relax_guard(
    node: PowlNode, *, choice_graph_path: NodePath, edge_src: int, edge_dst: int
) -> PowlNode:
    """Remove the guard from the ``ChoiceGraphEdge`` ``edge_src -> edge_dst``
    inside the ``ChoiceGraph`` at ``choice_graph_path``, making it
    unconditional.

    Refuses if no *guarded* edge with those endpoints exists. If an
    unguarded edge with the same endpoints already exists (two edges between
    the same pair of nodes, one guarded and one already unconditional),
    relaxing collapses them into the single already-present unguarded edge
    rather than raising a duplicate-edge error, since ``ChoiceGraph.edges``
    is a ``frozenset`` and two structurally identical unguarded edges are
    the same object.
    """
    parent = _require_choice_graph(node, choice_graph_path)
    guarded = [
        e for e in parent.edges if e.src == edge_src and e.dst == edge_dst and e.guard is not None
    ]
    if not guarded:
        raise PowlError(
            PowlRefusal.DANGLING_REFERENCE,
            f"no guarded edge {edge_src}->{edge_dst} exists to relax",
        )
    new_edges = frozenset(e for e in parent.edges if e not in guarded) | {
        ChoiceGraphEdge(NodeId(edge_src), NodeId(edge_dst), guard=None)
    }
    result = _rebuild_with_child_replaced(
        node,
        choice_graph_path,
        parent.children,
        edges=new_edges,
        start=parent.start,
        end=parent.end,
    )
    validate_model(result)
    return result
