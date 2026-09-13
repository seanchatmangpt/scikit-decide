# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Tests for :mod:`autofde_lab.ocel.queries` against a small synthetic log.

Builds a log via ``OcelLog.new`` + ``append_tool_call_event`` (the same
helper real MCP-session logging uses), converts to SQLite via
:mod:`autofde_lab.ocel.sqlite_store`, and asserts real expected aggregates.
"""

from __future__ import annotations

import sqlite3

import pytest

from autofde_lab.ocel.log import OcelLog
from autofde_lab.ocel.mcp_session import append_tool_call_event
from autofde_lab.ocel.model import OcelAttribute, OcelAttributeValue, OcelObject
from autofde_lab.ocel.queries import (
    all_session_ids,
    domain_refusal_rate,
    session_event_order,
    solver_timeout_rates,
)
from autofde_lab.ocel.sqlite_store import to_sqlite


def _build_log() -> OcelLog:
    log = OcelLog.new(
        objects=[
            OcelObject(
                "session-1",
                "MCPSession",
                (OcelAttribute("server", OcelAttributeValue.string("scikit-decide-fabric")),),
            ),
            OcelObject("domain-Maze", "Domain", (OcelAttribute("name", OcelAttributeValue.string("Maze")),)),
            OcelObject(
                "domain-MasterMind",
                "Domain",
                (OcelAttribute("name", OcelAttributeValue.string("MasterMind")),),
            ),
            OcelObject("solver-Astar", "Solver", (OcelAttribute("name", OcelAttributeValue.string("Astar")),)),
            OcelObject("solver-MCTS", "Solver", (OcelAttribute("name", OcelAttributeValue.string("MCTS")),)),
        ]
    )

    # Maze: Astar solves twice (SOLVED, SOLVED); MCTS times out twice
    # (TIMEOUT, TIMEOUT) -> Astar 0/2 timeout, MCTS 2/2 timeout.
    log = append_tool_call_event(
        log,
        event_id="evt-match-maze",
        activity="decision_match",
        object_ids=["session-1", "domain-Maze"],
        outcome={"standing": "MATCHED"},
        timestamp_ns=1_000,
    )
    log = append_tool_call_event(
        log,
        event_id="evt-solve-maze-astar-0",
        activity="decision_solve",
        object_ids=["session-1", "domain-Maze", "solver-Astar"],
        outcome={"standing": "SOLVED", "elapsed_s": 0.1},
        timestamp_ns=2_000,
    )
    log = append_tool_call_event(
        log,
        event_id="evt-solve-maze-astar-1",
        activity="decision_solve",
        object_ids=["session-1", "domain-Maze", "solver-Astar"],
        outcome={"standing": "SOLVED", "elapsed_s": 0.1},
        timestamp_ns=3_000,
    )
    log = append_tool_call_event(
        log,
        event_id="evt-solve-maze-mcts-0",
        activity="decision_solve",
        object_ids=["session-1", "domain-Maze", "solver-MCTS"],
        outcome={"standing": "TIMEOUT", "elapsed_s": 30.0},
        timestamp_ns=4_000,
    )
    log = append_tool_call_event(
        log,
        event_id="evt-solve-maze-mcts-1",
        activity="decision_solve",
        object_ids=["session-1", "domain-Maze", "solver-MCTS"],
        outcome={"standing": "TIMEOUT", "elapsed_s": 30.0},
        timestamp_ns=5_000,
    )

    # MasterMind: match refused, one solve refused, one bounded.
    log = append_tool_call_event(
        log,
        event_id="evt-match-mastermind",
        activity="decision_match",
        object_ids=["session-1", "domain-MasterMind"],
        outcome={"standing": "REFUSED", "detail": "no compatible solver"},
        timestamp_ns=6_000,
    )
    log = append_tool_call_event(
        log,
        event_id="evt-solve-mastermind-astar-0",
        activity="decision_solve",
        object_ids=["session-1", "domain-MasterMind", "solver-Astar"],
        outcome={"standing": "REFUSED", "detail": "domain requirements not met"},
        timestamp_ns=7_000,
    )
    log = append_tool_call_event(
        log,
        event_id="evt-solve-mastermind-astar-1",
        activity="decision_solve",
        object_ids=["session-1", "domain-MasterMind", "solver-Astar"],
        outcome={"standing": "BOUNDED", "elapsed_s": 0.2},
        timestamp_ns=8_000,
    )

    return log


@pytest.fixture()
def conn(tmp_path) -> sqlite3.Connection:
    log = _build_log()
    db_path = tmp_path / "queries_test.sqlite"
    to_sqlite(log, db_path)
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    try:
        yield connection
    finally:
        connection.close()


def test_solver_timeout_rates(conn: sqlite3.Connection) -> None:
    rows = {row["solver_id"]: row for row in solver_timeout_rates(conn)}

    assert rows["solver-Astar"]["total"] == 4  # 2 Maze solves + 2 MasterMind solves
    assert rows["solver-Astar"]["timeouts"] == 0
    assert rows["solver-Astar"]["timeout_rate"] == 0.0

    assert rows["solver-MCTS"]["total"] == 2
    assert rows["solver-MCTS"]["timeouts"] == 2
    assert rows["solver-MCTS"]["timeout_rate"] == 1.0


def test_domain_refusal_rate(conn: sqlite3.Connection) -> None:
    rows = {row["domain_id"]: row for row in domain_refusal_rate(conn)}

    # Maze: 1 match (MATCHED) + 4 solves (SOLVED/SOLVED/TIMEOUT/TIMEOUT) -> 0 refused / 5
    assert rows["domain-Maze"]["total"] == 5
    assert rows["domain-Maze"]["refusals"] == 0
    assert rows["domain-Maze"]["refusal_rate"] == 0.0

    # MasterMind: 1 match (REFUSED) + 2 solves (REFUSED, BOUNDED) -> 2 refused / 3
    assert rows["domain-MasterMind"]["total"] == 3
    assert rows["domain-MasterMind"]["refusals"] == 2
    assert rows["domain-MasterMind"]["refusal_rate"] == pytest.approx(2 / 3)


def test_domain_refusal_rate_since_ns_filters_by_time(conn: sqlite3.Connection) -> None:
    # Only events at or after timestamp_ns=6000 (the MasterMind events).
    rows = {row["domain_id"]: row for row in domain_refusal_rate(conn, since_ns=6_000)}

    assert "domain-Maze" not in rows
    assert rows["domain-MasterMind"]["total"] == 3
    assert rows["domain-MasterMind"]["refusals"] == 2


def test_session_event_order(conn: sqlite3.Connection) -> None:
    rows = session_event_order(conn, "session-1")

    assert len(rows) == 8
    # Real timestamp order, not insertion order coincidence -- check monotonic.
    timestamps = [row["timestamp_ns"] for row in rows]
    assert timestamps == sorted(timestamps)
    assert rows[0]["event_id"] == "evt-match-maze"
    assert rows[0]["activity"] == "decision_match"
    assert set(rows[0]["object_ids"]) == {"session-1", "domain-Maze"}
    assert rows[-1]["event_id"] == "evt-solve-mastermind-astar-1"
    assert set(rows[-1]["object_ids"]) == {"session-1", "domain-MasterMind", "solver-Astar"}


def test_session_event_order_unknown_session_returns_empty(conn: sqlite3.Connection) -> None:
    assert session_event_order(conn, "no-such-session") == []


def test_all_session_ids(conn: sqlite3.Connection) -> None:
    assert all_session_ids(conn) == ["session-1"]
