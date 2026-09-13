"""Real subprocess test of the `python -m autofde_lab_planner.scanner` CLI boundary.

Chicago style: a real subprocess, real stdin/stdout, no mocks -- asserts on
the actual JSON the process prints, exactly the discipline
tests/scanner/test_scanner_chicago.py already uses for scan() itself.
"""

from __future__ import annotations

import json
import subprocess
import sys


def _run_cli(state: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "autofde_lab_planner.scanner"],
        input=json.dumps(state),
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_cli_reports_real_replica_mismatch_anomaly():
    state = {
        "deployments": [
            {
                "metadata": {"name": "checkout", "namespace": "prod"},
                "spec": {"replicas": 3, "selector": {"matchLabels": {"app": "checkout"}}},
                "status": {"readyReplicas": 1},
            }
        ],
        "pods": [
            {
                "metadata": {"name": "checkout-abc", "namespace": "prod", "labels": {"app": "checkout"}},
                "status": {"phase": "Running", "conditions": [{"type": "Ready", "status": "True"}]},
            }
        ],
    }
    result = _run_cli(state)
    assert result.returncode == 0, result.stderr
    findings = json.loads(result.stdout)
    assert len(findings) == 1
    finding = findings[0]
    assert finding["kind"] == "Deployment"
    assert finding["object_name"] == "checkout"
    assert finding["namespace"] == "prod"
    assert finding["relation_class"] == "declared_vs_observed"
    assert finding["field"] == "readyReplicas"
    assert finding["observed"] == "1"
    assert finding["expected"] == "3"
    assert finding["taxonomy"] == "inject_scale_pods_to_zero"


def test_cli_reports_empty_array_for_healthy_state():
    result = _run_cli({})
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == []


def test_cli_fails_closed_on_malformed_json():
    result = subprocess.run(
        [sys.executable, "-m", "autofde_lab_planner.scanner"],
        input="not json",
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode != 0
    assert "malformed" in result.stderr.lower()


def test_cli_fails_closed_on_non_object_json():
    result = subprocess.run(
        [sys.executable, "-m", "autofde_lab_planner.scanner"],
        input="[1, 2, 3]",
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode != 0
    assert "expected a json object" in result.stderr.lower()
