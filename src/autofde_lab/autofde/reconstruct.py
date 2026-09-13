# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Reconstruct a work-execution graph from a generated ``.auto.tfvars``.

Anti-self-attestation
---------------------
This module **must not import** :mod:`autofde_lab.autofde.github_projection`.
Reconstruction that reuses the projector's own constants, parser or ordering
would be checking the projector against itself; the round trip would then pass
for any pair of mutually consistent bugs. The same discipline binds
:mod:`autofde_lab.powl.membership`, which is forbidden from importing
:mod:`autofde_lab.powl.executor` (see ``tests/powl/test_membership.py``).

So the marker strings, the HCL-subset parser and the canonical node ordering
below are all restated here independently.

What the round trip proves, and what it does not
------------------------------------------------
Reconstruction reads the **generated tfvars file**, not GitHub. Nothing is
applied — no ``terraform apply`` is ever run against the GitHub provider,
because ``github_issue`` creates real issues in a real repository. This is a
*projection* round trip: it shows that the rendered artifact still contains the
admitted work order. It says nothing about any deployed state, and must not be
read as saying so.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from autofde_lab.autofde.refusals import AutoFdeError, AutoFdeRefusal
from autofde_lab.powl import Atom, NodeId, OrderEdge, PartialOrder

__all__ = [
    "ParsedTfvars",
    "ReconstructedItem",
    "ReconstructedGraph",
    "parse_tfvars",
    "reconstruct_work_graph",
]

# Restated independently of the projector — see the module docstring.
_BEGIN = "<!-- autofde:begin -->"
_END = "<!-- autofde:end -->"
_NONE = "none"

_KV = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_-]*)\s*=\s*(.*)$")
_MAPKEY = re.compile(r'^\s*"([^"]+)"\s*=\s*\{\s*$')
_META = re.compile(r"^autofde-([a-z-]+):\s*(.*)$")


# ── a small HCL-subset reader ───────────────────────────────────────────────


def _unquote(raw: str) -> str:
    raw = raw.strip().rstrip(",").strip()
    if not (len(raw) >= 2 and raw[0] == '"' and raw[-1] == '"'):
        raise AutoFdeError(
            AutoFdeRefusal.MALFORMED_METADATA_BLOCK, f"not a string: {raw!r}"
        )
    return raw[1:-1].encode().decode("unicode_escape")


def _unlist(raw: str) -> tuple[str, ...]:
    raw = raw.strip().rstrip(",").strip()
    if not (raw.startswith("[") and raw.endswith("]")):
        raise AutoFdeError(
            AutoFdeRefusal.MALFORMED_METADATA_BLOCK, f"not a list: {raw!r}"
        )
    inner = raw[1:-1].strip()
    if not inner:
        return ()
    return tuple(_unquote(part) for part in inner.split(","))


def _read_attrs(lines: list[str], i: int, closer: str) -> tuple[dict[str, Any], int]:
    """Read ``key = value`` attributes until a line whose strip starts ``closer``."""
    attrs: dict[str, Any] = {}
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped.startswith(closer):
            return attrs, i + 1
        m = _KV.match(lines[i])
        if m is None:
            i += 1
            continue
        key, rest = m.group(1), m.group(2).strip()
        if rest.startswith("<<"):
            term = rest[2:].lstrip("-").strip()
            i += 1
            buf: list[str] = []
            while i < len(lines) and lines[i].strip() != term:
                buf.append(lines[i])
                i += 1
            if i >= len(lines):
                raise AutoFdeError(
                    AutoFdeRefusal.MALFORMED_METADATA_BLOCK,
                    f"unterminated heredoc for {key!r}",
                )
            attrs[key] = "\n".join(buf)
            i += 1
        elif rest.startswith("["):
            attrs[key] = _unlist(rest)
            i += 1
        else:
            attrs[key] = _unquote(rest)
            i += 1
    raise AutoFdeError(AutoFdeRefusal.MALFORMED_METADATA_BLOCK, "unterminated block")


