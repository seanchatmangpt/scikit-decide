# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""The admitted AutoFDE **work-execution** graph.

Two different partial orders exist in this package and conflating them is the
defect this module exists to prevent.

The **work-execution graph** (this module) has admitted phases and work items
as nodes; an edge means *must finish before*. It is projected to POWL 2.0 via
:func:`work_partial_order`.

The **provisioning graph** (Terraform, see :mod:`autofde_lab.autofde.github_projection`)
has GitHub API objects as nodes; an edge means *needs this object's id to
exist*. ``github_issue`` references ``github_repository_milestone.epics[k].number``
because the API needs the milestone number in order to create the issue.

The decisive argument for keeping them apart: take two issues where A
genuinely blocks B, and two issues that are fully independent. In both cases
they sit in the same milestone and carry the same labels — and Terraform emits
the *identical* resource graph, with no edge either way. The provisioning graph
is invariant under changes to work order, so it carries zero bits about work
order and can never falsify a work-order projection. GitHub milestones, labels
and issues have no native blocks/blocked-by edge, so work precedence must be
carried explicitly in generated issue *body content* — see
:mod:`autofde_lab.autofde.github_projection`.

This module computes structure. It does not actuate, admit, broker, or issue
receipts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from autofde_lab.autofde.refusals import AutoFdeError, AutoFdeRefusal
from autofde_lab.powl import (
    Atom,
    NodeId,
    OrderEdge,
    PartialOrder,
    transitive_closure,
    transitive_reduction,
)

__all__ = [
    "Phase",
    "WorkItem",
    "PhaseGraph",
    "work_partial_order",
    "reduce_order",
    "AUTOFDE_PHASE_GRAPH",
]


# ── nodes ───────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Phase:
    """A major phase of work. Projects to a GitHub *milestone*."""

    phase_id: str
    title: str
    description: str
    due_date: str = ""
    #: phase ids that must finish before this phase may start
    after: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class WorkItem:
    """A unit of work. Projects to a GitHub *issue*.

    ``requires`` is the only carrier of work precedence. ``occurrence``
    distinguishes replanned identities of the same intent: a replanned item is
    a *new* node with a fresh occurrence, never a mutation of the old one.
    """

    node_id: str
    title: str
    phase: str
    kind: str
    body: str
    #: node ids of work items that must finish before this one may start
    requires: tuple[str, ...] = ()
    status: str = "active"
    #: node id this item supersedes (lineage), if any
    supersedes: str = ""
    occurrence: int = 1


