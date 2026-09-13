# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Phase H: the self-triggering outer MAPE-K loop.

Plan reference: docs/2026-08-11-autofde-lab-togaf-autonomic-architecture-plan.md
section 13, "Phase H Becomes the Outer AutoFDE-Lab Loop" --

    Phase H is the actual autonomic trigger: `new observation/OCEL ->
    process inference -> conformance/drift analysis -> trigger evaluation`.
    If the admitted trigger fires, start a new architecture experiment
    cycle ... No human prompt required.

This module is a minimal, real implementation of that closure, scoped to
one concrete drift signal: the content hash of
``ontology/autofde-lab-capabilities.ttl`` versus a stored baseline hash.
When the live hash diverges from the baseline, that is drift -- the
capability ontology changed since the baseline was captured -- and the
trigger fires an unattended, in-process solve+falsify (via
``fabric.solve_and_falsify``) against the known-working PDDLDomain/Astar
blocksworld fixture (``tests/domains/python/pddl_domains/blocks``), with
zero interactive input, and returns both the real trajectory receipt
(``trajectory_sha256``) AND a real falsification standing as evidence the
outer loop closed -- not just "it solved," but "the solve's result was
checked against its own postconditions immediately, automatically."

This is a narrow instance of Phase H, not the full
conformance/drift-analysis pipeline the plan describes (OCEL process
inference is out of scope here) -- it demonstrates the specific claim in
question: that a trigger can fire, invoke a solve, and falsify the result,
with no human in the loop and no separate manual invocation required.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from autofde_lab.fabric.solve_and_falsify import solve_and_falsify

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_WATCH_FILE = REPO_ROOT / "ontology" / "autofde-lab-capabilities.ttl"
DEFAULT_BASELINE_FILE = REPO_ROOT / "src" / "autofde_lab" / "fabric" / ".phase_h_baseline.json"

XAAS_REPO_ROOT = Path.home() / "xaas"
DEFAULT_COVERAGE_STATE_FILE = (
    REPO_ROOT / "src" / "autofde_lab" / "fabric" / ".phase_h_coverage_state.json"
)

# `mix xaas.close_coverage_gap` (see ~/xaas/lib/mix/tasks/xaas.close_coverage_gap.ex)
# has NO internal guard: its `least_exercised/1` always Enum.min_by's the 5
# aacm: class counts and unconditionally Acts on whichever class comes out
# lowest -- even when all 5 counts are already equal (gap == 0), confirmed
# by a real run on 2026-08-20 against the live xaas Postgres rows, all at 2
# each, which still picked PlannerCandidate and attempted to Act on it. Real
# check of the current ~/xaas source this session (2026-08-20, same day as
# this fix) confirms the task has NOT since gained a gap==0 guard --
# `least_exercised/1` is unchanged. So calling the mix task itself is NOT
# naturally idempotent/self-limiting -- every invocation Acts, win or not,
# and a live gap==0 tick would spend a real cnv-deploy call for no coverage
# reason. The guard below is therefore real and additive: before invoking
# the mix task, autofde-lab consults the LAST real before/after counts it
# observed from the previous invocation (persisted locally in
# DEFAULT_COVERAGE_STATE_FILE) and only invokes again once that
# last-observed gap (max count - min count) exceeds COVERAGE_GAP_THRESHOLD.
# Rationale for the threshold value: a single Act call moves exactly one
# class's count by +1 (confirmed in the ex source -- one Ash.create per
# run), so immediately after any Act the freshly-created imbalance is
# exactly gap==1 relative to the other four classes -- that is the
# *expected*, not-yet-actionable state right after closing a gap, so
# threshold must be > 1 to avoid re-triggering on every single tick chasing
# its own last Act. COVERAGE_GAP_THRESHOLD = 1 means "skip while gap <= 1,
# invoke once gap >= 2" -- the smallest threshold that does not fire on the
# task's own immediate self-perturbation. The very first tick, with no
# persisted state yet, always invokes once so a real gap baseline exists to
# compare against.
COVERAGE_GAP_THRESHOLD = 1

