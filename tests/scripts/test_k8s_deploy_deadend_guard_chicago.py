"""Chicago-style tests for scripts/k8s_deploy_deadend_guard.py.

Real `kubectl` calls against the real, live local cluster this session's
own trial ran against -- no mocked subprocess, no faked event JSON. Each
test creates and tears down a real, throwaway namespace. Skips honestly
(never a mock substitute) if no real cluster is reachable.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

from k8s_deploy_deadend_guard import (  # noqa: E402
    DeadEndDetected,
    check_namespace_for_dead_end,
    wait_or_fail_fast,
)


def _cluster_reachable() -> bool:
    if shutil.which("kubectl") is None:
        return False
    try:
        proc = subprocess.run(
            ["kubectl", "cluster-info"], capture_output=True, text=True, timeout=10.0
        )
    except subprocess.TimeoutExpired:
        # A stale/unreachable kubeconfig context can make `kubectl` itself hang past
        # its own internal timeouts instead of failing fast -- this is real evidence
        # of "not reachable", not a collection-time crash. Caught here (not left to
        # propagate) so the module-level skipif below can classify it the same as any
        # other real UNREACHABLE, matching this file's own "skips honestly" contract.
        return False
    return proc.returncode == 0


pytestmark = pytest.mark.skipif(
    not _cluster_reachable(),
    reason="no reachable Kubernetes cluster -- real kubectl calls require one, never mocked",
)


@pytest.fixture
def real_throwaway_namespace():
    ns = f"deadend-guard-test-{uuid.uuid4().hex[:8]}"
    subprocess.run(["kubectl", "create", "namespace", ns], check=True, capture_output=True)
    try:
        yield ns
    finally:
        subprocess.run(
            ["kubectl", "delete", "namespace", ns, "--ignore-not-found", "--wait=false"],
            capture_output=True,
        )


def test_no_dead_end_on_a_namespace_with_no_pods(real_throwaway_namespace):
    result = check_namespace_for_dead_end(real_throwaway_namespace)
    assert not result.is_dead_end
    assert result.dead_end_reasons == {}


def test_real_unsatisfiable_node_selector_is_detected_as_a_dead_end(real_throwaway_namespace):
    """A real pod requesting a node label that exists nowhere on this
    cluster reproduces the exact live failure mode observed this session
    (`FailedScheduling`) -- real kubectl apply, real event, real detection."""
    manifest = f"""
apiVersion: v1
kind: Pod
metadata:
  name: unsatisfiable
  namespace: {real_throwaway_namespace}
spec:
  nodeSelector:
    this-label-does-not-exist-anywhere: "true"
  containers:
    - name: pause
      image: registry.k8s.io/pause:3.9
"""
    subprocess.run(
        ["kubectl", "apply", "-f", "-"],
        input=manifest,
        text=True,
        check=True,
        capture_output=True,
    )

    deadline = time.monotonic() + 30.0
    result = None
    while time.monotonic() < deadline:
        result = check_namespace_for_dead_end(real_throwaway_namespace, min_repeats=1)
        if result.is_dead_end:
            break
        time.sleep(2.0)

    assert result is not None
    assert result.is_dead_end, "expected a real FailedScheduling event within 30s"
    assert "FailedScheduling" in result.dead_end_reasons


def test_wait_or_fail_fast_raises_dead_end_detected_not_timeout(real_throwaway_namespace):
    """The real, load-bearing behavior this module exists for: given a
    doomed deploy, wait_or_fail_fast must raise DeadEndDetected well before
    max_wait_s elapses -- proving it does NOT block for the full blind
    timeout the way SREGym's own main.py did this session."""
    manifest = f"""
apiVersion: v1
kind: Pod
metadata:
  name: unsatisfiable
  namespace: {real_throwaway_namespace}
spec:
  nodeSelector:
    this-label-does-not-exist-anywhere: "true"
  containers:
    - name: pause
      image: registry.k8s.io/pause:3.9
"""
    subprocess.run(
        ["kubectl", "apply", "-f", "-"],
        input=manifest,
        text=True,
        check=True,
        capture_output=True,
    )

    start = time.monotonic()
    with pytest.raises(DeadEndDetected) as excinfo:
        wait_or_fail_fast(
            real_throwaway_namespace,
            max_wait_s=120.0,
            poll_interval_s=2.0,
            min_repeats=1,
            is_ready=lambda: False,
        )
    elapsed = time.monotonic() - start

    assert "FailedScheduling" in excinfo.value.reasons
    assert elapsed < 60.0, (
        f"took {elapsed:.1f}s to detect a dead end that should surface in "
        "well under the 120s budget -- fast-fail is the entire point"
    )
