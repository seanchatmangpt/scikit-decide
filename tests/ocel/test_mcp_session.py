# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Real checks for `autofde_lab.ocel.mcp_session.append_tool_call_event`."""

from __future__ import annotations

from autofde_lab.ocel.log import OcelLog
from autofde_lab.ocel.mcp_session import append_tool_call_event
from autofde_lab.ocel.model import OcelObject


def _base_log() -> OcelLog:
    return OcelLog.new().with_objects(
        OcelObject("session-1", "MCPSession"),
        OcelObject("domain-Maze", "Domain"),
        OcelObject("solver-Astar", "Solver"),
    )


def test_records_a_real_event_with_standing_and_relationships():
    log = append_tool_call_event(
        _base_log(),
        event_id="evt-1",
        activity="decision_solve",
        object_ids=["session-1", "domain-Maze", "solver-Astar"],
        outcome={"standing": "SOLVED", "elapsed_s": 1.5, "steps": 3},
    )
    log = log.validate()

    assert len(log.events) == 1
    event = log.events[0]
    assert event.activity == "decision_solve"
    linked = {link.object_id for link in log.event_object_links if link.event_id == "evt-1"}
    assert linked == {"session-1", "domain-Maze", "solver-Astar"}


def test_carries_receipt_digest_and_truncates_long_detail():
    outcome = {
        "standing": "ERROR",
        "elapsed_s": 0.5,
        "receipt_sha256": "a" * 64,
        "detail": "x" * 2000,
    }
    log = append_tool_call_event(
        _base_log(),
        event_id="evt-2",
        activity="decision_solve",
        object_ids=["session-1", "domain-Maze"],
        outcome=outcome,
    ).validate()

    doc = log.to_ocel2_json()
    attrs = {a["name"]: a["value"] for a in doc["events"][0]["attributes"]}
    assert attrs["receipt_sha256"] == "a" * 64
    assert len(attrs["detail"]) == 500


def test_prefers_error_key_when_detail_absent():
    log = append_tool_call_event(
        _base_log(),
        event_id="evt-3",
        activity="decision_match",
        object_ids=["session-1", "domain-Maze"],
        outcome={"standing": "REFUSED", "error": "SKD-FABRIC-006: failed"},
    ).validate()

    doc = log.to_ocel2_json()
    attrs = {a["name"]: a["value"] for a in doc["events"][0]["attributes"]}
    assert attrs["detail"] == "SKD-FABRIC-006: failed"


def test_carries_arbitrary_count_attributes():
    log = append_tool_call_event(
        _base_log(),
        event_id="evt-4",
        activity="decision_match",
        object_ids=["session-1", "domain-Maze"],
        outcome={"standing": "MATCHED", "compatible_solver_count": 42},
    ).validate()

    doc = log.to_ocel2_json()
    attrs = {a["name"]: a["value"] for a in doc["events"][0]["attributes"]}
    assert attrs["compatible_solver_count"] == 42


def test_missing_standing_raises_keyerror_not_a_silent_default():
    import pytest

    with pytest.raises(KeyError):
        append_tool_call_event(
            _base_log(),
            event_id="evt-5",
            activity="decision_solve",
            object_ids=["session-1"],
            outcome={"elapsed_s": 1.0},
        )
