# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Tests for the POWL 2.0 denotational semantics.

Every model here is small enough that its language is hand-computable, so the
assertions are on exact sets, never on cardinality alone. The exact expected set
per model is unchanged by compression — the models are now rows in a table whose
failure message reports every model whose language came out wrong, instead of one
item per model that stops at the first.
"""

from __future__ import annotations

from autofde_lab.powl import (
    ONCE,
    Atom,
    ChoiceGraph,
    ChoiceGraphEdge,
    Frequency,
    NodeId,
    OrderEdge,
    PartialOrder,
    PowlRefusal,
    Silent,
    Start,
)
from autofde_lab.powl.semantics import enabled_labels, interleavings, language

from ._accumulate import Failures

A, B, C = Atom("a"), Atom("b"), Atom("c")


def lang(node, max_traces=1024, max_unrolls=3):
    return language(node, max_traces=max_traces, max_unrolls=max_unrolls)


def edge(i, j):
    return OrderEdge(NodeId(i), NodeId(j))


def cedge(i, j):
    return ChoiceGraphEdge(NodeId(i), NodeId(j))


def two_branch_choice() -> ChoiceGraph:
    """start -> {a, b} -> end; a hand-computable union."""
    return ChoiceGraph(
        (Silent(), Silent(), A, B),
        frozenset({cedge(0, 2), cedge(2, 1), cedge(0, 3), cedge(3, 1)}),
        start=0,
        end=1,
    )


def _self_looping_a() -> ChoiceGraph:
    """start -> a, a -> a (iteration), a -> end."""
    return ChoiceGraph(
        (Silent(), Silent(), A),
        frozenset({cedge(0, 2), cedge(2, 2), cedge(2, 1)}),
        start=0,
        end=1,
        frequency=ONCE,
    )


# ── interleavings (Lean: Interleaves) ───────────────────────────────────────


def test_interleavings_matches_the_lean_specification():
    assert set(interleavings((), ())) == {()}
    assert set(interleavings(("a", "b"), ())) == {("a", "b")}
    assert set(interleavings((), ("a", "b"))) == {("a", "b")}
    # order-preserving shuffle: ("b", "a", "c") is absent because it violates
    # a-before-b inside the left operand.
    assert set(interleavings(("a", "b"), ("c",))) == {
        ("a", "b", "c"),
        ("a", "c", "b"),
        ("c", "a", "b"),
    }


# ── exact languages ─────────────────────────────────────────────────────────


def test_exact_language_of_every_hand_computable_model():
    """One property (``language(model)`` equals a hand-computed set) over every
    node kind. Rows are checked independently and all mismatches are reported."""
    inner_ac = PartialOrder((A, C), frozenset({edge(0, 1)}))
    inner_ab = PartialOrder((A, B), frozenset({edge(0, 1)}))

    cases = [
        # leaves
        ("atom", A, {}, {("a",)}),
        ("silent", Silent(), {}, {()}),
        ("start", Start(), {}, {()}),
        # partial orders
        ("unordered pair gives both orders", PartialOrder((A, B)), {},
         {("a", "b"), ("b", "a")}),
        ("edge a->b gives only one order", PartialOrder((A, B), frozenset({edge(0, 1)})),
         {}, {("a", "b")}),
        ("silent child contributes no symbol",
         PartialOrder((A, Silent()), frozenset({edge(0, 1)})), {}, {("a",)}),
        # a -> c, b unordered with both
        ("three atoms with one edge", PartialOrder((A, B, C), frozenset({edge(0, 2)})),
         {}, {("a", "b", "c"), ("a", "c", "b"), ("b", "a", "c")}),
        # (a -> c) concurrent with b: b may land between a and c
        ("nested partial orders interleave symbol by symbol",
         PartialOrder((inner_ac, B)), {},
         {("a", "c", "b"), ("a", "b", "c"), ("b", "a", "c")}),
        ("frequency repeats the body",
         PartialOrder((A, B), frozenset({edge(0, 1)}), Frequency(0, 2)), {},
         {(), ("a", "b"), ("a", "b", "a", "b")}),
        ("unbounded frequency is capped, not refused",
         PartialOrder((A, Silent()), frozenset({edge(0, 1)}), Frequency(1, None)),
         {"max_unrolls": 3}, {("a",), ("a", "a"), ("a", "a", "a")}),
        # choice graphs
        ("choice graph is the union of its branches", two_branch_choice(), {},
         {("a",), ("b",)}),
        ("cyclic choice graph at max_unrolls=1", _self_looping_a(),
         {"max_unrolls": 1}, {("a",)}),
        ("cyclic choice graph at max_unrolls=3", _self_looping_a(),
         {"max_unrolls": 3}, {("a",), ("a", "a"), ("a", "a", "a")}),
        ("branches of different lengths", ChoiceGraph(
            (Silent(), Silent(), inner_ab, C),
            frozenset({cedge(0, 2), cedge(2, 1), cedge(0, 3), cedge(3, 1)}),
            start=0, end=1), {}, {("a", "b"), ("c",)}),
    ]

    failures = Failures()
    for name, node, kwargs, expected in cases:
        try:
            got = lang(node, **kwargs)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{name}: language() raised {exc!r}")
            continue
        failures.check(
            got == frozenset(expected),
            f"{name}: expected {sorted(expected)}, got {sorted(got)}",
        )
    assert not failures, failures.report()


# ── bounds RAISE, never truncate ────────────────────────────────────────────


def test_bounds_raise_rather_than_truncating():
    """A truncated language silently claims a model has fewer behaviours than it
    has, so every way of exceeding a bound must refuse. Four distinct ways."""
    po3 = PartialOrder((A, B, C))
    assert len(lang(po3)) == 6, "the unbounded case must still be computable"

    cases = [
        ("max_traces exceeded", lambda: lang(po3, max_traces=3)),
        ("cyclic choice graph exceeds max_traces",
         lambda: lang(ChoiceGraph(
             (Silent(), Silent(), A),
             frozenset({cedge(0, 2), cedge(2, 2), cedge(2, 1)}),
             start=0, end=1), max_traces=2, max_unrolls=5)),
        ("explicit frequency beyond the unroll cap",
         lambda: lang(PartialOrder((A, B), frequency=Frequency(1, 9)), max_unrolls=3)),
        ("nonsense bounds", lambda: language(A, max_traces=0, max_unrolls=1)),
    ]
    failures = Failures()
    for name, run in cases:
        failures.expect_refusal(name, run, PowlRefusal.BOUND_EXHAUSTED)
    assert not failures, failures.report()


# ── enabled_labels ──────────────────────────────────────────────────────────


def test_enabled_labels_of_every_shape():
    cases = [
        ("atom", A, {"a"}),
        ("silent", Silent(), set()),
        ("unordered pair", PartialOrder((A, B)), {"a", "b"}),
        ("precedence a->b", PartialOrder((A, B), frozenset({edge(0, 1)})), {"a"}),
        ("nullable predecessor is seen through",
         PartialOrder((Silent(), B), frozenset({edge(0, 1)})), {"b"}),
        ("choice graph is the union of its branches", two_branch_choice(), {"a", "b"}),
    ]
    failures = Failures()
    for name, node, expected in cases:
        got = enabled_labels(node)
        failures.check(
            got == frozenset(expected),
            f"{name}: expected {sorted(expected)}, got {sorted(got)}",
        )
    assert not failures, failures.report()


def test_enabled_labels_agrees_with_the_language_first_symbols():
    """The independent cross-check: ``enabled_labels`` and ``language`` are
    different algorithms and must agree on which symbols can come first."""
    failures = Failures()
    for node in (
        PartialOrder((A, B, C), frozenset({edge(0, 2)})),
        two_branch_choice(),
        PartialOrder((PartialOrder((A, C), frozenset({edge(0, 1)})), B)),
    ):
        first = frozenset(t[0] for t in lang(node) if t)
        failures.check(
            enabled_labels(node) == first,
            f"{node!r}: enabled_labels={sorted(enabled_labels(node))} "
            f"but language first-symbols={sorted(first)}",
        )
    assert not failures, failures.report()