# FMEA finding this session, RPN=540 (Severity=6 x Occurrence=9 x
# Detection=10): the guard above is a real chicken-and-egg trap. The ONLY
# way to learn the CURRENT live gap is to invoke the mix task (it is the
# sole real Monitor step -- there is no read-only SPARQL-count path into
# xaas from here), but the guard blocks invocation whenever the LAST
# persisted gap was <= threshold. Confirmed real, current on-disk state:
# `.phase_h_coverage_state.json` has gap=0 (last real Monitor: all 5 classes
# at count=2), so every tick since has returned invoked=False with no way
# to tell "still genuinely healthy" from "permanently stuck" -- if the real
# live gap grew past threshold in the meantime (e.g. any real external
# K-graph write outside this trigger's own Act calls: xaas seed/import
# scripts, other automation, or a human running `mix
# xaas.close_coverage_gap` directly), this trigger would never rediscover
# it and would report "skipped" forever.
#
# Fix: a second, independent cadence that is NOT gated by the last-observed
# gap. MAX_CONSECUTIVE_SKIPS_BEFORE_PROBE bounds how many consecutive
# guard-held skips are allowed before the next tick is forced to invoke
# (probe) regardless of last_gap, re-discovering the real current state.
# This does not reintroduce the original problem (Act firing every tick
# even at gap==0): between forced probes, the threshold guard still holds
# exactly as before, so a genuinely healthy run of ticks still costs zero
# extra Act calls except for the bounded, periodic re-Monitor.
#
# Value: 5. Justification -- (a) must be > 1 tick, so the single expected
# post-Act perturbation (gap immediately becomes 1, see threshold rationale
# above) does not itself force a redundant second probe on the very next
# tick; (b) small enough that worst-case staleness ("using a stale prior
# observation instead of the live gap") is bounded and auditable -- at most
# 5 consecutive ticks -- never unbounded/permanent; (c) tick-count-based
# rather than wall-clock-based, since this repo has no established Phase H
# scheduling cadence to anchor a time threshold against (confirmed: no
# cron/systemd/launchd timer for phase_h_trigger exists in this repo --
# run_once() is invoked directly, once per process run), so counting
# invocations of this function itself is the only real, available signal.
MAX_CONSECUTIVE_SKIPS_BEFORE_PROBE = 5

FIXTURE_DOMAIN = REPO_ROOT / "tests" / "domains" / "python" / "pddl_domains" / "blocks" / "domain.pddl"
FIXTURE_PROBLEM = (
    REPO_ROOT / "tests" / "domains" / "python" / "pddl_domains" / "blocks" / "probBLOCKS-3-0.pddl"
)


def _sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True)
class DriftResult:
    drifted: bool
    watch_file: str
    baseline_sha256: str | None
    current_sha256: str


def read_baseline(baseline_file: Path = DEFAULT_BASELINE_FILE) -> str | None:
    """Return the stored baseline sha256, or None if no baseline exists yet."""
    if not baseline_file.exists():
        return None
    return json.loads(baseline_file.read_text())["sha256"]


def write_baseline(watch_file: Path = DEFAULT_WATCH_FILE, baseline_file: Path = DEFAULT_BASELINE_FILE) -> str:
    """Snapshot the current hash of watch_file as the new baseline."""
    digest = _sha256_of(watch_file)
    baseline_file.write_text(json.dumps({"watch_file": str(watch_file), "sha256": digest}, indent=2))
    return digest


def check_drift(
    watch_file: Path = DEFAULT_WATCH_FILE,
    baseline_file: Path = DEFAULT_BASELINE_FILE,
) -> DriftResult:
    """Compare the live ontology hash against the stored baseline."""
    current = _sha256_of(watch_file)
    baseline = read_baseline(baseline_file)
    return DriftResult(
        drifted=(baseline is not None and baseline != current),
        watch_file=str(watch_file),
        baseline_sha256=baseline,
        current_sha256=current,
    )


def unattended_solve() -> dict:
    """Invoke the real, in-process solve+falsify step with zero human input.

    Calls `fabric.solve_and_falsify.solve_and_falsify()` directly (no
    subprocess, no CLI re-invocation) against the real, already-working
    blocksworld fixture, and returns both the real trajectory receipt AND
    a real falsification standing -- the automatic trigger path now closes
    both halves of the loop (solve, then check the solve) in one call.
    """
    domain_arguments = {"domain_path": str(FIXTURE_DOMAIN), "problem_path": str(FIXTURE_PROBLEM)}
    result, falsification = solve_and_falsify(
        domain="PDDLDomain",
        domain_arguments=domain_arguments,
        solver="Astar",
    )
    return {
        "domain": "PDDLDomain",
        "standing": result.standing.value,
        "terminal": result.terminal,
        "steps": len(result.steps),
        "trajectory_sha256": result.receipt_sha256,
        "falsification": {
            "candidate_id": falsification.candidate_id,
            "standing": falsification.standing.value,
            "rationale": falsification.rationale,
            "receipt_refs": falsification.receipt_refs,
            "violated_constraints": falsification.violated_constraints,
        },
    }


