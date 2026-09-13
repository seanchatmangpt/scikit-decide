# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style test: every real MCP tool call becomes a real OCEL 2.0 event,
automatically, via `autofde_lab.ocel.mcp_instrumentation`.

Real components: a real `fastmcp.FastMCP` server (not `FakeFastMCP`), a real
`fastmcp.Client` driving the actual MCP protocol layer, a real registered
domain/solver pair (`Maze`/`Astar`) executed through `DecisionFabric.solve()`,
and a real refusal (an unregistered domain name) -- proving both the success
and failure paths are recorded, not just the happy path.
"""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("fastmcp")


def test_every_real_mcp_call_becomes_a_real_ocel_event():
    async def run():
        from fastmcp import Client

        from autofde_lab.fabric.mcp import create_server
        from autofde_lab.fabric.service import DecisionFabric
        from autofde_lab.ocel.mcp_instrumentation import OcelSessionRecorder

        fabric = DecisionFabric()
        recorder = OcelSessionRecorder("session-test-1")
        server = create_server(fabric, ocel_recorder=recorder)

        async with Client(server) as client:
            await client.call_tool("decision_catalog", {})
            await client.call_tool(
                "decision_match", {"domain": "Maze", "use_cache": False}
            )
            await client.call_tool(
                "decision_solve",
                {"request": {"domain": "Maze", "solver": "Astar", "max_steps": 20}},
            )
            with pytest.raises(Exception):
                await client.call_tool(
                    "decision_solve",
                    {"request": {"domain": "NoSuchDomain", "max_steps": 5}},
                )

        return recorder

    recorder = asyncio.run(run())

    log = recorder.close()  # raises on any OCPQ Definition 2 violation

    activities = [e.activity for e in log.events]
    assert activities == [
        "decision_catalog",
        "decision_match",
        "decision_solve",
        "decision_solve",
    ]

    doc = log.to_ocel2_json()
    standings = [
        next(a["value"] for a in e["attributes"] if a["name"] == "standing")
        for e in doc["events"]
    ]
    # catalog/match/first solve real and successful; the unregistered-domain
    # solve call is a real, recorded failure -- never silently dropped.
    # decision_catalog/decision_match's real return payloads carry no
    # "standing" key (only DecisionResult, from solve(), does) -- the
    # generic "COMPLETED" fallback is real, observed behavior, not a gap.
    assert standings[0] == "COMPLETED"
    assert standings[1] == "COMPLETED"
    assert standings[2] in ("SOLVED", "BOUNDED")
    assert standings[3] == "ERROR"

    object_types = {o["type"] for o in doc["objects"]}
    assert object_types == {"MCPSession", "Domain", "Solver"}

    # Every event links the session object -- OCPQ Definition 2's own
    # per-event "at least one qualified object reference" law, specialized:
    # this instrumentation always includes the session, regardless of what
    # else a given activity links.
    for event in doc["events"]:
        linked = {r["objectId"] for r in event["relationships"]}
        assert "session-test-1" in linked


def test_no_recorder_means_no_instrumentation_and_no_ocel_dependency():
    """ocel_recorder=None (the default) must not require or touch OCEL at all."""
    from autofde_lab.fabric.mcp import create_server
    from autofde_lab.fabric.service import DecisionFabric

    fabric = DecisionFabric()
    server = create_server(fabric)  # no ocel_recorder
    assert server is not None


def test_second_object_declaration_with_same_id_is_idempotent():
    from autofde_lab.ocel.mcp_instrumentation import OcelSessionRecorder

    recorder = OcelSessionRecorder("session-idem-1")
    recorder.ensure_object("domain-Maze", "Domain")
    before = len(recorder.log.objects)
    recorder.ensure_object("domain-Maze", "Domain")
    after = len(recorder.log.objects)
    assert before == after == 2  # session + one domain, no duplicate


def test_exception_in_tool_is_recorded_then_reraised_unchanged():
    from autofde_lab.ocel.mcp_instrumentation import OcelSessionRecorder, instrumented

    recorder = OcelSessionRecorder("session-err-1")

    @instrumented(recorder, activity="boom", objects_fn=lambda: [])
    def always_fails():
        raise ValueError("real failure, not a refusal type")

    with pytest.raises(ValueError, match="real failure"):
        always_fails()

    log = recorder.close()
    assert len(log.events) == 1
    doc = log.to_ocel2_json()
    attrs = {a["name"]: a["value"] for a in doc["events"][0]["attributes"]}
    assert attrs["standing"] == "ERROR"
    assert "real failure" in attrs["detail"]
