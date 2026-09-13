# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Unit tests for the POWL 2.0 type foundation.

Compression note: the construction-time refusals used to be one item each (plus a
3-way parametrization over cycle shapes). They are now one table-driven item that
walks every case and accumulates, so a regression still names *every* offender
and its expected-vs-actual :class:`PowlRefusal` — the same falsifiers, one item.
"""

from __future__ import annotations

from autofde_lab.powl import (
    DEFAULT_BOUND,
    MAX_POWL_DEPTH,
    ONE_OR_MORE,
    OPTIONAL,
    ZERO_OR_MORE,
    Atom,
    ChoiceGraph,
    ChoiceGraphEdge,
    End,
    ExecutionBound,
    Frequency,
    OrderEdge,
    PartialOrder,
    PowlRefusal,
    Silent,
    Start,
    activity_sha256,
    node_depth,
    node_id,
    node_structure,
    transitive_closure,
    transitive_reduction,
)

from ._accumulate import Failures


def E(*pairs: tuple[int, int]) -> frozenset[OrderEdge]:
    return frozenset(OrderEdge(a, b) for a, b in pairs)


def atoms(n: int) -> tuple[Atom, ...]:
    return tuple(Atom(f"a{i}") for i in range(n))


def _at_max_depth():
    node = PartialOrder(atoms(2))  # depth 2
    for _ in range(MAX_POWL_DEPTH - 2):
        node = PartialOrder((node, Atom("x")))
    return node


# ── adversarial negatives ───────────────────────────────────────────────────


def test_construction_refuses_every_malformed_shape_with_its_own_refusal():
    """One item, N distinct falsifiers: each row names its own expected refusal.

    Rows here are *not* redraws of one property — an arity defect and a cycle
    defect fail for different reasons — so every row is checked and every
    mismatch is reported, rather than stopping at the first.
    """
    deep = _at_max_depth()
    assert node_depth(deep) == MAX_POWL_DEPTH

    cases = [
        ("partial-order arity", lambda: PartialOrder(atoms(1)),
         PowlRefusal.INVALID_PARTIAL_ORDER_ARITY),
        ("choice-graph arity", lambda: ChoiceGraph(atoms(1)),
         PowlRefusal.INVALID_CHOICE_ARITY),
        ("cycle 0<->1", lambda: PartialOrder(atoms(3), E((0, 1), (1, 0))),
         PowlRefusal.CYCLIC_PARTIAL_ORDER),
        ("self-loop 0->0", lambda: PartialOrder(atoms(3), E((0, 0))),
         PowlRefusal.CYCLIC_PARTIAL_ORDER),
        ("3-cycle", lambda: PartialOrder(atoms(3), E((0, 1), (1, 2), (2, 0))),
         PowlRefusal.CYCLIC_PARTIAL_ORDER),
        ("dangling order index", lambda: PartialOrder(atoms(2), E((0, 5))),
         PowlRefusal.DANGLING_REFERENCE),
        ("start has an incoming edge", lambda: ChoiceGraph(
            atoms(3),
            frozenset({ChoiceGraphEdge(0, 2), ChoiceGraphEdge(2, 0)}),
            start=0, end=1),
         PowlRefusal.MULTI_BOUNDARY_CHOICE_GRAPH),
        ("end has an outgoing edge", lambda: ChoiceGraph(
            atoms(3),
            frozenset({ChoiceGraphEdge(0, 1), ChoiceGraphEdge(1, 2)}),
            start=0, end=1),
         PowlRefusal.MULTI_BOUNDARY_CHOICE_GRAPH),
        ("depth 9", lambda: PartialOrder((deep, Atom("x"))),
         PowlRefusal.DEPTH_EXCEEDED),
        ("OrderEdge inside a choice graph", lambda: ChoiceGraph(
            atoms(2), frozenset({OrderEdge(0, 1)}), start=0, end=1),
         PowlRefusal.EDGE_TYPE_MISMATCH),
        ("ChoiceGraphEdge inside a partial order", lambda: PartialOrder(
            atoms(2), frozenset({ChoiceGraphEdge(0, 1)})),
         PowlRefusal.EDGE_TYPE_MISMATCH),
        ("bare tuple is not an edge", lambda: PartialOrder(
            atoms(2), frozenset({(0, 1)})),
         PowlRefusal.EDGE_TYPE_MISMATCH),
        ("frequency min > max", lambda: Frequency(min=3, max=2),
         PowlRefusal.INVALID_FREQUENCY),
        ("frequency negative min", lambda: Frequency(min=-1),
         PowlRefusal.INVALID_FREQUENCY),
    ]

    failures = Failures()
    for name, build, expected in cases:
        failures.expect_refusal(name, build, expected)
    assert not failures, failures.report()


def test_cyclic_choice_graph_is_accepted():
    """POWL 2.0 expresses iteration as a cycle; it must never be refused.

    Kept standalone: this is the only signal for "the validator over-refuses
    iteration", the opposite defect class from every row in the table above.
    """
    cg = ChoiceGraph(
        atoms(4),
        frozenset(
            {
                ChoiceGraphEdge(0, 1),
                ChoiceGraphEdge(1, 2),
                ChoiceGraphEdge(2, 1),  # <- the cycle
                ChoiceGraphEdge(2, 3),
            }
        ),
        start=0,
        end=3,
        frequency=ZERO_OR_MORE,
    )
    assert ChoiceGraphEdge(2, 1) in cg.edges
    assert node_depth(cg) == 2


def test_edge_types_are_not_interchangeable_by_value():
    assert OrderEdge(0, 1) != ChoiceGraphEdge(0, 1)
    assert OrderEdge(0, 1) != (0, 1)


# ── frequency positives ─────────────────────────────────────────────────────


def test_frequency_semantics():
    assert Frequency().allows(1) and not Frequency().allows(0)
    assert OPTIONAL.is_skippable and not OPTIONAL.is_repeatable
    assert ONE_OR_MORE.is_unbounded and ONE_OR_MORE.is_repeatable
    assert ZERO_OR_MORE.is_skippable and ZERO_OR_MORE.allows(9999)
    assert not ZERO_OR_MORE.allows(-1)


# ── closure / reduction algebra ─────────────────────────────────────────────

DAGS = [
    (3, E((0, 1), (1, 2))),
    (4, E((0, 1), (0, 2), (1, 3), (2, 3))),
    (5, E((0, 1), (1, 2), (2, 3), (3, 4), (0, 4))),
    (6, E((0, 1), (0, 2), (1, 3), (2, 4), (3, 5), (4, 5), (0, 5))),
    (4, frozenset()),
    (5, E((4, 0), (0, 3), (3, 1))),
]


def test_reduce_close_idempotence_over_every_dag():
    """One invariant redrawn over six DAGs -> one item that walks all six."""
    failures = Failures()
    for n, edges in DAGS:
        red = transitive_reduction(edges, n)
        failures.check(
            transitive_reduction(transitive_closure(edges, n), n) == red,
            f"n={n} {sorted(edges)}: reduce(close(E)) != reduce(E)",
        )
        failures.check(
            transitive_reduction(red, n) == red, f"n={n}: reduction is not idempotent"
        )
        failures.check(
            transitive_closure(red, n) == transitive_closure(edges, n),
            f"n={n}: reduction did not preserve the closure",
        )
    assert not failures, failures.report()
    # the concrete shortcut case, spelled out so the property has a witness
    assert transitive_reduction(E((0, 1), (1, 2), (0, 2)), 3) == E((0, 1), (1, 2))
    assert transitive_closure(E((0, 1), (1, 2)), 3) == E((0, 1), (1, 2), (0, 2))


def test_partial_order_normalizes_input_to_reduction_over_every_dag():
    failures = Failures()
    for n, edges in DAGS:
        children = atoms(n)
        from_closure = PartialOrder(children, transitive_closure(edges, n))
        from_reduction = PartialOrder(children, transitive_reduction(edges, n))
        from_raw = PartialOrder(children, edges)
        failures.check(
            from_closure == from_reduction == from_raw,
            f"n={n} {sorted(edges)}: closure/reduction/raw inputs are not equal",
        )
        failures.check(
            hash(from_closure) == hash(from_reduction) == hash(from_raw),
            f"n={n}: hashes differ across equivalent inputs",
        )
        failures.check(
            from_closure.order == transitive_reduction(edges, n),
            f"n={n}: .order is not the reduction",
        )
        failures.check(
            from_closure.closure == transitive_closure(edges, n),
            f"n={n}: .closure is not the closure",
        )
    assert not failures, failures.report()

    po = PartialOrder(atoms(4), E((0, 1), (1, 2), (2, 3)))
    assert po.closure is po.closure  # same object, not recomputed
    assert len(po.closure) == 6 and len(po.order) == 3


def test_value_equality_and_hashing():
    a, b = PartialOrder(atoms(3), E((0, 1))), PartialOrder(atoms(3), E((0, 1)))
    assert a is not b and a == b and len({a, b}) == 1
    pay_a = Atom("pay", bindings={"amount": 3, "cur": "EUR"})
    pay_b = Atom("pay", bindings={"cur": "EUR", "amount": 3})
    assert pay_a == pay_b and hash(pay_a) == hash(pay_b)
    assert Atom("pay") != pay_a
    assert Start() == Start() and End() == End() and Silent() == Silent()
    assert Start() != End()


# ── identity ────────────────────────────────────────────────────────────────


def test_node_id_is_stable_where_it_must_be_and_sensitive_where_it_must_be():
    """Both halves accumulate: over-sensitivity and under-sensitivity are
    opposite defects and each row below can fail for its own reason."""
    n = 4
    edges = E((0, 1), (0, 2), (1, 3), (2, 3))
    inner = PartialOrder(atoms(2))
    base = PartialOrder(atoms(2))
    shortcut = PartialOrder(atoms(3), E((0, 1), (1, 2), (0, 2)))
    plain = PartialOrder(atoms(3), E((0, 1), (1, 2)))

    same = [
        ("edge-input order", PartialOrder(atoms(n), frozenset(sorted(edges))),
         PartialOrder(atoms(n), frozenset(sorted(edges, reverse=True)))),
        ("closure vs reduction input", PartialOrder(atoms(n), frozenset(sorted(edges))),
         PartialOrder(atoms(n), transitive_closure(edges, n))),
        ("explicit shortcut edge", shortcut, plain),
    ]
    different = [
        ("fewer edges", plain, PartialOrder(atoms(3), E((0, 1)))),
        ("frequency", base, PartialOrder(atoms(2), frequency=ZERO_OR_MORE)),
        ("labels", base, PartialOrder((Atom("z"), Atom("a1")))),
        ("nesting level", PartialOrder((inner, Atom("t")), E((0, 1))), inner),
    ]

    failures = Failures()
    for name, x, y in same:
        failures.check(node_id(x) == node_id(y), f"{name}: node_id must be stable")
    for name, x, y in different:
        failures.check(node_id(x) != node_id(y), f"{name}: node_id must differ")
    assert not failures, failures.report()

    outer = PartialOrder((inner, Atom("t")), E((0, 1)))
    assert node_structure(outer)["children"][0] == node_id(inner), "identity is Merkle"


def test_activity_sha256_covers_label_and_bindings_and_rejects_non_atoms():
    assert activity_sha256(Atom("a")) == activity_sha256(Atom("a"))
    assert activity_sha256(Atom("a")) != activity_sha256(Atom("b"))
    assert activity_sha256(Atom("a", bindings={"k": 1})) != activity_sha256(Atom("a"))
    assert len(activity_sha256(Atom("a"))) == 64
    failures = Failures()
    failures.expect_refusal(
        "activity_sha256(Silent())",
        lambda: activity_sha256(Silent()),
        PowlRefusal.PROHIBITED_NODE_KIND,
    )
    assert not failures, failures.report()


# ── bounds ──────────────────────────────────────────────────────────────────


def test_execution_bound_digest():
    assert DEFAULT_BOUND.sha256() == ExecutionBound().sha256()
    assert len(DEFAULT_BOUND.sha256()) == 64
    assert ExecutionBound(1, 2, 3).sha256() != DEFAULT_BOUND.sha256()
