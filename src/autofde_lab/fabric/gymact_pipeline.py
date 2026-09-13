# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""SRE-diagnosis-specific POWL pipeline construction, wired against the
generalized runner in :mod:`gymact.powl` (Phase 2 of the POWL v2 -> gymact
migration; see ``docs/2026-08-10-powl-v2-runner-definition-of-done.md`` and
the plan at ``~/.claude/plans/launch-5-lumen-explore-compressed-sutherland.md``).

This module owns exactly what is SRE-diagnosis-specific about the pipeline:
the 15 ``GYMACT_*_LABEL`` constants, the three label frozensets, and the
functions that build the concrete `PowlNode` tree
(`build_pipeline_turtle`/`build_pipeline_powl_node`) for this one caller
(:mod:`autofde_lab.reasoning.gymact_diagnosis_driver`). The mechanism-level
marking-advance/fire/OCEL-record driver lives in ``gymact.powl.runner`` and
is imported, not reimplemented, here.

Coexistence, not replacement
-----------------------------
``src/autofde_lab/powl/runner.py`` (the ORIGINAL, local implementation) is
left completely untouched by this migration step. Six test files
(`tests/powl/test_runner_pipeline_chicago.py`,
`test_conformance_chicago.py`, `test_turtle_bridge_runner_integration_chicago.py`,
`test_runner_bounds_concurrent_chicago.py`,
`test_runner_ocel_concurrency_shape_chicago.py`,
`test_conformance_property_based_chicago.py`) import its old API directly
and are part of the currently-`ALIVE`, 56/56-passing suite this repo's own
law (``CLAUDE.md``) forbids regressing. This module is a new, additive
production path -- only :mod:`autofde_lab.reasoning.gymact_diagnosis_driver`
is repointed to it. Retiring the old ``powl/runner.py`` module (and its
six dependent test files) is explicitly out of scope here; see the plan's
"Phase N -- shim removal" for when/how that happens, once every consumer
(not just this one driver) has migrated.

