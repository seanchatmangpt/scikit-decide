# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for `autofde_lab.powl.ocel_bridge`.

Real collaborators throughout: real `PartialOrder`/`ChoiceGraph`/`Atom`
construction (`autofde_lab.powl.algebra`), the real, unmodified
`autofde_lab.powl.guard_executor.execute` reached through
`execute_with_ocel`, a real `autofde_lab.ocel.log.OcelLog` accumulated by a
real `OcelExecutionRecorder`, and real, hand-written deterministic guard
evaluators / atom invokers -- no LLM call anywhere in this file.

No `unittest.mock` / `Mock` / `MagicMock` / `patch` / `monkeypatch` anywhere
in this file.
"""

from __future__ import annotations

from autofde_lab.ocel.model import OcelValueKind
from autofde_lab.powl.algebra import Atom, ChoiceGraph, ChoiceGraphEdge, End, Guard, NodeId, OrderEdge, PartialOrder, Silent, Start
from autofde_lab.powl.guard_executor import execute
from autofde_lab.powl.ocel_bridge import OcelExecutionRecorder, execute_with_ocel


def _three_atom_partial_order() -> PartialOrder:
    """A real, small partial order: three atoms of different consequences,
    strictly ordered a -> b -> c."""
    return PartialOrder(
        children=(
            Atom(label="fetch_state", consequence="READ"),
            Atom(label="compute_plan", consequence="PURE"),
            Atom(label="actuate_gate", consequence="DO"),
        ),
        order=frozenset(
            [
                OrderEdge(NodeId(0), NodeId(1)),
                OrderEdge(NodeId(1), NodeId(2)),
            ]
        ),
    )


def _real_invoker(calls: list[str]):
    def invoker(atom: Atom) -> str:
        calls.append(atom.label)
        return f"result-of-{atom.label}"

    return invoker


# ---------------------------------------------------------------------------
# Real event count and order match the real atoms visited
# ---------------------------------------------------------------------------


def test_execute_with_ocel_records_one_event_per_real_atom_visited_in_order() -> None:
    node = _three_atom_partial_order()
    calls: list[str] = []
    recorder = OcelExecutionRecorder()

    trace = execute_with_ocel(
        node,
        guard_evaluator=lambda n, a: True,
        atom_invoker=_real_invoker(calls),
        max_choice_transitions=10,
        recorder=recorder,
    )

    assert calls == ["fetch_state", "compute_plan", "actuate_gate"]

    log = recorder.close()
    assert len(log.events) == 3
    # Real execution order preserved in the real event stream.
    assert [e.activity for e in log.events] == ["AtomInvoked", "AtomInvoked", "AtomInvoked"]
    labels_in_order = [
        next(a.value.value for a in e.attributes if a.key == "label") for e in log.events
    ]
    assert labels_in_order == ["fetch_state", "compute_plan", "actuate_gate"]

    atom_steps = [s for s in trace.steps if s.kind == "Atom"]
    assert len(log.events) == len(atom_steps)


def test_events_carry_real_object_types_and_attributes() -> None:
    node = _three_atom_partial_order()
    recorder = OcelExecutionRecorder()

    execute_with_ocel(
        node,
        guard_evaluator=lambda n, a: True,
        atom_invoker=_real_invoker([]),
        max_choice_transitions=10,
        recorder=recorder,
    )
    log = recorder.close()

    object_types = {o.object_type for o in log.objects}
    assert "PowlExecution" in object_types
    assert "PowlActivity" in object_types

    execution_objects = [o for o in log.objects if o.object_type == "PowlExecution"]
    assert len(execution_objects) == 1
    assert execution_objects[0].id == recorder.execution_id

    activity_objects = {o.id: o for o in log.objects if o.object_type == "PowlActivity"}
    assert set(activity_objects) == {"activity-fetch_state", "activity-compute_plan", "activity-actuate_gate"}
    for expected_label, obj_id in (
        ("fetch_state", "activity-fetch_state"),
        ("compute_plan", "activity-compute_plan"),
        ("actuate_gate", "activity-actuate_gate"),
    ):
        label_attr = next(a for a in activity_objects[obj_id].attributes if a.key == "label")
        assert label_attr.value.kind is OcelValueKind.STRING
        assert label_attr.value.value == expected_label

    consequences_by_label = {
        next(a.value.value for a in e.attributes if a.key == "label"): next(
            a.value.value for a in e.attributes if a.key == "consequence"
        )
        for e in log.events
    }
    assert consequences_by_label == {
        "fetch_state": "READ",
        "compute_plan": "PURE",
        "actuate_gate": "DO",
    }

    # Each event links the one execution object and its one activity object.
    for event in log.events:
        linked = {link.object_id for link in log.event_object_links if link.event_id == event.id}
        assert recorder.execution_id in linked
        assert len(linked) == 2


def test_events_are_e2o_linked_to_activity_objects_matching_visitation_order() -> None:
    node = _three_atom_partial_order()
    recorder = OcelExecutionRecorder()

    execute_with_ocel(
        node,
        guard_evaluator=lambda n, a: True,
        atom_invoker=_real_invoker([]),
        max_choice_transitions=10,
        recorder=recorder,
    )
    log = recorder.close()

    ordered_activity_ids = []
    for event in log.events:
        linked = [link.object_id for link in log.event_object_links if link.event_id == event.id]
        activity_id = next(oid for oid in linked if oid != recorder.execution_id)
        ordered_activity_ids.append(activity_id)

    assert ordered_activity_ids == ["activity-fetch_state", "activity-compute_plan", "activity-actuate_gate"]


# ---------------------------------------------------------------------------
# The wrapper adds observation without changing real execution semantics
# ---------------------------------------------------------------------------


def test_execute_with_ocel_trace_is_identical_to_plain_execute_trace() -> None:
    """Same inputs, same real execution result -- proving the OCEL wrapper
    changes nothing about `execute()`'s own structural behaviour."""
    plain_calls: list[str] = []
    plain_trace = execute(
        _three_atom_partial_order(),
        guard_evaluator=lambda n, a: True,
        atom_invoker=_real_invoker(plain_calls),
        max_choice_transitions=10,
    )

    wrapped_calls: list[str] = []
    recorder = OcelExecutionRecorder()
    wrapped_trace = execute_with_ocel(
        _three_atom_partial_order(),
        guard_evaluator=lambda n, a: True,
        atom_invoker=_real_invoker(wrapped_calls),
        max_choice_transitions=10,
        recorder=recorder,
    )

    assert plain_calls == wrapped_calls
    assert plain_trace == wrapped_trace


