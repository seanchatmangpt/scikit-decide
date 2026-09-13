# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for `autofde_lab.powl.guard_executor`.

Real collaborators throughout: real `ChoiceGraph`/`PartialOrder`/`Atom`/
`Guard` construction (`autofde_lab.powl.algebra`), real
`autofde_lab.powl.validate.validate_model` admission (exercised through
`execute`, never bypassed), and real, hand-written deterministic guard
evaluators / atom invokers -- no LLM call anywhere in this file, since the
guard/atom-invocation contract is itself LLM-free by design.

No `unittest.mock` / `Mock` / `MagicMock` / `patch` / `monkeypatch` anywhere
in this file.
"""

from __future__ import annotations

import pytest

import threading
import time

from autofde_lab.powl.algebra import (
    Atom,
    ChoiceGraph,
    ChoiceGraphEdge,
    End,
    Guard,
    NodeId,
    OrderEdge,
    PartialOrder,
    Silent,
    Start,
)
from autofde_lab.powl.frequency import Frequency
from autofde_lab.powl.guard_executor import ExecutionContext, execute
from autofde_lab.powl.refusals import PowlError, PowlRefusal


def _four_branch_graph() -> ChoiceGraph:
    """The real causal_closure/overdetermined/underdetermined/exhausted
    shape `SreTroubleshootingDecisionBackend` builds, standalone -- 0=Start,
    1=End, 2=decide (Silent), 3=commit, 4=discriminate, 5=regenerate. Both
    branch atoms loop back to the decide node, never to Start."""
    return ChoiceGraph(
        children=(
            Start(),  # 0
            End(),  # 1
            Silent(),  # 2 decide
            Atom(label="commit"),  # 3
            Atom(label="discriminate"),  # 4
            Atom(label="regenerate"),  # 5
        ),
        edges=frozenset(
            [
                ChoiceGraphEdge(NodeId(0), NodeId(2)),
                ChoiceGraphEdge(NodeId(2), NodeId(3), guard=Guard("causal_closure")),
                ChoiceGraphEdge(NodeId(2), NodeId(4), guard=Guard("overdetermined")),
                ChoiceGraphEdge(NodeId(2), NodeId(4), guard=Guard("underdetermined")),
                ChoiceGraphEdge(NodeId(2), NodeId(5), guard=Guard("exhausted")),
                ChoiceGraphEdge(NodeId(3), NodeId(1)),
                ChoiceGraphEdge(NodeId(4), NodeId(2)),
                ChoiceGraphEdge(NodeId(5), NodeId(2)),
            ]
        ),
        start=0,
        end=1,
    )


# ---------------------------------------------------------------------------
# Each real branch is reachable under the right synthetic state
# ---------------------------------------------------------------------------


def test_causal_closure_branch_reached_immediately() -> None:
    graph = _four_branch_graph()
    calls: list[str] = []

    def evaluator(name: str, _args: dict) -> bool:
        return name == "causal_closure"

    def invoker(atom: Atom) -> str:
        calls.append(atom.label)
        return "ok"

    trace = execute(graph, guard_evaluator=evaluator, atom_invoker=invoker, max_choice_transitions=10)

    assert calls == ["commit"]
    assert trace.choice_transitions_taken == 3  # Start->decide, decide->commit, commit->End


def test_overdetermined_and_underdetermined_both_route_to_discriminate() -> None:
    for predicate in ("overdetermined", "underdetermined"):
        graph = _four_branch_graph()
        calls: list[str] = []
        rounds = {"n": 0}

        def evaluator(name: str, _args: dict, predicate: str = predicate, rounds: dict = rounds) -> bool:
            # Discriminate once, then close, proving the loop-back to
            # "decide" (not Start) really re-enters the choice.
            if rounds["n"] == 0:
                return name == predicate
            return name == "causal_closure"

        def invoker(atom: Atom, calls: list[str] = calls, rounds: dict = rounds) -> str:
            calls.append(atom.label)
            if atom.label == "discriminate":
                rounds["n"] += 1
            return "ok"

        execute(graph, guard_evaluator=evaluator, atom_invoker=invoker, max_choice_transitions=10)

        assert calls == ["discriminate", "commit"], f"failed for predicate={predicate}"


def test_exhausted_branch_loops_back_and_eventually_closes() -> None:
    graph = _four_branch_graph()
    calls: list[str] = []
    rounds = {"n": 0}

    def evaluator(name: str, _args: dict) -> bool:
        if rounds["n"] == 0:
            return name == "exhausted"
        return name == "causal_closure"

    def invoker(atom: Atom) -> str:
        calls.append(atom.label)
        if atom.label == "regenerate":
            rounds["n"] += 1
        return "ok"

    execute(graph, guard_evaluator=evaluator, atom_invoker=invoker, max_choice_transitions=10)

    assert calls == ["regenerate", "commit"]


# ---------------------------------------------------------------------------
# Refusal, not guessing
# ---------------------------------------------------------------------------


def test_no_guard_matched_and_no_else_edge_refuses() -> None:
    graph = _four_branch_graph()

    def evaluator(_name: str, _args: dict) -> bool:
        return False  # nothing ever matches, and there is no unguarded else edge

    def invoker(_atom: Atom) -> str:
        return "ok"

    with pytest.raises(PowlError) as excinfo:
        execute(graph, guard_evaluator=evaluator, atom_invoker=invoker, max_choice_transitions=10)

    assert excinfo.value.refusal == PowlRefusal.NO_GUARD_MATCHED


def test_transition_budget_exhausted_refuses_rather_than_hanging() -> None:
    graph = _four_branch_graph()

    def evaluator(name: str, _args: dict) -> bool:
        return name == "exhausted"  # never closes -- always regenerates

    def invoker(_atom: Atom) -> str:
        return "ok"

    with pytest.raises(PowlError) as excinfo:
        execute(graph, guard_evaluator=evaluator, atom_invoker=invoker, max_choice_transitions=5)

    assert excinfo.value.refusal == PowlRefusal.TRANSITION_BUDGET_EXHAUSTED


def test_execute_refuses_an_unadmitted_model_before_walking_anything() -> None:
    """A `ChoiceGraph` violating the real guard-exclusivity admission rule
    (two unguarded edges alongside a guarded one) is refused by
    `execute`'s own mandatory `validate_model` call before any atom is
    invoked -- proven here by a real invoker that would raise if ever
    actually called."""
    graph = ChoiceGraph(
        children=(Start(), End(), Atom(label="a"), Atom(label="b"), Atom(label="c")),
        edges=frozenset(
            [
                ChoiceGraphEdge(NodeId(0), NodeId(2), guard=Guard("p1")),
                ChoiceGraphEdge(NodeId(0), NodeId(3)),
                ChoiceGraphEdge(NodeId(0), NodeId(4)),
                ChoiceGraphEdge(NodeId(2), NodeId(1)),
                ChoiceGraphEdge(NodeId(3), NodeId(1)),
                ChoiceGraphEdge(NodeId(4), NodeId(1)),
            ]
        ),
        start=0,
        end=1,
    )

    def never_call(_atom: Atom) -> str:
        raise AssertionError("atom_invoker must not be called for an unadmitted model")

    with pytest.raises(PowlError) as excinfo:
        execute(graph, guard_evaluator=lambda n, a: True, atom_invoker=never_call, max_choice_transitions=10)

    assert excinfo.value.refusal == PowlRefusal.AMBIGUOUS_CHOICE_GUARD


# ---------------------------------------------------------------------------
# PartialOrder: deterministic topological walk
# ---------------------------------------------------------------------------


def test_partial_order_walks_in_a_real_deterministic_topological_order() -> None:
    from autofde_lab.powl.algebra import OrderEdge

    node = PartialOrder(
        children=(Atom(label="a"), Atom(label="b"), Atom(label="c")),
        order=frozenset([OrderEdge(NodeId(0), NodeId(1)), OrderEdge(NodeId(1), NodeId(2))]),
    )
    calls: list[str] = []

    def invoker(atom: Atom) -> str:
        calls.append(atom.label)
        return "ok"

    execute(node, guard_evaluator=lambda n, a: True, atom_invoker=invoker, max_choice_transitions=10)

    assert calls == ["a", "b", "c"]


# ---------------------------------------------------------------------------
# Atom consequence is passed through to the real invoker and recorded
# ---------------------------------------------------------------------------


def test_atom_consequence_is_visible_to_the_invoker_and_in_the_trace() -> None:
    from autofde_lab.powl.algebra import OrderEdge

    node = PartialOrder(
        children=(Atom(label="read_step", consequence="READ"), Atom(label="do_step", consequence="DO")),
        order=frozenset([OrderEdge(NodeId(0), NodeId(1))]),
    )
    seen_consequences: list[str] = []

    def invoker(atom: Atom) -> str:
        seen_consequences.append(atom.consequence)
        return "ok"

    trace = execute(node, guard_evaluator=lambda n, a: True, atom_invoker=invoker, max_choice_transitions=10)

    assert seen_consequences == ["READ", "DO"]
    atom_steps = [s for s in trace.steps if s.kind == "Atom"]
    assert [s.consequence for s in atom_steps] == ["READ", "DO"]


# ---------------------------------------------------------------------------
# Frequency-aware repetition (real, no longer silently ignored)
# ---------------------------------------------------------------------------


def test_mandatory_minimum_repetitions_run_without_a_repeat_evaluator() -> None:
    """`Frequency(min=2, max=2)` forces exactly 2 real repetitions -- no
    `repeat_evaluator` needed since neither repetition is optional."""
    node = PartialOrder(
        children=(Atom(label="a"), Atom(label="b")),
        order=frozenset([OrderEdge(NodeId(0), NodeId(1))]),
        frequency=Frequency(min=2, max=2),
    )
    calls: list[str] = []

    def invoker(atom: Atom) -> str:
        calls.append(atom.label)
        return "ok"

    trace = execute(node, guard_evaluator=lambda n, a: True, atom_invoker=invoker, max_choice_transitions=10)

    assert calls == ["a", "b", "a", "b"]
    labels_and_reps = [(s.label, s.repetition_index) for s in trace.steps if s.kind == "Atom"]
    assert labels_and_reps == [("a", 0), ("b", 0), ("a", 1), ("b", 1)]


def test_repeat_evaluator_decides_optional_repetitions_beyond_the_minimum() -> None:
    """`Frequency(min=1, max=None)` (ONE_OR_MORE): the first repetition is
    mandatory, every repetition after that is a real decision delegated to
    `repeat_evaluator` -- here it stops after 3 real repetitions."""
    node = PartialOrder(
        children=(Atom(label="a"), Atom(label="b")),
        order=frozenset([OrderEdge(NodeId(0), NodeId(1))]),
        frequency=Frequency(min=1, max=None),
    )
    calls: list[str] = []

    def repeat_evaluator(_composite_id: object, completed: int) -> bool:
        return completed < 3  # real decision: stop after 3 repetitions

    def invoker(atom: Atom) -> str:
        calls.append(atom.label)
        return "ok"

    execute(
        node,
        guard_evaluator=lambda n, a: True,
        atom_invoker=invoker,
        max_choice_transitions=10,
        repeat_evaluator=repeat_evaluator,
    )

    assert calls == ["a", "b"] * 3


# ---------------------------------------------------------------------------
# Real concurrency for independent PartialOrder ready-sets
# ---------------------------------------------------------------------------


def test_max_workers_greater_than_one_runs_a_ready_set_on_real_distinct_threads() -> None:
    """Two atoms with no order edge between them are one real ready set --
    with `max_workers=2` they run on two genuinely distinct OS threads
    (proven by real `threading.get_ident()` values captured inside the real
    invoker calls), never inferred from timing alone."""
    node = PartialOrder(children=(Atom(label="a"), Atom(label="b")))
    thread_ids: dict[str, int] = {}
    lock = threading.Lock()

    def invoker(atom: Atom) -> str:
        time.sleep(0.05)  # widen the concurrency window
        with lock:
            thread_ids[atom.label] = threading.get_ident()
        return "ok"

    trace = execute(node, guard_evaluator=lambda n, a: True, atom_invoker=invoker, max_choice_transitions=10, max_workers=2)

    assert len(thread_ids) == 2
    assert thread_ids["a"] != thread_ids["b"]
    # Trace ordering stays the real deterministic sorted-index order,
    # independent of which thread actually finished first.
    assert [s.label for s in trace.steps if s.kind == "Atom"] == ["a", "b"]


def test_max_workers_default_of_one_matches_the_original_serial_behavior() -> None:
    node = PartialOrder(children=(Atom(label="a"), Atom(label="b")))
    thread_ids: set[int] = set()

    def invoker(atom: Atom) -> str:
        thread_ids.add(threading.get_ident())
        return "ok"

    execute(node, guard_evaluator=lambda n, a: True, atom_invoker=invoker, max_choice_transitions=10)

    assert thread_ids == {threading.get_ident()}  # ran on the caller's own thread


# ---------------------------------------------------------------------------
# Typed atom-invocation failure, real partial trace preserved
# ---------------------------------------------------------------------------


def test_atom_invocation_failure_is_a_typed_chained_refusal_with_a_real_partial_trace() -> None:
    node = PartialOrder(
        children=(Atom(label="a"), Atom(label="b")),
        order=frozenset([OrderEdge(NodeId(0), NodeId(1))]),
    )

    def invoker(atom: Atom) -> str:
        if atom.label == "b":
            raise RuntimeError("real invocation failure")
        return "ok"

    with pytest.raises(PowlError) as excinfo:
        execute(node, guard_evaluator=lambda n, a: True, atom_invoker=invoker, max_choice_transitions=10)

    assert excinfo.value.refusal == PowlRefusal.ATOM_INVOCATION_FAILED
    assert isinstance(excinfo.value.__cause__, RuntimeError)  # chained, never swallowed
    partial = excinfo.value.partial_trace
    assert partial is not None
    assert [s.label for s in partial.steps] == ["a", "b"]
    assert partial.steps[0].failed is False
    assert partial.steps[1].failed is True


# ---------------------------------------------------------------------------
# Checkpoint / resume (top-level scoped, per this module's own documented
# limitation)
# ---------------------------------------------------------------------------


def test_resume_from_checkpoint_skips_already_completed_top_level_children() -> None:
    node = PartialOrder(
        children=(Atom(label="a"), Atom(label="b"), Atom(label="c")),
        order=frozenset([OrderEdge(NodeId(0), NodeId(1)), OrderEdge(NodeId(1), NodeId(2))]),
    )
    checkpoints = []
    first_calls: list[str] = []

    def failing_invoker(atom: Atom) -> str:
        first_calls.append(atom.label)
        if atom.label == "b":
            raise RuntimeError("boom")
        return "ok"

    with pytest.raises(PowlError) as excinfo:
        execute(
            node,
            guard_evaluator=lambda n, a: True,
            atom_invoker=failing_invoker,
            max_choice_transitions=10,
            on_step=checkpoints.append,
        )

    assert excinfo.value.refusal == PowlRefusal.ATOM_INVOCATION_FAILED
    assert first_calls == ["a", "b"]
    last_checkpoint = checkpoints[-1]
    assert last_checkpoint.cursor == ("partial_order", frozenset({0}))

    second_calls: list[str] = []

    def real_invoker(atom: Atom) -> str:
        second_calls.append(atom.label)
        return "ok"

    trace = execute(
        node,
        guard_evaluator=lambda n, a: True,
        atom_invoker=real_invoker,
        max_choice_transitions=10,
        resume_from=last_checkpoint,
    )

    # "a" is never re-invoked on resume -- only the failed "b" and the
    # never-attempted "c" run for real on this second call.
    assert second_calls == ["b", "c"]
    labels = [s.label for s in trace.steps if s.kind == "Atom"]
    assert labels == ["a", "b", "b", "c"]  # full audit trail: original a, failed b, resumed b, c


def test_resume_against_a_structurally_different_node_is_refused() -> None:
    node = PartialOrder(children=(Atom(label="a"), Atom(label="b")))
    checkpoints = []
    execute(node, guard_evaluator=lambda n, a: True, atom_invoker=lambda a: "ok", max_choice_transitions=10, on_step=checkpoints.append)
    checkpoint = checkpoints[-1]

    different_node = PartialOrder(children=(Atom(label="x"), Atom(label="y")))

    with pytest.raises(PowlError) as excinfo:
        execute(
            different_node,
            guard_evaluator=lambda n, a: True,
            atom_invoker=lambda a: "ok",
            max_choice_transitions=10,
            resume_from=checkpoint,
        )

    assert excinfo.value.refusal == PowlRefusal.CHECKPOINT_NODE_MISMATCH


# ---------------------------------------------------------------------------
# First-class ExecutionContext -- optional, arity-detected
# ---------------------------------------------------------------------------


def test_execution_context_is_threaded_through_to_context_aware_callbacks() -> None:
    node = ChoiceGraph(
        children=(Start(), End(), Atom(label="commit")),
        edges=frozenset([ChoiceGraphEdge(NodeId(0), NodeId(2), guard=Guard("go")), ChoiceGraphEdge(NodeId(2), NodeId(1))]),
        start=0,
        end=1,
    )
    context = ExecutionContext(attributes={"round": 0})

    def evaluator(name: str, _args: dict, ctx: ExecutionContext) -> bool:
        ctx.attributes["round"] += 1
        return name == "go"

    def invoker(atom: Atom, ctx: ExecutionContext) -> str:
        return f"round={ctx.attributes['round']}"

    trace = execute(node, guard_evaluator=evaluator, atom_invoker=invoker, max_choice_transitions=10, context=context)

    assert context.attributes["round"] == 1
    atom_step = next(s for s in trace.steps if s.kind == "Atom")
    assert atom_step.result == "round=1"
    # `history` is a real, derived, non-authoritative mirror of the same steps.
    assert [s.label for s in context.history if s.kind == "Atom"] == ["commit"]


def test_existing_two_and_one_arg_callbacks_are_unaffected_by_an_unused_context() -> None:
    """Backward compatibility: a caller that supplies `context` but keeps
    2-arg/1-arg callbacks (arity not extended) is never forced to accept it."""
    node = PartialOrder(children=(Atom(label="a"), Atom(label="b")))
    context = ExecutionContext()
    calls: list[str] = []

    def evaluator(_name: str, _args: dict) -> bool:
        return True

    def invoker(atom: Atom) -> str:
        calls.append(atom.label)
        return "ok"

    execute(node, guard_evaluator=evaluator, atom_invoker=invoker, max_choice_transitions=10, context=context)

    assert calls == ["a", "b"]
