# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Real tests for :mod:`autofde_lab.ocel.enhancement`.

Builds a small synthetic two-session log with one deliberately slow step
(a large real gap between two ``timestamp_ns`` values) and asserts that step
surfaces as the top real bottleneck -- a checkable claim on the mined
numbers, not a shape-only assertion.
"""

from __future__ import annotations

import sqlite3

import pytest

from autofde_lab.ocel.enhancement import activity_durations, bottleneck_ranking
from autofde_lab.ocel.log import OcelLog
from autofde_lab.ocel.mcp_session import append_tool_call_event
from autofde_lab.ocel.model import OcelAttribute, OcelAttributeValue, OcelObject
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
        ]
    )

    # session-1: catalog (fast) -> match (SLOW: 10_000_000ns gap) -> solve
    log = append_tool_call_event(
        log, event_id="s1-catalog", activity="decision_catalog",
        object_ids=["session-1"], outcome={"standing": "OK"}, timestamp_ns=0,
    )
    log = append_tool_call_event(
        log, event_id="s1-match", activity="decision_match",
        object_ids=["session-1"], outcome={"standing": "MATCHED"}, timestamp_ns=1_000,
    )
    log = append_tool_call_event(
        log, event_id="s1-solve", activity="decision_solve",
        object_ids=["session-1"], outcome={"standing": "SOLVED"}, timestamp_ns=10_001_000,
    )

    # session-2: catalog (fast) -> match (SLOW again) -> solve
    log = append_tool_call_event(
        log, event_id="s2-catalog", activity="decision_catalog",
        object_ids=["session-2"], outcome={"standing": "OK"}, timestamp_ns=0,
    )
    log = append_tool_call_event(
        log, event_id="s2-match", activity="decision_match",
        object_ids=["session-2"], outcome={"standing": "MATCHED"}, timestamp_ns=500,
    )
    log = append_tool_call_event(
        log, event_id="s2-solve", activity="decision_solve",
        object_ids=["session-2"], outcome={"standing": "SOLVED"}, timestamp_ns=9_000_500,
    )

    return log


@pytest.fixture()
def conn(tmp_path) -> sqlite3.Connection:
    log = _build_log()
    db_path = tmp_path / "enhancement_test.sqlite"
    to_sqlite(log, db_path)
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    try:
        yield connection
    finally:
        connection.close()


def test_activity_durations_real_gap_stats(conn: sqlite3.Connection) -> None:
    rows = {row.activity: row for row in activity_durations(conn)}

    # decision_catalog -> decision_match gap: 1000ns (s1) and 500ns (s2).
    assert rows["decision_catalog"].count == 2
    assert rows["decision_catalog"].mean_gap_ns == pytest.approx(750.0)

    # decision_match -> decision_solve gap: ~10_000_000ns and ~9_000_000ns -- the
    # deliberately slow step.
    assert rows["decision_match"].count == 2
    assert rows["decision_match"].mean_gap_ns == pytest.approx(9_500_000.0)

    # decision_solve is always last in its session -- no "gap after" to measure.
    assert "decision_solve" not in rows


def test_bottleneck_ranking_surfaces_the_real_slow_step(conn: sqlite3.Connection) -> None:
    ranking = bottleneck_ranking(conn)

    assert ranking[0].activity == "decision_match"
    assert ranking[0].mean_gap_ns > ranking[1].mean_gap_ns
    # Sorted descending by mean gap, not by name or insertion order.
    assert [row.mean_gap_ns for row in ranking] == sorted(
        (row.mean_gap_ns for row in ranking), reverse=True
    )
