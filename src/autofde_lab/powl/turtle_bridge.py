# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Bidirectional converter between the two real POWL representations.

``autofde_lab.fabric.powl`` parses/emits POWL2 Turtle into/from
:class:`~autofde_lab.fabric.powl.PowlModel` -- a flat, IRI-addressed,
node-id graph (``ChildBinding`` slots + ``ActivityLeaf`` + ``precedes``
edges). ``autofde_lab.powl.algebra`` is a *separate* real model,
:data:`~autofde_lab.powl.algebra.PowlNode`, consumed by
``autofde_lab.powl.executor``'s traversal (``enabled()``/``fire()``/
``is_final()``): index-addressed children with an explicit transitive-
reduction order relation.

Confirmed this session (``ocel/powl_replay.py``'s own module docstring and
``.claude/rules/ecosystem-boundary.md``) that no converter between the two
existed. This module is that converter, scoped exactly to the shape
``fabric/powl.py`` actually produces: a **flat total order** of
``powl2:ActivityLeaf`` steps (what ``project_plan_to_powl`` emits and
``parse_powl_turtle`` accepts -- there is no ``powl2:ChoiceGraph`` or nested
``powl2:PartialOrder`` in that vocabulary at all, so this module does not
attempt to invent a mapping for constructs that do not exist on the Turtle
side).

Two directions:

- :func:`powl_model_to_node` -- ``PowlModel`` (Turtle-parsed) ->
  :data:`~autofde_lab.powl.algebra.PowlNode` (executor-consumable).
- :func:`powl_node_to_model` -- the reverse, producing a ``PowlModel`` that
  :func:`model_to_turtle` (added here -- no ``PowlModel`` -> Turtle
  serializer existed anywhere in this repo before this module) can render
  back into ``parse_powl_turtle``-acceptable text.

Scope refusals, named rather than silent
-----------------------------------------
- A ``PowlModel`` with zero ``ChildBinding`` children is refused
  (``EMPTY_MODEL``): the algebra has no "empty" node.
- A :data:`~autofde_lab.powl.algebra.PowlNode` that is not a flat
  :class:`~autofde_lab.powl.algebra.PartialOrder` of
  :class:`~autofde_lab.powl.algebra.Atom` children (or a single bare
  ``Atom``) is refused (``UNSUPPORTED_NODE_SHAPE``): POWL2 Turtle as parsed
  by this repo's decoder has no vocabulary for ``ChoiceGraph``, ``Start``,
  ``End``, ``Silent``, or nested composites, so there is nothing honest to
  emit for one.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from autofde_lab.fabric.powl import (
    MFWP,
    POWL2,
    PROV,
    XSD,
    ActivityLeaf,
    ChildBinding,
    ParameterBinding,
    PowlModel,
)
from autofde_lab.powl.algebra import Atom, NodeId, OrderEdge, PartialOrder, PowlNode

__all__ = [
    "BridgeError",
    "powl_model_to_node",
    "powl_node_to_model",
    "model_to_turtle",
]


class BridgeError(ValueError):
    """Raised when a model on either side is outside this bridge's named scope."""


# ---------------------------------------------------------------------------
# PowlModel (Turtle-parsed) -> PowlNode (executor-consumable)
# ---------------------------------------------------------------------------


def powl_model_to_node(model: PowlModel) -> PowlNode:
    """Convert a parsed-Turtle :class:`PowlModel` into a :class:`PowlNode` tree.

    ``model.ordered_children()`` gives the ``ChildBinding`` slots sorted by
    ``child_index`` (contiguous from 0 -- already enforced by
    :func:`autofde_lab.fabric.powl.validate_powl`, which
    :func:`~autofde_lab.fabric.powl.parse_powl_turtle` always runs before
    returning). Each slot's ``child_index`` becomes that atom's 0-based
    position in the resulting :class:`~autofde_lab.powl.algebra.PartialOrder`
    -- the same arena convention ``algebra.py``'s own docstring describes.
    ``powl2:precedes`` edges between binding-slot IRIs become
    :class:`~autofde_lab.powl.algebra.OrderEdge` between those positions.

    A single-step model reduces to a bare :class:`Atom` (not a one-child
    ``PartialOrder`` -- ``PartialOrder`` itself refuses ``n < 2``, per
    ``INVALID_PARTIAL_ORDER_ARITY``). :func:`powl_node_to_model` accepts a
    bare ``Atom`` back symmetrically, so the round trip is stable at n=1.
    """
    ordered = model.ordered_children()
    if not ordered:
        raise BridgeError("EMPTY_MODEL: powl2:Model has zero powl2:ChildBinding children")

    index_of_child_iri: Dict[str, int] = {
        child.iri: position for position, child in enumerate(ordered)
    }

    atoms: List[Atom] = []
    for child in ordered:
        leaf = model.leaves.get(child.child_model)
        if leaf is None:
            # Unreachable given parse_powl_turtle's own validate_powl call,
            # but this module never trusts a caller-constructed PowlModel to
            # have gone through that gate.
            raise BridgeError(
                f"DANGLING_CHILD_MODEL: <{child.iri}> powl2:childModel "
                f"<{child.child_model}> has no matching powl2:ActivityLeaf"
            )
        bindings: Dict[str, str] = {}
        for binding_iri in leaf.binds_parameter:
            binding = model.bindings.get(binding_iri)
            if binding is None:
                raise BridgeError(
                    f"DANGLING_BINDING: <{leaf.iri}> mfwp:bindsParameter "
                    f"<{binding_iri}> has no matching mfwp:ParameterBinding"
                )
            bindings[str(binding.binding_index)] = binding.bound_object
        atoms.append(
            Atom(label=leaf.activity_label, action=leaf.implements_action, bindings=bindings)
        )

    order_edges: set[OrderEdge] = set()
    for child in ordered:
        src = index_of_child_iri[child.iri]
        for target_iri in child.precedes:
            if target_iri not in index_of_child_iri:
                raise BridgeError(
                    f"DANGLING_PRECEDES: <{child.iri}> powl2:precedes "
                    f"<{target_iri}> is not one of this model's child bindings"
                )
            order_edges.add(OrderEdge(NodeId(src), NodeId(index_of_child_iri[target_iri])))

    if len(atoms) == 1:
        return atoms[0]

    return PartialOrder(tuple(atoms), frozenset(order_edges))


