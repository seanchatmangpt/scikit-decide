# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""SQL queries over the schema written by :mod:`autofde_lab.ocel.sqlite_store`.

Three named functions, each one real SQL query against a plain
``sqlite3.Connection`` -- no ORM, no generic query framework. They answer the
exact questions raised in the session that motivated this module: "which
solvers reliably time out," "refusal-rate trend," and "what happened, in
order, inside one session." Not a conformance checker; see
``src/autofde_lab/ocel/powl_replay.py`` (a separate, larger piece) for
anything beyond ordering events.
"""

from __future__ import annotations

import sqlite3

__all__ = [
    "solver_timeout_rates",
    "domain_refusal_rate",
    "session_event_order",
    "all_session_ids",
]


def solver_timeout_rates(conn: sqlite3.Connection) -> list[dict]:
    """Per-``Solver`` object: ``TIMEOUT`` count / total ``decision_solve`` count.

    Joins ``decision_solve`` events' ``standing`` attribute (``attributes``,
    ``owner_table='event'``) to their linked ``Solver`` objects (via
    ``event_object_links`` -> ``objects`` where ``object_type='Solver'``).
    """
    rows = conn.execute(
        """
        SELECT
            o.id AS solver_id,
            COUNT(*) AS total,
            SUM(CASE WHEN a.value_json = '"TIMEOUT"' THEN 1 ELSE 0 END) AS timeouts
        FROM events e
        JOIN attributes a
            ON a.owner_table = 'event' AND a.owner_id = e.id AND a.key = 'standing'
        JOIN event_object_links l ON l.event_id = e.id
        JOIN objects o ON o.id = l.object_id AND o.object_type = 'Solver'
        WHERE e.activity = 'decision_solve'
        GROUP BY o.id
        ORDER BY o.id
        """
    ).fetchall()

    return [
        {
            "solver_id": row["solver_id"],
            "total": row["total"],
            "timeouts": row["timeouts"],
            "timeout_rate": (row["timeouts"] / row["total"]) if row["total"] else 0.0,
        }
        for row in rows
    ]


def domain_refusal_rate(conn: sqlite3.Connection, since_ns: int | None = None) -> list[dict]:
    """Per-``Domain`` object: ``REFUSED`` fraction across ``decision_match``/``decision_solve``.

    Optionally windowed to events with ``timestamp_ns >= since_ns``.
    """
    params: list[object] = []
    time_filter = ""
    if since_ns is not None:
        time_filter = "AND e.timestamp_ns >= ?"
        params.append(since_ns)

    rows = conn.execute(
        f"""
        SELECT
            o.id AS domain_id,
            COUNT(*) AS total,
            SUM(CASE WHEN a.value_json = '"REFUSED"' THEN 1 ELSE 0 END) AS refusals
        FROM events e
        JOIN attributes a
            ON a.owner_table = 'event' AND a.owner_id = e.id AND a.key = 'standing'
        JOIN event_object_links l ON l.event_id = e.id
        JOIN objects o ON o.id = l.object_id AND o.object_type = 'Domain'
        WHERE e.activity IN ('decision_match', 'decision_solve') {time_filter}
        GROUP BY o.id
        ORDER BY o.id
        """,
        params,
    ).fetchall()

    return [
        {
            "domain_id": row["domain_id"],
            "total": row["total"],
            "refusals": row["refusals"],
            "refusal_rate": (row["refusals"] / row["total"]) if row["total"] else 0.0,
        }
        for row in rows
    ]


def all_session_ids(conn: sqlite3.Connection) -> list[str]:
    """Every recorded ``MCPSession`` object id, for corpus-wide (not single-session)
    mining -- e.g. ``wasm4pm_bridge.discover_and_check(conn, all_session_ids(conn))``.
    """
    rows = conn.execute(
        "SELECT id FROM objects WHERE object_type = 'MCPSession' ORDER BY id"
    ).fetchall()
    return [row["id"] for row in rows]


def session_event_order(conn: sqlite3.Connection, session_id: str) -> list[dict]:
    """One ``MCPSession``'s events, in real ``timestamp_ns`` order.

    Each row includes the event's own linked object ids (including the
    session object itself), gathered via ``event_object_links``.
    """
    session_row = conn.execute(
        "SELECT id FROM objects WHERE id = ? AND object_type = 'MCPSession'",
        (session_id,),
    ).fetchone()
    if session_row is None:
        return []

    event_rows = conn.execute(
        """
        SELECT DISTINCT e.id AS event_id, e.activity AS activity, e.timestamp_ns AS timestamp_ns
        FROM events e
        JOIN event_object_links l ON l.event_id = e.id
        WHERE l.object_id = ?
        ORDER BY e.timestamp_ns ASC, e.id ASC
        """,
        (session_id,),
    ).fetchall()

    results: list[dict] = []
    for row in event_rows:
        object_ids = [
            r["object_id"]
            for r in conn.execute(
                "SELECT object_id FROM event_object_links WHERE event_id = ? ORDER BY object_id",
                (row["event_id"],),
            ).fetchall()
        ]
        results.append(
            {
                "event_id": row["event_id"],
                "activity": row["activity"],
                "timestamp_ns": row["timestamp_ns"],
                "object_ids": object_ids,
            }
        )
    return results
