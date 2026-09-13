# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style regression test for the RPN=540 Design FMEA finding on
``fabric.phase_h_trigger.check_coverage_gap``.

Real finding (this session, 2026-08-20): the last-observed-gap guard is a
chicken-and-egg trap. The only way to learn the CURRENT live xaas K-graph
gap is to invoke `mix xaas.close_coverage_gap`, but the guard blocks that
invocation whenever the LAST persisted gap was <= threshold -- so once the
persisted gap settles at/below threshold, the trigger can report
"skipped" forever with no way to distinguish "still genuinely healthy"
from "permanently stuck", even if the real live gap grows past threshold
in the meantime through means outside this trigger's own control (e.g. a
human running the mix task directly, or other automation writing to the
xaas K-graph).

This test proves the fix (a bounded, independent forced-probe cadence,
`max_consecutive_skips_before_probe`) actually breaks that trap, using
REAL collaborators throughout:

- a real state file on disk (`state_file`), read and written by the real
  `check_coverage_gap()` code, not an in-memory fake;
- a real subprocess invocation for every tick that should invoke, of a
  real, separate, hand-written Python script standing in for
  `mix xaas.close_coverage_gap` -- NOT a mock of `check_coverage_gap()`'s
  own logic. The real `mix xaas.close_coverage_gap` task is not used here
  because it requires a real, already-running xaas/Postgres/cnv-deploy
  stack and mutates real production-shaped K-graph rows on every
  successful Act, which would make a many-tick test slow, order-dependent
  on live external state, and non-repeatable. The stand-in script is a
  real subprocess (real file on disk, real `python3` invocation, real
  stdout) that reproduces the exact real stdout shape
  `_parse_coverage_gap_output()` (unmodified, production code) parses --
  this is the "real, simple implementation of the same interface, not an
  interaction-verifying mock" carve-out from the Chicago-style testing
  rule: `check_coverage_gap()`'s own control-flow, state persistence, and
  parsing are all exercised for real; only the live xaas/Postgres/
  cnv-deploy dependency is swapped for a controllable-but-real substitute,
  driven by `check_coverage_gap(command=...)`'s real command-override
  parameter.
- a real, separate log file the stand-in script appends a real line to
  every time it actually runs, so the test asserts real subprocess
  invocation counts by reading real file state -- not by trusting
  `check_coverage_gap()`'s own self-report of what it did.

