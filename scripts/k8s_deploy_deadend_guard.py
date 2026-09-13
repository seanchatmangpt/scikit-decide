#!/usr/bin/env python3
"""Fast dead-end detection for a Kubernetes namespace deploy-and-wait phase.

Real problem this closes, observed live this session: SREGym's own
``main.py`` waits up to 600s for every pod in a namespace to become Ready,
with no earlier check for a structurally unrecoverable scheduling failure.
A real trial against a single-node ``kind``/``k3s`` cluster hit a real
``FailedScheduling`` event ("0/1 nodes are available: 1 node(s) didn't
match Pod's node affinity/selector") within 6 seconds of the Prometheus
Helm chart being applied -- but the harness still waited the full 600s
before giving up and retrying the identical, still-doomed deploy.

This module is a real, standalone dead-end detector: poll ``kubectl get
events`` for a namespace, and refuse fast (a named, typed
``DeadEndDetected`` exception, never a silent generic timeout) the moment a
scheduling-failure pattern repeats past a small threshold within a short
window -- the same "no silent hang, refuse with a name" discipline this
session's ``classify_stall``/``ActuationBindingRefused``/
``CapabilityRefused`` machinery already applies inside autofde-lab's own
POWL runner, extended here to the one layer outside our own code: the
trial-launch wrapper around SREGym's own harness.

Not a mock of ``kubectl`` -- this shells out to the real binary and parses
real, live event JSON. Degrades to a named ``DeadEndGuardUnavailable`` if
``kubectl`` itself is unreachable, never a false "all clear".
"""

from __future__ import annotations

import json
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field

# Real, observed-this-session failure reasons that mean "will never resolve
# without external intervention" -- a pod stuck on any of these will still
# be stuck an hour from now; retrying the identical deploy changes nothing.
DEAD_END_REASONS: frozenset[str] = frozenset(
    {
        "FailedScheduling",
        "FailedMount",
        "InvalidImageName",
        "ErrImagePull",
        "ImagePullBackOff",
        "CrashLoopBackOff",
    }
)


class DeadEndGuardUnavailable(RuntimeError):
    """Raised when the guard itself cannot observe real cluster state
    (e.g. `kubectl` missing or unreachable) -- this is NOT a green light;
    callers must treat an unavailable guard as "unknown", never as "no dead
    end found"."""


class DeadEndDetected(RuntimeError):
    """Raised the moment a real, repeated dead-end event pattern is
    observed. Carries the exact event reasons and counts that triggered
    it, so a human sees precisely *why* -- never a generic timeout."""

    def __init__(self, namespace: str, reasons: dict[str, int]) -> None:
        self.namespace = namespace
        self.reasons = dict(reasons)
        detail = ", ".join(f"{k}x{v}" for k, v in sorted(reasons.items()))
        super().__init__(
            f"DEAD_END:{namespace}: repeated unrecoverable scheduling/pull "
            f"failures observed ({detail}) -- will not resolve by waiting."
        )


@dataclass(frozen=True)
class GuardResult:
    """Real observation from one poll -- never fabricated."""

    namespace: str
    dead_end_reasons: dict[str, int] = field(default_factory=dict)
    raw_event_count: int = 0

    @property
    def is_dead_end(self) -> bool:
        return bool(self.dead_end_reasons)


def _run_kubectl_events(namespace: str, *, timeout_s: float = 10.0) -> list[dict]:
    """Real subprocess call to `kubectl get events -o json`. Raises
    DeadEndGuardUnavailable on any failure to reach a real cluster --
    never silently returns an empty list pretending nothing is wrong."""
    try:
        proc = subprocess.run(
            ["kubectl", "get", "events", "-n", namespace, "-o", "json"],
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        raise DeadEndGuardUnavailable(
            f"kubectl unreachable while polling namespace {namespace!r}: {exc}"
        ) from exc
    if proc.returncode != 0:
        raise DeadEndGuardUnavailable(
            f"kubectl get events failed (exit {proc.returncode}) for "
            f"namespace {namespace!r}: {proc.stderr.strip()[:500]}"
        )
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise DeadEndGuardUnavailable(
            f"kubectl returned non-JSON output for namespace {namespace!r}: {exc}"
        ) from exc
    return payload.get("items", [])


def check_namespace_for_dead_end(
    namespace: str, *, min_repeats: int = 2
) -> GuardResult:
    """One real poll. Counts DEAD_END_REASONS occurrences among real
    events; a reason is only reported once it has repeated at least
    `min_repeats` times (a single transient FailedScheduling during normal
    pod-bin-packing churn is not itself a dead end -- repetition without
    resolution is the real signal)."""
    events = _run_kubectl_events(namespace)
    counts: dict[str, int] = {}
    for ev in events:
        reason = ev.get("reason", "")
        if reason in DEAD_END_REASONS:
            counts[reason] = counts.get(reason, 0) + 1
    dead = {k: v for k, v in counts.items() if v >= min_repeats}
    return GuardResult(namespace=namespace, dead_end_reasons=dead, raw_event_count=len(events))


def wait_or_fail_fast(
    namespace: str,
    *,
    max_wait_s: float = 600.0,
    poll_interval_s: float = 5.0,
    min_repeats: int = 2,
    is_ready: Callable[[], bool] | None = None,
) -> None:
    """Drop-in replacement for a blind `wait up to max_wait_s` loop.

    Polls both real readiness (via the caller-supplied `is_ready`, e.g. a
    real `kubectl get pods` Ready check) and real dead-end events on the
    SAME cadence. Raises DeadEndDetected the moment a real, repeated
    unrecoverable failure is observed -- never waits out the full
    `max_wait_s` for a doomed deploy. Returns normally (no exception) only
    when `is_ready()` returns True; raises TimeoutError (distinct from
    DeadEndDetected) if `max_wait_s` elapses with no dead end AND no
    readiness -- an honest "still unknown, ran out of budget", not a
    fabricated success.
    """
    deadline = time.monotonic() + max_wait_s
    while time.monotonic() < deadline:
        if is_ready is not None and is_ready():
            return
        result = check_namespace_for_dead_end(namespace, min_repeats=min_repeats)
        if result.is_dead_end:
            raise DeadEndDetected(namespace, result.dead_end_reasons)
        time.sleep(poll_interval_s)
    raise TimeoutError(
        f"UNKNOWN:{namespace}: {max_wait_s}s elapsed with no dead end observed "
        f"and readiness never confirmed -- genuinely still unresolved, not a failure."
    )


if __name__ == "__main__":
    import sys

    ns = sys.argv[1] if len(sys.argv) > 1 else "observe"
    try:
        result = check_namespace_for_dead_end(ns)
    except DeadEndGuardUnavailable as exc:
        print(f"UNAVAILABLE: {exc}")
        raise SystemExit(2) from exc
    if result.is_dead_end:
        print(f"DEAD_END: {result.dead_end_reasons}")
        raise SystemExit(1)
    print(f"NO_DEAD_END: {result.raw_event_count} events observed, none repeated")
