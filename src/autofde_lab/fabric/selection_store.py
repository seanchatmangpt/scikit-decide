"""Append-only SQLite evidence store for empirical planner selection.

Unlike the ERRC artifact cache, this ledger never overwrites an observation.
Exact duplicate receipts are idempotent, but distinct repeated runs accumulate
because repetition is evidence for HOT standing.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from threading import RLock
from typing import Iterator

from autofde_lab.fabric.selection import (
    EmpiricalPlannerIndex,
    EvidenceStanding,
    PlannerReceipt,
)


def _receipt_json(receipt: PlannerReceipt) -> str:
    row = asdict(receipt)
    row["standing"] = receipt.standing.value
    return json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def receipt_digest(receipt: PlannerReceipt, *, run_nonce: str) -> str:
    """Bind an observation to its payload and caller-provided run identity."""
    payload = f"{run_nonce}\n{_receipt_json(receipt)}".encode()
    return hashlib.sha256(payload).hexdigest()


class SQLitePlannerEvidenceStore:
    """Durable append-only planner receipt ledger."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        if self.path != ":memory:":
            path_obj = Path(self.path).expanduser()
            path_obj.parent.mkdir(parents=True, exist_ok=True)
            self.path = str(path_obj)
        self._lock = RLock()
        self._connection = sqlite3.connect(self.path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        if self.path != ":memory:":
            self._connection.execute("PRAGMA journal_mode=WAL")
        self._initialize()

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            try:
                yield self._connection
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise

    def _initialize(self) -> None:
        with self._transaction() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS planner_receipts (
                    receipt_digest TEXT PRIMARY KEY,
                    run_nonce TEXT NOT NULL,
                    signature_key TEXT NOT NULL,
                    planner_id TEXT NOT NULL,
                    objective TEXT NOT NULL,
                    environment TEXT NOT NULL,
                    hardware TEXT NOT NULL,
                    success INTEGER NOT NULL,
                    verified INTEGER NOT NULL,
                    standing TEXT NOT NULL,
                    wall_time_s REAL NOT NULL,
                    cost_usd REAL NOT NULL,
                    memory_bytes INTEGER NOT NULL,
                    quality REAL NOT NULL,
                    human_interventions INTEGER NOT NULL,
                    frontier_tokens INTEGER NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS planner_receipts_lookup
                ON planner_receipts(
                    signature_key, objective, environment, hardware, planner_id
                )
                """
            )

    def append(self, receipt: PlannerReceipt, *, run_nonce: str) -> bool:
        """Append one observation. Return False only for an exact replay."""
        if not run_nonce.strip():
            raise ValueError("run_nonce must be non-empty")
        digest = receipt_digest(receipt, run_nonce=run_nonce)
        row = asdict(receipt)
        row["standing"] = receipt.standing.value
        with self._transaction() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO planner_receipts(
                    receipt_digest, run_nonce, signature_key, planner_id,
                    objective, environment, hardware, success, verified,
                    standing, wall_time_s, cost_usd, memory_bytes, quality,
                    human_interventions, frontier_tokens
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    digest,
                    run_nonce,
                    row["signature_key"],
                    row["planner_id"],
                    row["objective"],
                    row["environment"],
                    row["hardware"],
                    int(bool(row["success"])),
                    int(bool(row["verified"])),
                    row["standing"],
                    row["wall_time_s"],
                    row["cost_usd"],
                    row["memory_bytes"],
                    row["quality"],
                    row["human_interventions"],
                    row["frontier_tokens"],
                ),
            )
            return cursor.rowcount == 1

    def receipts(
        self, *, signature_key: str | None = None
    ) -> tuple[PlannerReceipt, ...]:
        query = "SELECT * FROM planner_receipts"
        params: tuple[object, ...] = ()
        if signature_key is not None:
            query += " WHERE signature_key = ?"
            params = (signature_key,)
        query += " ORDER BY rowid ASC"
        with self._lock:
            rows = tuple(self._connection.execute(query, params))
        return tuple(
            PlannerReceipt(
                signature_key=str(row["signature_key"]),
                planner_id=str(row["planner_id"]),
                objective=str(row["objective"]),
                environment=str(row["environment"]),
                hardware=str(row["hardware"]),
                success=bool(row["success"]),
                verified=bool(row["verified"]),
                standing=EvidenceStanding(str(row["standing"])),
                wall_time_s=float(row["wall_time_s"]),
                cost_usd=float(row["cost_usd"]),
                memory_bytes=int(row["memory_bytes"]),
                quality=float(row["quality"]),
                human_interventions=int(row["human_interventions"]),
                frontier_tokens=int(row["frontier_tokens"]),
            )
            for row in rows
        )

    def hydrate(self, index: EmpiricalPlannerIndex) -> int:
        rows = self.receipts()
        for receipt in rows:
            index.record(receipt)
        return len(rows)

    def count(self) -> int:
        with self._lock:
            row = self._connection.execute(
                "SELECT COUNT(*) AS count FROM planner_receipts"
            ).fetchone()
        return int(row["count"])

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def __enter__(self) -> "SQLitePlannerEvidenceStore":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
