# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Deterministic sampling, honest counting, honest coverage statements."""

from __future__ import annotations

import math

from autofde_lab.powl.algebra import (
    Atom,
    ChoiceGraph,
    ChoiceGraphEdge,
    NodeId,
    OrderEdge,
    PartialOrder,
    Silent,
)
from autofde_lab.powl.membership import trace_in_language
from autofde_lab.powl.witness import (
    WitnessReport,
    count_linearizations,
    sample_linearizations,
)

from ._accumulate import Failures


def _diamond() -> PartialOrder:
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


def _cyclic_choice() -> ChoiceGraph:
    return ChoiceGraph(
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


# ── determinism ─────────────────────────────────────────────────────────────


def test_sampling_is_seed_deterministic_and_seed_sensitive():
    """Two opposite defects in one item: a sampler that ignored the seed would
    fail the second assert, one that ignored randomness the first."""
    po = _diamond()
    a = list(sample_linearizations(po, samples=50, seed="witness-seed"))
    b = list(sample_linearizations(po, samples=50, seed="witness-seed"))
    assert a == b, "the same seed must give the identical sequence"
    assert len(a) == 50
    assert a != list(sample_linearizations(po, samples=50, seed="seed-two")), (
        "a different seed must give a different sequence"
    )


def test_every_sample_is_in_the_language():
    """Cross-check against the independent membership decider, over both a
    partial order and a cyclic choice graph."""
    failures = Failures()
    for name, node, samples, seed in (
        ("diamond", _diamond(), 100, "cross-check"),
        ("cyclic choice graph", _cyclic_choice(), 30, "cyclic"),
    ):
        for trace in sample_linearizations(node, samples=samples, seed=seed):
            failures.check(
                trace_in_language(node, trace), f"{name}: sampled {trace!r} is not in the language"
            )
    assert not failures, failures.report()


def test_sampling_reaches_both_diamond_linearizations():
    """Coverage, not just legality: a sampler stuck on one linearization would
    pass the cross-check above and fail here."""
    seen = set(sample_linearizations(_diamond(), samples=100, seed="coverage"))
    assert seen == {("a", "b", "c", "d"), ("a", "c", "b", "d")}


# ── counting ────────────────────────────────────────────────────────────────


def test_counting_is_exact_where_it_can_be_and_None_where_it_cannot():
    """Under-counting and over-claiming are both defects: rows asserting an exact
    integer and rows asserting ``None`` are checked in the same pass."""
    flat6 = PartialOrder(children=tuple(Atom(f"a{i}") for i in range(6)))
    cases = [
        ("diamond", lambda: count_linearizations(_diamond()), 2),
        ("unordered 4 is 4!",
         lambda: count_linearizations(PartialOrder(children=tuple(Atom(c) for c in "abcd"))),
         math.factorial(4)),
        ("past the exact limit -> None",
         lambda: count_linearizations(flat6, exact_limit=4), None),
        ("within the exact limit -> 6!",
         lambda: count_linearizations(flat6, exact_limit=10), math.factorial(6)),
        ("choice graph -> None", lambda: count_linearizations(_cyclic_choice()), None),
        ("composite child -> None",
         lambda: count_linearizations(PartialOrder(
             children=(Atom("a"), PartialOrder(children=(Atom("x"), Atom("y")))))),
         None),
    ]
    failures = Failures()
    for name, run, expected in cases:
        got = run()
        failures.check(got == expected, f"{name}: got {got!r}, want {expected!r}")
    assert not failures, failures.report()


# ── coverage statement ──────────────────────────────────────────────────────


def test_coverage_statements_never_claim_a_percentage_they_cannot_know():
    unknown_total = WitnessReport(
        samples=tuple(sample_linearizations(_diamond(), samples=100, seed="s")),
        seed="s",
        counterexamples=(),
        total_linearizations=None,
    )
    known_total = WitnessReport(samples=(("a",),), seed="s", total_linearizations=2)
    with_counterexamples = WitnessReport(
        samples=(("a",), ("b",)),
        seed="s",
        counterexamples=(("b",),),
        total_linearizations=None,
    )

    failures = Failures()
    unknown = unknown_total.coverage_statement()
    failures.check("%" not in unknown, f"unknown total must not claim a %: {unknown!r}")
    failures.check(
        unknown
        == (
            "sampled 100 of an UNKNOWN total (counting is #P-complete); "
            "no counterexample found"
        ),
        f"unknown-total statement was {unknown!r}",
    )
    failures.check(
        known_total.coverage_statement()
        == "sampled 1 of 2 total linearizations; no counterexample found",
        f"known-total statement was {known_total.coverage_statement()!r}",
    )
    counter = with_counterexamples.coverage_statement()
    failures.check("%" not in counter, f"must not claim a %: {counter!r}")
    failures.check(
        "1 counterexample(s) found" in counter,
        f"counterexamples must be reported: {counter!r}",
    )
    assert not failures, failures.report()
