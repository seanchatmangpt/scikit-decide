# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Project an admitted work-execution graph onto GitHub provisioning inputs.

Projection table
----------------

============================  =========================================
Work concept                  GitHub representation
============================  =========================================
major phase                   milestone
work item                     issue
classification                ``Kind:*`` label
**work dependency**           **structured issue-body metadata**
concurrent work               *no edge emitted at all*
superseded work               status label + lineage metadata
replanned work                new issue with a fresh occurrence identity
============================  =========================================

Why work dependency is body metadata and never a Terraform edge
---------------------------------------------------------------
GitHub milestones, labels and issues have no native blocks/blocked-by edge.
The only Terraform edges available are provisioning edges — ``github_issue``
depends on ``github_repository_milestone.epics[k].number`` because the API
needs that number to create the issue. Those edges are *invariant* under any
change to work order: two issues where A blocks B and two fully independent
issues in the same milestone with the same labels emit the identical resource
graph. An invariant carries zero bits about the thing it is invariant under,
so the provisioning graph can never falsify a work-order projection.

Therefore precedence is written into generated issue *body content*, keyed by
source-graph node id, in a machine-parseable block. That block — not the
Terraform resource graph — is what :mod:`autofde_lab.autofde.reconstruct` reads.

Nothing here applies anything. It renders text.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterable

from autofde_lab.autofde.phase_graph import PhaseGraph, reduce_order, work_partial_order
from autofde_lab.autofde.refusals import AutoFdeError, AutoFdeRefusal

__all__ = [
    "METADATA_BEGIN",
    "METADATA_END",
    "IssueProjection",
    "kind_label_key",
    "kind_label_name",
    "render_issue_body",
    "project",
    "render_tfvars",
    "render_project_plan_json",
    "render_powl_json",
]

METADATA_BEGIN = "<!-- autofde:begin -->"
METADATA_END = "<!-- autofde:end -->"

_NONE = "none"

#: Deterministic label colours, keyed by classification.
_KIND_COLORS = {
    "Semantic": "5319A1",
    "Infrastructure": "B60205",
    "Runtime": "0E8A16",
    "Cloud": "1D76DB",
    "Verification": "FBCA04",
}
_STATUS_COLORS = {"superseded": "666666"}


def kind_label_key(kind: str) -> str:
    return f"kind-{kind.lower()}"


def kind_label_name(kind: str) -> str:
    return f"Kind:{kind}"


def _status_label_key(status: str) -> str:
    return f"status-{status.lower()}"


def _status_label_name(status: str) -> str:
    return f"Status:{status.capitalize()}"


@dataclass(frozen=True, slots=True)
class IssueProjection:
    """One work item as one GitHub issue. Exactly one issue per work item."""

    node_id: str
    title: str
    body: str
    labels: tuple[str, ...]
    milestone: str


# ── issue body ──────────────────────────────────────────────────────────────


def render_issue_body(graph: PhaseGraph, node_id: str) -> str:
    """Human prose plus the structured precedence block.

    The block is the sole carrier of work precedence in the projection.
    """
    item = graph.item_map[node_id]
    requires = ", ".join(sorted(item.requires)) or _NONE
    supersedes = item.supersedes or _NONE
    lines = [
        item.body.strip(),
        "",
        METADATA_BEGIN,
        f"autofde-node: {item.node_id}",
        f"autofde-phase: {item.phase}",
        f"autofde-kind: {item.kind}",
        f"autofde-occurrence: {item.occurrence}",
        f"autofde-status: {item.status}",
        f"autofde-requires: {requires}",
        f"autofde-supersedes: {supersedes}",
        METADATA_END,
    ]
    return "\n".join(lines) + "\n"


# ── projection ──────────────────────────────────────────────────────────────


def project(graph: PhaseGraph) -> tuple[IssueProjection, ...]:
    """One issue per work item, in :meth:`PhaseGraph.sorted_item_ids` order."""
    out: list[IssueProjection] = []
    for nid in graph.sorted_item_ids():
        item = graph.item_map[nid]
        labels = [kind_label_key(item.kind)]
        if item.status != "active":
            labels.append(_status_label_key(item.status))
        out.append(
            IssueProjection(
                node_id=nid,
                title=item.title,
                body=render_issue_body(graph, nid),
                labels=tuple(labels),
                milestone=item.phase,
            )
        )
    seen = {p.node_id for p in out}
    if len(seen) != len(out) or seen != set(graph.item_map):
        raise AutoFdeError(
            AutoFdeRefusal.NON_INJECTIVE_PROJECTION,
            f"{len(out)} issues for {len(graph.items)} work items",
        )
    return tuple(out)