def test_execute_with_ocel_over_a_real_choice_graph_preserves_transition_count() -> None:
    """A real, guarded `ChoiceGraph` -- same shape as `test_guard_executor_chicago.py`'s
    fixtures -- proving the bridge also works over the choice-graph walk, not
    only the partial-order walk, and that `choice_transitions_taken` is
    unaffected by OCEL emission."""
    graph = ChoiceGraph(
        children=(
            Start(),  # 0
            End(),  # 1
            Silent(),  # 2
            Atom(label="commit", consequence="DO"),  # 3
        ),
        edges=frozenset(
            [
                ChoiceGraphEdge(NodeId(0), NodeId(2)),
                ChoiceGraphEdge(NodeId(2), NodeId(3), guard=Guard("ready")),
                ChoiceGraphEdge(NodeId(3), NodeId(1)),
            ]
        ),
        start=0,
        end=1,
    )

    def evaluator(name: str, _args: dict) -> bool:
        return name == "ready"

    calls: list[str] = []
    recorder = OcelExecutionRecorder()
    trace = execute_with_ocel(
        graph,
        guard_evaluator=evaluator,
        atom_invoker=_real_invoker(calls),
        max_choice_transitions=10,
        recorder=recorder,
    )

    assert calls == ["commit"]
    assert trace.choice_transitions_taken == 3  # Start->decide, decide->commit, commit->End

    log = recorder.close()
    assert len(log.events) == 1
    assert next(a.value.value for a in log.events[0].attributes if a.key == "label") == "commit"
