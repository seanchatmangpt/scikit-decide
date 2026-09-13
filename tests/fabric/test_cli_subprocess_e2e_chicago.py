# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Real, out-of-process, end-to-end test of the decision-fabric CLI.

Chicago-style per `.claude/rules/testing-chicago-style.md`: no mock, no
stub, no `FakeBackend`. This spawns the actual `python -m autofde_lab.fabric`
entry point (`src/autofde_lab/fabric/__main__.py`) as a real subprocess, which
loads the real `entry_points`-registered backend
(`autofde_lab.fabric.backend`), the real `Maze` domain
(`autofde_lab.hub.domain.maze`), and the real compiled `Astar` solver
(`autofde_lab.hub.solver.astar`, C++ hub extension). `tests/fabric/test_cli.py`
covers the Typer app in-process against `FakeBackend`; this test is the
complement -- the full process boundary against the real catalog, matching
`tests/fabric/test_mcp_ocel_instrumentation_chicago.py`'s choice of Maze/Astar
as the real domain/solver pair, at the CLI/subprocess layer instead of the
`DecisionFabric.solve()` layer.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

pytest.importorskip("typer")


def _run_fabric_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "autofde_lab.fabric", *args],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def _emitted_json(stdout: str) -> dict:
    """The CLI's `_emit` prints the JSON payload last; construction of the
    real domain/solver (gym space reprs, solver info logs) writes preceding
    lines to the same stream. Isolate the payload by its opening brace
    rather than assuming stdout is JSON-only.
    """
    return json.loads(stdout[stdout.index("{") :])


def test_catalog_lists_the_real_registered_maze_domain_and_astar_solver() -> None:
    result = _run_fabric_cli("catalog")

    assert result.returncode == 0, result.stderr
    payload = _emitted_json(result.stdout)
    assert "Maze" in payload["domains"]
    assert "Astar" in payload["solvers"]


def test_match_finds_astar_for_the_real_maze_domain() -> None:
    result = _run_fabric_cli("match", "Maze")

    assert result.returncode == 0, result.stderr
    payload = _emitted_json(result.stdout)
    assert "Astar" in payload["compatible_solvers"]


def test_solve_end_to_end_real_subprocess_real_domain_real_cpp_solver() -> None:
    """Real subprocess -> real Maze domain -> real compiled Astar solver.

    Asserts on final process state only: exit code, the emitted JSON receipt,
    and evidence in stderr that the real C++ A* solver actually ran (not a
    substituted double) -- final state, not an interaction expectation.
    """
    result = _run_fabric_cli(
        "solve",
        "Maze",
        "--solver",
        "Astar",
        "--max-steps",
        "60",
        "--no-cache",
    )

    assert result.returncode == 0, result.stderr
    # The real compiled Astar solver logs when it actually runs -- via
    # typer.echo/stdout, not something the test could fabricate.
    assert "A* solver" in result.stdout

    payload = _emitted_json(result.stdout)
    assert payload["standing"] == "SOLVED"
    assert payload["solver"] == "Astar"
    assert payload["request"]["domain"] == "Maze"
    assert payload["request"]["max_steps"] == 60
    assert isinstance(payload["receipt_sha256"], str) and payload["receipt_sha256"]
    assert (
        isinstance(payload["trajectory_sha256"], str) and payload["trajectory_sha256"]
    )
    steps = payload["steps"]
    assert len(steps) > 0
    # Every emitted transition is a real rollout step, not a placeholder.
    for step in steps:
        assert step["observation"] != step["next_observation"] or step["termination"]
    # A* on the default maze reaches the goal well inside 60 bounded steps.
    assert payload["terminal"] is True


def test_solve_rejects_unmatched_solver_with_typed_refusal() -> None:
    """A real refusal path: SimpleGreedy cannot drive a plain Maze rollout to
    the requested solver name -- Astar deliberately misspelled -- so the CLI
    must exit non-zero with a typed refusal payload, not a stack trace.
    """
    result = _run_fabric_cli(
        "solve",
        "Maze",
        "--solver",
        "NotARegisteredSolverName",
        "--max-steps",
        "5",
        "--no-cache",
    )

    assert result.returncode == 3, result.stderr
    payload = _emitted_json(result.stdout)
    assert payload["code"]
    assert "NotARegisteredSolverName" in json.dumps(payload)
