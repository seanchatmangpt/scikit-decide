# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for the POWL2 projector and its strict decoder.

The defect these tests exist to prevent recurring: ``project_plan_to_powl``
emitted Turtle that was **SHACL-invalid** against mfw's own committed shapes at
``~/mfw/mfw-planner/shapes/powl2.shacl.ttl``. ``powl2:ActivityLeafShape``
requires ``mfwp:implementsAction`` with ``minCount 1 / maxCount 1``; the
projector never emitted it, while the Rust reference emitter
(``~/mfw/mfw-planner/src/projection/powl_rdf.rs``) and the real committed
artifact ``~/mfw/runs/ticket-10/plan.powl.ttl`` both do. Nothing in the test
suite noticed, because every assertion checked for the presence of terms we
emitted rather than the presence of terms the shapes require.

Discipline, following ``tests/ecosystem/test_chatman_chain_chicago.py``: where
an mfw artifact is genuinely absent the test SKIPS with the blocker named
(``BLOCKED:<TOKEN>: ...``) and never substitutes a fixture in its place. A
green run against a fixture standing in for the real artifact would assert
nothing about the real artifact.

Scope reminder: this file exercises a projector. Projection is not execution,
and nothing here is admitted, receipted, or authorised to actuate.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from autofde_lab.fabric.powl import (
    MFWP,
    POWL2,
    PROV,
    PowlDecodeError,
    parse_powl_turtle,
    project_plan_to_powl,
    validate_powl,
)
from autofde_lab.fabric.shacl_conformance import (
    ShaclDependencyMissing,
    check_shacl_conformance,
)

HOME = Path.home()
MFW = HOME / "mfw"
MFW_TICKET10_POWL = MFW / "runs" / "ticket-10" / "plan.powl.ttl"
MFW_SHAPES = MFW / "mfw-planner" / "shapes" / "powl2.shacl.ttl"
MFW_RUST_EMITTER = MFW / "mfw-planner" / "src" / "projection" / "powl_rdf.rs"

PLAN = [
    "(unstack b a)",
    "(put-down b)",
    "(pick-up a)",
    "(stack a c)",
    "; cost = 4 (unit cost)",
]

BASE = "urn:skdecide:plan"


@pytest.fixture
def turtle() -> str:
    return project_plan_to_powl(PLAN, base_iri=BASE)


def plan_lines_from_model(model) -> list[str]:
    """Recover VAL-format plan lines from a decoded model."""
    lines = []
    for child in model.ordered_children():
        leaf = model.leaves[child.child_model]
        arguments = [
            model.bindings[b].bound_object.rsplit("/object/", 1)[-1]
            for b in leaf.binds_parameter
        ]
        lines.append("(" + " ".join([leaf.activity_label] + arguments) + ")")
    return lines


# ---------------------------------------------------------------------------
# The regression that motivated this file
# ---------------------------------------------------------------------------


