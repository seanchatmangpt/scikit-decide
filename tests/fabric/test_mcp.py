# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Real `fastmcp.FastMCP` server driven by a real `fastmcp.Client`, matching the
pattern already established in ``test_mcp_ocel_instrumentation_chicago.py`` (whose
own docstring says "not FakeFastMCP"). ``fastmcp`` is a real, installed dependency
here (confirmed via `import fastmcp` in this repo's `.venv`) -- there is no reason to
fake a real, already-available dependency, so this no longer does. Skips (named,
not silent) via `pytest.importorskip` on a machine where fastmcp genuinely isn't
installed, rather than substituting a fake for it.
"""

from __future__ import annotations

import asyncio

import pytest

fastmcp = pytest.importorskip("fastmcp")

from autofde_lab.fabric.mcp import create_server  # noqa: E402
from autofde_lab.fabric.service import DecisionFabric  # noqa: E402


def test_mcp_projects_one_fabric(fabric: DecisionFabric) -> None:
    server = create_server(fabric)

    async def run():
        async with fastmcp.Client(server) as client:
            tools = await client.list_tools()
            catalog_result = await client.call_tool("decision_catalog", {})
            solve_result = await client.call_tool(
                "decision_solve",
                {"request": {"domain": "Counter", "domain_arguments": {"limit": 1}}},
            )
            return tools, catalog_result, solve_result

    tools, catalog_result, solve_result = asyncio.run(run())

    assert {t.name for t in tools} == {
        "decision_cache_hotset",
        "decision_cache_stats",
        "decision_catalog",
        "decision_match",
        "decision_solve",
    }
    assert catalog_result.structured_content["domains"] == ["Counter"]
    assert solve_result.structured_content["standing"] == "SOLVED"
