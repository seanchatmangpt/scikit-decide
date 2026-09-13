"""Chicago-style TDD prep: real fastmcp.FastMCP server driven by a real fastmcp.Client.

Follows the exact pattern already established and proven in this repo at
tests/fabric/test_mcp.py and tests/fabric/test_mcp_ocel_instrumentation_chicago.py
(both explicitly "not FakeFastMCP"). `fastmcp` is a real, already-declared
dependency (the `mcp` extra). `autofde_lab.gymact.mcp` does not exist yet --
expected to fail at collection until the next pass adds a real
`create_server()` that registers the GymAct kernel operations as real MCP tools.
"""

from __future__ import annotations

import asyncio

import pytest

fastmcp = pytest.importorskip("fastmcp")

from autofde_lab.gymact.mcp import create_server  # noqa: E402


def test_gymact_mcp_server_exposes_kernel_operations() -> None:
    server = create_server()

    async def run():
        async with fastmcp.Client(server) as client:
            return await client.list_tools()

    tools = asyncio.run(run())

    assert {t.name for t in tools} == {
        "gymact_discover",
        "gymact_act",
        "gymact_observe",
        "gymact_verify",
    }


def test_gymact_mcp_act_returns_real_structured_content() -> None:
    server = create_server()

    async def run():
        async with fastmcp.Client(server) as client:
            return await client.call_tool(
                "gymact_act",
                {
                    "request": {
                        "subject": "cloudgoat",
                        "operation": "act",
                        "episode_id": "episode-1",
                        "payload": {},
                        "authority_ref": None,
                        "idempotency_key": "idem-1",
                    }
                },
            )

    result = asyncio.run(run())

    assert "standing" in result.structured_content
