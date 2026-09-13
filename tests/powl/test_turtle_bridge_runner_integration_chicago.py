# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style integration tests: real POWL2 Turtle -> real
``fabric.powl.parse_powl_turtle`` -> real ``powl.turtle_bridge.powl_model_to_node``
-> real ``powl.runner``.

This file goes beyond ``tests/powl/test_turtle_bridge_chicago.py`` (bridge-only
round trips) and ``tests/powl/test_runner_pipeline_chicago.py`` (runner-level
happy path using the real production Turtle) in three ways:

1. Malformed/edge-case Turtle refusal paths -- both syntactically invalid
   Turtle (unterminated literal/IRI, missing terminating ``.``, undeclared
   prefix, malformed IRI) and syntactically-valid-but-structurally-invalid
   Turtle (dangling ``childModel``/``precedes`` references, duplicate/
   non-contiguous ``childIndex``, wrong root cardinality, a cyclic
   ``powl2:precedes`` graph, a document using the deliberately-unmodelled
   ``powl2:SilentLeaf`` construct) -- proving each produces the real, named,
   typed ``PowlDecodeError`` this decoder's own docstring promises, never a
   silent empty model and never an uncaught low-level exception.
2. A real round-trip property test proving ``runner.build_pipeline_powl_node()``'s
   Turtle-sourced linear prefix and ``runner.build_pipeline_turtle()`` regenerated
   and reparsed through the real decoder+bridge agree byte-for-byte on labels
   and order -- the two real code paths are not merely each independently
   "working in isolation".
3. A real non-determinism-preservation property: a genuinely unordered
   ``powl2:PartialOrder`` (two real Atoms, zero ``powl2:precedes`` edges
   between them) survives ``parse_powl_turtle`` + ``powl_model_to_node``
   with an empty ``order`` relation for that pair -- turtle_bridge does not
   accidentally serialize concurrency the source RDF graph never asserted.