# ---------------------------------------------------------------------------
# PowlNode (executor-consumable) -> PowlModel (Turtle-parseable)
# ---------------------------------------------------------------------------


def powl_node_to_model(
    node: PowlNode,
    base_iri: str = "urn:autofde-lab:powl-bridge",
    planner_run: str = "run-turtle-bridge",
) -> PowlModel:
    """Convert an executor-consumable :class:`PowlNode` back into a ``PowlModel``.

    Accepts exactly the two shapes :func:`powl_model_to_node` can produce: a
    bare :class:`Atom` (n=1), or a :class:`PartialOrder` whose children are
    all :class:`Atom` (n>=2, per ``PartialOrder``'s own arity refusal).
    Anything else -- a :class:`~autofde_lab.powl.algebra.ChoiceGraph`, a
    :class:`~autofde_lab.powl.algebra.Start`/:class:`End`/
    :class:`~autofde_lab.powl.algebra.Silent` leaf, or a nested composite --
    is refused by name (``UNSUPPORTED_NODE_SHAPE``): POWL2 Turtle as this
    repo's decoder accepts has no vocabulary for any of them.

    The order relation emitted is the model's transitive closure, so it
    round-trips through :func:`parse_powl_turtle`'s acyclicity check
    correctly even though it may be denser than the minimal reduction
    ``fabric/powl.py`` itself emits for a pure total order.
    """
    if isinstance(node, Atom):
        atoms: Tuple[Atom, ...] = (node,)
        precedes_by_index: Dict[int, Tuple[int, ...]] = {0: ()}
    elif isinstance(node, PartialOrder) and all(isinstance(c, Atom) for c in node.children):
        atoms = node.children  # type: ignore[assignment]
        by_src: Dict[int, List[int]] = {i: [] for i in range(len(atoms))}
        for edge in node.closure:
            by_src[int(edge.src)].append(int(edge.dst))
        precedes_by_index = {i: tuple(sorted(dsts)) for i, dsts in by_src.items()}
    else:
        raise BridgeError(
            f"UNSUPPORTED_NODE_SHAPE: {type(node).__name__} has no POWL2 Turtle "
            "vocabulary in this repo's decoder/emitter (fabric/powl.py models "
            "only a flat total order of powl2:ActivityLeaf steps)"
        )

    plan_iri = f"{base_iri}/plan"
    domain_iri = f"{base_iri}/domain"

    children: Dict[str, ChildBinding] = {}
    leaves: Dict[str, ActivityLeaf] = {}
    bindings: Dict[str, ParameterBinding] = {}
    has_child: List[str] = []

    for index, atom in enumerate(atoms):
        step_iri = f"{plan_iri}/step/{index}"
        slot_iri = f"{plan_iri}/binding-slot/{index}"
        implements_action = (
            atom.action if isinstance(atom.action, str) and atom.action else f"{base_iri}/{atom.label}"
        )

        binds_parameter: List[str] = []
        for position, key in enumerate(sorted(atom.bindings, key=_binding_sort_key)):
            binding_iri = f"{step_iri}/binding/{position}"
            bound_object = atom.bindings[key]
            bindings[binding_iri] = ParameterBinding(
                iri=binding_iri,
                binding_index=_binding_index(key, position),
                parameter=f"{base_iri}/{atom.label}-p{position}",
                bound_object=str(bound_object),
            )
            binds_parameter.append(binding_iri)

        leaves[step_iri] = ActivityLeaf(
            iri=step_iri,
            activity_label=atom.label,
            implements_action=implements_action,
            plan_ordinal=index,
            binds_parameter=tuple(binds_parameter),
        )

        precedes_iris = tuple(
            f"{plan_iri}/binding-slot/{target}" for target in precedes_by_index.get(index, ())
        )
        children[slot_iri] = ChildBinding(
            iri=slot_iri,
            child_index=index,
            child_model=step_iri,
            precedes=precedes_iris,
        )
        has_child.append(slot_iri)

    return PowlModel(
        iri=plan_iri,
        types=(POWL2 + "Model", POWL2 + "PartialOrder"),
        derived_from=(base_iri,),
        was_derived_from=(domain_iri,),
        has_child=tuple(has_child),
        projection="total-order",
        planner_run=planner_run,
        domain_digest=None,
        problem_digest=None,
        activity_count=len(atoms),
        children=children,
        leaves=leaves,
        bindings=bindings,
    )