class TestShaclConformance:
    """Re-expresses the committed shapes. Would have caught the real defect."""

    def test_projection_satisfies_the_committed_shapes(self, turtle):
        """Three shape-derived properties of our own output, all named on failure.

        Collapsed from three sibling tests, each redrawing "the emitted Turtle
        conforms to mfw's committed shapes". Every check still runs.

        * IMPLEMENTS_ACTION -- powl2:ActivityLeafShape requires
          ``mfwp:implementsAction`` minCount 1 / maxCount 1. This is the
          assertion whose absence let SHACL-invalid output ship.
        * PROV_DERIVATION -- the root binds the plan to its source domain.
        * PRECEDES_EDGES -- a declared PartialOrder with zero edges is a chain
          by accident.
        """
        failures: list[str] = []

        leaves = [
            block
            for block in turtle.split("\n\n")
            if "a powl2:Leaf, powl2:ActivityLeaf" in block
        ]
        if len(leaves) != 4:
            failures.append(f"IMPLEMENTS_ACTION: expected 4 leaves, got {len(leaves)}")
        for block in leaves:
            if block.count("mfwp:implementsAction") != 1:
                failures.append(
                    "IMPLEMENTS_ACTION: every powl2:ActivityLeaf must carry "
                    f"exactly one mfwp:implementsAction; got:\n{block}"
                )

        if "prov:wasDerivedFrom" not in turtle:
            failures.append(
                "PROV_DERIVATION: the prov: prefix was declared and never used; "
                "mfw's emitter binds the plan to its domain with prov:wasDerivedFrom"
            )
        if turtle.count("powl2:precedes") != 3:
            failures.append(
                "PRECEDES_EDGES: 4 steps in total order must yield 3 "
                f"powl2:precedes edges, got {turtle.count('powl2:precedes')}"
            )

        model = parse_powl_turtle(turtle)
        if model.derived_from != (BASE,):
            failures.append(f"PROV_DERIVATION: derived_from {model.derived_from!r}")
        if model.was_derived_from != (f"{BASE}/domain",):
            failures.append(
                f"PROV_DERIVATION: was_derived_from {model.was_derived_from!r}"
            )
        ordered = model.ordered_children()
        for before, after in zip(ordered, ordered[1:]):
            if after.iri not in before.precedes:
                failures.append(
                    f"PRECEDES_EDGES: {before.iri} does not precede {after.iri}"
                )

        assert not failures, "\n".join(failures)

    def test_projection_conforms_to_real_pyshacl_validation(self, turtle):
        """Run the REAL SHACL engine against the REAL committed shapes.

        The three checks in ``test_projection_satisfies_the_committed_shapes``
        above are a hand-reimplementation of what the shapes require -- the
        exact pattern that let SHACL-invalid output ship undetected once
        already (see this file's module docstring). This test runs
        ``pyshacl.validate()`` -- an independent, spec-compliant SHACL
        engine -- against the literal committed
        ``~/mfw/mfw-planner/shapes/powl2.shacl.ttl``, so there is no second
        hand-written copy of the constraints to drift from the first.

        SKIPs (never silently passes) if ``~/mfw``'s shapes file is absent
        or if ``pyshacl``/``rdflib`` are not installed (both are declared
        only under this repo's optional ``ofmf`` extra).
        """
        try:
            result = check_shacl_conformance(turtle)
        except FileNotFoundError as exc:
            pytest.skip(f"BLOCKED:MFW_SHAPES_ABSENT: {exc}")
        except ShaclDependencyMissing as exc:
            pytest.skip(f"BLOCKED:PYSHACL_ABSENT: {exc}")

        assert result.conforms, (
            f"emitted Turtle is not SHACL-conformant against "
            f"{result.shapes_path} ({result.violation_count} violation(s)):\n"
            f"{result.report_text}"
        )

    def test_shape_file_still_requires_what_we_assert(self):
        """The shapes are the authority; assert we did not drift from them."""
        if not MFW_SHAPES.exists():
            pytest.skip(f"BLOCKED:MFW_SHAPES_ABSENT: {MFW_SHAPES} not present")
        shapes = MFW_SHAPES.read_text()
        assert "powl2:ActivityLeafShape" in shapes
        assert "mfwp:implementsAction" in shapes
        # 3 node shapes, 6 sh:property constraint blocks.
        assert shapes.count("a sh:NodeShape") == 3
        assert shapes.count("sh:property") == 6

    def test_rust_emitter_agrees_on_the_terms_we_emit(self):
        if not MFW_RUST_EMITTER.exists():
            pytest.skip(
                f"BLOCKED:MFW_SOURCE_ABSENT: {MFW_RUST_EMITTER} not present"
            )
        rust = MFW_RUST_EMITTER.read_text()
        for term in (
            "mfwp:implementsAction",
            "prov:wasDerivedFrom",
            "powl2:precedes",
        ):
            assert term in rust, f"{term} absent from mfw's reference emitter"


# ---------------------------------------------------------------------------
# Round trip
# ---------------------------------------------------------------------------


class TestRoundTrip:
    def test_project_parse_project_is_faithful(self, turtle):
        """Five round-trip properties, each named on failure.

        Collapsed from five sibling tests, all redrawing "what the projector
        emits is exactly what the decoder reads back". Every check still runs.

        BYTE_IDENTICAL / STRUCTURE / COMMENTS_DROPPED / EMPTY_PLAN /
        SINGLE_STEP / VALIDATE_CALLABLE.
        """
        failures: list[str] = []
        model = parse_powl_turtle(turtle)

        again = project_plan_to_powl(plan_lines_from_model(model), base_iri=BASE)
        if again != turtle:
            failures.append("BYTE_IDENTICAL: re-projection differs from the original")

        for label, actual, expected in (
            ("STRUCTURE activity_count", model.activity_count, 4),
            ("STRUCTURE children", len(model.children), 4),
            ("STRUCTURE leaves", len(model.leaves), 4),
            (
                "STRUCTURE child_index",
                [c.child_index for c in model.ordered_children()],
                [0, 1, 2, 3],
            ),
            (
                "STRUCTURE labels",
                [
                    model.leaves[c.child_model].activity_label
                    for c in model.ordered_children()
                ],
                ["unstack", "put-down", "pick-up", "stack"],
            ),
            ("STRUCTURE projection", model.projection, "total-order"),
        ):
            if actual != expected:
                failures.append(f"{label}: got {actual!r}, expected {expected!r}")

        if "cost" in turtle:
            failures.append("COMMENTS_DROPPED: a comment line became an activity")

        empty = parse_powl_turtle(project_plan_to_powl([], base_iri=BASE))
        if empty.children != {} or empty.activity_count != 0:
            failures.append(
                f"EMPTY_PLAN: {empty.children!r} / count {empty.activity_count}"
            )

        single = project_plan_to_powl(["(pick-up a)"], base_iri=BASE)
        if "powl2:precedes" in single:
            failures.append("SINGLE_STEP: one-step plan emitted a precedes edge")
        if len(parse_powl_turtle(single).children) != 1:
            failures.append("SINGLE_STEP: one-step plan did not decode to one child")

        if validate_powl(model) is None:
            failures.append("VALIDATE_CALLABLE: validate_powl returned None")

        assert not failures, "\n".join(failures)