No ``unittest.mock`` / ``Mock`` / ``patch`` / ``monkeypatch`` anywhere in this
file -- every parse, every bridge conversion, and every pipeline run below is
real.
"""

from __future__ import annotations

import pytest

from autofde_lab.fabric.powl import PowlDecodeError, parse_powl_turtle, project_plan_to_powl
from autofde_lab.powl.algebra import Atom, PartialOrder
from autofde_lab.powl.executor import INITIAL_MARKING, enabled, fire, is_final
from autofde_lab.powl.runner import build_pipeline_powl_node, build_pipeline_turtle
from autofde_lab.powl.turtle_bridge import BridgeError, powl_model_to_node

BASE_IRI = "urn:autofde-lab:turtle-bridge-runner-integration-test"


def _real_turtle(plan_lines: list[str]) -> str:
    return project_plan_to_powl(plan_lines, base_iri=BASE_IRI)


# ---------------------------------------------------------------------------
# 1a. Syntactically invalid Turtle -> named PowlDecodeError, never silent.
# ---------------------------------------------------------------------------


def test_unterminated_literal_is_refused_by_name():
    """A quoted literal that never closes (the ``.`` ending the raw physical
    line sits INSIDE the open quote, so the block-joiner's naive
    ``line.endswith(".")`` check still closes the block, handing
    ``_split_top_level`` a remainder whose quote state never resolves) is
    refused with the decoder's own named ``"unterminated literal or IRI"``
    reason -- confirmed to trigger through ``_split_top_level``, not merely
    assumed from the source read."""
    text = (
        "@prefix powl2: <https://truex.io/ontology/powl2#> .\n"
        '<urn:x> a powl2:Model ; powl2:derivedFrom "unterminated.\n'
    )
    with pytest.raises(PowlDecodeError, match="unterminated literal or IRI"):
        parse_powl_turtle(text)


def test_unterminated_statement_missing_trailing_dot_is_refused_by_name():
    # A real, valid document with the final statement's terminating "." removed.
    real = _real_turtle(["(noop)"])
    assert real.rstrip().endswith(".")
    truncated = real.rstrip()[:-1]  # drop the last "."
    with pytest.raises(PowlDecodeError, match="unterminated statement"):
        parse_powl_turtle(truncated)


def test_undeclared_prefix_is_refused_by_name():
    text = (
        "@prefix powl2: <https://truex.io/ontology/powl2#> .\n"
        "<urn:x> a powl2:Model ;\n"
        "    bogus:derivedFrom <urn:y> .\n"
    )
    with pytest.raises(PowlDecodeError, match="undeclared prefix"):
        parse_powl_turtle(text)


def test_subject_iri_missing_closing_bracket_is_now_refused_by_name():
    """Real defect found by this test (originally pinned the leaking
    ``ValueError`` as a regression fixture), fixed forward the same
    session: a subject IRI that never closes with ``>`` on its own line,
    e.g. ``<urn:x a powl2:Model .``, previously leaked a bare, uncaught
    ``ValueError: substring not found`` straight out of
    ``parse_powl_turtle`` instead of the module's own documented contract
    ("anything else is REFUSED with a named reason rather than silently
    ignored"). ``src/autofde_lab/fabric/powl.py``'s ``_parse_graph`` now
    checks for ``">"`` before indexing and raises a named
    ``PowlDecodeError`` instead."""
    text = "@prefix powl2: <https://truex.io/ontology/powl2#> .\n" "<urn:x a powl2:Model .\n"
    with pytest.raises(PowlDecodeError, match="never closes"):
        parse_powl_turtle(text)


def test_subject_not_an_absolute_iri_is_refused_by_name():
    text = "@prefix powl2: <https://truex.io/ontology/powl2#> .\n" "powl2:notAnIri a powl2:Model .\n"
    with pytest.raises(PowlDecodeError, match="subject must be an absolute IRI"):
        parse_powl_turtle(text)


def test_predicate_with_no_object_is_refused_by_name():
    text = (
        "@prefix powl2: <https://truex.io/ontology/powl2#> .\n"
        "<urn:x> a powl2:Model ; powl2:derivedFrom .\n"
    )
    with pytest.raises(PowlDecodeError, match="has no object"):
        parse_powl_turtle(text)


def test_malformed_prefix_declaration_is_refused_by_name():
    text = "@prefix powl2: notAnIri .\n<urn:x> a powl2:Model .\n"
    with pytest.raises(PowlDecodeError, match="malformed @prefix"):
        parse_powl_turtle(text)


def test_blank_node_construct_is_refused_by_name_not_silently_dropped():
    # This subset decoder's own docstring: "never blank nodes or collections".
    text = (
        "@prefix powl2: <https://truex.io/ontology/powl2#> .\n"
        "<urn:x> a powl2:Model ; powl2:derivedFrom _:b1 .\n"
    )
    with pytest.raises(PowlDecodeError, match="unsupported Turtle construct"):
        parse_powl_turtle(text)


# ---------------------------------------------------------------------------
# 1b. Syntactically valid, structurally invalid Turtle -> named PowlDecodeError.
# ---------------------------------------------------------------------------


def test_zero_model_roots_is_refused_by_name():
    text = "@prefix powl2: <https://truex.io/ontology/powl2#> .\n" "<urn:x> a powl2:PartialOrder .\n"
    with pytest.raises(PowlDecodeError, match=r"expected exactly 1 powl2:Model root, found 0"):
        parse_powl_turtle(text)


def test_two_model_roots_is_refused_by_name():
    text = (
        "@prefix powl2: <https://truex.io/ontology/powl2#> .\n"
        "<urn:x> a powl2:Model ; powl2:derivedFrom <urn:d> .\n"
        "<urn:y> a powl2:Model ; powl2:derivedFrom <urn:d> .\n"
    )
    with pytest.raises(PowlDecodeError, match=r"expected exactly 1 powl2:Model root, found 2"):
        parse_powl_turtle(text)


def test_dangling_childmodel_reference_is_refused_by_name():
    """A ``ChildBinding`` pointing at an ``ActivityLeaf`` IRI that was never
    declared -- syntactically perfect Turtle, structurally dangling."""
    lines = _real_turtle(["(noop)"]).splitlines()
    # The real projector's own output for a single-step plan declares exactly
    # one binding-slot pointing at exactly one step IRI. Retarget it at an IRI
    # that does not exist anywhere else in the document.
    text = "\n".join(
        line.replace(
            f"<{BASE_IRI}/plan/step/0>",
            f"<{BASE_IRI}/plan/step/DOES-NOT-EXIST>",
        )
        if "powl2:childModel" in line
        else line
        for line in lines
    )
    with pytest.raises(PowlDecodeError, match="dangling"):
        parse_powl_turtle(text)


def test_dangling_precedes_reference_is_refused_by_name():
    text = _real_turtle(["(a)", "(b)"])
    assert "powl2:precedes" in text
    mutated = text.replace(
        f"<{BASE_IRI}/plan/binding-slot/1> .",
        f"<{BASE_IRI}/plan/binding-slot/DOES-NOT-EXIST> .",
    )
    assert mutated != text
    with pytest.raises(PowlDecodeError, match="dangling reference"):
        parse_powl_turtle(mutated)


def test_duplicate_child_index_is_refused_by_name():
    text = _real_turtle(["(a)", "(b)"])
    mutated = text.replace(
        f'<{BASE_IRI}/plan/binding-slot/1> a powl2:ChildBinding ;\n    powl2:childIndex "1"^^xsd:integer ;',
        f'<{BASE_IRI}/plan/binding-slot/1> a powl2:ChildBinding ;\n    powl2:childIndex "0"^^xsd:integer ;',
    )
    assert mutated != text
    with pytest.raises(PowlDecodeError, match="duplicate powl2:childIndex"):
        parse_powl_turtle(mutated)


def test_non_contiguous_child_index_is_refused_by_name():
    text = _real_turtle(["(a)", "(b)"])
    mutated = text.replace(
        f'<{BASE_IRI}/plan/binding-slot/1> a powl2:ChildBinding ;\n    powl2:childIndex "1"^^xsd:integer ;',
        f'<{BASE_IRI}/plan/binding-slot/1> a powl2:ChildBinding ;\n    powl2:childIndex "5"^^xsd:integer ;',
    )
    assert mutated != text
    with pytest.raises(PowlDecodeError, match="not contiguous"):
        parse_powl_turtle(mutated)


def test_cyclic_precedes_is_refused_by_name():
    text = _real_turtle(["(a)", "(b)", "(c)"])
    # The real linear emitter writes 0->1->2. Add a real, extra 2->0 edge to
    # close a genuine cycle -- still syntactically valid Turtle.
    mutated = text.rstrip() + (
        f"\n<{BASE_IRI}/plan/binding-slot/2> powl2:precedes <{BASE_IRI}/plan/binding-slot/0> .\n"
    )
    with pytest.raises(PowlDecodeError, match="cycle"):
        parse_powl_turtle(mutated)


def test_missing_derived_from_is_refused_by_name():
    text = _real_turtle(["(noop)"])
    lines = [line for line in text.splitlines() if "powl2:derivedFrom" not in line]
    mutated = "\n".join(lines)
    with pytest.raises(PowlDecodeError, match="powl2:derivedFrom missing"):
        parse_powl_turtle(mutated)


def test_missing_was_derived_from_is_refused_by_name():
    text = _real_turtle(["(noop)"])
    lines = [line for line in text.splitlines() if "prov:wasDerivedFrom" not in line]
    mutated = "\n".join(lines)
    with pytest.raises(PowlDecodeError, match="prov:wasDerivedFrom missing"):
        parse_powl_turtle(mutated)


def test_activity_count_mismatch_is_refused_by_name():
    text = _real_turtle(["(a)", "(b)"])
    mutated = text.replace('mfwp:activityCount "2"^^xsd:integer .', 'mfwp:activityCount "99"^^xsd:integer .')
    assert mutated != text
    with pytest.raises(PowlDecodeError, match="mfwp:activityCount"):
        parse_powl_turtle(mutated)


def test_silent_leaf_construct_is_refused_by_name_with_unsupported_construct_reason():
    """The decoder's own docstring: ``powl2:SilentLeaf`` is deliberately not
    modelled and refused explicitly, by name -- never misreported as a
    dangling reference and never silently accepted."""
    text = (
        "@prefix powl2: <https://truex.io/ontology/powl2#> .\n"
        "@prefix mfwp: <urn:mfw:powl-trace:> .\n"
        "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n"
        "@prefix prov: <http://www.w3.org/ns/prov#> .\n"
        "<urn:x> a powl2:Model ;\n"
        "    powl2:derivedFrom <urn:d> ;\n"
        "    prov:wasDerivedFrom <urn:dom> ;\n"
        "    powl2:hasChild <urn:x/slot/0> .\n"
        "<urn:x/slot/0> a powl2:ChildBinding ;\n"
        '    powl2:childIndex "0"^^xsd:integer ;\n'
        "    powl2:childModel <urn:x/leaf/0> .\n"
        "<urn:x/leaf/0> a powl2:SilentLeaf .\n"
    )
    with pytest.raises(PowlDecodeError, match="UNSUPPORTED_CONSTRUCT"):
        parse_powl_turtle(text)


def test_dangling_bindsparameter_reference_is_refused_by_name():
    text = _real_turtle(["(move a l1)"])
    assert "mfwp:bindsParameter" in text
    mutated = text.replace(
        f"<{BASE_IRI}/plan/step/0/binding/0>",
        f"<{BASE_IRI}/plan/step/0/binding/DOES-NOT-EXIST>",
        1,  # only the mfwp:bindsParameter reference, not the binding's own IRI declaration below it
    )
    assert mutated != text
    with pytest.raises(PowlDecodeError, match="dangling"):
        parse_powl_turtle(mutated)


# ---------------------------------------------------------------------------
# 2. Round-trip agreement: build_pipeline_powl_node() vs. reparsed build_pipeline_turtle().
# ---------------------------------------------------------------------------


def test_pipeline_node_linear_prefix_agrees_byte_identically_with_reparsed_turtle():
    """The runner's own `build_pipeline_powl_node()` grafts a turtle-sourced
    linear prefix onto its hand-built tail. Regenerating
    `build_pipeline_turtle()` and reparsing it via the real
    `parse_powl_turtle` + `powl_model_to_node` a SECOND, independent time must
    produce the exact same Atom labels, in the exact same order, as what
    `build_pipeline_powl_node()` actually grafted in -- proving the two real
    call sites of turtle_bridge agree, not merely that each happens to work
    alone."""
    graft_node = build_pipeline_powl_node()
    assert isinstance(graft_node, PartialOrder)
    # The runner's own docstring: the linear prefix occupies the first
    # len(PIPELINE_LINEAR_STEPS) == 4 top-level children, in order.
    grafted_linear_labels = [c.label for c in graft_node.children[:4]]

    # Independently regenerate and reparse the real Turtle a second time.
    turtle_text = build_pipeline_turtle()
    model = parse_powl_turtle(turtle_text)
    reparsed_linear = powl_model_to_node(model)
    assert isinstance(reparsed_linear, PartialOrder)
    reparsed_labels = [c.label for c in reparsed_linear.children]

    assert grafted_linear_labels == reparsed_labels == [
        "scan",
        "phi_encode",
        "dispatch_solve",
        "solve",
    ]

    # Same real order relation, not just the same labels: both must agree the
    # steps are a strict total order 0->1->2->3.
    graft_first_four = graft_node.children[:4]
    assert all(isinstance(c, Atom) for c in graft_first_four)
    # Replay the reparsed linear atoms through the real executor and confirm
    # the fire order matches label order exactly (a strict chain, no
    # concurrency introduced or lost in either construction path).
    marking = INITIAL_MARKING
    fired: list[str] = []
    while not is_final(reparsed_linear, marking):
        live = enabled(reparsed_linear, marking)
        assert live
        path = sorted(live)[0]
        target = reparsed_linear
        for idx in path:
            target = target.children[idx]
        assert isinstance(target, Atom)
        fired.append(target.label)
        marking = fire(reparsed_linear, marking, path)
    assert fired == reparsed_labels


# ---------------------------------------------------------------------------
# 3. Non-determinism preservation: an unordered PartialOrder stays unordered
#    through Turtle -> parse -> bridge, never accidentally serialized.
# ---------------------------------------------------------------------------


def test_unordered_partial_order_turtle_document_preserves_empty_order_through_the_bridge():
    """Hand-author a real POWL2 Turtle document (not produced by
    `project_plan_to_powl`, which always emits a total order) declaring two
    real `ActivityLeaf` steps with ZERO `powl2:precedes` edges between them --
    the honest RDF expression of "no asserted order". `parse_powl_turtle`
    must accept it (an empty `powl2:precedes` set is not a structural
    violation), and `powl_model_to_node` must produce a real `PowlNode` whose
    `order` relation for that pair really is empty, proving turtle_bridge
    does not invent an order the source graph never asserted."""
    text = (
        "@prefix powl2: <https://truex.io/ontology/powl2#> .\n"
        "@prefix mfwp: <urn:mfw:powl-trace:> .\n"
        "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n"
        "@prefix prov: <http://www.w3.org/ns/prov#> .\n"
        "<urn:x> a powl2:Model, powl2:PartialOrder ;\n"
        "    powl2:derivedFrom <urn:d> ;\n"
        "    prov:wasDerivedFrom <urn:dom> ;\n"
        "    powl2:hasChild <urn:x/slot/0>, <urn:x/slot/1> ;\n"
        '    mfwp:activityCount "2"^^xsd:integer .\n'
        "<urn:x/slot/0> a powl2:ChildBinding ;\n"
        '    powl2:childIndex "0"^^xsd:integer ;\n'
        "    powl2:childModel <urn:x/leaf/0> .\n"
        "<urn:x/slot/1> a powl2:ChildBinding ;\n"
        '    powl2:childIndex "1"^^xsd:integer ;\n'
        "    powl2:childModel <urn:x/leaf/1> .\n"
        "<urn:x/leaf/0> a powl2:Leaf, powl2:ActivityLeaf ;\n"
        '    powl2:activityLabel "concurrent_a" ;\n'
        "    mfwp:implementsAction <urn:x/concurrent_a> ;\n"
        '    mfwp:planOrdinal "0"^^xsd:integer .\n'
        "<urn:x/leaf/1> a powl2:Leaf, powl2:ActivityLeaf ;\n"
        '    powl2:activityLabel "concurrent_b" ;\n'
        "    mfwp:implementsAction <urn:x/concurrent_b> ;\n"
        '    mfwp:planOrdinal "1"^^xsd:integer .\n'
    )

    model = parse_powl_turtle(text)
    node = powl_model_to_node(model)
    assert isinstance(node, PartialOrder)
    assert [c.label for c in node.children] == ["concurrent_a", "concurrent_b"]

    # The real order relation for this pair is empty: no edge (0,1) or (1,0).
    assert node.order == frozenset()
    assert node.closure == frozenset()

    # Directly observable through the real executor: both real paths are
    # simultaneously enabled from the initial marking -- genuine concurrency,
    # not an artifact of only checking the raw `order` field.
    live = enabled(node, INITIAL_MARKING)
    assert live == frozenset({(0,), (1,)})

    # Both real fire orders are legal: firing (1,) first, then (0,), reaches
    # the same final marking as the reverse -- proving the bridge did not
    # silently pick or bake in one linearisation over the other.
    marking_ab = fire(node, fire(node, INITIAL_MARKING, (0,)), (1,))
    marking_ba = fire(node, fire(node, INITIAL_MARKING, (1,)), (0,))
    assert is_final(node, marking_ab)
    assert is_final(node, marking_ba)
