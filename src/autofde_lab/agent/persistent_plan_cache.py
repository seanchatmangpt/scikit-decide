# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Durable candidate-plan memory for continuous planning.

The SQLite database is a persistence and retrieval index only. A row is never
an admission proof and never carries execution authority. Every artifact is
reconstructed, content-verified, and still has to pass ``admit_plan`` before a
``ContinuousPlanner`` may reuse it.

The store deliberately opens a short-lived SQLite connection per operation.
That makes lifecycle ownership explicit, avoids leaked descriptors, and lets
independent processes safely share a WAL-backed cache without sharing Python
objects or ambient authority.

Enterprise boundaries are explicit:

* every cache instance has a non-empty namespace; exact and similarity lookup
  are namespace-scoped so one tenant/workload cannot enumerate another's
  candidate plans through this API;
* every namespace has a deterministic capacity ceiling, with oldest inserted
  candidates evicted after successful insertion so durable memory cannot grow
  without bound;
* the SQLite file is owner-readable/writable only on POSIX after creation;
* legacy pre-namespace databases are migrated into the ``default`` namespace
  transactionally rather than becoming silently unreadable.
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Mapping

from autofde_lab.agent.continuous_planning import (
    PlanApplicability,
    PlanArtifact,
    PlanningContext,
)
from autofde_lab.fabric.canonical import canonical_json, sha256, to_jsonable
from autofde_lab.powl.algebra import (
    Atom,
    ChoiceGraph,
    ChoiceGraphEdge,
    End,
    Guard,
    NodeId,
    OrderEdge,
    PartialOrder,
    PowlNode,
    Silent,
    Start,
)
from autofde_lab.powl.frequency import Frequency

__all__ = ["PersistentPlanCorruption", "SQLitePlanCache"]

_ARTIFACT_SCHEMA_VERSION = 1
_DEFAULT_MAX_ENTRIES = 100_000


class PersistentPlanCorruption(ValueError):
    """A persisted row cannot reproduce the content identity it claims."""


def _encode_frequency(value: Frequency) -> dict[str, int | None]:
    return {"min": value.min, "max": value.max}


def _decode_frequency(value: Mapping[str, Any]) -> Frequency:
    return Frequency(min=int(value["min"]), max=value.get("max"))


