"""Persistent retention of ``UNCLASSIFIED`` scan results as taxonomy-growth candidates.

``taxonomy.classify()`` already returns ``UNCLASSIFIED`` honestly, rather than
guessing, for any :class:`~autofde_lab_planner.scanner.models.Anomaly` that
doesn't match a known ``inject_*`` signature (see that module's docstring).
Until this module, an ``UNCLASSIFIED`` result was simply discarded by every
caller -- the anomaly that revealed a taxonomy gap left no trace once the
scan finished. That is exactly the kind of loss
``.claude/rules/absence-is-not-evidence.md`` names: an unclassified signal is
not "nothing happened", it is a real, typed observation (the taxonomy does
not yet cover this anomaly shape) that deserves to survive as its own
artifact rather than being coerced into silence.

This module is deliberately mechanism-only: it persists real
``UNCLASSIFIED`` :class:`Anomaly` records so a human (or a later, explicit
taxonomy-extension pass) can review them and decide whether a new ``inject_*``
category is warranted. It does not itself guess a category, does not
synthesize example anomalies, and does not promote anything into
``taxonomy.py`` automatically -- that would be exactly the guessing
``classify()`` already refuses to do.

Style mirrors :mod:`autofde_lab.case_library.sqlite_store`: stdlib
``sqlite3``, ``sqlite3.connect(path, check_same_thread=False)``,
``row_factory = sqlite3.Row``, idempotent ``CREATE TABLE IF NOT EXISTS``, a
``_transaction()`` contextmanager, and a ``:memory:``-first design -- a
fresh, unrelated schema reusing only the persistence *pattern*.

Schema:

.. code-block:: sql

    CREATE TABLE taxonomy_growth_candidates(
        candidate_id TEXT PRIMARY KEY,
        kind TEXT NOT NULL,
        object_name TEXT NOT NULL,
        namespace TEXT NOT NULL,
        relation_class TEXT NOT NULL,
        field TEXT NOT NULL,
        observed TEXT NOT NULL,
        expected TEXT,
        detail TEXT NOT NULL,
        first_seen_at TEXT NOT NULL
    );
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator
from uuid import uuid4

from autofde_lab_planner.scanner.models import Anomaly
from autofde_lab_planner.scanner.taxonomy import UNCLASSIFIED, classify

__all__ = ["TaxonomyGrowthCandidate", "TaxonomyGrowthStore", "retain_if_unclassified"]


class TaxonomyGrowthCandidate:
    """One persisted ``UNCLASSIFIED`` anomaly, retained for taxonomy review.

    :param candidate_id: Stable identifier, primary key in the store.
    :param anomaly: The real :class:`Anomaly` that ``classify()`` could not
        place in the known taxonomy.
    :param first_seen_at: ISO-8601 UTC timestamp this candidate was first
        retained (never overwritten by a later ``put`` of the same
        ``candidate_id`` -- see :meth:`TaxonomyGrowthStore.put`).
    """

    __slots__ = ("candidate_id", "anomaly", "first_seen_at")

    def __init__(self, candidate_id: str, anomaly: Anomaly, first_seen_at: str) -> None:
        self.candidate_id = candidate_id
        self.anomaly = anomaly
        self.first_seen_at = first_seen_at

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, TaxonomyGrowthCandidate):
            return NotImplemented
        return (
            self.candidate_id == other.candidate_id
            and self.anomaly == other.anomaly
            and self.first_seen_at == other.first_seen_at
        )

    def __repr__(self) -> str:  # pragma: no cover -- debugging aid only
        return (
            f"TaxonomyGrowthCandidate(candidate_id={self.candidate_id!r}, "
            f"anomaly={self.anomaly!r}, first_seen_at={self.first_seen_at!r})"
        )


def _initialize(connection: sqlite3.Connection) -> None:
    connection.execute(
        "CREATE TABLE IF NOT EXISTS taxonomy_growth_candidates("
        "candidate_id TEXT PRIMARY KEY, "
        "kind TEXT NOT NULL, "
        "object_name TEXT NOT NULL, "
        "namespace TEXT NOT NULL, "
        "relation_class TEXT NOT NULL, "
        "field TEXT NOT NULL, "
        "observed TEXT NOT NULL, "
        "expected TEXT, "
        "detail TEXT NOT NULL, "
        "first_seen_at TEXT NOT NULL"
        ")"
    )


@contextmanager
def _transaction(connection: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def _candidate_to_row(
    candidate: TaxonomyGrowthCandidate,
) -> tuple[str, str, str, str, str, str, str, str | None, str, str]:
    anomaly = candidate.anomaly
    return (
        candidate.candidate_id,
        anomaly.kind,
        anomaly.object_name,
        anomaly.namespace,
        anomaly.relation_class,
        anomaly.field,
        anomaly.observed,
        anomaly.expected,
        anomaly.detail,
        candidate.first_seen_at,
    )


def _row_to_candidate(row: sqlite3.Row) -> TaxonomyGrowthCandidate:
    anomaly = Anomaly(
        kind=row["kind"],
        object_name=row["object_name"],
        namespace=row["namespace"],
        relation_class=row["relation_class"],
        field=row["field"],
        observed=row["observed"],
        expected=row["expected"],
        detail=row["detail"],
    )
    return TaxonomyGrowthCandidate(
        candidate_id=row["candidate_id"],
        anomaly=anomaly,
        first_seen_at=row["first_seen_at"],
    )


class TaxonomyGrowthStore:
    """A persistent, SQLite-backed store of :class:`TaxonomyGrowthCandidate`
    records -- ``UNCLASSIFIED`` scan results kept as evidence that the
    taxonomy has a gap, rather than discarded.

    :param path: Filesystem path to the SQLite database, or ``":memory:"``.
        Parent directories are created if missing.
    """

    def __init__(
        self, path: str | Path = "docs/case_library/taxonomy_growth.sqlite"
    ) -> None:
        self._path = str(path)
        if self._path != ":memory:":
            Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self._path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        _initialize(self._connection)
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "TaxonomyGrowthStore":
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()

    def put(self, candidate: TaxonomyGrowthCandidate) -> None:
        """Insert ``candidate``, keyed by ``candidate.candidate_id``.

        Uses ``INSERT OR IGNORE`` (not ``OR REPLACE``): a taxonomy-growth
        candidate records *first sighting* of a gap, so a repeat retain of
        the same ``candidate_id`` must not overwrite the original
        ``first_seen_at``.
        """
        with _transaction(self._connection) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO taxonomy_growth_candidates("
                "candidate_id, kind, object_name, namespace, relation_class, "
                "field, observed, expected, detail, first_seen_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                _candidate_to_row(candidate),
            )

    def get(self, candidate_id: str) -> TaxonomyGrowthCandidate | None:
        """Return the candidate stored under ``candidate_id``, or ``None``."""
        cursor = self._connection.execute(
            "SELECT * FROM taxonomy_growth_candidates WHERE candidate_id = ?",
            (candidate_id,),
        )
        row = cursor.fetchone()
        return None if row is None else _row_to_candidate(row)

    def all_candidates(self) -> list[TaxonomyGrowthCandidate]:
        """Return every stored candidate, ordered by ``candidate_id``."""
        cursor = self._connection.execute(
            "SELECT * FROM taxonomy_growth_candidates ORDER BY candidate_id"
        )
        return [_row_to_candidate(row) for row in cursor.fetchall()]

    def __len__(self) -> int:
        cursor = self._connection.execute(
            "SELECT COUNT(*) AS n FROM taxonomy_growth_candidates"
        )
        return int(cursor.fetchone()["n"])


def retain_if_unclassified(
    anomaly: Anomaly,
    store: TaxonomyGrowthStore,
    *,
    candidate_id: str | None = None,
) -> TaxonomyGrowthCandidate | None:
    """Run the real ``classify()`` against ``anomaly``; retain it as a
    taxonomy-growth candidate iff the real result is ``UNCLASSIFIED``.

    Returns the persisted :class:`TaxonomyGrowthCandidate`, or ``None`` when
    ``anomaly`` classified successfully -- a classified anomaly is not a
    taxonomy gap and has nothing to retain here (it belongs in the case
    library's own retain path instead).
    """
    if classify(anomaly) != UNCLASSIFIED:
        return None
    candidate = TaxonomyGrowthCandidate(
        candidate_id=candidate_id or f"unclassified-{uuid4().hex}",
        anomaly=anomaly,
        first_seen_at=datetime.now(timezone.utc).isoformat(),
    )
    store.put(candidate)
    return candidate