def _read_coverage_state(state_file: Path = DEFAULT_COVERAGE_STATE_FILE) -> dict | None:
    if not state_file.exists():
        return None
    return json.loads(state_file.read_text())


def _write_coverage_state(state: dict, state_file: Path = DEFAULT_COVERAGE_STATE_FILE) -> None:
    state_file.write_text(json.dumps(state, indent=2, sort_keys=True))


def _parse_coverage_gap_output(stdout: str) -> dict:
    """Parse the real `mix xaas.close_coverage_gap` stdout.

    Pulls the "before" per-class counts (`  aacm:<Class> -> <n>` lines,
    the first block printed under "Monitor: real K graph (before)") and
    the real "Closed-loop result: <Class> before=<n> after=<n>
    (delta=<n>)" line the task prints only once it reaches its own final
    Monitor step. If the task's Act step raised (e.g. a real downstream
    cnv-deploy error) the Closed-loop line is absent, which is captured
    honestly as closed=False rather than assumed to have happened.
    """
    before_counts: dict[str, int] = {}
    for match in re.finditer(r"aacm:(\w+)\s*->\s*(\d+)", stdout):
        cls, n = match.group(1), int(match.group(2))
        if cls not in before_counts:
            before_counts[cls] = n

    closed_match = re.search(
        r"Closed-loop result:\s*(\w+)\s*before=(\d+)\s*after=(\d+)\s*\(delta=(-?\d+)\)",
        stdout,
    )
    closed = closed_match is not None
    gap = (max(before_counts.values()) - min(before_counts.values())) if before_counts else 0
    result = {
        "before_counts": before_counts,
        "gap": gap,
        "closed": closed,
    }
    if closed_match:
        result["closed_class"] = closed_match.group(1)
        result["before"] = int(closed_match.group(2))
        result["after"] = int(closed_match.group(3))
        result["delta"] = int(closed_match.group(4))
    return result


