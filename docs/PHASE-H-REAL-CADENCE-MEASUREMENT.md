# Phase H: Real 10-Tick Cadence Measurement

Real, unmodified-state measurement of `python -m autofde_lab.fabric.phase_h_trigger`
(which calls `run_once()` through `main()`), run 10 times in a row on 2026-08-21
against the live, current on-disk baseline/coverage-state files -- no reset, no
fixture substitution, no mocked `mix xaas.close_coverage_gap` subprocess. Each tick
was a real `.venv/bin/python -m autofde_lab.fabric.phase_h_trigger` process
invocation; ticks 4 and 10 made a real subprocess call into the live `~/xaas`
Elixir/Postgres stack (`returncode=0` both times).

Starting on-disk state before tick 1 (from a prior, unrelated session):
`.phase_h_coverage_state.json` had `gap=1`, `skips_since_last_invoke=2`.

## Real 10-tick table

| tick | drift.triggered | coverage_gap.invoked | coverage_gap.detection_status      | skips_since_last_invoke |
|-----:|:----------------:|:---------------------:|:------------------------------------|:------------------------:|
|    1 | False            | False                 | stale_skip_using_prior_observation  | 3                        |
|    2 | False            | False                 | stale_skip_using_prior_observation  | 4                        |
|    3 | False            | False                 | stale_skip_using_prior_observation  | 5                        |
|    4 | False            | **True**               | verified_healthy_this_tick          | 0                        |
|    5 | False            | False                 | stale_skip_using_prior_observation  | 1                        |
|    6 | False            | False                 | stale_skip_using_prior_observation  | 2                        |
|    7 | False            | False                 | stale_skip_using_prior_observation  | 3                        |
|    8 | False            | False                 | stale_skip_using_prior_observation  | 4                        |
|    9 | False            | False                 | stale_skip_using_prior_observation  | 5                        |
|   10 | False            | **True**               | verified_healthy_this_tick          | 0                        |

Real observed `gap` at each invoke (from `before_counts`, the live xaas K-graph
counts at the moment of that invoke): tick 4 `gap=0` (all 5 classes tied at 5, Act
bumped `PlannerCandidate` 5->6); tick 10 `gap=1` (`PlannerCandidate` at 6 vs. the
other 4 classes at 5, Act bumped `PlannerCatalogRequest` 5->6).

`drift.triggered` was `False` on all 10 ticks: `baseline_sha256 == current_sha256`
throughout (`5934c2005d7f9f2549548b49e08de7009bd0a182af84c112bb244851fe358a15`) --
the watched ontology file was never touched during this measurement, so the
solve+falsify half of Phase H never fired in this window. That is a real, expected
"no drift" outcome given no edits were made to
`ontology/autofde-lab-capabilities.ttl`, not evidence of a bug in the drift check.

Final on-disk `.phase_h_coverage_state.json` after tick 10 matches tick 10's
printed output exactly (`gap=1`, `skips_since_last_invoke=0`,
`detection_status=verified_healthy_this_tick`), confirming the state persisted to
disk is the same state the trigger reported.

## Analysis

### 1. Does the real skip counter cycle correctly?

Yes, exactly, with no divergence from the earlier synthetic-test predictions. The
real, measured `skips_since_last_invoke` sequence across the 10 live ticks,
continuing from the pre-existing on-disk value of 2, was:

```
3, 4, 5, [forced probe -> invoked, reset to 0], 1, 2, 3, 4, 5, [forced probe -> invoked, reset to 0]
```

The counter increments by exactly 1 on every guard-held skip, and the tick
immediately following an on-disk value of 5 is always a forced probe that invokes
`mix xaas.close_coverage_gap` for real and resets the counter to 0. This held on
both cycle boundaries observed in this window (tick 3->4 and tick 9->10). Real
production behavior matches the design and the earlier synthetic-test predictions
on this specific question -- no divergence found.

### 2. Real measured skip:invoke ratio vs. the theoretical cadence

Over these 10 real ticks: 8 skips, 2 invokes -- a raw 4:1 (80% skipped / 20%
invoked) ratio, which numerically coincides with the "4-skip-then-1-invoke-in-5"
framing.

That numeric coincidence is misleading about the real underlying cadence, and is
worth stating plainly: tracing the two real cycle boundaries actually captured in
this window (invoke at tick 4, next invoke at tick 10) shows the real repeating
unit is **6 ticks**, not 5 -- 5 consecutive skips (`skips_since_last_invoke` counts
1 through 5) followed by 1 forced-probe invoke that resets the counter to 0. That
is a 5:1 skip:invoke ratio per real cycle (~83.3% skipped / ~16.7% invoked), not
4:1. `MAX_CONSECUTIVE_SKIPS_BEFORE_PROBE=5` means "allow 5 consecutive skips,"
which real measurement confirms produces a 6-tick cycle (1 invoke tick + 5 skip
ticks), because the forced-probe check compares the counter's value *before* this
tick's would-be increment against the threshold (`skips_since_last_invoke >= 5`
fires on the tick that would otherwise become the 6th skip).

This window's apparent 4:1 ratio is a real artifact of the measurement's start
point, not the steady-state cadence: ticks 1-10 began mid-cycle at
`skips_since_last_invoke=2` (carried over from a prior, unrelated session) rather
than at a fresh cycle boundary of 0, so the first partial cycle in this window
(ticks 1-4) only contained 3 skips before its invoke instead of a full 5. The
second, complete cycle captured in this window (ticks 5-10) shows the true
cadence unambiguously: 5 skips then 1 invoke, 6 ticks total. Extrapolated over a
longer, cycle-aligned run, the real ratio converges to 5:1 (5 skips per invoke),
not 4:1.

### 3. Other real, unexpected behavior

One real subtlety, not a bug, worth flagging plainly: the `gap` value persisted
to `state_file` after an invoke -- the value the *next* tick's guard reads to
decide skip-vs-invoke -- is computed from that invoke's `before_counts` (the live
xaas K-graph counts observed immediately *before* that invoke's own `Act` step
ran), not from the resulting *after* imbalance `Act` itself just created. The
design rationale in the module's `MAX_CONSECUTIVE_SKIPS_BEFORE_PROBE` docstring
reasons about "the freshly-created imbalance is exactly gap==1" right after an
Act call -- but the real, persisted `gap` the next cycle's guard actually sees is
the *pre*-Act gap of the invoke that just ran, which can differ from 1. This was
directly observed in this measurement: tick 4's real invoke found all 5 classes
already tied at 5 (`gap=0` pre-Act) even though Act then bumped
`PlannerCandidate` to 6 (a real post-Act imbalance of 1) -- the persisted `gap`
carried into ticks 5-9's skip cycle was 0, not 1. The design still functioned
correctly (0 <= threshold=1, so the skip cycle proceeded exactly as it would
have with gap=1), and by tick 10's forced probe the live counts had drifted back
to the "expected" pre-Act gap of 1 (`PlannerCandidate` at 6 vs. the other four at
5, real accumulated drift from tick 4's own Act) -- so no incorrect skip/invoke
decision resulted from this in the window measured, but it is a real gap between
the docstring's stated post-Act-gap-is-1 assumption and what the code actually
persists and the next cycle actually reads.

No other unexpected behavior: `drift.triggered` was `False` and stable across all
10 ticks (the watched ontology file was not modified during this measurement);
both real invokes into the live `~/xaas` Elixir/Postgres stack returned
`returncode=0` with no timeout and no `FileNotFoundError` -- the
`invoke_failed_transient_error` resilience path was not exercised in this run.