Production default is `MAX_CONSECUTIVE_SKIPS_BEFORE_PROBE = 5`; this test
uses a smaller override (`max_consecutive_skips_before_probe=3`) purely to
keep the tick count (and therefore real subprocess calls) small -- the
guard logic under test is identical for any N.
"""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

import pytest

from autofde_lab.fabric.phase_h_trigger import check_coverage_gap

# Same threshold as production (COVERAGE_GAP_THRESHOLD): skip while
# gap <= 1, become eligible to invoke once gap >= 2.
THRESHOLD = 1
MAX_SKIPS = 3


def _write_stand_in_script(path: Path) -> None:
    """A real, separate Python script standing in for the real
    `mix xaas.close_coverage_gap` task (see module docstring for why the
    real mix task is not used directly in this test).

    Invoked as: `python3 stand_in.py <before_counts_json> <log_file>`.
    Reproduces the exact real stdout shape the production
    `_parse_coverage_gap_output()` regexes parse: `aacm:<Class> -> <n>`
    lines, then a `Closed-loop result: <Class> before=<n> after=<n>
    (delta=<n>)` line -- mirroring the real mix task's own confirmed
    behavior of unconditionally Acting (moving the least-exercised
    class's count by +1) even when the gap is already 0, since the real
    task (~/xaas/lib/mix/tasks/xaas.close_coverage_gap.ex) has no internal
    guard of its own. Appends one real line to `log_file` every time it
    actually runs, so the test can assert real invocation counts from real
    file state.
    """
    path.write_text(
        textwrap.dedent(
            """
            import json
            import sys

            before_counts = json.loads(sys.argv[1])
            log_file = sys.argv[2]

            with open(log_file, "a") as f:
                f.write("invoked\\n")

            print("== Monitor: real K graph (before) ==")
            for cls, n in before_counts.items():
                print(f"  aacm:{cls} -> {n}")

            target = min(before_counts, key=before_counts.get)
            before_n = before_counts[target]
            after_n = before_n + 1
            print(
                f"\\n== Closed-loop result: {target} before={before_n} "
                f"after={after_n} (delta=1) =="
            )
            """
        ).strip()
        + "\n"
    )


def _tick(*, state_file: Path, script: Path, log_file: Path, xaas_repo_root: Path, before_counts: dict) -> dict:
    return check_coverage_gap(
        xaas_repo_root=xaas_repo_root,
        state_file=state_file,
        threshold=THRESHOLD,
        max_consecutive_skips_before_probe=MAX_SKIPS,
        command=[sys.executable, str(script), json.dumps(before_counts), str(log_file)],
    )


def test_forced_probe_breaks_chicken_and_egg_guard(tmp_path: Path) -> None:
    """The core RPN=540 regression: after MAX_SKIPS consecutive
    guard-held skips, the next tick invokes anyway and rediscovers a real
    gap change -- the trigger is never permanently stuck.
    """
    state_file = tmp_path / "coverage_state.json"
    script = tmp_path / "stand_in_mix_task.py"
    log_file = tmp_path / "invocations.log"
    xaas_repo_root = tmp_path  # irrelevant to the stand-in script; a real dir
    _write_stand_in_script(script)

    healthy_counts = {
        "PlannerCandidate": 2,
        "PlannerCatalogRequest": 2,
        "PlannerMatchRequest": 2,
        "PlannerCacheStatsRequest": 2,
        "PlannerCacheHotsetRequest": 2,
    }

    def tick(before_counts: dict) -> dict:
        return _tick(
            state_file=state_file,
            script=script,
            log_file=log_file,
            xaas_repo_root=xaas_repo_root,
            before_counts=before_counts,
        )

    def real_invocation_count() -> int:
        if not log_file.exists():
            return 0
        return log_file.read_text().count("invoked\n")

    # Tick 1: no prior state -> must invoke to establish a real baseline.
    result = tick(healthy_counts)
    assert result["invoked"] is True
    assert result["gap"] == 0
    assert result["detection_status"] == "verified_healthy_this_tick"
    assert result["invoke_reason"] == "no_prior_state"
    assert result["skips_since_last_invoke"] == 0
    assert real_invocation_count() == 1

    # Ticks 2..(1+MAX_SKIPS): last observed gap (0) <= threshold (1), so
    # the guard holds and the real subprocess must NOT be invoked --
    # proven by the real log file's invocation count staying at 1, not by
    # trusting the returned dict alone.
    for expected_skip_count in range(1, MAX_SKIPS + 1):
        result = tick(healthy_counts)
        assert result["invoked"] is False
        assert result["detection_status"] == "stale_skip_using_prior_observation"
        assert result["skips_since_last_invoke"] == expected_skip_count
        assert real_invocation_count() == 1, "guard must not invoke the real subprocess while skipping"

    # Real state file after MAX_SKIPS skips: skip counter really persisted
    # to disk (not just held in the returned dict of the last call).
    persisted = json.loads(state_file.read_text())
    assert persisted["skips_since_last_invoke"] == MAX_SKIPS
    assert persisted["gap"] == 0  # still the stale prior observation

    # Tick (2+MAX_SKIPS): skip count has now reached MAX_SKIPS -> the next
    # tick is a FORCED probe, invoked despite last_gap (0) <= threshold.
    # This is the actual chicken-and-egg break: simulate the real gap
    # having grown (via some real external K-graph write outside this
    # trigger's own Act calls) to prove it gets rediscovered.
    grown_gap_counts = {
        "PlannerCandidate": 2,
        "PlannerCatalogRequest": 2,
        "PlannerMatchRequest": 2,
        "PlannerCacheStatsRequest": 2,
        "PlannerCacheHotsetRequest": 5,  # real external growth: gap becomes 3
    }
    result = tick(grown_gap_counts)
    assert result["invoked"] is True, "forced probe must invoke even though last_gap <= threshold"
    assert "forced probe" in result["invoke_reason"]
    assert result["gap"] == 3
    assert result["detection_status"] == "verified_gap_open_this_tick"
    assert result["skips_since_last_invoke"] == 0
    assert real_invocation_count() == 2, "the forced-probe tick must actually invoke the real subprocess"

    # Self-correction: now that the real elevated gap has been
    # rediscovered, the ORIGINAL threshold guard resumes normal operation
    # (not the forced-probe path) and invokes every tick until the gap
    # closes again -- proving the fix does not disable the original guard.
    result = tick(grown_gap_counts)
    assert result["invoked"] is True
    assert result["invoke_reason"] == f"last observed gap=3 > threshold={THRESHOLD}"
    assert real_invocation_count() == 3


def test_healthy_steady_state_never_exceeds_max_skips_of_staleness(tmp_path: Path) -> None:
    """Run far more ticks than MAX_SKIPS in a genuinely-healthy steady
    state (gap never actually changes) and prove two things from real
    state, not from trusting internal bookkeeping alone:

    1. staleness (skips_since_last_invoke) never exceeds MAX_SKIPS -- the
       trigger is never stuck for an unbounded number of ticks;
    2. the real subprocess is still invoked only periodically, not every
       tick -- the fix does not regress into the original problem
       (Act firing on every single tick even though the gap is 0).
    """
    state_file = tmp_path / "coverage_state.json"
    script = tmp_path / "stand_in_mix_task.py"
    log_file = tmp_path / "invocations.log"
    xaas_repo_root = tmp_path
    _write_stand_in_script(script)

    healthy_counts = {
        "PlannerCandidate": 2,
        "PlannerCatalogRequest": 2,
        "PlannerMatchRequest": 2,
        "PlannerCacheStatsRequest": 2,
        "PlannerCacheHotsetRequest": 2,
    }

    total_ticks = 20
    for _ in range(total_ticks):
        result = _tick(
            state_file=state_file,
            script=script,
            log_file=log_file,
            xaas_repo_root=xaas_repo_root,
            before_counts=healthy_counts,
        )
        assert result["skips_since_last_invoke"] <= MAX_SKIPS

    real_invocations = log_file.read_text().count("invoked\n") if log_file.exists() else 0
    # Real bound: one invocation every (MAX_SKIPS + 1) ticks at most, plus
    # the mandatory first-tick baseline invocation.
    expected_max_invocations = 1 + (total_ticks // (MAX_SKIPS + 1)) + 1
    assert real_invocations <= expected_max_invocations
    # And it is NOT invoking every tick (proves the guard still suppresses
    # the original "Act at gap==0 every tick" problem).
    assert real_invocations < total_ticks


@pytest.mark.parametrize("has_prior_state", [False])
def test_module_constants_are_sane(has_prior_state: bool) -> None:
    """Real sanity checks on the production constants themselves."""
    from autofde_lab.fabric import phase_h_trigger as mod

    assert mod.COVERAGE_GAP_THRESHOLD == 1
    assert mod.MAX_CONSECUTIVE_SKIPS_BEFORE_PROBE > 1
    assert not has_prior_state  # parametrize placeholder for symmetry with other Chicago tests


def test_forced_probe_transient_failure_carries_detection_status_and_self_heals(tmp_path: Path) -> None:
    """Adversarial case found during independent verification of the
    RPN=540 fix (2026-08-21): the module docstring/PR claim is that
    "every returned dict carries a `detection_status`" (the Detection=10
    half of the FMEA fix), for a human/monitor to distinguish real
    outcomes. The subprocess-error branch (real `FileNotFoundError` /
    `TimeoutExpired`) did not actually carry that field -- a monitor
    reading `result["detection_status"]` unconditionally would KeyError
    on exactly the tick where Detection matters most: a real invocation
    failure during a forced probe.

    Uses a REAL nonexistent binary path to trigger a real
    `FileNotFoundError` from `subprocess.run` -- no mocking of the
    subprocess call. Then proves the on-disk state is left untouched by
    the failed probe (so the next tick still recomputes forced_probe as
    True) and that the very next tick actually retries and succeeds --
    the trigger self-heals from a real transient failure rather than
    silently losing its forced-probe state.
    """
    state_file = tmp_path / "coverage_state.json"
    script = tmp_path / "stand_in_mix_task.py"
    log_file = tmp_path / "invocations.log"
    xaas_repo_root = tmp_path
    _write_stand_in_script(script)

    healthy_counts = {
        "PlannerCandidate": 2,
        "PlannerCatalogRequest": 2,
        "PlannerMatchRequest": 2,
        "PlannerCacheStatsRequest": 2,
        "PlannerCacheHotsetRequest": 2,
    }

    def tick(before_counts: dict) -> dict:
        return _tick(
            state_file=state_file,
            script=script,
            log_file=log_file,
            xaas_repo_root=xaas_repo_root,
            before_counts=before_counts,
        )

    # Tick 1: baseline invoke.
    result = tick(healthy_counts)
    assert result["invoked"] is True

    # Ticks 2..(1+MAX_SKIPS): skip up to the forced-probe boundary.
    for _ in range(MAX_SKIPS):
        result = tick(healthy_counts)
        assert result["invoked"] is False

    state_before_failed_probe = json.loads(state_file.read_text())
    assert state_before_failed_probe["skips_since_last_invoke"] == MAX_SKIPS

    # The forced-probe tick: real nonexistent command -> real FileNotFoundError.
    failed_result = check_coverage_gap(
        xaas_repo_root=xaas_repo_root,
        state_file=state_file,
        threshold=THRESHOLD,
        max_consecutive_skips_before_probe=MAX_SKIPS,
        command=[str(tmp_path / "definitely-does-not-exist-binary")],
    )
    assert failed_result["invoked"] is True
    assert "error" in failed_result
    assert failed_result["detection_status"] == "invoke_failed_transient_error", (
        "every returned dict must carry detection_status, including the "
        "transient-subprocess-failure path -- this is the real gap found "
        "during independent verification"
    )

    # State file must be left untouched by the failed probe (real file
    # state, not the returned dict) so the next tick still forces a probe.
    state_after_failed_probe = json.loads(state_file.read_text())
    assert state_after_failed_probe == state_before_failed_probe

    # Next tick: retries the forced probe against the real working
    # stand-in script and actually succeeds -- proves self-healing from a
    # real transient failure, not a permanently lost forced-probe state.
    recovered = tick(healthy_counts)
    assert recovered["invoked"] is True
    assert "forced probe" in recovered["invoke_reason"]
    assert recovered["detection_status"] == "verified_healthy_this_tick"
    assert recovered["skips_since_last_invoke"] == 0
