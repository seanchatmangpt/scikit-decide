# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Adversarial structural-validation tests for :mod:`autofde_lab.powl.validate`.

Every refusal ``validate_model`` can raise still gets a model built specifically
to trigger it, and the *exact* refusal is still asserted — not merely that a
``PowlError`` occurred. What changed is packaging: the cases are now rows in two
accumulating tables instead of one pytest item each, so a regression reports
every offending row rather than only the first alphabetically.

This file is **not** redundant with ``test_algebra.py`` even where the refusal
names coincide: ``test_algebra.py`` exercises ``__post_init__`` (the constructor
path), this file exercises ``validate_model`` on ``_raw`` objects (the wire /
future-builder path). They are different functions and a defect in one is
invisible to the other.

Why ``_raw`` exists
-------------------
:mod:`autofde_lab.powl.algebra` refuses most malformed inputs at construction, so
several of these models cannot be built through the normal constructors.
:func:`_raw` allocates the frozen dataclass and writes its fields directly.
"""

from __future__ import annotations

from dataclasses import dataclass

from autofde_lab.powl.algebra import (
    Atom,
    ChoiceGraph,
    ChoiceGraphEdge,
    End,
    OrderEdge,
    PartialOrder,
    Silent,
    Start,
)
from autofde_lab.powl.frequency import ONCE, ZERO_OR_MORE, Frequency
from autofde_lab.powl.refusals import PowlRefusal
from autofde_lab.powl.validate import validate_model

from ._accumulate import Failures


def _raw(cls, **fields):
    """Allocate ``cls`` without running ``__post_init__`` and set fields directly."""
    obj = object.__new__(cls)
    for name, value in fields.items():
        object.__setattr__(obj, name, value)
    return obj


def _raw_po(children, order=frozenset(), frequency=ONCE, closure=None):
    return _raw(
        PartialOrder,
        children=tuple(children),
        order=frozenset(order),
        frequency=frequency,
        _closure=frozenset(order if closure is None else closure),
        _depth=2,
    )


def _raw_cg(children, edges=frozenset(), start=0, end=1, frequency=ONCE):
    return _raw(
        ChoiceGraph,
        children=tuple(children),
        edges=frozenset(edges),
        start=start,
        end=end,
        frequency=frequency,
        _depth=2,
    )


A, B, C, D = Atom("a"), Atom("b"), Atom("c"), Atom("d")


@dataclass(frozen=True)
class _Xor:
    """POWL 1.0's ``Xor`` — prohibited in POWL 2.0."""

    children: tuple = ()


def _max_depth_nesting():
    node = PartialOrder((A, B))  # depth 2
    for _ in range(6):
        node = PartialOrder((node, Atom("x")))  # -> depth 8, the legal maximum
    return node


# ── positives ───────────────────────────────────────────────────────────────


def test_wellformed_models_are_accepted():
    """One property (``validate_model`` returns ``None``) over every legal shape.

    Each row is a distinct *over-refusal* defect; the loop accumulates so a
    validator that started rejecting, say, self-loops names that row.
    """
    deep = _max_depth_nesting()
    assert deep.depth == 8

    cases = {
        "leaf Start": Start(),
        "leaf End": End(),
        "leaf Silent": Silent(),
        "leaf Atom": Atom("a"),
        "well-formed partial order": PartialOrder(
            (A, B, C), frozenset({OrderEdge(0, 1), OrderEdge(1, 2)})
        ),
        # construction normalizes a closure input to the reduction
        "partial order built from a closure": PartialOrder(
            (A, B, C), frozenset({OrderEdge(0, 1), OrderEdge(1, 2), OrderEdge(0, 2)})
        ),
        "well-formed choice graph": ChoiceGraph(
            (A, B), frozenset({ChoiceGraphEdge(0, 1)}), start=0, end=1
        ),
        # a cycle in a choice graph is iteration, not a defect. ~/powlv2lsp
        # rejects this shape; POWL 2.0 requires accepting it.
        "cyclic choice graph": ChoiceGraph(
            (A, B, C, D),
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
        ),
        "self-loop in a choice graph": ChoiceGraph(
            (A, B, C),
            frozenset(
                {
                    ChoiceGraphEdge(0, 1),
                    ChoiceGraphEdge(1, 1),  # <- repeat this step
                    ChoiceGraphEdge(1, 2),
                }
            ),
            start=0,
            end=2,
        ),
        "nesting at max depth": deep,
        "ZERO_OR_MORE frequency": PartialOrder((A, B), frozenset(), frequency=ZERO_OR_MORE),
    }

    failures = Failures()
    for name, node in cases.items():
        failures.expect_ok(name, lambda node=node: validate_model(node))
        failures.check(
            validate_model(node) is None, f"{name}: validate_model must return None"
        )
    assert not failures, failures.report()


# ── negatives: every refusal the validator can raise ────────────────────────


