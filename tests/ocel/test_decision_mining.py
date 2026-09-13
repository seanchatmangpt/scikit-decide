# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Real tests for :mod:`autofde_lab.ocel.decision_mining`.

Builds a synthetic log where one domain's ``compatible_solvers`` set never
changes across two matches (deterministic) and another's changes between
two matches (simulating a solver-registry change -- non-deterministic), and
asserts ``compatible_solver_set_stability`` classifies both correctly.
"""

from __future__ import annotations

import sqlite3

import pytest

from autofde_lab.ocel.decision_mining import DomainDecisionStability, compatible_solver_set_stability
from autofde_lab.ocel.log import OcelLog
from autofde_lab.ocel.mcp_session import append_tool_call_event
from autofde_lab.ocel.model import OcelAttribute, OcelAttributeValue, OcelObject
from autofde_lab.ocel.sqlite_store import to_sqlite


def _build_log() -> OcelLog:
    log = OcelLog.new(
        objects=[
            OcelObject(
                "session-1", "MCPSession",
                (OcelAttribute("server", OcelAttributeValue.string("scikit-decide-fabric")),),
            ),
            OcelObject("domain-Maze", "Domain", (OcelAttribute("name", OcelAttributeValue.string("Maze")),)),
            OcelObject(
                "domain-MasterMind", "Domain",
                (OcelAttribute("name", OcelAttributeValue.string("MasterMind")),),
            ),
        ]
    )

    # domain-Maze: matched twice, always the same solver set -> deterministic.
    log = append_tool_call_event(
        log, event_id="match-maze-0", activity="decision_match",
        object_ids=["session-1", "domain-Maze"],
        outcome={"standing": "MATCHED", "compatible_solvers": ["Astar", "MCTS"]},
        timestamp_ns=0,
    )
    log = append_tool_call_event(
        log, event_id="match-maze-1", activity="decision_match",
        object_ids=["session-1", "domain-Maze"],
        outcome={"standing": "MATCHED", "compatible_solvers": ["MCTS", "Astar"]},  # same set, different order
        timestamp_ns=1_000,
    )

    # domain-MasterMind: matched twice, the solver set changes -> non-deterministic.
    log = append_tool_call_event(
        log, event_id="match-mastermind-0", activity="decision_match",
        object_ids=["session-1", "domain-MasterMind"],
        outcome={"standing": "MATCHED", "compatible_solvers": ["Astar"]},
        timestamp_ns=2_000,
    )
    log = append_tool_call_event(
        log, event_id="match-mastermind-1", activity="decision_match",
        object_ids=["session-1", "domain-MasterMind"],
        outcome={"standing": "MATCHED", "compatible_solvers": ["Astar", "BFWS"]},
        timestamp_ns=3_000,
    )

    return log


@pytest.fixture()
def conn(tmp_path) -> sqlite3.Connection:
    log = _build_log()
    db_path = tmp_path / "decision_mining_test.sqlite"
    to_sqlite(log, db_path)
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    try:
        yield connection
    finally:
        connection.close()


def test_compatible_solver_set_stability_classifies_both_domains(conn: sqlite3.Connection) -> None:
    results = compatible_solver_set_stability(conn)

    # Sorted by domain_id -- "domain-MasterMind" < "domain-Maze" lexicographically.
    assert results == [
        DomainDecisionStability(
            domain_id="domain-MasterMind", distinct_solver_sets=2, is_deterministic=False
        ),
        DomainDecisionStability(
            domain_id="domain-Maze", distinct_solver_sets=1, is_deterministic=True
        ),
    ]
