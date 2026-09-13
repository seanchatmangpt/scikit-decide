# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Real tests for :mod:`autofde_lab.ocel.resource_perspective`.

Builds a synthetic two-session log with a deliberate solver handover in one
session (Astar hands off to MCTS on retry) and none in the other (Astar
solves twice), and asserts ``handover_of_work`` reports exactly the expected
edge and count -- a real, checkable claim, not a shape-only test.
"""

from __future__ import annotations

import sqlite3

import pytest

from autofde_lab.ocel.log import OcelLog
from autofde_lab.ocel.mcp_session import append_tool_call_event
from autofde_lab.ocel.model import OcelAttribute, OcelAttributeValue, OcelObject
from autofde_lab.ocel.resource_perspective import HandoverEdge, handover_of_work
from autofde_lab.ocel.sqlite_store import to_sqlite


def _build_log() -> OcelLog:
    log = OcelLog.new(
        objects=[
            OcelObject(
                "session-1",
                "MCPSession",
                (OcelAttribute("server", OcelAttributeValue.string("scikit-decide-fabric")),),
            ),
            OcelObject(
                "session-2",
                "MCPSession",
                (OcelAttribute("server", OcelAttributeValue.string("scikit-decide-fabric")),),
            ),
            OcelObject("domain-Maze", "Domain", (OcelAttribute("name", OcelAttributeValue.string("Maze")),)),
            OcelObject("solver-Astar", "Solver", (OcelAttribute("name", OcelAttributeValue.string("Astar")),)),
            OcelObject("solver-MCTS", "Solver", (OcelAttribute("name", OcelAttributeValue.string("MCTS")),)),
        ]
    )

    # session-1: catalog (no solver) -> solve/Astar -> solve/MCTS (retry) -> real handover.
    log = append_tool_call_event(
        log, event_id="s1-catalog", activity="decision_catalog",
        object_ids=["session-1"], outcome={"standing": "OK"}, timestamp_ns=0,
    )
    log = append_tool_call_event(
        log, event_id="s1-solve-astar", activity="decision_solve",
        object_ids=["session-1", "domain-Maze", "solver-Astar"],
        outcome={"standing": "TIMEOUT"}, timestamp_ns=1_000,
    )
    log = append_tool_call_event(
        log, event_id="s1-solve-mcts", activity="decision_solve",
        object_ids=["session-1", "domain-Maze", "solver-MCTS"],
        outcome={"standing": "SOLVED"}, timestamp_ns=2_000,
    )

    # session-2: catalog (no solver) -> solve/Astar -> solve/Astar again -> no handover.
    log = append_tool_call_event(
        log, event_id="s2-catalog", activity="decision_catalog",
        object_ids=["session-2"], outcome={"standing": "OK"}, timestamp_ns=0,
    )
    log = append_tool_call_event(
        log, event_id="s2-solve-astar-0", activity="decision_solve",
        object_ids=["session-2", "domain-Maze", "solver-Astar"],
        outcome={"standing": "BOUNDED"}, timestamp_ns=1_000,
    )
    log = append_tool_call_event(
        log, event_id="s2-solve-astar-1", activity="decision_solve",
        object_ids=["session-2", "domain-Maze", "solver-Astar"],
        outcome={"standing": "SOLVED"}, timestamp_ns=2_000,
    )

    return log


@pytest.fixture()
def conn(tmp_path) -> sqlite3.Connection:
    log = _build_log()
    db_path = tmp_path / "resource_perspective_test.sqlite"
    to_sqlite(log, db_path)
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    try:
        yield connection
    finally:
        connection.close()


def test_handover_of_work_reports_the_real_solver_switch(conn: sqlite3.Connection) -> None:
    edges = handover_of_work(conn)

    assert edges == [
        HandoverEdge(from_solver="solver-Astar", to_solver="solver-MCTS", count=1)
    ]


def test_handover_of_work_ignores_same_solver_retries(conn: sqlite3.Connection) -> None:
    edges = handover_of_work(conn)

    # session-2's Astar -> Astar retry must not appear as a handover edge.
    assert not any(
        edge.from_solver == edge.to_solver for edge in edges
    )
    assert HandoverEdge(from_solver="solver-Astar", to_solver="solver-Astar", count=1) not in edges
