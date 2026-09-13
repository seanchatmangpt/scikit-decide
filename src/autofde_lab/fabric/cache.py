# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Receipt-safe 80/20 ERRC cache for planning artifacts and refusals.

ERRC means:

* Eliminate exact repeated solves.
* Reduce repeated registry matching and construction.
* Raise evidence by binding all material identities.
* Create a measured hot set and deterministic refusal memory.

The cache stores JSON artifacts, never live solver objects, credentials, or
actuation authority.
"""

from __future__ import annotations

import json
import math
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from threading import RLock
from typing import Any, Iterator

from autofde_lab.fabric.canonical import canonical_json

# Persisted envelope identifier -- see autofde_lab.schema_ids.
from autofde_lab.schema_ids import (  # noqa: E402
    ACCEPTED_CACHE_SCHEMAS,
    CACHE_SCHEMA as _CACHE_SCHEMA,
    LEGACY_CACHE_SCHEMAS,
)


class SQLiteERRCCache:
    """A small durable cache with Pareto hot-set accounting."""

    def __init__(self, path: str | Path | None = None) -> None:
        configured = path or os.environ.get("SKDECIDE_FABRIC_CACHE")
        if configured is None:
            configured = Path.home() / ".cache" / "scikit-decide" / "fabric.sqlite3"
        self.path = str(configured)
        if self.path != ":memory:":
            Path(self.path).expanduser().parent.mkdir(parents=True, exist_ok=True)
            self.path = str(Path(self.path).expanduser())
        self._lock = RLock()
        self._connection = sqlite3.connect(self.path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._initialize()

    def _initialize(self) -> None:
        with self._transaction() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS entries (
                    cache_key TEXT PRIMARY KEY,
                    namespace TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_ns INTEGER NOT NULL,
                    expires_ns INTEGER,
                    hit_count INTEGER NOT NULL DEFAULT 0,
                    last_hit_ns INTEGER
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS counters (
                    name TEXT PRIMARY KEY,
                    value INTEGER NOT NULL
                )
                """
            )

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            try:
                yield self._connection
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise

    def _bump(self, name: str, amount: int = 1) -> None:
        self._connection.execute(
            """
            INSERT INTO counters(name, value) VALUES (?, ?)
            ON CONFLICT(name) DO UPDATE SET value = value + excluded.value
            """,
            (name, amount),
        )

    def get(self, cache_key: str) -> dict[str, Any] | None:
        """Return a cached JSON artifact and record hit/miss evidence."""
        now = time.time_ns()
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT * FROM entries WHERE cache_key = ?", (cache_key,)
            ).fetchone()
            if row is None:
                self._bump("misses")
                return None
            expires_ns = row["expires_ns"]
            if expires_ns is not None and int(expires_ns) <= now:
                connection.execute(
                    "DELETE FROM entries WHERE cache_key = ?", (cache_key,)
                )
                self._bump("expired")
                self._bump("misses")
                return None
            connection.execute(
                """
                UPDATE entries
                SET hit_count = hit_count + 1, last_hit_ns = ?
                WHERE cache_key = ?
                """,
                (now, cache_key),
            )
            self._bump("hits")
            return dict(json.loads(str(row["payload_json"])))

    def put(
        self,
        cache_key: str,
        namespace: str,
        payload: dict[str, Any],
        *,
        ttl_seconds: float | None = None,
    ) -> None:
        """Store a canonical JSON artifact under an already-bound identity."""
        now = time.time_ns()
        expires_ns = (
            None if ttl_seconds is None else now + int(ttl_seconds * 1_000_000_000)
        )
        payload_json = canonical_json(payload)
        with self._transaction() as connection:
            connection.execute(
                """
                INSERT INTO entries(
                    cache_key, namespace, payload_json, created_ns, expires_ns,
                    hit_count, last_hit_ns
                ) VALUES (?, ?, ?, ?, ?, 0, NULL)
                ON CONFLICT(cache_key) DO UPDATE SET
                    namespace = excluded.namespace,
                    payload_json = excluded.payload_json,
                    created_ns = excluded.created_ns,
                    expires_ns = excluded.expires_ns,
                    hit_count = 0,
                    last_hit_ns = NULL
                """,
                (cache_key, namespace, payload_json, now, expires_ns),
            )
            self._bump("writes")

    def delete(self, cache_key: str) -> bool:
        """Delete one cache identity."""
        with self._transaction() as connection:
            cursor = connection.execute(
                "DELETE FROM entries WHERE cache_key = ?", (cache_key,)
            )
            return cursor.rowcount > 0

    def clear(self) -> None:
        """Delete cached artifacts and counters."""
        with self._transaction() as connection:
            connection.execute("DELETE FROM entries")
            connection.execute("DELETE FROM counters")

    def stats(self) -> dict[str, Any]:
        """Return durable cache and avoidance counters."""
        with self._lock:
            entries = self._connection.execute(
                "SELECT COUNT(*) AS count, COALESCE(SUM(hit_count), 0) AS entry_hits FROM entries"
            ).fetchone()
            counters = {
                str(row["name"]): int(row["value"])
                for row in self._connection.execute("SELECT name, value FROM counters")
            }
            namespaces = {
                str(row["namespace"]): int(row["count"])
                for row in self._connection.execute(
                    "SELECT namespace, COUNT(*) AS count FROM entries GROUP BY namespace"
                )
            }
        hits = int(counters.get("hits", 0))
        misses = int(counters.get("misses", 0))
        attempts = hits + misses
        return {
            "schema": _CACHE_SCHEMA,
            "path": self.path,
            "entries": int(entries["count"]),
            "entry_hits": int(entries["entry_hits"]),
            "hits": hits,
            "misses": misses,
            "writes": int(counters.get("writes", 0)),
            "expired": int(counters.get("expired", 0)),
            "hit_rate": 0.0 if attempts == 0 else hits / attempts,
            "namespaces": namespaces,
        }

    def hotset(self) -> dict[str, Any]:
        """Measure whether the top 20% of artifacts account for 80% of reuse."""
        with self._lock:
            rows = list(
                self._connection.execute(
                    """
                    SELECT cache_key, namespace, hit_count
                    FROM entries
                    WHERE hit_count > 0
                    ORDER BY hit_count DESC, cache_key ASC
                    """
                )
            )
        if not rows:
            return {
                "schema": _CACHE_SCHEMA,
                "active_entries": 0,
                "total_hits": 0,
                "top_20_percent_count": 0,
                "top_20_percent_hit_share": 0.0,
                "pareto_80_count": 0,
                "pareto_80_fraction": 0.0,
                "pareto_target_reached_within_20_percent": False,
                "entries": [],
            }

        total_hits = sum(int(row["hit_count"]) for row in rows)
        top_count = max(1, math.ceil(len(rows) * 0.20))
        top_rows = rows[:top_count]
        top_hits = sum(int(row["hit_count"]) for row in top_rows)

        cumulative = 0
        pareto_count = 0
        for row in rows:
            cumulative += int(row["hit_count"])
            pareto_count += 1
            if cumulative / total_hits >= 0.80:
                break

        return {
            "schema": _CACHE_SCHEMA,
            "active_entries": len(rows),
            "total_hits": total_hits,
            "top_20_percent_count": top_count,
            "top_20_percent_hit_share": top_hits / total_hits,
            "pareto_80_count": pareto_count,
            "pareto_80_fraction": pareto_count / len(rows),
            "pareto_target_reached_within_20_percent": pareto_count <= top_count,
            "entries": [
                {
                    "cache_key": str(row["cache_key"]),
                    "namespace": str(row["namespace"]),
                    "hit_count": int(row["hit_count"]),
                }
                for row in top_rows
            ],
        }

    def close(self) -> None:
        """Close the durable connection."""
        with self._lock:
            self._connection.close()

    def __enter__(self) -> SQLiteERRCCache:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
