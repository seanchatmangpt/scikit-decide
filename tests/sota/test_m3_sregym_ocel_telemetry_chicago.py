"""Chicago-style zero-mock tests for real-time OCEL 2.0 telemetry on SREGym trials.

Strict zero-mock policy: NO unittest.mock, NO Mock, NO MagicMock, NO patch, NO monkeypatch.

Two tiers, per this repo's testing-chicago-style rule:

1. Unit-level (always runs): exercises the real `record_and_flush` helper against a
   real `OcelSessionRecorder` and a real on-disk SQLite file -- no network, no cluster.
2. Live integration (`skipif` when the real kubectl-mcp server this session's live
   SREGym batch already has port-forwarded is unreachable): drives one real,
   read-only `call_kubectl("kubectl get namespaces")` through the actual vendored
   driver module and asserts a real OCEL event lands. Named, visible skip rather
   than a silent mock substitution, matching this repo's own TurboFieldfare
   precedent (`.claude/rules/testing-chicago-style.md`'s worked example).
"""

from __future__ import annotations

import socket
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SREGYM_ROOT = REPO_ROOT / "vendor" / "gyms" / "sregym"
DRIVER_PATH = SREGYM_ROOT / "clients" / "autofde_lab_planner" / "driver.py"


def _mcp_server_reachable(host: str = "127.0.0.1", port: int = 9954, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Tier 1: unit-level, real recorder + real SQLite, no network required.
# ---------------------------------------------------------------------------


def test_record_and_flush_writes_a_real_queryable_sqlite_log(tmp_path):
    from autofde_lab.ocel.live_flush import record_and_flush
    from autofde_lab.ocel.mcp_instrumentation import OcelSessionRecorder
    from autofde_lab.ocel.sqlite_store import from_sqlite

    recorder = OcelSessionRecorder("session-ocel-telemetry-test", server_name="sregym-autofde-lab-planner")
    db_path = tmp_path / "problem-x.ocel2.sqlite"

    record_and_flush(
        recorder,
        activity="kubectl get",
        objects=[("problem-misconfig_app_hotel_res", "Problem"), ("namespace-hotel-reservation", "Namespace")],
        outcome={"standing": "COMPLETED", "elapsed_s": 0.42, "detail": "kubectl get deployments -n hotel-reservation"},
        path=db_path,
    )

    assert db_path.exists()

    # Real, independent read-back from disk -- not the in-memory recorder.
    reloaded = from_sqlite(db_path)
    activities = [e.activity for e in reloaded.events]
    assert activities == ["kubectl get"]
    object_types = {o.object_type for o in reloaded.objects}
    assert object_types == {"MCPSession", "Problem", "Namespace"}


def test_record_and_flush_accumulates_across_multiple_calls_real_time(tmp_path):
    """Each call overwrites the DB with the FULL accumulated log -- the real,
    intended "queryable while still running" behavior, not just a last-event
    snapshot."""
    from autofde_lab.ocel.live_flush import record_and_flush
    from autofde_lab.ocel.mcp_instrumentation import OcelSessionRecorder
    from autofde_lab.ocel.sqlite_store import from_sqlite

    recorder = OcelSessionRecorder("session-ocel-telemetry-test-2")
    db_path = tmp_path / "problem-y.ocel2.sqlite"

    for i in range(3):
        record_and_flush(
            recorder,
            activity=f"kubectl step-{i}",
            objects=[("problem-y", "Problem")],
            outcome={"standing": "COMPLETED", "elapsed_s": 0.1 * i},
            path=db_path,
        )
        # Real, on-disk state after each individual flush -- proves this is
        # queryable mid-session, not just after the loop finishes.
        reloaded = from_sqlite(db_path)
        assert len(reloaded.events) == i + 1

    final = from_sqlite(db_path)
    assert [e.activity for e in final.events] == ["kubectl step-0", "kubectl step-1", "kubectl step-2"]


def test_record_and_flush_on_a_real_error_outcome_is_still_valid_ocel(tmp_path):
    from autofde_lab.ocel.live_flush import record_and_flush
    from autofde_lab.ocel.mcp_instrumentation import OcelSessionRecorder

    recorder = OcelSessionRecorder("session-ocel-telemetry-error")
    db_path = tmp_path / "problem-z.ocel2.sqlite"

    record_and_flush(
        recorder,
        activity="kubectl patch",
        objects=[("problem-z", "Problem")],
        outcome={"standing": "ERROR", "elapsed_s": 1.5, "detail": "ConnectionError: real transport failure"},
        path=db_path,
    )

    log = recorder.close()  # raises on any OCPQ Definition 2 structural violation
    doc = log.to_ocel2_json()
    standings = [
        next(a["value"] for a in e["attributes"] if a["name"] == "standing") for e in doc["events"]
    ]
    assert standings == ["ERROR"]


# ---------------------------------------------------------------------------
# Tier 2: live integration against the real kubectl-mcp server, when reachable.
# ---------------------------------------------------------------------------


SREGYM_PYTHON = SREGYM_ROOT / ".venv" / "bin" / "python"

# Real, exact production script: exercises driver.py under the SAME interpreter
# the live batch uses (vendor/gyms/sregym/.venv, fastmcp 2.9.2), not the outer
# repo's .venv (fastmcp 3.4.6) -- the two disagree on CallToolResult's shape,
# discovered live by an earlier version of this test that imported driver.py
# under the wrong interpreter and hit a real, environment-specific TypeError.
_LIVE_CHECK_SCRIPT = """
import asyncio, json, sys
sys.path.insert(0, {sregym_root!r})
sys.path.insert(0, {driver_dir!r})
import importlib.util
spec = importlib.util.spec_from_file_location("autofde_lab_planner_driver_under_test", {driver_path!r})
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)
assert driver.OcelSessionRecorder is not None, "OCEL import must succeed"
driver._init_ocel_recorder("test-ocel-telemetry-problem", "default", "test-app")
result = asyncio.run(driver.call_kubectl("kubectl get namespaces"))
assert isinstance(result, str) and len(result) > 0
activities = [e.activity for e in driver._OCEL_RECORDER.log.events]
log = driver._OCEL_RECORDER.close()
doc = log.to_ocel2_json()
standings = [next(a["value"] for a in e["attributes"] if a["name"] == "standing") for e in doc["events"]]
print(json.dumps({{"activities": activities, "standings": standings}}))
"""


@pytest.mark.skipif(
    not DRIVER_PATH.exists(),
    reason="UNSUPPORTED: vendor/gyms/sregym submodule not checked out",
)
@pytest.mark.skipif(
    not SREGYM_PYTHON.exists(),
    reason="UNSUPPORTED: vendor/gyms/sregym/.venv not present",
)
@pytest.mark.skipif(
    not _mcp_server_reachable(),
    reason="BLOCKED:MCP_SERVER_UNREACHABLE (127.0.0.1:9954) -- no live SREGym cluster session",
)
def test_call_kubectl_emits_a_real_ocel_event_against_the_live_cluster(tmp_path):
    import json
    import os
    import subprocess

    script = _LIVE_CHECK_SCRIPT.format(
        sregym_root=str(SREGYM_ROOT), driver_dir=str(DRIVER_PATH.parent), driver_path=str(DRIVER_PATH)
    )
    env = dict(os.environ)
    env["AUTOFDE_OCEL_DIR"] = str(tmp_path)

    completed = subprocess.run(
        [str(SREGYM_PYTHON), "-c", script],
        cwd=str(SREGYM_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert completed.returncode == 0, (
        f"live driver.py subprocess failed (rc={completed.returncode}):\\n"
        f"stdout={completed.stdout}\\nstderr={completed.stderr}"
    )
    last_line = completed.stdout.strip().splitlines()[-1]
    payload = json.loads(last_line)
    assert "kubectl get" in payload["activities"]
    assert "COMPLETED" in payload["standings"]