@dataclass(frozen=True, slots=True)
class ParsedTfvars:
    """The raw ``milestones`` / ``labels`` / ``issues`` values, unvalidated."""

    milestones: dict[str, dict[str, Any]]
    labels: dict[str, dict[str, Any]]
    issues: tuple[dict[str, Any], ...]


def parse_tfvars(text: str) -> ParsedTfvars:
    """Parse the HCL subset this repository's ``.auto.tfvars`` is written in."""
    lines = text.split("\n")
    milestones: dict[str, dict[str, Any]] = {}
    labels: dict[str, dict[str, Any]] = {}
    issues: list[dict[str, Any]] = []

    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped.startswith("milestones") and stripped.endswith("{"):
            i, milestones = _read_map(lines, i + 1)
        elif stripped.startswith("labels") and stripped.endswith("{"):
            i, labels = _read_map(lines, i + 1)
        elif stripped.startswith("issues") and stripped.endswith("["):
            i += 1
            while i < len(lines) and lines[i].strip() != "]":
                if lines[i].strip() == "{":
                    attrs, i = _read_attrs(lines, i + 1, "}")
                    issues.append(attrs)
                else:
                    i += 1
            i += 1
        else:
            i += 1
    return ParsedTfvars(milestones=milestones, labels=labels, issues=tuple(issues))


def _read_map(lines: list[str], i: int) -> tuple[int, dict[str, dict[str, Any]]]:
    out: dict[str, dict[str, Any]] = {}
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped == "}":
            return i + 1, out
        m = _MAPKEY.match(lines[i])
        if m is None:
            i += 1
            continue
        key = m.group(1)
        attrs, i = _read_attrs(lines, i + 1, "}")
        if key in out:
            raise AutoFdeError(AutoFdeRefusal.DUPLICATE_NODE_ID, key)
        out[key] = attrs
    raise AutoFdeError(AutoFdeRefusal.MALFORMED_METADATA_BLOCK, "unterminated map")


# ── metadata block ──────────────────────────────────────────────────────────


def _read_metadata(body: str) -> dict[str, str]:
    lines = body.split("\n")
    try:
        start = lines.index(_BEGIN)
        end = lines.index(_END)
    except ValueError as exc:
        raise AutoFdeError(
            AutoFdeRefusal.MISSING_PRECEDENCE_METADATA,
            "no autofde metadata block in issue body",
        ) from exc
    if end <= start:
        raise AutoFdeError(AutoFdeRefusal.MALFORMED_METADATA_BLOCK, "end before begin")
    fields: dict[str, str] = {}
    for line in lines[start + 1 : end]:
        m = _META.match(line.strip())
        if m is None:
            raise AutoFdeError(
                AutoFdeRefusal.MALFORMED_METADATA_BLOCK, f"unparseable: {line!r}"
            )
        fields[m.group(1)] = m.group(2).strip()
    required = {
        "node",
        "phase",
        "kind",
        "occurrence",
        "status",
        "requires",
        "supersedes",
    }
    missing = required - set(fields)
    if missing:
        raise AutoFdeError(
            AutoFdeRefusal.MISSING_PRECEDENCE_METADATA,
            f"missing keys: {sorted(missing)}",
        )
    return fields


# ── reconstruction ──────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ReconstructedItem:
    node_id: str
    title: str
    phase: str
    kind: str
    requires: tuple[str, ...]
    status: str
    supersedes: str
    occurrence: int


@dataclass(frozen=True, slots=True)
class ReconstructedGraph:
    items: tuple[ReconstructedItem, ...]
    milestones: tuple[str, ...]

    def partial_order(self) -> PartialOrder:
        """Canonical POWL projection: children are ``Atom(node_id)``, id-sorted.

        The ordering rule is restated here rather than imported, so a change to
        the projector's ordering cannot silently propagate into the check.
        """
        ids = tuple(sorted(it.node_id for it in self.items))
        idx = {nid: i for i, nid in enumerate(ids)}
        by_id = {it.node_id: it for it in self.items}
        edges = frozenset(
            OrderEdge(NodeId(idx[r]), NodeId(idx[nid]))
            for nid in ids
            for r in by_id[nid].requires
        )
        try:
            return PartialOrder(children=tuple(Atom(nid) for nid in ids), order=edges)
        except Exception as exc:
            raise AutoFdeError(AutoFdeRefusal.CYCLIC_WORK_GRAPH, str(exc)) from exc


