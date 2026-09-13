"""Real fastmcp.FastMCP server exposing the GymAct kernel operations as MCP tools.

Follows the exact real-server/real-client pattern already proven in this repo at
`tests/fabric/test_mcp.py` / `test_mcp_ocel_instrumentation_chicago.py`.
"""

from __future__ import annotations

from fastmcp import FastMCP

from autofde_lab.gymact.kernel import GymActKernel
from autofde_lab.gymact.models import ActuationIntent, ActuationResult


def create_server() -> FastMCP:
    server: FastMCP = FastMCP("gymact")
    kernel = GymActKernel()

    @server.tool
    def gymact_discover(subject: str, episode_id: str) -> ActuationResult:
        return kernel.discover(subject=subject, episode_id=episode_id)

    @server.tool
    def gymact_observe(subject: str, episode_id: str) -> ActuationResult:
        return kernel.observe(subject=subject, episode_id=episode_id)

    @server.tool
    def gymact_verify(subject: str, episode_id: str) -> ActuationResult:
        return kernel.verify(subject=subject, episode_id=episode_id)

    @server.tool
    def gymact_act(request: ActuationIntent) -> ActuationResult:
        return kernel.act(
            subject=request.subject,
            episode_id=request.episode_id,
            payload=request.payload,
        )

    return server