# ---------------------------------------------------------------------------
# The real mfw artifact -- skipped, never substituted
# ---------------------------------------------------------------------------


class TestRealMfwArtifact:
    @pytest.fixture
    def reference(self) -> str:
        if not MFW_TICKET10_POWL.exists():
            pytest.skip(
                f"BLOCKED:MFW_ARTIFACT_ABSENT: {MFW_TICKET10_POWL} not present"
            )
        return MFW_TICKET10_POWL.read_text()

    def test_decoder_accepts_mfws_committed_output(self, reference):
        """Three properties of reading mfw's real artifact, named on failure.

        Collapsed from three sibling tests behind the same
        ``BLOCKED:MFW_ARTIFACT_ABSENT`` gate, all redrawing "our decoder reads
        the real emitter's real output, unmodified".

        DECODES / SHAPE_WE_ENFORCE / PREFIXES_EXPANDED.
        """
        failures: list[str] = []
        model = parse_powl_turtle(reference)

        for label, condition in (
            ("DECODES powl2:Model", POWL2 + "Model" in model.types),
            ("DECODES powl2:PartialOrder", POWL2 + "PartialOrder" in model.types),
            ("DECODES activity_count", model.activity_count == len(model.children)),
            ("DECODES projection", model.projection == "total-order"),
            ("SHAPE_WE_ENFORCE was_derived_from", bool(model.was_derived_from)),
            ("PREFIXES_EXPANDED model iri", model.iri.startswith("urn:mfw:id:")),
            ("PREFIXES_EXPANDED namespaces", MFWP.endswith(":") and PROV.endswith("#")),
        ):
            if not condition:
                failures.append(label)

        for leaf in model.leaves.values():
            if not leaf.implements_action.startswith("urn:mfw:id:"):
                failures.append(
                    f"SHAPE_WE_ENFORCE implementsAction: {leaf.implements_action!r}"
                )
            if leaf.implements_action.startswith("mfwp:"):
                failures.append(
                    "PREFIXES_EXPANDED: a prefixed name was compared as a string"
                )

        assert not failures, "\n".join(failures)


# ---------------------------------------------------------------------------
# Rejection cases -- a decoder that skips what it cannot read cannot validate
# ---------------------------------------------------------------------------


def _mutate(turtle: str, old: str, new: str) -> str:
    assert old in turtle, f"fixture drifted: {old!r} not present"
    return turtle.replace(old, new, 1)


