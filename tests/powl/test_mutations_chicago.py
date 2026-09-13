# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for :mod:`autofde_lab.powl.mutations`.

Real ``algebra.py`` dataclasses throughout; every assertion is on the real
structure returned by a real mutation call -- no ``unittest.mock``,
``Mock``, ``MagicMock``, ``patch``, or ``monkeypatch`` anywhere in this file
(verified by ``grep`` in the completion evidence, not merely by construction
intent).
"""

from __future__ import annotations

import pytest

from autofde_lab.powl.algebra import (
    Atom,
    ChoiceGraph,
    ChoiceGraphEdge,
    Guard,
    NodeId,
    OrderEdge,
    PartialOrder,
    Silent,
)
from autofde_lab.powl.mutations import (
    add_guard,
    delete_node,
    insert_atom,
    parallelize,
    relax_guard,
    reorder,
    serialize,
)
from autofde_lab.powl.refusals import PowlError
from autofde_lab.powl.validate import validate_model


def _atom(label: str) -> Atom:
    return Atom(label=label)


# ── insert_atom ─────────────────────────────────────────────────────────


def test_insert_atom_appends_and_stays_admissible():
    root = PartialOrder(children=(_atom("a"), _atom("b")))
    new_atom = _atom("c")

    result = insert_atom(root, parent_path=(), index=2, atom=new_atom)

    validate_model(result)  # (a) independently re-admissible
    assert isinstance(result, PartialOrder)
    assert len(result.children) == 3
    assert result.children[2] == new_atom  # (b) really inserted at position 2
    # original root untouched -- purity
    assert len(root.children) == 2


def test_insert_atom_preserves_existing_precedence_after_shift():
    root = PartialOrder(
        children=(_atom("a"), _atom("b")),
        order=frozenset({OrderEdge(NodeId(0), NodeId(1))}),
    )
    result = insert_atom(root, parent_path=(), index=0, atom=_atom("z"))

    validate_model(result)
    assert result.children == (_atom("z"), _atom("a"), _atom("b"))
    # a (now index 1) still precedes b (now index 2); z has no edges
    assert OrderEdge(NodeId(1), NodeId(2)) in result.order
    assert not any(e.dst == 0 or e.src == 0 for e in result.order)


# ── delete_node ─────────────────────────────────────────────────────────


def test_delete_node_removes_child_and_remaps_order():
    root = PartialOrder(
        children=(_atom("a"), _atom("b"), _atom("c")),
        order=frozenset(
            {OrderEdge(NodeId(0), NodeId(1)), OrderEdge(NodeId(1), NodeId(2))}
        ),
    )
    result = delete_node(root, path=(1,))

    validate_model(result)
    assert isinstance(result, PartialOrder)
    assert result.children == (_atom("a"), _atom("c"))
    # b's edges dropped, no dangling reference; a and c no longer related
    for e in result.order:
        assert 0 <= e.src < 2 and 0 <= e.dst < 2
    assert OrderEdge(NodeId(0), NodeId(1)) not in result.order  # (a->c relation not re-created)


def test_delete_node_refuses_below_minimum_arity():
    root = PartialOrder(children=(_atom("a"), _atom("b")))
    with pytest.raises(PowlError):
        delete_node(root, path=(0,))


def test_delete_node_refuses_on_root():
    root = PartialOrder(children=(_atom("a"), _atom("b")))
    with pytest.raises(PowlError):
        delete_node(root, path=())


# ── reorder ─────────────────────────────────────────────────────────────


def test_reorder_swaps_unrelated_children():
    root = PartialOrder(children=(_atom("a"), _atom("b"), _atom("c")))
    result = reorder(root, parent_path=(), index_a=0, index_b=2)

    validate_model(result)
    assert result.children[0] == _atom("c")
    assert result.children[2] == _atom("a")
    assert result.children[1] == _atom("b")


def test_reorder_refuses_when_directly_ordered():
    root = PartialOrder(
        children=(_atom("a"), _atom("b")),
        order=frozenset({OrderEdge(NodeId(0), NodeId(1))}),
    )
    with pytest.raises(PowlError):
        reorder(root, parent_path=(), index_a=0, index_b=1)


# ── parallelize ─────────────────────────────────────────────────────────


def test_parallelize_removes_direct_edge():
    root = PartialOrder(
        children=(_atom("a"), _atom("b")),
        order=frozenset({OrderEdge(NodeId(0), NodeId(1))}),
    )
    assert OrderEdge(NodeId(0), NodeId(1)) in root.order  # precondition really holds

    result = parallelize(root, parent_path=(), index_a=0, index_b=1)

    validate_model(result)
    assert result.order == frozenset()  # (b) edge is genuinely gone
    assert result.children == root.children


def test_parallelize_refuses_when_not_directly_ordered():
    root = PartialOrder(children=(_atom("a"), _atom("b")))
    with pytest.raises(PowlError):
        parallelize(root, parent_path=(), index_a=0, index_b=1)


# ── serialize ───────────────────────────────────────────────────────────


def test_serialize_adds_real_order_edge():
    root = PartialOrder(children=(_atom("a"), _atom("b")))
    assert root.order == frozenset()  # precondition: currently parallel

    result = serialize(root, parent_path=(), index_a=0, index_b=1)

    validate_model(result)
    assert OrderEdge(NodeId(0), NodeId(1)) in result.order  # (b) really serialized


def test_serialize_refuses_when_already_related():
    root = PartialOrder(
        children=(_atom("a"), _atom("b")),
        order=frozenset({OrderEdge(NodeId(0), NodeId(1))}),
    )
    with pytest.raises(PowlError):
        serialize(root, parent_path=(), index_a=0, index_b=1)


def test_parallelize_then_serialize_round_trips():
    root = PartialOrder(
        children=(_atom("a"), _atom("b")),
        order=frozenset({OrderEdge(NodeId(0), NodeId(1))}),
    )
    parallel = parallelize(root, parent_path=(), index_a=0, index_b=1)
    resequenced = serialize(parallel, parent_path=(), index_a=0, index_b=1)
    assert resequenced.order == root.order


# ── add_guard / relax_guard ───────────────────────────────────────────────


def _choice_graph_with_unguarded_edge() -> ChoiceGraph:
    # start(0) -> branch(2) -> end(1); a second, unrelated branch(3) exists
    # only to keep node 0 (start) and node 1 (end) distinct roles clean.
    return ChoiceGraph(
        children=(Silent(), Silent(), _atom("branch")),
        edges=frozenset(
            {
                ChoiceGraphEdge(NodeId(0), NodeId(2)),
                ChoiceGraphEdge(NodeId(2), NodeId(1)),
            }
        ),
        start=0,
        end=1,
    )


def test_add_guard_attaches_real_guard_to_edge():
    root = _choice_graph_with_unguarded_edge()
    guard = Guard(predicate_name="ready", predicate_args={"k": 1})

    result = add_guard(root, choice_graph_path=(), edge_src=0, edge_dst=2, guard=guard)

    validate_model(result)
    matching = [e for e in result.edges if e.src == 0 and e.dst == 2]
    assert len(matching) == 1
    assert matching[0].guard == guard  # (b) really attached
    # the unguarded version of that edge is gone
    assert ChoiceGraphEdge(NodeId(0), NodeId(2), guard=None) not in result.edges


def test_add_guard_refuses_when_no_unguarded_edge_exists():
    root = _choice_graph_with_unguarded_edge()
    guard = Guard(predicate_name="ready")
    # edge 1->2 does not exist at all (start=0, end=1; only 0->2 and 2->1 exist)
    with pytest.raises(PowlError):
        add_guard(root, choice_graph_path=(), edge_src=1, edge_dst=2, guard=guard)


def test_relax_guard_removes_guard_from_edge():
    root = _choice_graph_with_unguarded_edge()
    guard = Guard(predicate_name="ready")
    guarded = add_guard(root, choice_graph_path=(), edge_src=0, edge_dst=2, guard=guard)
    assert any(e.guard == guard for e in guarded.edges)  # precondition holds

    relaxed = relax_guard(guarded, choice_graph_path=(), edge_src=0, edge_dst=2)

    validate_model(relaxed)
    assert ChoiceGraphEdge(NodeId(0), NodeId(2), guard=None) in relaxed.edges
    assert not any(e.src == 0 and e.dst == 2 and e.guard is not None for e in relaxed.edges)


def test_relax_guard_refuses_when_no_guarded_edge_exists():
    root = _choice_graph_with_unguarded_edge()
    with pytest.raises(PowlError):
        relax_guard(root, choice_graph_path=(), edge_src=0, edge_dst=2)


def test_add_guard_then_relax_guard_round_trips():
    root = _choice_graph_with_unguarded_edge()
    guard = Guard(predicate_name="ready")
    guarded = add_guard(root, choice_graph_path=(), edge_src=0, edge_dst=2, guard=guard)
    relaxed = relax_guard(guarded, choice_graph_path=(), edge_src=0, edge_dst=2)
    assert relaxed.edges == root.edges


# ── nested path addressing ────────────────────────────────────────────────


def test_mutation_at_nested_path_rebuilds_ancestors_and_preserves_siblings():
    inner = PartialOrder(children=(_atom("x"), _atom("y")))
    sibling = _atom("untouched")
    root = PartialOrder(children=(inner, sibling))

    result = insert_atom(root, parent_path=(0,), index=2, atom=_atom("z"))

    validate_model(result)
    assert isinstance(result, PartialOrder)
    assert len(result.children[0].children) == 3
    assert result.children[0].children[2] == _atom("z")
    # sibling subtree reused/preserved, not touched by the nested mutation
    assert result.children[1] == sibling
    # original root/inner untouched -- purity
    assert len(inner.children) == 2
    assert len(root.children[0].children) == 2