OCEL adapter, not a second bookkeeping path
---------------------------------------------
``gymact.powl.runner.run_pipeline`` returns a raw OCEL2-JSON ``dict``
(gymact must not import ``autofde_lab.ocel.log.OcelLog``), but this driver's
downstream code (``gymact_diagnosis_driver.py``) threads a real ``OcelLog``
object through ``append_tool_call_event`` and a typed dataclass field.
``_ocel_dict_to_log`` below converts one into the other using ``OcelLog``'s
own real constructors (``OcelLog.new``, ``OcelObject``, ``OcelEvent``,
``EventObjectLink``, ``OcelAttributeValue.from_json``) -- never a hand-rolled
guess at the schema -- so there is exactly one real ``OcelLog`` construction
path, not two independently-maintained ones (``no-dual-bookkeeping.md``).
"""

from __future__ import annotations

from typing import Any

from gymact.powl.algebra import (
    Atom,
    ChoiceGraph,
    ChoiceGraphEdge,
    NodeId,
    OrderEdge,
    PartialOrder,
    PowlNode,
)
from gymact.powl.spec import PowlPipelineSpec
from gymact.powl.turtle_bridge import BridgeError, powl_model_to_node
from gymact.powl._turtle import PowlModel as GymactPowlModel

from autofde_lab.fabric.powl import PowlModel as AutofdeLabPowlModel
from autofde_lab.fabric.powl import parse_powl_turtle, project_plan_to_powl
from autofde_lab.ocel.log import OcelLog
from autofde_lab.ocel.model import (
    EventObjectLink,
    OcelAttribute,
    OcelAttributeValue,
    OcelEvent,
    OcelObject,
    parse_ns,
)

__all__ = [
    "PIPELINE_LINEAR_STEPS",
    "CASE_RETRIEVE_LABEL",
    "CASE_HIT_LABEL",
    "CASE_MISS_LABEL",
    "CASE_RETAIN_LABEL",
    "RECORD_LABEL",
    "GYMACT_SCAN_ANOMALIES_LABEL",
    "GYMACT_RECHECK_SCAN_LABEL",
    "GYMACT_CHECK_STATUS_LABEL",
    "GYMACT_CHECK_NAMESPACE_LABEL",
    "GYMACT_CHECK_DEPLOYMENTS_LABEL",
    "GYMACT_CHECK_PODS_LABEL",
    "GYMACT_CHECK_SERVICES_LABEL",
    "GYMACT_SUBMIT_DIAGNOSIS_LABEL",
    "GYMACT_ACTUATE_REMEDIATE_LABEL",
    "GYMACT_SUBMIT_MITIGATION_LABEL",
    "GYMACT_VERIFY_LABEL",
    "GYMACT_WAIT_FOR_DEPLOY_LABEL",
    "GYMACT_RECHECK_DEPLOYMENTS_LABEL",
    "GYMACT_RECHECK_PODS_LABEL",
    "GYMACT_RECHECK_SERVICES_LABEL",
    "ALLOWED_ACTION_BINDING_LABELS",
    "ALLOWED_ACTUATION_BINDING_LABELS",
    "ALLOWED_ACTUATION_ORACLE_LABELS",
    "PIPELINE_SPEC",
    "build_pipeline_turtle",
    "build_pipeline_powl_node",
]

#: Reproduced verbatim from ``autofde_lab.powl.runner`` -- same string
#: values, so `PIPELINE_SPEC` below admits exactly the same labels the old
#: pipeline did. Zero behavior change in *which* labels are allowed.
PIPELINE_LINEAR_STEPS: tuple[str, ...] = (
    "(scan cluster)",
    "(phi_encode anomaly)",
    "(dispatch_solve problem)",
    "(solve problem)",
)

CASE_RETRIEVE_LABEL = "cbr_retrieve"
CASE_HIT_LABEL = "case_hit"
CASE_MISS_LABEL = "case_miss"
CASE_RETAIN_LABEL = "cbr_retain"
RECORD_LABEL = "ocel_record"
GYMACT_SCAN_ANOMALIES_LABEL = "gymact_scan_anomalies"
GYMACT_RECHECK_SCAN_LABEL = "gymact_recheck_scan"
GYMACT_CHECK_STATUS_LABEL = "gymact_check_status"
GYMACT_CHECK_NAMESPACE_LABEL = "gymact_check_namespace"
GYMACT_CHECK_DEPLOYMENTS_LABEL = "gymact_check_deployments"
GYMACT_CHECK_PODS_LABEL = "gymact_check_pods"
GYMACT_CHECK_SERVICES_LABEL = "gymact_check_services"
GYMACT_SUBMIT_DIAGNOSIS_LABEL = "gymact_submit_diagnosis"
GYMACT_ACTUATE_REMEDIATE_LABEL = "gymact_actuate_remediate"
GYMACT_SUBMIT_MITIGATION_LABEL = "gymact_submit_mitigation"
GYMACT_VERIFY_LABEL = "gymact_verify"
GYMACT_WAIT_FOR_DEPLOY_LABEL = "gymact_wait_for_deploy"
GYMACT_RECHECK_DEPLOYMENTS_LABEL = "gymact_recheck_deployments"
GYMACT_RECHECK_PODS_LABEL = "gymact_recheck_pods"
GYMACT_RECHECK_SERVICES_LABEL = "gymact_recheck_services"

ALLOWED_ACTION_BINDING_LABELS: frozenset[str] = frozenset(
    {
        "scan",
        "phi_encode",
        "dispatch_solve",
        "solve",
        CASE_RETRIEVE_LABEL,
        CASE_HIT_LABEL,
        CASE_MISS_LABEL,
        CASE_RETAIN_LABEL,
        RECORD_LABEL,
        GYMACT_SCAN_ANOMALIES_LABEL,
        GYMACT_RECHECK_SCAN_LABEL,
    }
)

ALLOWED_ACTUATION_BINDING_LABELS: frozenset[str] = frozenset(
    {
        GYMACT_CHECK_STATUS_LABEL,
        GYMACT_CHECK_NAMESPACE_LABEL,
        GYMACT_CHECK_DEPLOYMENTS_LABEL,
        GYMACT_CHECK_PODS_LABEL,
        GYMACT_CHECK_SERVICES_LABEL,
        GYMACT_SUBMIT_DIAGNOSIS_LABEL,
        GYMACT_ACTUATE_REMEDIATE_LABEL,
        GYMACT_SUBMIT_MITIGATION_LABEL,
        GYMACT_RECHECK_DEPLOYMENTS_LABEL,
        GYMACT_RECHECK_PODS_LABEL,
        GYMACT_RECHECK_SERVICES_LABEL,
    }
)

ALLOWED_ACTUATION_ORACLE_LABELS: frozenset[str] = frozenset(
    {GYMACT_VERIFY_LABEL, GYMACT_WAIT_FOR_DEPLOY_LABEL}
)

#: The generalized contract `gymact.powl.runner.run_pipeline` requires as a
#: mandatory keyword-only `spec` argument -- constructed once, here, from
#: the exact label sets above. Any of gymact's ~25 other gyms would supply
#: their own `PowlPipelineSpec`; this is this one caller's.
PIPELINE_SPEC = PowlPipelineSpec(
    readonly_labels=ALLOWED_ACTION_BINDING_LABELS,
    actuation_labels=ALLOWED_ACTUATION_BINDING_LABELS,
    oracle_labels=ALLOWED_ACTUATION_ORACLE_LABELS,
    default_session_id="powl-runner-pipeline",
    recorder_server_name="powl-runner",
)


def build_pipeline_turtle(base_iri: str = "urn:autofde-lab:powl-runner") -> str:
    """Real POWL2 Turtle text for the linear scan/phi/dispatch/solve prefix.

    Unchanged from the original: `project_plan_to_powl` stays in
    `autofde_lab.fabric.powl` (CONSTRUCT is this repo's job, not gymact's,
    per gymact's own constitution)."""
    return project_plan_to_powl(list(PIPELINE_LINEAR_STEPS), base_iri=base_iri)


def _concurrent_read_block(labels: "list[str]") -> PartialOrder:
    """N unordered `Atom` children, no order edges among them -- ported
    verbatim from `autofde_lab.powl.runner._concurrent_read_block`, now
    built from `gymact.powl.algebra` types instead of the local ones (same
    shapes, different import source)."""
    return PartialOrder(children=tuple(Atom(label=l) for l in labels), order=frozenset())


def _sequence(nodes: tuple[PowlNode, ...], *, start_index: int) -> frozenset[OrderEdge]:
    """Ported verbatim from `autofde_lab.powl.runner._sequence`."""
    return frozenset(
        OrderEdge(NodeId(start_index + i), NodeId(start_index + i + 1))
        for i in range(len(nodes) - 1)
    )


def _to_gymact_powl_model(model: AutofdeLabPowlModel) -> GymactPowlModel:
    """Convert autofde-lab's real, rdflib-backed `PowlModel` (the only place
    Turtle text is actually parsed -- `gymact.powl._turtle` forked only the
    dataclass shapes, never the parser) into gymact's content-forked,
    field-for-field-identical `PowlModel`, so `gymact.powl.turtle_bridge
    .powl_model_to_node` (which type-checks against the gymact class) can
    consume it. A real field-by-field copy, not a cast -- the two classes
    are structurally identical by construction (see `_turtle.py`'s own
    header) but are distinct types, so `isinstance`/type-checked consumers
    on either side must receive their own class's instances."""
    from gymact.powl._turtle import ActivityLeaf as GymactActivityLeaf
    from gymact.powl._turtle import ChildBinding as GymactChildBinding
    from gymact.powl._turtle import ParameterBinding as GymactParameterBinding

    return GymactPowlModel(
        iri=model.iri,
        types=model.types,
        derived_from=model.derived_from,
        was_derived_from=model.was_derived_from,
        has_child=model.has_child,
        projection=model.projection,
        planner_run=model.planner_run,
        domain_digest=model.domain_digest,
        problem_digest=model.problem_digest,
        activity_count=model.activity_count,
        children={
            iri: GymactChildBinding(
                iri=cb.iri, child_index=cb.child_index, child_model=cb.child_model, precedes=cb.precedes
            )
            for iri, cb in model.children.items()
        },
        leaves={
            iri: GymactActivityLeaf(
                iri=leaf.iri,
                activity_label=leaf.activity_label,
                implements_action=leaf.implements_action,
                plan_ordinal=leaf.plan_ordinal,
                binds_parameter=leaf.binds_parameter,
            )
            for iri, leaf in model.leaves.items()
        },
        bindings={
            iri: GymactParameterBinding(
                iri=pb.iri, binding_index=pb.binding_index, parameter=pb.parameter, bound_object=pb.bound_object
            )
            for iri, pb in model.bindings.items()
        },
    )


def build_pipeline_powl_node(turtle_text: str | None = None) -> PowlNode:
    """The full pipeline as one real, `gymact.powl.executor`-consumable
    `PowlNode` tree -- ported from `autofde_lab.powl.runner
    .build_pipeline_powl_node`, rebuilt over `gymact.powl.algebra`/
    `gymact.powl.turtle_bridge` types. Same tree shape, same labels."""
    text = turtle_text if turtle_text is not None else build_pipeline_turtle()
    model = _to_gymact_powl_model(parse_powl_turtle(text))
    linear = powl_model_to_node(model)
    if not isinstance(linear, PartialOrder) or not all(
        isinstance(c, Atom) for c in linear.children
    ):
        raise BridgeError(
            f"expected a flat PartialOrder of Atom leaves from turtle_bridge, "
            f"got {type(linear).__name__}"
        )
    linear_atoms: tuple[Atom, ...] = linear.children  # type: ignore[assignment]
    n_linear = len(linear_atoms)

    choice_children: tuple[PowlNode, ...] = (
        Atom(label=CASE_RETRIEVE_LABEL),
        Atom(label=CASE_HIT_LABEL),
        Atom(label=CASE_MISS_LABEL),
        Atom(label=CASE_RETAIN_LABEL),
    )
    choice_edges = frozenset(
        {
            ChoiceGraphEdge(NodeId(0), NodeId(1)),
            ChoiceGraphEdge(NodeId(0), NodeId(2)),
            ChoiceGraphEdge(NodeId(1), NodeId(3)),
            ChoiceGraphEdge(NodeId(2), NodeId(3)),
        }
    )
    choice_graph = ChoiceGraph(children=choice_children, edges=choice_edges, start=0, end=3)

    record_atom = Atom(label=RECORD_LABEL)

    observe_block = _concurrent_read_block(
        [
            GYMACT_CHECK_STATUS_LABEL,
            GYMACT_CHECK_NAMESPACE_LABEL,
            GYMACT_CHECK_DEPLOYMENTS_LABEL,
            GYMACT_CHECK_PODS_LABEL,
            GYMACT_CHECK_SERVICES_LABEL,
        ]
    )
    remediate_block = _concurrent_read_block(
        [
            GYMACT_RECHECK_DEPLOYMENTS_LABEL,
            GYMACT_RECHECK_PODS_LABEL,
            GYMACT_RECHECK_SERVICES_LABEL,
        ]
    )
    actuation_entries: tuple[PowlNode, ...] = (
        Atom(label=GYMACT_WAIT_FOR_DEPLOY_LABEL),
        observe_block,
        Atom(label=GYMACT_SCAN_ANOMALIES_LABEL),
        Atom(label=GYMACT_SUBMIT_DIAGNOSIS_LABEL),
        remediate_block,
        Atom(label=GYMACT_RECHECK_SCAN_LABEL),
        Atom(label=GYMACT_SUBMIT_MITIGATION_LABEL),
        Atom(label=GYMACT_VERIFY_LABEL),
    )

    tail: tuple[PowlNode, ...] = (choice_graph, record_atom) + actuation_entries
    top_children: tuple[PowlNode, ...] = linear_atoms + tail

    order_edges: set[OrderEdge] = {OrderEdge(edge.src, edge.dst) for edge in linear.order}
    order_edges.add(OrderEdge(NodeId(n_linear - 1), NodeId(n_linear)))
    order_edges |= _sequence(tail, start_index=n_linear)

    return PartialOrder(children=top_children, order=frozenset(order_edges))


def ocel_dict_to_log(raw: dict[str, Any]) -> OcelLog:
    """Convert `gymact.powl.runner.run_pipeline`'s raw OCEL2-JSON `dict`
    return value into a real `autofde_lab.ocel.log.OcelLog`, using `OcelLog`'s
    own construction primitives -- never a hand-rolled reconstruction. See
    this module's docstring ("OCEL adapter, not a second bookkeeping path")."""

    def _attrs(raw_attrs: "list[dict[str, Any]]") -> tuple[OcelAttribute, ...]:
        return tuple(
            OcelAttribute(key=a["name"], value=OcelAttributeValue.from_json(a["value"]))
            for a in raw_attrs
        )

    objects = tuple(
        OcelObject(
            id=o["id"],
            object_type=o["type"],
            attributes=_attrs(o.get("attributes", [])),
        )
        for o in raw.get("objects", [])
    )

    events: list[OcelEvent] = []
    links: list[EventObjectLink] = []
    for e in raw.get("events", []):
        timestamp_ns = parse_ns(e["time"]) if e.get("time") else 0
        events.append(
            OcelEvent(
                id=e["id"],
                activity=e["type"],
                timestamp_ns=timestamp_ns,
                attributes=_attrs(e.get("attributes", [])),
            )
        )
        for rel in e.get("relationships", []):
            links.append(
                EventObjectLink(
                    event_id=e["id"],
                    object_id=rel["objectId"],
                    qualifier=rel.get("qualifier"),
                )
            )

    return OcelLog.new(
        objects=objects,
        events=tuple(events),
        event_object_links=tuple(links),
    )
