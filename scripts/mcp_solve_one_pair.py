#!/usr/bin/env python3
# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Solve exactly one (domain, solver) pair through a real MCP call, in a
fresh process, so the caller can enforce a hard OS-level timeout.

No timeout mechanism exists anywhere in this repo for a `solve()` call
(confirmed this session: `fabric/coverage.py::_run_solver`, the only
existing "run every solver" precedent, has none). Several registered
solvers are real RL-training methods (`RayRLlib`, `StableBaseline`,
`AugmentedRandomSearch`, `MaxentIRL`) with no bound on training time.
Running each pair as its own subprocess lets the caller
(`subprocess.run(..., timeout=N)`) kill a hung pair without losing the
whole sweep -- an in-process `asyncio.wait_for` cannot preempt a blocking
synchronous `solve()` call sharing the same event loop as the MCP client.

Prints exactly one JSON line to stdout: the tool's own JSON result on
success, or `{"error": "<type>: <message>"}` on a real, caught exception
(refusals from DecisionFabric surface this way -- SKD-FABRIC-* codes).
Exit code is 0 either way; the caller distinguishes real outcomes from a
hard timeout by process behavior (returned in time vs. killed), not by
exit code.
"""

from __future__ import annotations

import asyncio
import json
import sys


async def _run(domain: str, solver: str, max_steps: int) -> dict:
    from fastmcp import Client

    from autofde_lab.fabric.mcp import create_server
    from autofde_lab.fabric.service import DecisionFabric

    fabric = DecisionFabric()
    server = create_server(fabric)

    async with Client(server) as client:
        request = {
            "domain": domain,
            "solver": solver,
            "domain_arguments": {},
            "solver_arguments": {},
            "max_steps": max_steps,
        }
        result = await client.call_tool("decision_solve", {"request": request})
        return result.data


def main() -> int:
    domain, solver, max_steps_str = sys.argv[1], sys.argv[2], sys.argv[3]
    try:
        payload = asyncio.run(_run(domain, solver, int(max_steps_str)))
    except Exception as exc:  # noqa: BLE001 -- caught, reported as data, not a crash
        payload = {"error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