def _label_table(graph: PhaseGraph) -> tuple[tuple[str, str, str], ...]:
    """``(key, name, color)`` triples, deterministically ordered."""
    rows: dict[str, tuple[str, str]] = {}
    for it in graph.items:
        rows[kind_label_key(it.kind)] = (
            kind_label_name(it.kind),
            _KIND_COLORS.get(it.kind, "EDEDED"),
        )
        if it.status != "active":
            rows[_status_label_key(it.status)] = (
                _status_label_name(it.status),
                _STATUS_COLORS.get(it.status, "EDEDED"),
            )
    return tuple((k, rows[k][0], rows[k][1]) for k in sorted(rows))


# ── HCL rendering ───────────────────────────────────────────────────────────


def _heredoc(value: str) -> str:
    """Render ``value`` as an HCL heredoc.

    Terraform interpolates ``${`` and ``%{`` inside a heredoc, so a body
    containing either is refused rather than silently mangled. A line equal to
    the terminator would end the heredoc early and is refused too.
    """
    for bad in ("${", "%{"):
        if bad in value:
            raise AutoFdeError(
                AutoFdeRefusal.UNSAFE_HEREDOC_BODY, f"body contains {bad!r}"
            )
    lines = value.rstrip("\n").split("\n")
    if any(line.strip() == "EOT" for line in lines):
        raise AutoFdeError(
            AutoFdeRefusal.UNSAFE_HEREDOC_BODY, "body contains a bare EOT line"
        )
    body = "\n".join(lines)
    return "<<EOT\n" + body + "\nEOT"


def _q(value: str) -> str:
    return json.dumps(value, ensure_ascii=True)


def _list(values: Iterable[str]) -> str:
    return "[" + ", ".join(_q(v) for v in values) + "]"


def render_tfvars(graph: PhaseGraph) -> str:
    """Render a drop-in ``.auto.tfvars`` for ``infra/github/project_management``.

    Deterministic: the same graph renders byte-identical output. Variable names
    and value shapes match ``main.tf`` in the same directory.
    """
    parts: list[str] = [
        "# GENERATED by `python -m autofde_lab.autofde` from the admitted AutoFDE",
        "# phase graph (src/autofde_lab/autofde/phase_graph.py). Do not hand-edit.",
        "#",
        "# Work precedence is carried in issue-body metadata, never as a",
        "# Terraform edge: the provisioning graph is invariant under work order.",
        "",
        "milestones = {",
    ]
    for pid in graph.sorted_phase_ids():
        p = graph.phase_map[pid]
        parts += [
            f"  {_q(pid)} = {{",
            f"    title       = {_q(p.title)}",
            f"    due_date    = {_q(p.due_date)}",
            f"    description = {_heredoc(p.description)}",
            "  },",
        ]
    parts += ["}", "", "labels = {"]
    for key, name, color in _label_table(graph):
        parts += [
            f"  {_q(key)} = {{",
            f"    name  = {_q(name)}",
            f"    color = {_q(color)}",
            "  },",
        ]
    parts += ["}", "", "issues = ["]
    for iss in project(graph):
        parts += [
            "  {",
            f"    title     = {_q(iss.title)}",
            f"    body      = {_heredoc(iss.body)}",
            f"    labels    = {_list(iss.labels)}",
            f"    milestone = {_q(iss.milestone)}",
            "  },",
        ]
    parts += ["]", ""]
    return "\n".join(parts)


# ── JSON artifacts ──────────────────────────────────────────────────────────


def render_project_plan_json(graph: PhaseGraph) -> str:
    """The projection as JSON: what would be provisioned, and from which node."""
    payload: dict[str, Any] = {
        "generator": "autofde_lab.autofde.github_projection",
        "applied": False,
        "milestones": [
            {
                "key": pid,
                "title": graph.phase_map[pid].title,
                "due_date": graph.phase_map[pid].due_date,
                "after": sorted(graph.phase_map[pid].after),
            }
            for pid in graph.sorted_phase_ids()
        ],
        "labels": [
            {"key": k, "name": n, "color": c} for k, n, c in _label_table(graph)
        ],
        "issues": [
            {
                "source_node": iss.node_id,
                "title": iss.title,
                "labels": list(iss.labels),
                "milestone": iss.milestone,
                "requires": sorted(graph.item_map[iss.node_id].requires),
                "status": graph.item_map[iss.node_id].status,
                "occurrence": graph.item_map[iss.node_id].occurrence,
                "supersedes": graph.item_map[iss.node_id].supersedes or None,
            }
            for iss in project(graph)
        ],
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def render_powl_json(graph: PhaseGraph) -> str:
    """The admitted work graph as POWL 2.0 structure (transitive reduction)."""
    po = work_partial_order(graph)
    ids = graph.sorted_item_ids()
    payload = {
        "kind": "PartialOrder",
        "children": [{"kind": "Atom", "label": nid} for nid in ids],
        "order": sorted([[ids[e.src], ids[e.dst]] for e in reduce_order(po)]),
        "note": (
            "Transitive reduction. An absent edge between two nodes in "
            "different branches means genuine concurrency, not unknown order."
        ),
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"