def _binding_index(key: str, fallback_position: int) -> int:
    """Recover an int binding index from an ``Atom.bindings`` key.

    :func:`powl_model_to_node` always writes ``str(binding_index)`` keys, so
    this round-trips exactly for any model this bridge produced. A caller
    handing this function a hand-built ``Atom`` with non-numeric keys still
    gets a deterministic index (sorted position), rather than a crash.
    """
    try:
        return int(key)
    except ValueError:
        return fallback_position


def _binding_sort_key(key: str) -> Tuple[int, str]:
    try:
        return (0, f"{int(key):020d}")
    except ValueError:
        return (1, key)


# ---------------------------------------------------------------------------
# PowlModel -> Turtle. No such serializer existed anywhere in this repo
# before this module -- fabric/powl.py's writer goes plan_lines -> Turtle
# directly and never materializes a PowlModel on the way. This is the
# missing leg needed to close the round-trip loop for a test.
# ---------------------------------------------------------------------------


def model_to_turtle(model: PowlModel) -> str:
    """Render ``model`` as POWL2 Turtle, in exactly the subset
    :func:`~autofde_lab.fabric.powl.parse_powl_turtle` accepts.

    Structurally mirrors ``project_plan_to_powl``'s emission shape (same
    predicates, same literal datatypes) but is driven from a real
    :class:`PowlModel` object rather than from raw plan lines, so it can
    round-trip a model built by :func:`powl_node_to_model`.
    """
    out: List[str] = [
        f"@prefix powl2: <{POWL2}> .",
        f"@prefix mfwp: <{MFWP}> .",
        f"@prefix prov: <{PROV}> .",
        f"@prefix xsd: <{XSD}> .",
        "",
    ]

    root = [f"<{model.iri}> a powl2:Model, powl2:PartialOrder ;"]
    for iri in model.derived_from:
        root.append(f"    powl2:derivedFrom <{iri}> ;")
    for iri in model.was_derived_from:
        root.append(f"    prov:wasDerivedFrom <{iri}> ;")
    if model.domain_digest is not None:
        root.append(f'    mfwp:domainDigest "{model.domain_digest}" ;')
    if model.problem_digest is not None:
        root.append(f'    mfwp:problemDigest "{model.problem_digest}" ;')
    if model.planner_run is not None:
        root.append(f'    mfwp:plannerRun "{model.planner_run}" ;')
    if model.projection is not None:
        root.append(f'    mfwp:projection "{model.projection}" ;')
    for iri in model.has_child:
        root.append(f"    powl2:hasChild <{iri}> ;")
    activity_count = model.activity_count if model.activity_count is not None else len(model.children)
    root.append(f'    mfwp:activityCount "{activity_count}"^^xsd:integer .')
    out.extend(root)
    out.append("")

    for slot in model.ordered_children():
        out.extend(
            [
                f"<{slot.iri}> a powl2:ChildBinding ;",
                f'    powl2:childIndex "{slot.child_index}"^^xsd:integer ;',
                f"    powl2:childModel <{slot.child_model}> .",
                "",
            ]
        )
        leaf = model.leaves[slot.child_model]
        leaf_lines = [
            f"<{leaf.iri}> a powl2:Leaf, powl2:ActivityLeaf ;",
            f'    powl2:activityLabel "{leaf.activity_label}" ;',
            f"    mfwp:implementsAction <{leaf.implements_action}> ;",
        ]
        for binding_iri in leaf.binds_parameter:
            leaf_lines.append(f"    mfwp:bindsParameter <{binding_iri}> ;")
        leaf_lines.append(f'    mfwp:planOrdinal "{leaf.plan_ordinal}"^^xsd:integer .')
        out.extend(leaf_lines)
        out.append("")

        for binding_iri in leaf.binds_parameter:
            binding = model.bindings[binding_iri]
            out.extend(
                [
                    f"<{binding.iri}> a mfwp:ParameterBinding ;",
                    f'    mfwp:bindingIndex "{binding.binding_index}"^^xsd:integer ;',
                    f"    mfwp:parameter <{binding.parameter}> ;",
                    f"    mfwp:boundObject <{binding.bound_object}> .",
                    "",
                ]
            )

    for slot in model.ordered_children():
        for target in slot.precedes:
            out.append(f"<{slot.iri}> powl2:precedes <{target}> .")
    if any(slot.precedes for slot in model.ordered_children()):
        out.append("")

    return "\n".join(out)