class TestRejections:
    def test_missing_implements_action_is_refused(self, turtle):
        broken = _mutate(
            turtle, f"    mfwp:implementsAction <{BASE}/unstack> ;\n", ""
        )
        with pytest.raises(PowlDecodeError, match="implementsAction"):
            parse_powl_turtle(broken)

    def test_missing_derived_from_is_refused(self, turtle):
        broken = _mutate(turtle, f"    powl2:derivedFrom <{BASE}> ;\n", "")
        with pytest.raises(PowlDecodeError, match="derivedFrom"):
            parse_powl_turtle(broken)

    def test_missing_prov_derivation_is_refused(self, turtle):
        broken = _mutate(turtle, f"    prov:wasDerivedFrom <{BASE}/domain> ;\n", "")
        with pytest.raises(PowlDecodeError, match="wasDerivedFrom"):
            parse_powl_turtle(broken)

    def test_duplicate_child_index_is_refused(self, turtle):
        broken = _mutate(
            turtle, '    powl2:childIndex "1"^^xsd:integer ;', '    powl2:childIndex "0"^^xsd:integer ;'
        )
        with pytest.raises(PowlDecodeError, match="childIndex"):
            parse_powl_turtle(broken)

    def test_non_integer_ordinal_is_refused(self, turtle):
        broken = _mutate(
            turtle, 'mfwp:planOrdinal "0"^^xsd:integer', 'mfwp:planOrdinal "first"'
        )
        with pytest.raises(PowlDecodeError, match="planOrdinal"):
            parse_powl_turtle(broken)

    def test_cyclic_precedes_is_refused(self, turtle):
        broken = turtle + (
            f"\n<{BASE}/plan/binding-slot/3> powl2:precedes "
            f"<{BASE}/plan/binding-slot/0> .\n"
        )
        with pytest.raises(PowlDecodeError, match="cycle"):
            parse_powl_turtle(broken)

    def test_dangling_child_model_is_refused(self, turtle):
        broken = _mutate(
            turtle,
            f"    powl2:childModel <{BASE}/plan/step/0> .",
            f"    powl2:childModel <{BASE}/plan/step/99> .",
        )
        with pytest.raises(PowlDecodeError, match="dangling"):
            parse_powl_turtle(broken)

    def test_silent_leaf_is_refused_by_name_not_as_a_dangling_reference(
        self, turtle
    ):
        """A powl2:SilentLeaf child must be refused as an unsupported construct.

        Before this test the document was refused only *incidentally*: the
        silent leaf never registered in ``model.leaves``, so the dangling
        ``childModel`` check fired and blamed a malformed reference. That
        message sends an operator hunting a truncated document instead of
        telling them this projector does not model silent transitions. The
        second assertion is the regression guard.
        """
        broken = _mutate(
            turtle,
            f"    powl2:childModel <{BASE}/plan/step/0> .",
            f"    powl2:childModel <{BASE}/plan/step/tau> .",
        ) + (
            f"\n<{BASE}/plan/step/tau> a powl2:SilentLeaf .\n"
        )
        with pytest.raises(PowlDecodeError) as excinfo:
            parse_powl_turtle(broken)
        message = str(excinfo.value)
        assert "UNSUPPORTED_CONSTRUCT" in message
        assert "powl2:SilentLeaf" in message
        assert f"{BASE}/plan/step/tau" in message
        assert "dangling" not in message

    def test_dangling_binds_parameter_is_refused(self, turtle):
        broken = _mutate(
            turtle,
            f"    mfwp:bindsParameter <{BASE}/plan/step/0/binding/0> ;",
            f"    mfwp:bindsParameter <{BASE}/plan/step/0/binding/7> ;",
        )
        with pytest.raises(PowlDecodeError, match="dangling"):
            parse_powl_turtle(broken)

    def test_stray_predicate_after_terminator_is_refused(self, turtle):
        broken = turtle + '\n    mfwp:projection "temporal-order" .\n'
        with pytest.raises(PowlDecodeError):
            parse_powl_turtle(broken)

    def test_unknown_construct_is_refused(self, turtle):
        broken = _mutate(
            turtle,
            f"    powl2:derivedFrom <{BASE}> ;",
            "    powl2:derivedFrom [ a powl2:Thing ] ;",
        )
        with pytest.raises(PowlDecodeError):
            parse_powl_turtle(broken)

    def test_undeclared_prefix_is_refused(self, turtle):
        broken = _mutate(
            turtle, "    mfwp:projection", "    nosuch:projection"
        )
        with pytest.raises(PowlDecodeError, match="undeclared prefix"):
            parse_powl_turtle(broken)

    def test_unterminated_statement_is_refused(self, turtle):
        with pytest.raises(PowlDecodeError, match="unterminated"):
            parse_powl_turtle(turtle + f"\n<{BASE}/x> a powl2:Leaf ;\n")

    def test_activity_count_disagreement_is_refused(self, turtle):
        broken = _mutate(
            turtle,
            'mfwp:activityCount "4"^^xsd:integer',
            'mfwp:activityCount "9"^^xsd:integer',
        )
        with pytest.raises(PowlDecodeError, match="activityCount"):
            parse_powl_turtle(broken)


# ---------------------------------------------------------------------------
# The projector remains a projector
# ---------------------------------------------------------------------------


def test_projection_claims_no_admission(turtle):
    """Same boundary as test_chatman_chain_chicago.py, asserted at unit level."""
    for forbidden in ("Admitted", "admitted", "ALIVE", "receipt("):
        assert forbidden not in turtle