# ── graph ───────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class PhaseGraph:
    """An *admitted* work-execution graph. Validated at construction."""

    phases: tuple[Phase, ...]
    items: tuple[WorkItem, ...]
    _phase_closure: frozenset[tuple[str, str]] = field(
        init=False, compare=False, repr=False, hash=False, default=frozenset()
    )

    def __post_init__(self) -> None:
        if not self.phases or not self.items:
            raise AutoFdeError(
                AutoFdeRefusal.EMPTY_GRAPH,
                f"{len(self.phases)} phases, {len(self.items)} items",
            )
        seen: set[str] = set()
        for p in self.phases:
            if p.phase_id in seen:
                raise AutoFdeError(AutoFdeRefusal.DUPLICATE_NODE_ID, p.phase_id)
            seen.add(p.phase_id)
        for p in self.phases:
            for a in p.after:
                if a not in seen:
                    raise AutoFdeError(AutoFdeRefusal.UNKNOWN_PHASE, a)

        item_ids: set[str] = set()
        for it in self.items:
            if it.node_id in item_ids:
                raise AutoFdeError(AutoFdeRefusal.DUPLICATE_NODE_ID, it.node_id)
            item_ids.add(it.node_id)
        for it in self.items:
            if it.phase not in seen:
                raise AutoFdeError(
                    AutoFdeRefusal.UNKNOWN_PHASE, f"{it.node_id} -> {it.phase}"
                )
            for r in it.requires:
                if r not in item_ids:
                    raise AutoFdeError(
                        AutoFdeRefusal.UNKNOWN_WORK_ITEM, f"{it.node_id} requires {r}"
                    )
            if it.supersedes and it.supersedes not in item_ids:
                raise AutoFdeError(
                    AutoFdeRefusal.UNKNOWN_WORK_ITEM,
                    f"{it.node_id} supersedes {it.supersedes}",
                )

        object.__setattr__(self, "_phase_closure", self._compute_phase_closure())
        self._check_phase_consistency()
        # raises CYCLIC_PARTIAL_ORDER -> re-raised as CYCLIC_WORK_GRAPH
        work_partial_order(self)

    # -- phase order -------------------------------------------------------

    def _compute_phase_closure(self) -> frozenset[tuple[str, str]]:
        ids = [p.phase_id for p in self.phases]
        idx = {pid: i for i, pid in enumerate(ids)}
        edges = frozenset(
            OrderEdge(NodeId(idx[a]), NodeId(idx[p.phase_id]))
            for p in self.phases
            for a in p.after
        )
        try:
            closure = transitive_closure(edges, len(ids))
        except Exception as exc:  # pragma: no cover - defensive
            raise AutoFdeError(AutoFdeRefusal.CYCLIC_WORK_GRAPH, str(exc)) from exc
        return frozenset((ids[e.src], ids[e.dst]) for e in closure)

    @property
    def phase_closure(self) -> frozenset[tuple[str, str]]:
        """Transitive closure of the phase order, as ``(before, after)`` pairs."""
        return self._phase_closure

    def phases_are_concurrent(self, a: str, b: str) -> bool:
        """True when neither phase precedes the other."""
        return (a, b) not in self._phase_closure and (b, a) not in self._phase_closure

    def _check_phase_consistency(self) -> None:
        """A work edge may never run against, or across, the phase order."""
        by_id = {it.node_id: it for it in self.items}
        for it in self.items:
            for r in it.requires:
                src, dst = by_id[r].phase, it.phase
                if src == dst:
                    continue
                if (src, dst) not in self._phase_closure:
                    raise AutoFdeError(
                        AutoFdeRefusal.PHASE_ORDER_VIOLATION,
                        f"{r} ({src}) -> {it.node_id} ({dst}) is not permitted by "
                        f"the phase order",
                    )

    # -- accessors ---------------------------------------------------------

    @property
    def item_map(self) -> Mapping[str, WorkItem]:
        return {it.node_id: it for it in self.items}

    @property
    def phase_map(self) -> Mapping[str, Phase]:
        return {p.phase_id: p for p in self.phases}

    def phase_rank(self, phase_id: str) -> int:
        """Number of phases strictly preceding ``phase_id`` (a stable sort key)."""
        return sum(1 for (a, b) in self._phase_closure if b == phase_id)

    def sorted_item_ids(self) -> tuple[str, ...]:
        """Deterministic node ordering: node id, lexicographic.

        Deliberately *not* keyed on phase rank. Phase precedence is not
        recoverable from a rendered ``.auto.tfvars`` (the ``milestones`` schema
        in ``main.tf`` has no ``after`` field), so keying the canonical node
        order on it would make the round trip depend on information the
        projection does not carry.
        """
        return tuple(sorted(it.node_id for it in self.items))

    def sorted_phase_ids(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                (p.phase_id for p in self.phases), key=lambda p: (self.phase_rank(p), p)
            )
        )


# ── POWL projection ─────────────────────────────────────────────────────────


def work_partial_order(graph: PhaseGraph) -> PartialOrder:
    """Project the work-execution graph onto a POWL 2.0 :class:`PartialOrder`.

    Children are ``Atom(node_id)`` in :meth:`PhaseGraph.sorted_item_ids` order,
    so two graphs with the same items and the same precedence compare equal
    regardless of declaration order. ``PartialOrder`` normalizes ``order`` to
    the transitive reduction itself.
    """
    ids = graph.sorted_item_ids()
    idx = {nid: i for i, nid in enumerate(ids)}
    by_id = graph.item_map
    edges = frozenset(
        OrderEdge(NodeId(idx[r]), NodeId(idx[nid]))
        for nid in ids
        for r in by_id[nid].requires
    )
    try:
        return PartialOrder(children=tuple(Atom(nid) for nid in ids), order=edges)
    except Exception as exc:
        raise AutoFdeError(AutoFdeRefusal.CYCLIC_WORK_GRAPH, str(exc)) from exc


def reduce_order(po: PartialOrder) -> frozenset[OrderEdge]:
    """The transitive reduction of ``po``'s order.

    ``PartialOrder`` already stores the reduction; this calls
    :func:`autofde_lab.powl.transitive_reduction` explicitly so the round-trip law
    is stated in terms of an operation, not an invariant we merely trust.
    """
    return transitive_reduction(po.closure, len(po.children))


# ── the admitted graph for this repository ──────────────────────────────────

