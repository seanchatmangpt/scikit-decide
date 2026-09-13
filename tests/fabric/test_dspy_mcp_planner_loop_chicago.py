# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style test for the loop `tests/fabric/test_dspy.py`/`test_mcp.py`
never covered: a DSPy-compiled decision request, resolved by a real LLM call
against a real local model, executed through a real ``fastmcp`` server --
protocol layer included, not the ``FakeFastMCP`` stand-in `test_mcp.py` uses.

The gap this file closes (found this session, five parallel audits): every
existing dspy test drives `DSPyPolicy`/`DSPyDecisionCompiler` as a plain
Python object; every existing MCP test fakes `fastmcp` out entirely. No test
anywhere proved a DSPy-produced plan ever reached the MCP-exposed planner and
came back executed. This one does, scoped to one repo (no sibling-repo
process spawned, so it belongs here under `tests/fabric/`, not
`tests/ecosystem/`).

Real components exercised end to end:
  1. A real local LM (`real_dspy_lm`, ``tests/conftest.py`` -- spawns/reuses a
     real ``TurboFieldfareServer`` process).
  2. A real ``dspy.Predict(JobToDecision)`` call
     (`DSPyDecisionCompiler.compile`, `fabric/dspy.py`).
  3. A real ``fastmcp.FastMCP`` server (`create_server`, `fabric/mcp.py`) --
     no `FakeFastMCP`.
  4. A real ``fastmcp.Client`` connected in-memory to that server, driving
     the actual MCP protocol layer (`initialize`/`tools/call`), not a bare
     Python function call.
  5. A real registered domain+solver pair (`Maze`/`Astar`) executed through
     `DecisionFabric.solve()` -- a real bounded rollout, not a fixture.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

# Mirrors tests/conftest.py's own gate exactly (not imported directly: this
# file lives under tests/fabric/, which has its own conftest.py, and rootless
# pytest layouts insert both same-named "conftest" modules into sys.path --
# `from conftest import ...` from here is not guaranteed to resolve to the
# top-level tests/conftest.py rather than tests/fabric/conftest.py).
_TURBO_FIELDFARE_DIR = Path.home() / "turbo-fieldfare"
_SERVER_BINARY = _TURBO_FIELDFARE_DIR / ".build" / "release" / "TurboFieldfareServer"
_MODEL_PATH = _TURBO_FIELDFARE_DIR / "scratch" / "gemma4.gturbo"
requires_real_turbo_fieldfare_binary_and_model = pytest.mark.skipif(
    not (_SERVER_BINARY.exists() and _MODEL_PATH.exists()),
    reason=(
        f"Real TurboFieldfareServer binary ({_SERVER_BINARY}) or real model "
        f"weights ({_MODEL_PATH}) not present -- build/install them per "
        "turbo-fieldfare's README before running this real end-to-end test."
    ),
)

pytest.importorskip("fastmcp")
pytest.importorskip("dspy")


@requires_real_turbo_fieldfare_binary_and_model
def test_dspy_compiled_job_reaches_a_real_mcp_server_and_executes(real_dspy_lm):
    # A plain sync test driving its own event loop with asyncio.run, rather
    # than @pytest.mark.asyncio: neither pytest-asyncio nor an asyncio-mode
    # anyio config is installed in this environment (confirmed this
    # session -- anyio is present but its pytest plugin defaults to
    # collecting only functions explicitly marked/fixtured for it), and a
    # real fastmcp.Client still requires an event loop regardless of which
    # plugin would otherwise supply one.
    asyncio.run(_run(real_dspy_lm))


async def _run(real_dspy_lm) -> None:
    import dspy
    from fastmcp import Client

    from autofde_lab.fabric.dspy import DSPyDecisionCompiler
    from autofde_lab.fabric.mcp import create_server
    from autofde_lab.fabric.service import DecisionFabric

    fabric = DecisionFabric()
    server = create_server(fabric, compiler=DSPyDecisionCompiler())

    async with Client(server) as client:
        tools = {tool.name for tool in await client.list_tools()}
        assert "decision_compile" in tools, (
            "decision_compile must be registered when a compiler is passed "
            "to create_server -- this is exactly the wiring "
            "fabric/cli.py's --dspy-compile flag now does"
        )

        # Directive job text, not free-form prose: this test's job is to
        # prove the wire is connected end to end, not to grade a small local
        # model's free-form natural-language understanding. The Signature
        # (fabric/dspy.py's JobToDecision) still does real inference over
        # this text -- domain/solver selection and JSON argument synthesis
        # are genuinely produced by the LM, not hardcoded here.
        job_text = (
            "Solve the registered domain named exactly 'Maze' using the "
            "registered solver named exactly 'Astar'. Use empty JSON "
            "objects {} for both domain_arguments and solver_arguments. "
            "Use max_steps 200."
        )

        with dspy.context(lm=real_dspy_lm):
            compiled = await client.call_tool(
                "decision_compile", {"job": job_text}
            )

        request = compiled.data
        assert request["domain"] == "Maze", (
            f"DSPy compiled a different domain than asked: {request!r}"
        )
        assert request["solver"] == "Astar", (
            f"DSPy compiled a different solver than asked: {request!r}"
        )

        result = await client.call_tool("decision_solve", {"request": request})
        payload = result.data

        assert payload["standing"] in ("SOLVED", "BOUNDED"), (
            f"expected a real executed rollout, got: {payload!r}"
        )
        assert len(payload["steps"]) > 0, "solve produced zero steps"
        assert payload["request"]["domain"] == "Maze"
        # Real receipt digests, not placeholders (mirrors this session's
        # scripts/mutate_pddl_gate_check.py / ofmf audit discipline: a
        # "receipt" with no real hash behind it is worse than none).
        for digest_key in (
            "input_sha256",
            "trajectory_sha256",
            "receipt_sha256",
        ):
            digest = payload[digest_key]
            assert isinstance(digest, str) and len(digest) == 64, (
                f"{digest_key} does not look like a real sha256 hex digest: "
                f"{digest!r}"
            )
