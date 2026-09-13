# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style round-trip test for ``autofde_lab.powl.turtle_bridge``.

Real collaborators throughout, no test doubles:

1. A real plan is projected to real POWL2 Turtle text via
   ``fabric.powl.project_plan_to_powl`` (the actual writer, not a hand-typed
   fixture pretending to be its output).
2. That real Turtle text is decoded by the real ``fabric.powl.parse_powl_turtle``
   (which itself runs the real ``validate_powl`` before returning).
3. The real ``PowlModel`` is converted to a real
   ``autofde_lab.powl.algebra.PowlNode`` via ``powl_model_to_node``.
4. That real ``PowlNode`` is driven through the real, already-tested
   ``autofde_lab.powl.executor`` (``enabled()``/``fire()``/``is_final()``) --
   the exact traversal ``powl/executor.py``'s own test suite exercises --
   confirming the converted tree actually replays a legal, complete run.
5. The resulting ``PowlNode`` is converted back to a ``PowlModel`` via
   ``powl_node_to_model``, serialized to Turtle via the new
   ``model_to_turtle``, and re-parsed by the real ``parse_powl_turtle`` again,
   confirming semantic equivalence (same activity labels in the same total
   order) with the original.

Zero mocks: no ``unittest.mock``, no ``Mock``, no ``patch``, no
``monkeypatch`` anywhere in this file.
"""

from __future__ import annotations

from autofde_lab.fabric.powl import parse_powl_turtle, project_plan_to_powl
from autofde_lab.powl.algebra import Atom, OrderEdge, PartialOrder
from autofde_lab.powl.executor import INITIAL_MARKING, enabled, fire, is_final
from autofde_lab.powl.turtle_bridge import (
    BridgeError,
    model_to_turtle,
    powl_model_to_node,
    powl_node_to_model,
)

# A real multi-step plan, VAL-format lines -- the same shape
# ``project_plan_to_powl``'s own docstring and tests exercise.
REAL_PLAN_LINES = [
    "(pick-up a)",
    "(stack a b)",
    "(unstack b c)",
    "(put-down c)",
]

BASE_IRI = "urn:autofde-lab:turtle-bridge-test"


def _real_turtle() -> str:
    """The real projector's real output for :data:`REAL_PLAN_LINES`."""
    return project_plan_to_powl(
        REAL_PLAN_LINES,
        base_iri=BASE_IRI,
        planner_run="run-turtle-bridge-chicago",
    )


def _replay_to_finality(node) -> tuple[str, ...]:
    """Drive ``node`` through the real executor to completion.

    Returns the observed activity-label sequence in the order fired. At each
    step every enabled leaf is legal to fire under the total order the
    Turtle projector emits, so firing them in ``sorted()`` order (a
    deterministic policy the *caller* supplies, per executor.py's law 1 --
    the executor itself never chooses) produces the plan's original order.
    """
    marking = INITIAL_MARKING
    fired_labels: list[str] = []
    for _ in range(64):
        if is_final(node, marking):
            break
        live = enabled(node, marking)
        assert live, "executor reported neither final nor enabled: real deadlock"
        path = sorted(live)[0]
        # Recover the label of the node about to fire, from the real tree.
        target = node
        for idx in path:
            target = target.children[idx]
        assert isinstance(target, Atom)
        fired_labels.append(target.label)
        marking = fire(node, marking, path)
    else:  # pragma: no cover - safety net, not expected to trigger
        raise AssertionError("real executor did not reach a final marking in 64 fires")
    assert is_final(node, marking)
    return tuple(fired_labels)


def test_real_turtle_document_matches_this_repos_real_projector_shape():
    """Sanity check the fixture is real projector output, not a hand fixture."""
    text = _real_turtle()
    assert "powl2:ActivityLeaf" in text
    assert "pick-up" in text
    model = parse_powl_turtle(text)
    assert len(model.children) == len(REAL_PLAN_LINES)


def test_powl_model_to_node_produces_a_partial_order_of_atoms():
    model = parse_powl_turtle(_real_turtle())
    node = powl_model_to_node(model)
    assert isinstance(node, PartialOrder)
    assert len(node.children) == len(REAL_PLAN_LINES)
    assert all(isinstance(c, Atom) for c in node.children)
    labels = [c.label for c in node.children]
    assert labels == ["pick-up", "stack", "unstack", "put-down"]


def test_powl_model_to_node_preserves_the_total_order_as_a_chain():
    model = parse_powl_turtle(_real_turtle())
    node = powl_model_to_node(model)
    assert isinstance(node, PartialOrder)
    expected_chain = {OrderEdge(i, i + 1) for i in range(len(node.children) - 1)}
    assert node.closure >= expected_chain
    # Under this precedence, only step 0 is enabled from the initial marking.
    assert enabled(node) == frozenset({(0,)})


def test_end_to_end_turtle_to_node_to_real_executor_replay_to_finality():
    """The headline claim: the converted tree actually replays via the REAL
    executor, and produces the same activity sequence as the source plan.
    """
    model = parse_powl_turtle(_real_turtle())
    node = powl_model_to_node(model)

    fired = _replay_to_finality(node)

    expected_labels = tuple(line.strip("()").split()[0] for line in REAL_PLAN_LINES)
    assert fired == expected_labels