def check_coverage_gap(
    xaas_repo_root: Path = XAAS_REPO_ROOT,
    state_file: Path = DEFAULT_COVERAGE_STATE_FILE,
    threshold: int = COVERAGE_GAP_THRESHOLD,
    max_consecutive_skips_before_probe: int = MAX_CONSECUTIVE_SKIPS_BEFORE_PROBE,
    timeout_seconds: int = 180,
    command: list[str] | None = None,
) -> dict:
    """Second real Phase H trigger: the xaas real-SPARQL K-graph coverage gap.

    Real, additive READ-then-invoke call from autofde-lab into xaas -- no
    code is copied or duplicated; `mix xaas.close_coverage_gap` itself
    remains the sole owner of the SPARQL count / least-exercised / Act
    logic (~/xaas/lib/mix/tasks/xaas.close_coverage_gap.ex, untouched).

    Guarded by `threshold` (see COVERAGE_GAP_THRESHOLD docstring above)
    using the last real gap this function itself observed, persisted in
    `state_file`, since the mix task has no internal guard of its own.

    Second, independent guard (the RPN=540 chicken-and-egg fix, see
    MAX_CONSECUTIVE_SKIPS_BEFORE_PROBE docstring above): every tick the
    threshold guard would skip, this function increments and persists a
    `skips_since_last_invoke` counter. Once that counter reaches
    `max_consecutive_skips_before_probe`, the next tick invokes anyway (a
    forced probe) regardless of the last-observed gap, so the trigger can
    never become permanently stuck reporting a stale "skipped" forever --
    worst case it goes stale for `max_consecutive_skips_before_probe`
    ticks, then self-corrects.

    Every returned dict carries a `detection_status` distinguishing real
    outcomes for a human/monitor (the Detection=10 half of the FMEA fix):
    - "verified_healthy_this_tick": invoked this tick, and the real live
      gap it observed is genuinely <= threshold right now.
    - "verified_gap_open_this_tick": invoked this tick, and the real live
      gap it observed is genuinely > threshold right now.
    - "stale_skip_using_prior_observation": did NOT invoke this tick;
      reporting the last real observation from `skips_since_last_invoke`
      ticks ago, not the current live state.

    `command` overrides the real subprocess argv (default
    `["mix", "xaas.close_coverage_gap"]`) -- used by tests to run a real,
    separate, controllable subprocess instead of the live xaas/Postgres/
    cnv-deploy stack, without mocking any of this function's own logic.
    """
    last_state = _read_coverage_state(state_file)
    last_gap = last_state.get("gap") if last_state else None
    skips_since_last_invoke = last_state.get("skips_since_last_invoke", 0) if last_state else 0

    guard_would_skip = last_state is not None and last_gap is not None and last_gap <= threshold
    forced_probe = guard_would_skip and skips_since_last_invoke >= max_consecutive_skips_before_probe

    if guard_would_skip and not forced_probe and last_state is not None:
        next_skip_count = skips_since_last_invoke + 1
        skip_state = dict(last_state)
        skip_state["skips_since_last_invoke"] = next_skip_count
        skip_state["detection_status"] = "stale_skip_using_prior_observation"
        skip_state["skip_reason"] = (
            f"last observed gap={last_gap} <= threshold={threshold}; "
            f"skip {next_skip_count}/{max_consecutive_skips_before_probe} "
            "before a forced re-probe"
        )
        _write_coverage_state(skip_state, state_file)
        return {
            "invoked": False,
            "reason": skip_state["skip_reason"],
            "detection_status": skip_state["detection_status"],
            "skips_since_last_invoke": next_skip_count,
            "last_state": last_state,
        }

    if last_state is None:
        invoke_reason = "no_prior_state"
    elif forced_probe:
        invoke_reason = (
            f"forced probe after {skips_since_last_invoke} consecutive skips "
            f"(max_consecutive_skips_before_probe={max_consecutive_skips_before_probe})"
        )
    else:
        invoke_reason = f"last observed gap={last_gap} > threshold={threshold}"

    try:
        proc = subprocess.run(
            list(command) if command is not None else ["mix", "xaas.close_coverage_gap"],
            cwd=str(xaas_repo_root),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        # Real gap closed 2026-08-21 (adversarial verification of the RPN=540
        # fix): every OTHER return path carries `detection_status` (the
        # Detection=10 half of the fix), but this transient-subprocess-
        # failure path did not. A monitor/consumer reading this field
        # unconditionally would KeyError precisely on a real failure --
        # the one moment Detection matters most. State does NOT get
        # persisted here on purpose: the on-disk skip counter is left as-is
        # so the very next tick recomputes forced_probe as still True and
        # retries, rather than silently losing the forced-probe state.
        return {
            "invoked": True,
            "error": f"{type(exc).__name__}: {exc}",
            "invoke_reason": invoke_reason,
            "detection_status": "invoke_failed_transient_error",
        }

    stdout = (proc.stdout or "") + (proc.stderr or "")
    parsed = _parse_coverage_gap_output(stdout)
    parsed["invoked"] = True
    parsed["returncode"] = proc.returncode
    parsed["skips_since_last_invoke"] = 0
    parsed["invoke_reason"] = invoke_reason
    parsed["detection_status"] = (
        "verified_healthy_this_tick" if parsed["gap"] <= threshold else "verified_gap_open_this_tick"
    )
    _write_coverage_state(parsed, state_file)
    return parsed


def run_once(
    watch_file: Path = DEFAULT_WATCH_FILE,
    baseline_file: Path = DEFAULT_BASELINE_FILE,
) -> dict:
    """The Phase H tick: check drift; if triggered, solve unattended.

    Returns a dict describing what happened -- always includes the drift
    result; includes the solve receipt only if the trigger actually fired.
    """
    drift = check_drift(watch_file, baseline_file)
    result: dict = {
        "phase": "H",
        "drift": {
            "drifted": drift.drifted,
            "watch_file": drift.watch_file,
            "baseline_sha256": drift.baseline_sha256,
            "current_sha256": drift.current_sha256,
        },
        "triggered": False,
    }
    if drift.drifted:
        receipt = unattended_solve()
        result["triggered"] = True
        result["architecture_change_trigger"] = {
            "evidence": "ontology sha256 diverged from stored baseline",
            "detected_drift": {
                "watch_file": drift.watch_file,
                "baseline_sha256": drift.baseline_sha256,
                "current_sha256": drift.current_sha256,
            },
            "trigger_policy": "sha256-baseline-diff",
        }
        result["solve_receipt"] = receipt
        # Absorb the drift: new baseline is the current hash, so the same
        # unresolved drift does not re-trigger on the next tick.
        write_baseline(watch_file, baseline_file)

    coverage = check_coverage_gap()
    result["coverage_gap"] = coverage
    result["coverage_triggered"] = bool(coverage.get("invoked") and coverage.get("closed"))
    return result


def main() -> None:
    result = run_once()
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