def test_every_structural_defect_raises_its_own_refusal():
    """N distinct falsifiers in one item — each row carries its own expected
    :class:`PowlRefusal` (and, where the message is load-bearing, its own
    expected detail substring). Nothing short-circuits."""
    legal_depth_8 = _max_depth_nesting()

    R = PowlRefusal
    cases = [
        # arity
        ("partial-order arity", _raw_po((A,)), R.INVALID_PARTIAL_ORDER_ARITY, ""),
        ("choice-graph arity", _raw_cg((A,)), R.INVALID_CHOICE_ARITY, ""),
        # partial order relation laws
        ("order not irreflexive", _raw_po((A, B), {OrderEdge(0, 0)}),
         R.CYCLIC_PARTIAL_ORDER, ""),
        ("order cyclic", _raw_po(
            (A, B, C), {OrderEdge(0, 1), OrderEdge(1, 2), OrderEdge(2, 0)}),
         R.CYCLIC_PARTIAL_ORDER, ""),
        ("closure not antisymmetric", _raw_po(
            (A, B), order=frozenset(), closure={OrderEdge(0, 1), OrderEdge(1, 0)}),
         R.CYCLIC_PARTIAL_ORDER, ""),
        ("closure not irreflexive", _raw_po(
            (A, B), order=frozenset(), closure={OrderEdge(1, 1)}),
         R.CYCLIC_PARTIAL_ORDER, ""),
        # stored order is the closure, not the reduction: refuse the wire form
        ("order not transitively reduced", _raw_po(
            (A, B, C), {OrderEdge(0, 1), OrderEdge(1, 2), OrderEdge(0, 2)}),
         R.NOT_TRANSITIVELY_REDUCED, ""),
        ("closure not transitive", _raw_po(
            (A, B, C),
            order={OrderEdge(0, 1), OrderEdge(1, 2)},
            closure={OrderEdge(0, 1), OrderEdge(1, 2)}),  # missing 0->2
         R.NOT_TRANSITIVELY_REDUCED, ""),
        # dangling references
        ("dangling order edge", _raw_po((A, B), {OrderEdge(0, 7)}),
         R.DANGLING_REFERENCE, ""),
        ("dangling choice-graph edge", _raw_cg((A, B), {ChoiceGraphEdge(0, 9)}),
         R.DANGLING_REFERENCE, ""),
        ("dangling start index", _raw_cg((A, B), frozenset(), start=5, end=1),
         R.DANGLING_REFERENCE, ""),
        ("dangling end index", _raw_cg((A, B), frozenset(), start=0, end=-1),
         R.DANGLING_REFERENCE, ""),
        # edge types
        ("choice edge in a partial order", _raw_po((A, B), {ChoiceGraphEdge(0, 1)}),
         R.EDGE_TYPE_MISMATCH, ""),
        ("order edge in a choice graph", _raw_cg((A, B), {OrderEdge(0, 1)}),
         R.EDGE_TYPE_MISMATCH, ""),
        # choice-graph boundary
        ("start has an incoming edge", _raw_cg(
            (A, B, C), {ChoiceGraphEdge(2, 0), ChoiceGraphEdge(0, 1)}, start=0, end=1),
         R.MULTI_BOUNDARY_CHOICE_GRAPH, ""),
        ("end has an outgoing edge", _raw_cg(
            (A, B, C), {ChoiceGraphEdge(0, 1), ChoiceGraphEdge(1, 2)}, start=0, end=1),
         R.MULTI_BOUNDARY_CHOICE_GRAPH, ""),
        ("start equals end", _raw_cg((A, B), frozenset(), start=1, end=1),
         R.MULTI_BOUNDARY_CHOICE_GRAPH, ""),
        # connectivity — the detail string is the only thing separating these two
        ("node unreachable from start", ChoiceGraph(
            (A, B, C), frozenset({ChoiceGraphEdge(0, 1)}), start=0, end=1),
         R.CHOICE_GRAPH_DISCONNECTED, "not reachable from start"),
        ("node does not co-reach end", ChoiceGraph(
            (A, B, C),
            frozenset({ChoiceGraphEdge(0, 1), ChoiceGraphEdge(0, 2)}),
            start=0, end=1),
         R.CHOICE_GRAPH_DISCONNECTED, "co-reach"),
        # depth
        ("height 9", _raw_po((legal_depth_8, Atom("y"))), R.DEPTH_EXCEEDED, ""),
        # frequency
        ("frequency wrong type", _raw_po((A, B), frequency="often"),
         R.INVALID_FREQUENCY, ""),
        ("frequency max below min", _raw_cg(
            (A, B), {ChoiceGraphEdge(0, 1)}, frequency=_raw(Frequency, min=3, max=1)),
         R.INVALID_FREQUENCY, ""),
        ("frequency negative min", _raw_po(
            (A, B), frequency=_raw(Frequency, min=-1, max=None)),
         R.INVALID_FREQUENCY, ""),
        # prohibited node kinds
        ("POWL 1.0 Xor at the root", _Xor((A, B)), R.PROHIBITED_NODE_KIND, ""),
    ]

    failures = Failures()
    for name, node, expected, detail in cases:
        failures.expect_refusal(
            name, lambda node=node: validate_model(node), expected, detail
        )
    assert not failures, failures.report()


def test_validation_recurses_into_children():
    """A defect buried in a grandchild is still found — the only signal for
    "the validator checks the root and stops"."""
    failures = Failures()
    buried_cg = _raw_cg((A, B, C), frozenset({ChoiceGraphEdge(0, 1)}), start=0, end=1)
    failures.expect_refusal(
        "disconnected choice graph as a grandchild",
        lambda: validate_model(PartialOrder((PartialOrder((A, buried_cg)), B))),
        PowlRefusal.CHOICE_GRAPH_DISCONNECTED,
    )
    failures.expect_refusal(
        "prohibited node kind as a child",
        lambda: validate_model(_raw_po((A, _Xor((B, C))))),
        PowlRefusal.PROHIBITED_NODE_KIND,
    )
    assert not failures, failures.report()
