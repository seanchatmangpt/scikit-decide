# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Bounded reference executor: enabling, bounded termination, replay, digest.

The headline property is the first test: a partial order with no precedence
enables *both* children at once. An executor that silently serialized
concurrency would still pass a trace-membership check, so it has to be pinned
directly.

Compression note: the seed axes and the frequency-model cross product used to be
pytest parametrizations (4, and 10x3). They are single items that walk the same
seeds and the same models, accumulating every failure — the models themselves are
untouched, because they are distinct models rather than redraws of one.
"""

from __future__ import annotations

import random

import pytest

from autofde_lab.powl.algebra import (
    Atom,
    ChoiceGraph,
    ChoiceGraphEdge,
    NodeId,
    OrderEdge,
    PartialOrder,
    Silent,
)
from autofde_lab.powl.bounds import ExecutionBound
from autofde_lab.powl.frequency import Frequency
from autofde_lab.powl.executor import (
    INITIAL_MARKING,
    ChoiceRecord,
    DeadlockKind,
    Marking,
    ReplayDivergedError,
    classify_stall,
    enabled,
    fire,
    is_final,
    node_at,
    replay,
    trace_of,
)
from autofde_lab.powl.membership import explain, trace_in_language
from autofde_lab.powl.semantics import language
from autofde_lab.powl.normalize import canonical_form, model_digest
from autofde_lab.powl.refusals import PowlError, PowlRefusal

from ._accumulate import Failures


def _oe(a: int, b: int) -> OrderEdge:
    return OrderEdge(NodeId(a), NodeId(b))


def _ce(a: int, b: int) -> ChoiceGraphEdge:
    return ChoiceGraphEdge(NodeId(a), NodeId(b))


# ── enabling ────────────────────────────────────────────────────────────────


def test_unordered_partial_order_enables_both_children_initially():
    """Concurrency is preserved, not serialized. The headline property.

    Kept standalone: this is the only signal for "the executor serialized
    concurrency", a defect every trace-membership check is blind to.
    """
    model = PartialOrder((Atom("a"), Atom("b")))
    assert enabled(model) == frozenset({(0,), (1,)})


def test_precedence_governs_enabling_and_is_read_from_the_closure():
    model = PartialOrder((Atom("a"), Atom("b")), frozenset({_oe(0, 1)}))
    assert enabled(model) == frozenset({(0,)})
    after = fire(model, INITIAL_MARKING, (0,))
    assert enabled(model, after) == frozenset({(1,)})
    assert not is_final(model, after)
    final = fire(model, after, (1,))
    assert enabled(model, final) == frozenset()
    assert is_final(model, final)

    # a -> b -> c; the reduction drops a -> c, the closure keeps it.
    chain = PartialOrder(
        (Atom("a"), Atom("b"), Atom("c")), frozenset({_oe(0, 1), _oe(1, 2)})
    )
    assert _oe(0, 2) not in chain.order
    assert _oe(0, 2) in chain.closure
    assert enabled(chain) == frozenset({(0,)})

    # two enabled steps stay two enabled steps; no tie-break is applied
    free = PartialOrder((Atom("a"), Atom("b"), Atom("c")))
    live = enabled(free)
    assert isinstance(live, frozenset) and len(live) == 3
    assert enabled(free, fire(free, INITIAL_MARKING, (2,))) == frozenset({(0,), (1,)})


def test_firing_unordered_siblings_in_either_order_yields_equal_markings():
    """Confluence: for genuinely unordered leaf siblings, the order in which the
    caller fires them does not affect the resulting Marking. This is the generic
    executor property behind the gymact concurrent-read blocks (POWL v2
    Definition 3.11 marked-graph concurrency) -- proven here independent of any
    driver/runner machinery.
    """
    model = PartialOrder((Atom("a"), Atom("b"), Atom("c")))
    marking_ab = fire(model, fire(model, INITIAL_MARKING, (0,)), (1,))
    marking_ba = fire(model, fire(model, INITIAL_MARKING, (1,)), (0,))
    assert marking_ab == marking_ba
    assert enabled(model, marking_ab) == enabled(model, marking_ba) == frozenset({(2,)})


def test_firing_a_path_that_is_not_enabled_is_refused():
    model = PartialOrder((Atom("a"), Atom("b")), frozenset({_oe(0, 1)}))
    with pytest.raises(PowlError) as excinfo:
        fire(model, INITIAL_MARKING, (1,))
    assert excinfo.value.refusal is PowlRefusal.LANGUAGE_MISMATCH


# ── cyclic choice graph terminates structurally ─────────────────────────────


def _cyclic_model() -> ChoiceGraph:
    """start=0, end=1, cycle 0 -> 2 -> 3 -> 2, with an exit 2 -> 1."""
    return ChoiceGraph(
        (Silent(), Silent(), Atom("a"), Atom("b")),
        frozenset({_ce(0, 2), _ce(2, 3), _ce(3, 2), _ce(2, 1)}),
        start=0,
        end=1,
    )


def test_cyclic_choice_graph_terminates_and_reports_bound_exhausted():
    model = _cyclic_model()
    bound = ExecutionBound(max_node_visits=3)
    marking = INITIAL_MARKING
    for _ in range(200):  # guard: a hang would be a failure, not a timeout
        live = enabled(model, marking, bound)
        if not live:
            break
        # a policy that refuses to take the exit, to force the cap
        looping = sorted(p for p in live if p != (1,))
        marking = fire(model, marking, looping[0] if looping else sorted(live)[0], bound=bound)
    else:
        pytest.fail("cyclic choice graph did not terminate within 200 steps")

    assert not is_final(model, marking)
    assert classify_stall(model, marking, bound) is DeadlockKind.BOUND_EXHAUSTED
    assert classify_stall(model, marking, bound).value == "BLOCKED:BOUND_EXHAUSTED"


def test_cyclic_choice_graph_reaches_its_end_and_carries_visit_counts():
    """Two distinct falsifiers, both about the same run: the exit stays
    reachable under a cap, and re-entry increments rather than resets."""
    model = _cyclic_model()
    bound = ExecutionBound(max_node_visits=3)
    m = fire(model, INITIAL_MARKING, (0,), bound=bound)
    m = fire(model, m, (2,), bound=bound)
    assert (1,) in enabled(model, m, bound)
    assert is_final(model, fire(model, m, (1,), bound=bound))

    generous = ExecutionBound(max_node_visits=10)
    m = fire(model, INITIAL_MARKING, (0,), bound=generous)
    m = fire(model, m, (2,), bound=generous)
    assert dict(m.visits)[((), 2)] == 1
    m = fire(model, m, (3,), bound=generous)
    m = fire(model, m, (2,), bound=generous)
    assert dict(m.visits)[((), 2)] == 2, "re-entry must increment, never reset"


def test_a_choice_graph_with_no_way_forward_is_a_deadlock_not_a_bound():
    # node 2 has no outgoing edge and is not the end node.
    model = ChoiceGraph(
        (Silent(), Silent(), Atom("a")), frozenset({_ce(0, 2)}), start=0, end=1
    )
    m = fire(model, INITIAL_MARKING, (0,))
    m = fire(model, m, (2,))
    assert enabled(model, m) == frozenset()
    assert not is_final(model, m)
    assert classify_stall(model, m) is DeadlockKind.DEADLOCK


# ── replay ──────────────────────────────────────────────────────────────────


def _record_run(model, bound=ExecutionBound(), seed="run") -> tuple[list[ChoiceRecord], Marking]:
    rng = random.Random(seed)
    marking = INITIAL_MARKING
    records: list[ChoiceRecord] = []
    for step in range(200):
        live = enabled(model, marking, bound)
        if not live:
            break
        chosen = rng.choice(sorted(live))
        records.append(
            ChoiceRecord(
                step=step,
                path=chosen,
                enabled=tuple(sorted(live)),
                chosen=chosen,
                decided_by="test-policy",
            )
        )
        marking = fire(model, marking, chosen, bound=bound)
    return records, marking


def _mixed_model() -> PartialOrder:
    return PartialOrder(
        (
            Atom("a"),
            Atom("b"),
            PartialOrder((Atom("c"), Atom("d")), frozenset({_oe(0, 1)})),
        ),
        frozenset({_oe(0, 1)}),
    )


def test_replay_reproduces_the_run_and_detects_every_kind_of_tampering():
    """Four distinct falsifiers accumulated: faithful replay, a swapped pick, a
    narrowed ``enabled`` set (legal pick, tampered evidence), and a fabricated
    record. Each fails for its own reason and all are reported."""
    model = _mixed_model()
    records, final = _record_run(model)
    failures = Failures()

    failures.check(bool(records), "the run must have taken at least one step")
    failures.check(
        replay(model, records) == final, "replay did not reproduce the final marking"
    )

    # swap the pick at a branching step
    tampered_pick = None
    for i, rec in enumerate(records):
        others = [p for p in rec.enabled if p != rec.chosen]
        if others:
            tampered_pick = list(records)
            tampered_pick[i] = ChoiceRecord(
                rec.step, others[0], rec.enabled, others[0], rec.decided_by
            )
            break
    failures.check(tampered_pick is not None, "no branching step to tamper with")

    # the record stores the full enabled set precisely so this is catchable
    rec0 = records[0]
    narrowed = (
        [ChoiceRecord(rec0.step, rec0.path, (rec0.chosen,), rec0.chosen, "x")] + records[1:]
        if len(rec0.enabled) > 1
        else None
    )
    failures.check(narrowed is not None, "first step was not branching in this model")

    divergences = [
        ("tampered choice", tampered_pick),
        ("tampered enabled set", narrowed),
        (
            "fabricated record for a different model",
            [ChoiceRecord(0, (1,), ((1,),), (1,), "bogus")],
        ),
    ]
    for name, tampered in divergences:
        if tampered is None:
            continue
        target = model if name != "fabricated record for a different model" else (
            PartialOrder((Atom("a"), Atom("b")), frozenset({_oe(0, 1)}))
        )
        try:
            replay(target, tampered)
        except ReplayDivergedError as exc:
            failures.check(
                exc.kind is DeadlockKind.REPLAY_DIVERGED
                and exc.kind.value == "BLOCKED:REPLAY_DIVERGED",
                f"{name}: diverged with kind {exc.kind!r}",
            )
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{name}: expected ReplayDivergedError, raised {exc!r}")
        else:
            failures.append(f"{name}: replay accepted a tampered record")

    assert not failures, failures.report()


# ── cross-check against the independent membership implementation ───────────


def test_every_executor_trace_is_in_the_language():
    """One invariant over four seeds — the seed is a redraw, not a falsifier of
    its own, so the seeds are looped rather than parametrized."""
    model = _mixed_model()
    failures = Failures()
    for seed in (f"s{i}" for i in range(4)):
        records, final = _record_run(model, seed=seed)
        failures.check(is_final(model, final), f"seed={seed}: run ended non-final")
        trace = trace_of(model, records)
        failures.check(
            sorted(trace) == ["a", "b", "c", "d"], f"seed={seed}: trace={trace!r}"
        )
        failures.check(
            trace_in_language(model, trace),
            f"seed={seed}: executor produced {trace!r}, not in the language",
        )
    assert not failures, failures.report()


def _branching_choice_graph() -> ChoiceGraph:
    return ChoiceGraph(
        (Silent(), Silent(), Atom("x"), Atom("y")),
        frozenset({_ce(0, 2), _ce(0, 3), _ce(2, 1), _ce(3, 1)}),
        start=0,
        end=1,
    )


def test_cross_check_covers_a_choice_graph_too():
    model = _branching_choice_graph()
    seen = set()
    failures = Failures()
    for seed in range(30):
        records, final = _record_run(model, seed=f"cg{seed}")
        failures.check(is_final(model, final), f"cg{seed}: run ended non-final")
        trace = trace_of(model, records)
        failures.check(
            trace_in_language(model, trace), f"cg{seed}: executor produced {trace!r}"
        )
        seen.add(trace)
    assert not failures, failures.report()
    assert seen == {("x",), ("y",)}, "both branches must be reachable"


def test_membership_decides_a_choice_graph_nested_in_a_partial_order():
    """Positive cross-check over a nested choice graph.

    This test previously pinned a *gap*: ``membership.static_labels`` returns
    ``()`` for a :class:`~autofde_lab.powl.algebra.ChoiceGraph` (its length is
    branch-dependent), so an enclosing partial order's label multiset came out
    short and a genuinely-in-language trace was rejected. ``membership`` now
    enumerates the branch options (``membership.label_options``) and checks the
    partial order against each, so this is a real independent check of the
    executor's output rather than a recorded limitation.
    """
    model = PartialOrder((Atom("a"), _branching_choice_graph()), frozenset({_oe(0, 1)}))
    records, final = _record_run(model, seed="nested")
    assert is_final(model, final)
    trace = trace_of(model, records)
    assert trace[0] == "a" and trace[1] in {"x", "y"} and len(trace) == 2
    assert trace_in_language(model, trace), explain(model, trace)
    # and it still rejects: order reversed, and a branch the graph cannot emit
    assert not trace_in_language(model, tuple(reversed(trace)))
    assert not trace_in_language(model, ("a", "z"))


# ── digest / normalization ──────────────────────────────────────────────────


def test_model_digest_is_stable_across_equivalent_forms_and_separates_real_ones():
    """Under-sensitivity (two different orders colliding) and over-sensitivity
    (a reduction and its closure differing) are opposite defects; both rows run.
    """
    kids = (Atom("a"), Atom("b"), Atom("c"))
    reduced = PartialOrder(kids, frozenset({_oe(0, 1), _oe(1, 2)}))
    closed = PartialOrder(kids, frozenset({_oe(0, 1), _oe(1, 2), _oe(0, 2)}))
    forward = PartialOrder(kids, frozenset({_oe(0, 1), _oe(1, 2)}))
    relabelled = PartialOrder(
        (Atom("c"), Atom("b"), Atom("a")), frozenset({_oe(2, 1), _oe(1, 0)})
    )

    failures = Failures()
    failures.check(
        model_digest(reduced) == model_digest(closed),
        "closure and reduction inputs must digest identically",
    )
    failures.check(
        model_digest(forward) == model_digest(relabelled),
        "differently ordered children denoting the same order must digest identically",
    )
    failures.check(len(model_digest(reduced)) == 64, "digest must be sha256 hex")
    failures.check(
        model_digest(PartialOrder(kids, frozenset({_oe(0, 1)})))
        != model_digest(PartialOrder(kids, frozenset({_oe(1, 0)}))),
        "a -> b and b -> a must not collide",
    )
    failures.check(
        model_digest(PartialOrder(kids))
        != model_digest(PartialOrder(kids, frozenset({_oe(0, 1)}))),
        "unordered and ordered must not collide",
    )
    assert not failures, failures.report()


def test_canonical_form_is_idempotent_and_semantics_preserving():
    model = _mixed_model()
    once = canonical_form(model)
    assert model_digest(once) == model_digest(canonical_form(once))
    records, final = _record_run(once)
    assert is_final(once, final)
    assert trace_in_language(once, trace_of(once, records))


def test_marking_digest_material_is_sorted_not_set_ordered():
    model = PartialOrder((Atom("a"), Atom("b"), Atom("c")))
    m = INITIAL_MARKING
    for p in [(2,), (0,), (1,)]:
        m = fire(model, m, p)
    material = m.digest_material()
    assert material["completed_paths"] == sorted(material["completed_paths"])
    assert material["fires"] == 3


def test_node_at_addresses_nested_nodes_and_refuses_dangling_paths():
    model = _mixed_model()
    assert node_at(model, ()) is model
    assert node_at(model, (2, 1)) == Atom("d")
    with pytest.raises(PowlError) as excinfo:
        node_at(model, (0, 0))
    assert excinfo.value.refusal is PowlRefusal.DANGLING_REFERENCE


# ── repetition (Frequency) ──────────────────────────────────────────────────
#
# These pin the defect that no earlier test could see: nothing in this file ever
# fired a frequency-carrying model, so the executor could ignore ``frequency``
# entirely and still look correct. It declared a COMPLETE traversal whose trace
# was outside the model's own language, i.e. two components of this package
# contradicting each other.


def _greedy_run(model, bound=ExecutionBound(), seed="freq"):
    """Fire until nothing is enabled. Returns (marking, observable trace)."""
    rng = random.Random(seed)
    marking = INITIAL_MARKING
    trace: list[str] = []
    for _ in range(500):
        live = enabled(model, marking, bound)
        if not live:
            break
        chosen = rng.choice(sorted(live))
        node = node_at(model, chosen)
        if isinstance(node, Atom):
            trace.append(node.label)
        marking = fire(model, marking, chosen, bound=bound)
    return marking, tuple(trace)


def _lang(model, *, max_traces: int = 400, max_unrolls: int = 4):
    return language(model, max_traces=max_traces, max_unrolls=max_unrolls)


def test_repetition_is_executed_round_by_round():
    """Every distinct repetition behaviour, each its own falsifier, accumulated.

    The exact reproducer is the first block: before the fix a ``Frequency(2, 2)``
    composite reported 2 fires and ``is_final`` True.
    """
    failures = Failures()

    # exactly two rounds
    twice = PartialOrder((Atom("a"), Atom("b")), frozenset(), frequency=Frequency(2, 2))
    marking, trace = _greedy_run(twice)
    failures.check(
        marking.fires == 4, f"exactly-2: expected two rounds of two atoms, got {trace!r}"
    )
    failures.check(is_final(twice, marking), "exactly-2: two full rounds must be final")
    failures.check(sorted(trace) == ["a", "a", "b", "b"], f"exactly-2: trace={trace!r}")
    failures.check(
        min(len(t) for t in _lang(twice)) == 4,
        "exactly-2: the shortest trace in the language must be 4 symbols",
    )

    # ...and one round is not enough
    half = fire(twice, INITIAL_MARKING, (0,))
    half = fire(twice, half, (1,))
    failures.check(
        not is_final(twice, half), "exactly-2: one round of a (2, 2) composite is not complete"
    )
    failures.check(bool(enabled(twice, half)), "exactly-2: the second round must be offered")
    # repetition must not have serialized concurrency
    failures.check(
        enabled(twice, half) == frozenset({(0,), (1,)}),
        f"exactly-2: both children must stay enabled, got {sorted(enabled(twice, half))}",
    )

    # Frequency(0, 1): min=0 must be reachable, i.e. final immediately
    skippable = PartialOrder(
        (Atom("a"), Atom("b")), frozenset(), frequency=Frequency(0, 1)
    )
    failures.check(
        is_final(skippable, INITIAL_MARKING), "skippable: zero rounds must be final"
    )
    # skippable is not the same as empty: the round may still be run...
    failures.check(
        enabled(skippable, INITIAL_MARKING) == frozenset({(0,), (1,)}),
        "skippable: the round must still be offered",
    )
    # ...and a half-run round is NOT final, or the trace ('a',) would pass
    failures.check(
        not is_final(skippable, fire(skippable, INITIAL_MARKING, (0,))),
        "skippable: a half-run round must not be final",
    )
    skip_lang = _lang(skippable)
    failures.check(
        () in skip_lang and ("a",) not in skip_lang,
        f"skippable: language is {sorted(skip_lang)}",
    )

    # a skippable child nested in a partial order may contribute zero rounds
    inner = PartialOrder((Atom("c"), Atom("d")), frozenset(), frequency=Frequency(0, 1))
    nested = PartialOrder((Atom("a"), inner), frozenset({_oe(0, 1)}))
    failures.check(
        is_final(nested, fire(nested, INITIAL_MARKING, (0,))),
        "nested skippable: the child may contribute zero rounds",
    )

    # max=None is bounded by max_node_visits and runs out of enabled nodes
    # rather than raising — the same rule that terminates a cyclic choice graph.
    unbounded = PartialOrder(
        (Atom("a"), Atom("b")), frozenset(), frequency=Frequency(1, None)
    )
    bound = ExecutionBound(max_node_visits=3)
    marking, trace = _greedy_run(unbounded, bound=bound)
    failures.check(
        marking.fires == 6, f"unbounded: three rounds of two atoms, got {trace!r}"
    )
    failures.check(is_final(unbounded, marking), "unbounded: must end final, not raise")
    failures.check(
        enabled(unbounded, marking, bound) == frozenset(),
        "unbounded: must run out of enabled nodes",
    )

    assert not failures, failures.report()


# ── the cross-check that would have caught this originally ──────────────────


def _frequency_models():
    """Models whose completion the static membership checker cannot decide.

    ``membership.trace_in_language`` refuses a non-``ONCE`` frequency outright
    (``IRREDUCIBLE_PROJECTION``: its label multiset is not static), so the
    independent oracle for these is :mod:`autofde_lab.powl.semantics`, which is a
    different algorithm from the executor's and imports none of it.

    These are ten *distinct models*, not ten redraws — the set is unchanged by
    compression; only the item packaging changed.
    """
    return {
        "po-exactly-2": PartialOrder(
            (Atom("a"), Atom("b")), frozenset(), frequency=Frequency(2, 2)
        ),
        "po-ordered-exactly-2": PartialOrder(
            (Atom("a"), Atom("b")), frozenset({_oe(0, 1)}), frequency=Frequency(2, 2)
        ),
        "po-skippable": PartialOrder(
            (Atom("a"), Atom("b")), frozenset({_oe(0, 1)}), frequency=Frequency(0, 1)
        ),
        "po-1-to-3": PartialOrder(
            (Atom("a"), Atom("b")), frozenset({_oe(0, 1)}), frequency=Frequency(1, 3)
        ),
        "nested-repeat": PartialOrder(
            (
                Atom("a"),
                PartialOrder(
                    (Atom("c"), Atom("d")),
                    frozenset({_oe(0, 1)}),
                    frequency=Frequency(2, 2),
                ),
            ),
            frozenset({_oe(0, 1)}),
        ),
        "repeat-of-nested": PartialOrder(
            (
                Atom("a"),
                PartialOrder((Atom("c"), Atom("d")), frozenset({_oe(0, 1)})),
            ),
            frozenset({_oe(0, 1)}),
            frequency=Frequency(2, 2),
        ),
        "skippable-nested": PartialOrder(
            (
                Atom("a"),
                PartialOrder(
                    (Atom("c"), Atom("d")),
                    frozenset({_oe(0, 1)}),
                    frequency=Frequency(0, 1),
                ),
            ),
            frozenset({_oe(0, 1)}),
        ),
        "repeat-inside-a-choice-branch": ChoiceGraph(
            (
                Silent(),
                Silent(),
                PartialOrder(
                    (Atom("x"), Atom("y")),
                    frozenset({_oe(0, 1)}),
                    frequency=Frequency(2, 2),
                ),
                Atom("z"),
            ),
            frozenset({_ce(0, 2), _ce(0, 3), _ce(2, 1), _ce(3, 1)}),
            start=0,
            end=1,
        ),
        "choice-graph-twice": ChoiceGraph(
            (Silent(), Silent(), Atom("x"), Atom("y")),
            frozenset({_ce(0, 2), _ce(0, 3), _ce(2, 1), _ce(3, 1)}),
            start=0,
            end=1,
            frequency=Frequency(2, 2),
        ),
    }


def test_every_final_frequency_trace_is_in_the_language():
    """The invariant that was violated: a marking the executor calls FINAL must
    have an observable trace inside the model's own language.

    A general property over every frequency-carrying model and three seeds — the
    reason no earlier test caught the defect is that none of them fired a model
    carrying a frequency at all. Every (model, seed) pair is still run; the seed
    is a redraw and the model is not, so failures name both.
    """
    models = _frequency_models()
    failures = Failures()
    for name in sorted(models):
        model = models[name]
        for seed in (f"x{i}" for i in range(3)):
            marking, trace = _greedy_run(model, seed=seed)
            if not is_final(model, marking):
                failures.append(
                    f"{name}/{seed}: ran out of enabled nodes at a non-final marking, "
                    f"trace={trace!r}"
                )
                continue
            lang = _lang(model)
            failures.check(
                trace in lang,
                f"{name}/{seed}: executor called {trace!r} a COMPLETE traversal, but "
                f"it is not in the language of the model",
            )
    assert not failures, failures.report()


def test_every_frequency_model_still_refuses_the_static_membership_check():
    """Pins *why* the cross-check above uses ``semantics`` and not ``membership``:
    the static checker declines rather than guessing. Recorded, not worked around.
    """
    models = _frequency_models()
    failures = Failures()
    for name in sorted(models):
        failures.expect_refusal(
            name,
            lambda m=models[name]: trace_in_language(m, ("a", "b")),
            PowlRefusal.IRREDUCIBLE_PROJECTION,
        )
    assert not failures, failures.report()
