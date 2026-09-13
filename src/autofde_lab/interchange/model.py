"""Canonical carrier shared by AutoFDE → mmdio planning exporters."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping

SCHEMA = "autofde.mmdio-planning-export/1"
CLAIM_CEILING = "NATIVE_PLANNING_SEMANTICS_TO_MMDIO_PROJECTION_ONLY"
FORMALISMS = frozenset({"pddl", "ppddl", "pddl+", "rddl", "powl-2.0"})
NODE_KINDS = frozenset(
    {
        "state",
        "action",
        "process",
        "event",
        "goal",
        "constraint",
        "fluent",
        "reward",
        "choice",
        "observation",
        "silent",
    }
)
EDGE_KINDS = frozenset(
    {
        "precondition",
        "effect",
        "transition",
        "precedence",
        "causal",
        "probabilistic",
        "temporal",
        "dependency",
        "observation",
        "reward",
    }
)


class PlanningExportError(ValueError):
    """Typed refusal raised when an export cannot be admitted."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True, slots=True)
class ExportLimits:
    max_states: int = 128
    max_depth: int = 16
    max_actions_per_state: int = 64
    max_successors_per_action: int = 32
    max_steps: int = 256

    def validate(self) -> None:
        for name, value in self.as_dict().items():
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise PlanningExportError(
                    "AFL-MMDIO-001", f"{name} must be a positive integer"
                )

    def as_dict(self) -> dict[str, int]:
        return {
            "max_states": self.max_states,
            "max_depth": self.max_depth,
            "max_actions_per_state": self.max_actions_per_state,
            "max_successors_per_action": self.max_successors_per_action,
            "max_steps": self.max_steps,
        }


