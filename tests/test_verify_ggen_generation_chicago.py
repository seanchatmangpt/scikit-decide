# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style test for `scripts/verify_ggen_generation.py`.

Real collaborator: the actual script run as a real subprocess against this
repo's real, committed `ontology/*.ttl` and generated `src/autofde_lab/**`
files -- no mocking of `rdflib`, no stubbed file contents. Asserts on the
real JSON receipt printed to real stdout and the real process exit code.

No `unittest.mock` / `Mock` / `MagicMock` / `patch` / `monkeypatch` anywhere
in this file.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "verify_ggen_generation.py"


def _run_verifier() -> tuple[int, dict]:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return completed.returncode, json.loads(completed.stdout)


def test_verifier_reports_alive_and_exits_zero_against_the_real_committed_generation() -> None:
    returncode, receipt = _run_verifier()

    assert returncode == 0
    assert receipt["standing"] == "ALIVE"
    assert all(r["match"] for r in receipt["results"])


def test_verifier_recomputes_the_real_378_cell_k8s_cross_product_independently_of_ggen() -> None:
    _, receipt = _run_verifier()

    k8s_result = next(r for r in receipt["results"] if r["check"] == "k8s-fault-universes")
    assert k8s_result["axis_counts"] == {
        "Component": 6,
        "FailureMode": 7,
        "AppTopology": 3,
        "Severity": 3,
    }
    assert k8s_result["expected_universe_count"] == 378
    assert k8s_result["actual_universe_count"] == 378


def test_verifier_recomputes_the_real_world_transformation_scenario_count_independently_of_ggen() -> None:
    _, receipt = _run_verifier()

    scenario_result = next(r for r in receipt["results"] if r["check"] == "world-transformation-scenarios")
    assert scenario_result["expected_scenario_count"] == 1
    assert scenario_result["actual_scenario_count"] == 1
    assert scenario_result["match"] is True


def test_verifier_checks_every_one_of_the_eight_constitution_modules() -> None:
    _, receipt = _run_verifier()

    constitution_checks = {r["check"] for r in receipt["results"] if r["check"].startswith("constitution-")}
    assert constitution_checks == {
        "constitution-lab",
        "constitution-world",
        "constitution-planning",
        "constitution-process",
        "constitution-authority",
        "constitution-evidence",
        "constitution-standing",
        "constitution-interop",
    }