def reconstruct_work_graph(tfvars_text: str) -> ReconstructedGraph:
    """Recover the work-execution graph from generated tfvars text.

    Reads only issue-body metadata for precedence. The Terraform resource graph
    is never consulted, because it is invariant under work order.
    """
    parsed = parse_tfvars(tfvars_text)
    if not parsed.issues:
        raise AutoFdeError(AutoFdeRefusal.EMPTY_GRAPH, "no issues in tfvars")

    label_names = {k: v.get("name", "") for k, v in parsed.labels.items()}
    items: list[ReconstructedItem] = []
    seen: set[str] = set()
    used_milestones: set[str] = set()

    for issue in parsed.issues:
        for key in ("title", "body", "labels", "milestone"):
            if key not in issue:
                raise AutoFdeError(
                    AutoFdeRefusal.MALFORMED_METADATA_BLOCK, f"issue missing {key!r}"
                )
        meta = _read_metadata(issue["body"])
        node_id = meta["node"]
        if not node_id:
            raise AutoFdeError(AutoFdeRefusal.ORPHAN_ISSUE, issue["title"])
        if node_id in seen:
            raise AutoFdeError(AutoFdeRefusal.NON_INJECTIVE_PROJECTION, node_id)
        seen.add(node_id)

        if issue["milestone"] not in parsed.milestones:
            raise AutoFdeError(
                AutoFdeRefusal.ORPHAN_MILESTONE,
                f"{node_id} bound to undeclared milestone {issue['milestone']!r}",
            )
        if issue["milestone"] != meta["phase"]:
            raise AutoFdeError(
                AutoFdeRefusal.MILESTONE_BINDING_MISMATCH,
                f"{node_id}: milestone={issue['milestone']!r} phase={meta['phase']!r}",
            )
        used_milestones.add(issue["milestone"])

        kind_names = tuple(
            label_names[k][len("Kind:") :]
            for k in issue["labels"]
            if k in label_names and label_names[k].startswith("Kind:")
        )
        if len(kind_names) != 1:
            raise AutoFdeError(
                AutoFdeRefusal.LABEL_MISMATCH,
                f"{node_id}: expected exactly one Kind:* label, got {list(kind_names)}",
            )
        if kind_names[0] != meta["kind"]:
            raise AutoFdeError(
                AutoFdeRefusal.LABEL_MISMATCH,
                f"{node_id}: label Kind:{kind_names[0]} vs metadata kind {meta['kind']}",
            )

        requires = (
            ()
            if meta["requires"] == _NONE
            else tuple(
                sorted(p.strip() for p in meta["requires"].split(",") if p.strip())
            )
        )
        items.append(
            ReconstructedItem(
                node_id=node_id,
                title=issue["title"],
                phase=meta["phase"],
                kind=meta["kind"],
                requires=requires,
                status=meta["status"],
                supersedes="" if meta["supersedes"] == _NONE else meta["supersedes"],
                occurrence=int(meta["occurrence"]),
            )
        )

    for it in items:
        for r in it.requires:
            if r not in seen:
                raise AutoFdeError(
                    AutoFdeRefusal.UNKNOWN_WORK_ITEM,
                    f"{it.node_id} requires {r}, which no issue declares",
                )
        if it.supersedes and it.supersedes not in seen:
            raise AutoFdeError(
                AutoFdeRefusal.UNKNOWN_WORK_ITEM,
                f"{it.node_id} supersedes {it.supersedes}, which no issue declares",
            )

    orphan = set(parsed.milestones) - used_milestones
    if orphan:
        raise AutoFdeError(
            AutoFdeRefusal.ORPHAN_MILESTONE,
            f"milestones with no admitted phase work: {sorted(orphan)}",
        )

    return ReconstructedGraph(
        items=tuple(items), milestones=tuple(sorted(parsed.milestones))
    )