@dataclass(frozen=True, slots=True)
class PlanningExport:
    """Canonical JSON carrier accepted by ``mmdio.planning.jsonio``."""

    formalism: str
    subject: str
    nodes: tuple[dict[str, Any], ...]
    edges: tuple[dict[str, Any], ...]
    metadata: dict[str, Any]

    def canonical_dict(self) -> dict[str, Any]:
        payload = {
            "formalism": self.formalism,
            "subject": self.subject,
            "nodes": sorted(
                (canonical(dict(node)) for node in self.nodes),
                key=lambda node: (node["id"], node["kind"], node["label"]),
            ),
            "edges": sorted(
                (canonical(dict(edge)) for edge in self.edges),
                key=edge_sort_key,
            ),
            "metadata": canonical(dict(self.metadata)),
        }
        validate_payload(payload)
        return payload

    def canonical_json(self) -> str:
        return json.dumps(
            self.canonical_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )

    def digest(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()

    def write_json(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(
                self.canonical_dict(),
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n",
            encoding="utf-8",
        )
        return target


class Builder:
    """Identity-preserving constructor for one planning export."""

    def __init__(
        self,
        formalism: str,
        subject: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        if formalism not in FORMALISMS:
            raise PlanningExportError(
                "AFL-MMDIO-002", f"unsupported formalism {formalism!r}"
            )
        if not subject.strip():
            raise PlanningExportError("AFL-MMDIO-003", "subject must be non-empty")
        self.formalism = formalism
        self.subject = subject
        self.nodes: dict[str, dict[str, Any]] = {}
        self.edges: dict[str, dict[str, Any]] = {}
        self.metadata = dict(metadata or {})

    def node(
        self,
        node_id: str,
        kind: str,
        label: str,
        attributes: Mapping[str, Any] | None = None,
    ) -> str:
        if kind not in NODE_KINDS:
            raise PlanningExportError("AFL-MMDIO-004", f"unknown node kind {kind!r}")
        payload = {
            "id": node_id,
            "kind": kind,
            "label": str(label),
            "attributes": canonical(dict(attributes or {})),
        }
        previous = self.nodes.get(node_id)
        if previous is not None and previous != payload:
            raise PlanningExportError(
                "AFL-MMDIO-005", f"node identity collision {node_id!r}"
            )
        self.nodes[node_id] = payload
        return node_id

    def edge(
        self,
        source: str,
        target: str,
        kind: str,
        label: str | None = None,
        attributes: Mapping[str, Any] | None = None,
    ) -> None:
        if kind not in EDGE_KINDS:
            raise PlanningExportError("AFL-MMDIO-006", f"unknown edge kind {kind!r}")
        payload = {
            "source": source,
            "target": target,
            "kind": kind,
            "label": None if label is None else str(label),
            "attributes": canonical(dict(attributes or {})),
        }
        identity = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        self.edges[identity] = payload

    def finish(self) -> PlanningExport:
        known = set(self.nodes)
        for edge in self.edges.values():
            if edge["source"] not in known or edge["target"] not in known:
                raise PlanningExportError(
                    "AFL-MMDIO-007",
                    f"dangling edge {edge['source']!r}->{edge['target']!r}",
                )
        export = PlanningExport(
            formalism=self.formalism,
            subject=self.subject,
            nodes=tuple(self.nodes.values()),
            edges=tuple(self.edges.values()),
            metadata={
                **self.metadata,
                "schema": SCHEMA,
                "claim_ceiling": CLAIM_CEILING,
                "authority": "non-actuating",
            },
        )
        export.canonical_dict()
        return export


def validate_payload(payload: Mapping[str, Any]) -> None:
    if payload.get("formalism") not in FORMALISMS:
        raise PlanningExportError("AFL-MMDIO-011", "non-canonical formalism")
    if not str(payload.get("subject", "")).strip():
        raise PlanningExportError("AFL-MMDIO-011", "empty subject")
    nodes = list(payload.get("nodes", []))
    ids = [str(node.get("id", "")) for node in nodes]
    if any(not node_id for node_id in ids) or len(ids) != len(set(ids)):
        raise PlanningExportError("AFL-MMDIO-011", "invalid or duplicate node identity")
    known = set(ids)
    for node in nodes:
        if node.get("kind") not in NODE_KINDS:
            raise PlanningExportError("AFL-MMDIO-011", "invalid node kind")
    for edge in payload.get("edges", []):
        if edge.get("source") not in known or edge.get("target") not in known:
            raise PlanningExportError("AFL-MMDIO-011", "dangling edge")
        if edge.get("kind") not in EDGE_KINDS:
            raise PlanningExportError("AFL-MMDIO-011", "invalid edge kind")
        probability = dict(edge.get("attributes", {})).get("probability")
        if probability is not None and (
            isinstance(probability, bool)
            or not isinstance(probability, (int, float))
            or not math.isfinite(float(probability))
            or not 0 <= float(probability) <= 1
        ):
            raise PlanningExportError("AFL-MMDIO-011", "invalid probability")


def canonical(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): canonical(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, (list, tuple)):
        return [canonical(item) for item in value]
    if isinstance(value, (set, frozenset)):
        items = [canonical(item) for item in value]
        return sorted(items, key=canonical_json)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise PlanningExportError("AFL-MMDIO-012", "non-finite numeric value")
        return value
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    enum_value = getattr(value, "value", None)
    if isinstance(enum_value, (str, int, float, bool)):
        return canonical(enum_value)
    return stable_repr(value)


def canonical_json(value: Any) -> str:
    return json.dumps(
        canonical(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def digest(value: Any) -> str:
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()


def stable_repr(value: Any) -> str:
    text = repr(value)
    if " at 0x" in text:
        return f"<{type(value).__module__}.{type(value).__qualname__}>"
    return text


def short_label(value: Any, limit: int = 160) -> str:
    text = stable_repr(value).replace("\n", " ").replace("\r", " ")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def edge_sort_key(edge: Mapping[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        str(edge["source"]),
        str(edge["target"]),
        str(edge["kind"]),
        str(edge.get("label") or ""),
        json.dumps(edge.get("attributes", {}), sort_keys=True, separators=(",", ":")),
    )