def test_round_trip_node_to_model_to_turtle_to_model_is_semantically_equivalent():
    """PowlModel -> PowlNode -> (real executor replay happens above) ->
    PowlNode -> PowlModel -> Turtle -> PowlModel, confirming the final model
    carries the same activities in the same partial-order structure as the
    one the real projector originally emitted.
    """
    original_model = parse_powl_turtle(_real_turtle())
    node = powl_model_to_node(original_model)

    # Round-trip back out.
    rebuilt_model = powl_node_to_model(node, base_iri=BASE_IRI)
    turtle_text = model_to_turtle(rebuilt_model)

    # The real decoder must accept this real serializer's real output.
    reparsed_model = parse_powl_turtle(turtle_text)

    original_labels = [
        original_model.leaves[c.child_model].activity_label
        for c in original_model.ordered_children()
    ]
    reparsed_labels = [
        reparsed_model.leaves[c.child_model].activity_label
        for c in reparsed_model.ordered_children()
    ]
    assert reparsed_labels == original_labels

    # Same total-order structure: re-derive the PowlNode from the reparsed
    # model and confirm it replays to the same activity sequence through the
    # real executor again.
    reparsed_node = powl_model_to_node(reparsed_model)
    assert _replay_to_finality(reparsed_node) == _replay_to_finality(node)


def test_single_step_plan_round_trips_through_the_bare_atom_shape():
    """n=1 is the shape boundary: PartialOrder refuses n<2, so a one-step
    plan must reduce to a bare Atom on both sides of the bridge.
    """
    text = project_plan_to_powl(["(noop)"], base_iri=BASE_IRI)
    model = parse_powl_turtle(text)
    node = powl_model_to_node(model)
    assert isinstance(node, Atom)
    assert node.label == "noop"

    fired = _replay_to_finality(node)
    assert fired == ("noop",)

    rebuilt = powl_node_to_model(node, base_iri=BASE_IRI)
    reparsed = parse_powl_turtle(model_to_turtle(rebuilt))
    assert len(reparsed.children) == 1
    only_leaf = next(iter(reparsed.leaves.values()))
    assert only_leaf.activity_label == "noop"


def test_parameter_bindings_survive_the_round_trip():
    text = project_plan_to_powl(["(move a l1 l2)", "(move a l2 l3)"], base_iri=BASE_IRI)
    model = parse_powl_turtle(text)
    node = powl_model_to_node(model)
    assert isinstance(node, PartialOrder)
    first = node.children[0]
    assert isinstance(first, Atom)
    assert first.bindings == {
        "0": f"{BASE_IRI}/object/a",
        "1": f"{BASE_IRI}/object/l1",
        "2": f"{BASE_IRI}/object/l2",
    }

    rebuilt = powl_node_to_model(node, base_iri=BASE_IRI)
    reparsed = parse_powl_turtle(model_to_turtle(rebuilt))
    reparsed_node = powl_model_to_node(reparsed)
    assert reparsed_node.children[0].bindings == first.bindings  # type: ignore[union-attr]


def test_unordered_partial_order_from_algebra_round_trips_via_closure():
    """A PowlNode with no explicit order (both children immediately enabled)
    is a legal input to powl_node_to_model even though fabric/powl.py never
    emits that shape itself -- the bridge must still honestly represent
    "no precedence" as zero powl2:precedes edges, not invent an order.
    """
    node = PartialOrder((Atom("a"), Atom("b")))
    assert enabled(node) == frozenset({(0,), (1,)})

    model = powl_node_to_model(node, base_iri=BASE_IRI)
    slot0, slot1 = model.ordered_children()
    assert slot0.precedes == ()
    assert slot1.precedes == ()

    turtle_text = model_to_turtle(model)
    reparsed = parse_powl_turtle(turtle_text)
    reparsed_node = powl_model_to_node(reparsed)
    assert enabled(reparsed_node) == frozenset({(0,), (1,)})


def test_empty_model_is_refused_by_name():
    model = parse_powl_turtle(project_plan_to_powl(["(noop)"], base_iri=BASE_IRI))
    # Construct an empty variant by hand (parse_powl_turtle can never itself
    # produce one, since project_plan_to_powl always emits >=0 steps and the
    # decoder's own validate_powl only checks the *shape* it received).
    empty = model.__class__(
        iri=model.iri,
        types=model.types,
        derived_from=model.derived_from,
        was_derived_from=model.was_derived_from,
        has_child=(),
        children={},
        leaves={},
        bindings={},
    )
    try:
        powl_model_to_node(empty)
    except BridgeError as exc:
        assert "EMPTY_MODEL" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected BridgeError for an empty PowlModel")


def test_choice_graph_shape_is_refused_by_name_not_silently_flattened():
    from autofde_lab.powl.algebra import ChoiceGraph

    node = ChoiceGraph((Atom("a"), Atom("b")))
    try:
        powl_node_to_model(node, base_iri=BASE_IRI)
    except BridgeError as exc:
        assert "UNSUPPORTED_NODE_SHAPE" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected BridgeError for a ChoiceGraph")


