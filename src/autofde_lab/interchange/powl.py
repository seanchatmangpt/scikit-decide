"""POWL 2.0 structural export preserving partial order, guards and cycles."""

from __future__ import annotations

from typing import Any

from .model import Builder, PlanningExport, PlanningExportError, canonical, digest


def export_powl(root: Any, *, subject: str) -> PlanningExport:
    builder = Builder(
        "powl-2.0",
        subject,
        {"source": "autofde-lab:POWL2", "export_mode": "structural"},
    )
    _visit(builder, root, "root")
    builder.metadata["powl_depth"] = int(getattr(root, "depth", 1))
    return builder.finish()


def _visit(builder: Builder, node: Any, path: str) -> tuple[set[str], set[str]]:
    kind = type(node).__name__
    if kind == "Atom":
        node_id = builder.node(
            f"powl_{digest({'path': path, 'key': getattr(node, 'key', repr(node))})[:20]}",
            "action",
            str(getattr(node, "label", "atom")),
            {
                "consequence": getattr(node, "consequence", "PURE"),
                "bindings": canonical(dict(getattr(node, "bindings", {}) or {})),
            },
        )
        return {node_id}, {node_id}
    if kind == "Silent":
        node_id = builder.node(f"powl_{digest(path)[:20]}", "silent", "τ")
        return {node_id}, {node_id}
    if kind in {"Start", "End"}:
        node_id = builder.node(f"powl_{digest(path)[:20]}", "state", kind.lower())
        return {node_id}, {node_id}
    if kind == "PartialOrder":
        children = tuple(getattr(node, "children"))
        bounds = [
            _visit(builder, child, f"{path}.{i}") for i, child in enumerate(children)
        ]
        incoming, outgoing = [0] * len(children), [0] * len(children)
        for edge in tuple(getattr(node, "order", ())):
            src, dst = int(getattr(edge, "src")), int(getattr(edge, "dst"))
            incoming[dst] += 1
            outgoing[src] += 1
            for left in sorted(bounds[src][1]):
                for right in sorted(bounds[dst][0]):
                    builder.edge(left, right, "precedence", "powl-order")
        entries, exits = set(), set()
        for i in range(len(children)):
            if incoming[i] == 0:
                entries.update(bounds[i][0])
            if outgoing[i] == 0:
                exits.update(bounds[i][1])
        return entries, exits
    if kind == "ChoiceGraph":
        children = tuple(getattr(node, "children"))
        bounds = [
            _visit(builder, child, f"{path}.{i}") for i, child in enumerate(children)
        ]
        edges = sorted(
            getattr(node, "edges", ()),
            key=lambda edge: (
                int(getattr(edge, "src")),
                int(getattr(edge, "dst")),
                getattr(getattr(edge, "guard", None), "key", ""),
            ),
        )
        for edge in edges:
            src, dst = int(getattr(edge, "src")), int(getattr(edge, "dst"))
            guard = getattr(edge, "guard", None)
            label, attrs = "choice", {"choice": True}
            if guard is not None:
                label = str(getattr(guard, "predicate_name", "guard"))
                attrs["guard"] = {
                    "predicate_name": label,
                    "predicate_args": canonical(
                        dict(getattr(guard, "predicate_args", {}) or {})
                    ),
                }
            for left in sorted(bounds[src][1]):
                for right in sorted(bounds[dst][0]):
                    builder.edge(left, right, "transition", label, attrs)
        return (
            set(bounds[int(getattr(node, "start"))][0]),
            set(bounds[int(getattr(node, "end"))][1]),
        )
    raise PlanningExportError("AFL-MMDIO-010", f"unsupported POWL node type {kind!r}")