_PHASES: tuple[Phase, ...] = (
    Phase(
        phase_id="semantic-foundation",
        title="Semantic Foundation",
        description=(
            "The ontology, refusal vocabulary and standing-law terms every "
            "later phase is written against."
        ),
        due_date="2026-08-14",
        after=(),
    ),
    Phase(
        phase_id="project-infrastructure",
        title="Project Infrastructure",
        description=(
            "Declarative project management and the CI gates that enforce the "
            "semantic foundation."
        ),
        due_date="2026-08-21",
        after=("semantic-foundation",),
    ),
    Phase(
        phase_id="runtime-kernel",
        title="Runtime Kernel",
        description=(
            "Bounded plan-structure execution machinery. Concurrent with Azure "
            "Pack: neither phase precedes the other."
        ),
        due_date="2026-09-04",
        after=("project-infrastructure",),
    ),
    Phase(
        phase_id="azure-pack",
        title="Azure Pack",
        description=(
            "Cloud landing zone and identity surfaces. Concurrent with Runtime "
            "Kernel: neither phase precedes the other."
        ),
        due_date="2026-09-04",
        after=("project-infrastructure",),
    ),
    Phase(
        phase_id="breach-clock-crown",
        title="Breach Clock Crown",
        description=(
            "Deadline accounting and attestation over the joined kernel and "
            "cloud surfaces."
        ),
        due_date="2026-09-18",
        after=("runtime-kernel", "azure-pack"),
    ),
)

_ITEMS: tuple[WorkItem, ...] = (
    WorkItem(
        node_id="sf-ontology",
        title="Author the AutoFDE phase-graph ontology",
        phase="semantic-foundation",
        kind="Semantic",
        body=(
            "Hand-author a T-Box and A-Box describing phases, work items and "
            "work precedence, so a projection can be checked against a "
            "declared vocabulary rather than against itself."
        ),
    ),
    WorkItem(
        node_id="sf-refusal-vocab",
        title="Name every AutoFDE refusal",
        phase="semantic-foundation",
        kind="Semantic",
        body=(
            "Every rejection names a specific law. No bare strings, no generic "
            "ValueError text."
        ),
    ),
    WorkItem(
        node_id="pi-ci-gate-v0",
        title="First CI gate attempt (superseded)",
        phase="project-infrastructure",
        kind="Infrastructure",
        body=(
            "Superseded: this attempt inferred work precedence from the "
            "Terraform resource graph, which is invariant under work order and "
            "therefore carries no bits about it."
        ),
        requires=("sf-refusal-vocab",),
        status="superseded",
    ),
    WorkItem(
        node_id="pi-ci-gate",
        title="CI gate on the round-trip law",
        phase="project-infrastructure",
        kind="Infrastructure",
        body=(
            "Replans pi-ci-gate-v0 with a fresh occurrence identity. The gate "
            "reads precedence from generated issue-body metadata, never from "
            "the Terraform resource graph."
        ),
        requires=("sf-refusal-vocab",),
        supersedes="pi-ci-gate-v0",
        occurrence=2,
    ),
    WorkItem(
        node_id="pi-terraform-module",
        title="Declarative GitHub project management module",
        phase="project-infrastructure",
        kind="Infrastructure",
        body=(
            "Milestones, labels and issues rendered from one admitted graph "
            "into a drop-in .auto.tfvars."
        ),
        requires=("sf-ontology",),
    ),
    WorkItem(
        node_id="rk-scheduler",
        title="Bounded plan-structure scheduler",
        phase="runtime-kernel",
        kind="Runtime",
        body="Walk a partial order under an explicit execution bound.",
        requires=("pi-terraform-module",),
    ),
    WorkItem(
        node_id="rk-bounds",
        title="Execution bound accounting",
        phase="runtime-kernel",
        kind="Runtime",
        body="Account for every step against the declared bound; refuse on exhaustion.",
        requires=("rk-scheduler",),
    ),
    WorkItem(
        node_id="ap-landing-zone",
        title="Azure landing zone",
        phase="azure-pack",
        kind="Cloud",
        body="Subscription, resource group and network scaffolding.",
        requires=("pi-terraform-module",),
    ),
    WorkItem(
        node_id="ap-identity",
        title="Workload identity federation",
        phase="azure-pack",
        kind="Cloud",
        body="Federated credentials with no long-lived secret material.",
        requires=("ap-landing-zone",),
    ),
    WorkItem(
        node_id="bc-clock",
        title="Breach clock",
        phase="breach-clock-crown",
        kind="Verification",
        body="Deadline accounting over the joined kernel and cloud surfaces.",
        requires=("rk-bounds", "ap-identity"),
    ),
    WorkItem(
        node_id="bc-attestation",
        title="Breach attestation record",
        phase="breach-clock-crown",
        kind="Verification",
        body="A checkable record of what the clock observed. Records, never actuates.",
        requires=("bc-clock",),
    ),
)

#: The admitted AutoFDE phase graph for this repository.
AUTOFDE_PHASE_GRAPH = PhaseGraph(phases=_PHASES, items=_ITEMS)
