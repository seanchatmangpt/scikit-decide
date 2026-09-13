# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Membership is decided independently of any executor."""

from __future__ import annotations

from autofde_lab.powl.algebra import (
    Atom,
    ChoiceGraph,
    ChoiceGraphEdge,
    End,
    NodeId,
    OrderEdge,
    PartialOrder,
    Silent,
)
from autofde_lab.powl.frequency import ONE_OR_MORE
from autofde_lab.powl.membership import explain, static_labels, trace_in_language
from autofde_lab.powl.refusals import PowlRefusal

from ._accumulate import Failures


def _diamond() -> PartialOrder:
    """a -> b, a -> c, b -> d, c -> d."""
    return PartialOrder(
        children=(Atom("a"), Atom("b"), Atom("c"), Atom("d")),
        order=frozenset(
            {
                OrderEdge(NodeId(0), NodeId(1)),
                OrderEdge(NodeId(0), NodeId(2)),
                OrderEdge(NodeId(1), NodeId(3)),
                OrderEdge(NodeId(2), NodeId(3)),
            }
        ),
    )


def test_membership_module_does_not_import_the_executor():
    import autofde_lab.powl.membership as m

    src = open(m.__file__).read()
    import_lines = [
        line
        for line in src.splitlines()
        if line.startswith(("import ", "from ")) or line.lstrip().startswith(("import ", "from "))
    ]
    assert import_lines  # guard against a vacuous pass
    assert not [line for line in import_lines if "executor" in line]
    # and the loaded module object never grew the dependency either
    assert not any(
        "executor" in name for name in vars(m) if not name.startswith("__")
    )


# ── accept / reject, each with its own diagnostic reason ────────────────────


def test_decisions_and_reasons_over_the_diamond_and_nesting():
    """Rows are distinct falsifiers: each rejection has its own ``explain``
    reason, so a checker that rejected for the wrong reason still fails here."""
    po = _diamond()
    inner = PartialOrder(
        children=(Atom("b1"), Atom("b2")),
        order=frozenset({OrderEdge(NodeId(0), NodeId(1))}),
    )
    nested = PartialOrder(
        children=(Atom("a"), inner),
        order=frozenset({OrderEdge(NodeId(0), NodeId(1))}),
    )

    cases = [
        ("diamond linearization 1", po, ("a", "b", "c", "d"), True, "accepted"),
        ("diamond linearization 2", po, ("a", "c", "b", "d"), True, "accepted"),
        ("precedence violated (b before a)", po, ("b", "a", "c", "d"), False,
         "precedence violated"),
        ("missing occurrence of d", po, ("a", "b", "c"), False, "missing occurrence"),
        ("duplicate occurrence of b", po, ("a", "b", "b", "c", "d"), False,
         "duplicate occurrence"),
        # a -> d only holds in the closure (the reduction has a->b->d, a->c->d)
        ("transitive precedence via the closure", po, ("b", "c", "d", "a"), False, ""),
        ("nested child accepted", nested, ("a", "b1", "b2"), True, "accepted"),
        ("nested child order violated", nested, ("a", "b2", "b1"), False, "child 1"),
    ]

    failures = Failures()
    for name, node, trace, expected, reason in cases:
        got = trace_in_language(node, trace)
        failures.check(
            got is expected, f"{name}: trace_in_language({trace}) == {got}, want {expected}"
        )
        explanation = explain(node, trace)
        failures.check(
            explanation.startswith("accepted" if expected else "rejected"),
            f"{name}: explain() said {explanation!r}",
        )
        if reason:
            failures.check(reason in explanation, f"{name}: {reason!r} not in {explanation!r}")
    # the rejection reasons must name the offending activity, not just the class
    failures.check("'d'" in explain(po, ("a", "b", "c")), "missing-occurrence reason must name 'd'")
    assert not failures, failures.report()


# ── leaves and label projection ─────────────────────────────────────────────


def test_leaves_and_silent_children_carry_no_label():
    po = PartialOrder(
        children=(Atom("a"), Silent(), Atom("b")),
        order=frozenset({OrderEdge(NodeId(0), NodeId(2))}),
    )
    cases = [
        ("atom accepts its own label", Atom("x"), ("x",), True),
        ("atom rejects epsilon", Atom("x"), (), False),
        ("silent accepts epsilon", Silent(), (), True),
        ("end rejects a symbol", End(), ("x",), False),
        ("silent child projects away", po, ("a", "b"), True),
        ("silent child does not relax precedence", po, ("b", "a"), False),
    ]
    failures = Failures()
    for name, node, trace, expected in cases:
        got = trace_in_language(node, trace)
        failures.check(got is expected, f"{name}: got {got}, want {expected}")
    failures.check(
        static_labels(po) == ("a", "b"), f"static_labels == {static_labels(po)}"
    )
    assert not failures, failures.report()


# ── choice graph ────────────────────────────────────────────────────────────


def test_choice_graph_membership_accepts_iteration_and_rejects_branch_mixing():
    cyclic = ChoiceGraph(  # s -> w -> w (loop), w -> e; boundaries are silent
        children=(Silent(), Silent(), Atom("w")),
        edges=frozenset(
            {
                ChoiceGraphEdge(NodeId(0), NodeId(2)),
                ChoiceGraphEdge(NodeId(2), NodeId(2)),
                ChoiceGraphEdge(NodeId(2), NodeId(1)),
            }
        ),
        start=0,
        end=1,
    )
    branching = ChoiceGraph(
        children=(Silent(), Silent(), Atom("p"), Atom("q")),
        edges=frozenset(
            {
                ChoiceGraphEdge(NodeId(0), NodeId(2)),
                ChoiceGraphEdge(NodeId(0), NodeId(3)),
                ChoiceGraphEdge(NodeId(2), NodeId(1)),
                ChoiceGraphEdge(NodeId(3), NodeId(1)),
            }
        ),
        start=0,
        end=1,
    )
    cases = [
        ("one iteration", cyclic, ("w",), True),
        ("three iterations", cyclic, ("w", "w", "w"), True),
        ("zero iterations is not a start->end walk", cyclic, (), False),
        ("unknown label", cyclic, ("w", "z"), False),
        ("left branch", branching, ("p",), True),
        ("right branch", branching, ("q",), True),
        ("branches must not be mixed", branching, ("p", "q"), False),
    ]
    failures = Failures()
    for name, node, trace, expected in cases:
        got = trace_in_language(node, trace)
        failures.check(got is expected, f"{name}: got {got}, want {expected}")
    failures.check(
        "no start->end walk" in explain(cyclic, ()),
        f"explain(cyclic, ()) == {explain(cyclic, ())!r}",
    )
    assert not failures, failures.report()


# ── refusal ─────────────────────────────────────────────────────────────────


def test_non_once_frequency_refuses_rather_than_guessing():
    po = PartialOrder(
        children=(Atom("a"), Atom("b")),
        order=frozenset({OrderEdge(NodeId(0), NodeId(1))}),
        frequency=ONE_OR_MORE,
    )
    failures = Failures()
    failures.expect_refusal(
        "ONE_OR_MORE frequency",
        lambda: trace_in_language(po, ("a", "b")),
        PowlRefusal.IRREDUCIBLE_PROJECTION,
    )
    assert not failures, failures.report()