def _portable_action(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise ValueError(
        "UNSUPPORTED:PERSISTENT_PLAN_ACTION: durable plans require a scalar "
        "action identity; executable Python objects remain process-local"
    )


def _encode_guard(value: Guard | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return {
        "predicate_name": value.predicate_name,
        "predicate_args": to_jsonable(dict(value.predicate_args)),
    }


def _decode_guard(value: Mapping[str, Any] | None) -> Guard | None:
    if value is None:
        return None
    return Guard(
        predicate_name=str(value["predicate_name"]),
        predicate_args=dict(value.get("predicate_args", {})),
    )


def _encode_node(node: PowlNode) -> dict[str, Any]:
    if isinstance(node, Start):
        return {"kind": "start"}
    if isinstance(node, End):
        return {"kind": "end"}
    if isinstance(node, Silent):
        return {"kind": "silent"}
    if isinstance(node, Atom):
        return {
            "kind": "atom",
            "label": node.label,
            "action": _portable_action(node.action),
            "bindings": to_jsonable(dict(node.bindings)),
            "consequence": node.consequence,
        }
    if isinstance(node, PartialOrder):
        return {
            "kind": "partial-order",
            "children": [_encode_node(child) for child in node.children],
            "order": [
                [int(edge.src), int(edge.dst)]
                for edge in sorted(
                    node.order, key=lambda item: (int(item.src), int(item.dst))
                )
            ],
            "frequency": _encode_frequency(node.frequency),
        }
    if isinstance(node, ChoiceGraph):
        return {
            "kind": "choice-graph",
            "children": [_encode_node(child) for child in node.children],
            "edges": [
                {
                    "src": int(edge.src),
                    "dst": int(edge.dst),
                    "guard": _encode_guard(edge.guard),
                }
                for edge in sorted(node.edges)
            ],
            "start": node.start,
            "end": node.end,
            "frequency": _encode_frequency(node.frequency),
        }
    raise TypeError(f"UNSUPPORTED:PERSISTENT_POWL_NODE:{type(node).__name__}")


def _decode_node(value: Mapping[str, Any]) -> PowlNode:
    kind = value.get("kind")
    if kind == "start":
        return Start()
    if kind == "end":
        return End()
    if kind == "silent":
        return Silent()
    if kind == "atom":
        return Atom(
            label=str(value["label"]),
            action=value.get("action"),
            bindings=dict(value.get("bindings", {})),
            consequence=str(value.get("consequence", "PURE")),  # type: ignore[arg-type]
        )
    if kind == "partial-order":
        children = tuple(_decode_node(child) for child in value.get("children", []))
        order = frozenset(
            OrderEdge(NodeId(int(src)), NodeId(int(dst)))
            for src, dst in value.get("order", [])
        )
        return PartialOrder(
            children=children,
            order=order,
            frequency=_decode_frequency(value.get("frequency", {"min": 1, "max": 1})),
        )
    if kind == "choice-graph":
        children = tuple(_decode_node(child) for child in value.get("children", []))
        edges = frozenset(
            ChoiceGraphEdge(
                NodeId(int(edge["src"])),
                NodeId(int(edge["dst"])),
                _decode_guard(edge.get("guard")),
            )
            for edge in value.get("edges", [])
        )
        return ChoiceGraph(
            children=children,
            edges=edges,
            start=int(value.get("start", 0)),
            end=int(value.get("end", 1)),
            frequency=_decode_frequency(value.get("frequency", {"min": 1, "max": 1})),
        )
    raise PersistentPlanCorruption(f"REFUSED:UNKNOWN_PERSISTED_POWL_KIND:{kind!r}")


def _path_key(path: tuple[int, ...]) -> str:
    return "/".join(str(item) for item in path)


def _decode_path(value: str) -> tuple[int, ...]:
    if not value:
        return ()
    return tuple(int(item) for item in value.split("/"))


def _artifact_payload(plan: PlanArtifact) -> dict[str, Any]:
    return {
        "schema": f"urn:autofde-lab:persistent-plan-cache:{_ARTIFACT_SCHEMA_VERSION}",
        "model": _encode_node(plan.model),
        "applicability": plan.applicability.as_dict(),
        "planner": plan.planner,
        "planner_parameters": to_jsonable(dict(plan.planner_parameters)),
        "dependency_keys": {
            _path_key(path): sorted(values)
            for path, values in sorted(plan.dependency_keys.items())
        },
        "downstream": {
            _path_key(path): sorted(_path_key(item) for item in values)
            for path, values in sorted(plan.downstream.items())
        },
        "family_id": plan.family_id,
        "version": plan.version,
        "required_authority_classes": list(plan.required_authority_classes),
    }


def _decode_artifact(payload: Mapping[str, Any]) -> PlanArtifact:
    expected_schema = (
        f"urn:autofde-lab:persistent-plan-cache:{_ARTIFACT_SCHEMA_VERSION}"
    )
    if payload.get("schema") != expected_schema:
        raise PersistentPlanCorruption(
            f"REFUSED:PERSISTED_PLAN_SCHEMA:{payload.get('schema')!r}"
        )
    raw_applicability = dict(payload["applicability"])
    applicability = PlanApplicability(
        goal=str(raw_applicability["goal"]),
        required_facts=frozenset(raw_applicability.get("required_facts", [])),
        forbidden_facts=frozenset(raw_applicability.get("forbidden_facts", [])),
        required_capabilities=frozenset(
            raw_applicability.get("required_capabilities", [])
        ),
        constraint_digest=str(raw_applicability.get("constraint_digest", "")),
        semantic_revision=str(raw_applicability.get("semantic_revision", "")),
    )
    return PlanArtifact(
        model=_decode_node(dict(payload["model"])),
        applicability=applicability,
        planner=str(payload["planner"]),
        planner_parameters=dict(payload.get("planner_parameters", {})),
        dependency_keys={
            _decode_path(path): frozenset(values)
            for path, values in dict(payload.get("dependency_keys", {})).items()
        },
        downstream={
            _decode_path(path): frozenset(_decode_path(item) for item in values)
            for path, values in dict(payload.get("downstream", {})).items()
        },
        family_id=payload.get("family_id"),
        version=int(payload.get("version", 1)),
        required_authority_classes=tuple(
            str(item) for item in payload.get("required_authority_classes", [])
        ),
    )


def _context_signature(context: PlanningContext) -> str:
    return sha256(
        {
            "goal": context.goal,
            "constraint_digest": context.constraint_digest,
            "semantic_revision": context.semantic_revision,
        }
    )


def _create_current_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS plan_artifacts (
            stored_seq INTEGER PRIMARY KEY AUTOINCREMENT,
            namespace TEXT NOT NULL,
            exact_key TEXT NOT NULL,
            retrieval_signature TEXT NOT NULL,
            artifact_json TEXT NOT NULL,
            artifact_digest TEXT NOT NULL,
            schema_version INTEGER NOT NULL,
            UNIQUE(namespace, exact_key)
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS plan_artifacts_signature_idx
        ON plan_artifacts (namespace, retrieval_signature, exact_key)
        """
    )


def _migrate_legacy_schema(connection: sqlite3.Connection) -> None:
    columns = {
        str(row[1]) for row in connection.execute("PRAGMA table_info(plan_artifacts)")
    }
    if not columns or "namespace" in columns:
        return
    required = {
        "exact_key",
        "retrieval_signature",
        "artifact_json",
        "artifact_digest",
        "schema_version",
    }
    if not required.issubset(columns):
        raise PersistentPlanCorruption(
            f"REFUSED:PERSISTED_PLAN_DB_SCHEMA:{sorted(columns)!r}"
        )
    connection.execute("ALTER TABLE plan_artifacts RENAME TO plan_artifacts_legacy")
    _create_current_schema(connection)
    connection.execute(
        """
        INSERT INTO plan_artifacts (
            namespace,
            exact_key,
            retrieval_signature,
            artifact_json,
            artifact_digest,
            schema_version
        )
        SELECT 'default', exact_key, retrieval_signature, artifact_json,
               artifact_digest, schema_version
        FROM plan_artifacts_legacy
        ORDER BY exact_key
        """
    )
    connection.execute("DROP TABLE plan_artifacts_legacy")


class SQLitePlanCache:
    """Restart-survivable, namespace-partitioned candidate plan cache.

    SQLite indexes candidates; it does not admit them. The class intentionally
    implements the same ``remember``/``exact``/``retrieve_candidates`` surface
    as ``PlanCache`` so ``ContinuousPlanner`` can consume it without gaining a
    new authority or execution path.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        namespace: str = "default",
        max_entries: int = _DEFAULT_MAX_ENTRIES,
    ) -> None:
        self.path = Path(path)
        if self.path == Path(":memory:"):
            raise ValueError(
                "UNSUPPORTED:PERSISTENT_PLAN_CACHE_REQUIRES_FILE: short-lived "
                "connection ownership cannot provide restart durability for :memory:"
            )
        if not isinstance(namespace, str) or not namespace.strip():
            raise ValueError("REFUSED:EMPTY_PERSISTENT_PLAN_NAMESPACE")
        if len(namespace) > 256 or "\x00" in namespace:
            raise ValueError("REFUSED:INVALID_PERSISTENT_PLAN_NAMESPACE")
        if (
            not isinstance(max_entries, int)
            or isinstance(max_entries, bool)
            or max_entries < 1
        ):
            raise ValueError("REFUSED:INVALID_PERSISTENT_PLAN_CAPACITY")
        self.namespace = namespace
        self.max_entries = max_entries
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()
        if os.name == "posix":
            os.chmod(self.path, 0o600)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            str(self.path),
            timeout=30.0,
            isolation_level=None,
        )
        connection.execute("PRAGMA busy_timeout = 30000")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            _migrate_legacy_schema(connection)
            _create_current_schema(connection)
            connection.commit()

    def _enforce_capacity(self, connection: sqlite3.Connection) -> None:
        row = connection.execute(
            "SELECT COUNT(*) FROM plan_artifacts WHERE namespace = ?",
            (self.namespace,),
        ).fetchone()
        assert row is not None
        excess = int(row[0]) - self.max_entries
        if excess <= 0:
            return
        connection.execute(
            """
            DELETE FROM plan_artifacts
            WHERE stored_seq IN (
                SELECT stored_seq
                FROM plan_artifacts
                WHERE namespace = ?
                ORDER BY stored_seq ASC
                LIMIT ?
            )
            """,
            (self.namespace, excess),
        )

    def remember(self, plan: PlanArtifact) -> str:
        key = plan.exact_key
        payload = _artifact_payload(plan)
        artifact_json = canonical_json(payload)
        artifact_digest = sha256(payload)
        signature = plan.applicability.retrieval_signature
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO plan_artifacts (
                    namespace,
                    exact_key,
                    retrieval_signature,
                    artifact_json,
                    artifact_digest,
                    schema_version
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(namespace, exact_key) DO UPDATE SET
                    retrieval_signature = excluded.retrieval_signature,
                    artifact_json = excluded.artifact_json,
                    artifact_digest = excluded.artifact_digest,
                    schema_version = excluded.schema_version
                """,
                (
                    self.namespace,
                    key,
                    signature,
                    artifact_json,
                    artifact_digest,
                    _ARTIFACT_SCHEMA_VERSION,
                ),
            )
            self._enforce_capacity(connection)
            connection.commit()
        return key

    def _decode_row(
        self,
        exact_key: str,
        artifact_json: str,
        artifact_digest: str,
        schema_version: int,
    ) -> PlanArtifact:
        if schema_version != _ARTIFACT_SCHEMA_VERSION:
            raise PersistentPlanCorruption(
                f"REFUSED:PERSISTED_PLAN_SCHEMA_VERSION:{schema_version}"
            )
        try:
            payload = json.loads(artifact_json)
        except json.JSONDecodeError as exc:
            raise PersistentPlanCorruption(
                "REFUSED:PERSISTED_PLAN_JSON_CORRUPT"
            ) from exc
        if sha256(payload) != artifact_digest:
            raise PersistentPlanCorruption("REFUSED:PERSISTED_PLAN_DIGEST_MISMATCH")
        plan = _decode_artifact(payload)
        if plan.exact_key != exact_key:
            raise PersistentPlanCorruption("REFUSED:PERSISTED_PLAN_EXACT_KEY_MISMATCH")
        return plan

    def exact(self, key: str) -> PlanArtifact | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT exact_key, artifact_json, artifact_digest, schema_version
                FROM plan_artifacts
                WHERE namespace = ? AND exact_key = ?
                """,
                (self.namespace, key),
            ).fetchone()
        if row is None:
            return None
        return self._decode_row(*row)

    def retrieve_candidates(self, context: PlanningContext) -> tuple[PlanArtifact, ...]:
        signature = _context_signature(context)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT exact_key, artifact_json, artifact_digest, schema_version
                FROM plan_artifacts
                WHERE namespace = ? AND retrieval_signature = ?
                ORDER BY exact_key
                """,
                (self.namespace, signature),
            ).fetchall()
        return tuple(self._decode_row(*row) for row in rows)

    def count(self) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) FROM plan_artifacts WHERE namespace = ?",
                (self.namespace,),
            ).fetchone()
        assert row is not None
        return int(row[0])
