# RCPSP Solver Standing vs Published Reference Makespans

`cp_reference_makespans` is the set of published-reference (PSPLIB J30/J120) optimal or
best-known RCPSP makespans this repo compares its own solvers against, instance-by-instance,
to compute a percentage gap. This report measures, on 2026-08-07, on this machine, via a real
local run of the repo's own solver harness (no mocks, no CI), how each registered solver method
in `solvers_map` performs against those reference makespans across its attempted instance set.

## Per-solver standing table

| method | instances_attempted | instances_solved | instances_matching_or_beating_reference (gap≤0) | mean_gap_pct | max_gap_pct | standing |
|---|---|---|---|---|---|---|
| PILE | 30 | 30 | 8 | 7.50 | 21.82 | PARTIAL_ALIVE |
| GA | 30 | 30 | 18 | 1.91 | 19.30 | PARTIAL_ALIVE |
| LS | 30 | 30 | 17 | 2.01 | 14.68 | PARTIAL_ALIVE |
| LP | 30 | 30 | 29 | -2.43 | 3.81 | PARTIAL_ALIVE |
| CP | 30 | 30 | 30 | -2.59 | 0.00 | ALIVE |
| LNS_CP | 23 | 23 | 23 | -2.80 | 0.00 | ALIVE |
| LNS_LP | 0 | 0 | 0 | — | — | UNVERIFIED (not registered in `solvers_map` for single-mode `RcpspProblem`; never attempted) |

Notes on the table:

- Zero exceptions occurred anywhere (`error: null` on all 173 rows), so `instances_attempted ==
  instances_solved` for every method that ran.
- LNS_CP's `instances_attempted` is 23, not 30 — the remaining 7 (`j1201_3` through `j1201_9.sm`)
  were never run because the harness hit its 620s wall-clock cap after `j1201_1.sm` alone took
  92.15s. LNS_CP earns ALIVE only over the 23 instances actually measured; there is no basis
  (measured or otherwise) for a claim about the missing 7.
- LP's one non-matching instance keeps it at PARTIAL_ALIVE by the stated rule (ALIVE requires
  gap≤0 on 100% of attempted instances) despite a negative mean gap.

## Grounded summary

Across the instances actually measured, **CP** is the solver method that gets closest to the
published RCPSP reference: over all 30 attempted instances it solved every one and matched-or-beat
the reference on all 30 (mean gap -2.59%, max gap 0.00%, standing ALIVE). **LNS_CP** shows an
equal or slightly better mean gap (-2.80%) and a matching 0.00% max gap with 100% match-or-beat,
but that result is grounded in only 23 of 30 target instances — 7 `j1201_*` instances were never
run due to the wall-clock cap on the harness, so LNS_CP's ALIVE standing is scoped to those 23 and
cannot be extended to claim SOTA-matching performance on the full 30-instance set. LP is the
closest fully-attempted-and-solved alternative behind CP, matching or beating the reference on
29/30 instances (mean gap -2.43%, one outlier at +3.81% keeps it PARTIAL_ALIVE rather than ALIVE).
PILE, GA, and LS all remain PARTIAL_ALIVE with substantially larger mean and max gaps (PILE worst
at mean 7.50% / max 21.82%), meaning they solved every attempted instance without error but
frequently produced makespans measurably above the published reference. LNS_LP was never
attempted — UNVERIFIED, not BLOCKED, since it was never given the chance to run rather than
having failed a run.

## Falsifiers

What would invalidate this report if found true:

- A `.sm` parse mismatch: if this repo's PSPLIB `.sm` parser silently produces a problem instance
  (different activity durations, resource capacities, or precedence edges) that diverges from
  PSPLIB's canonical instance, every gap-percentage number above is computed against the wrong
  problem and is void, even though the run itself executed without error.
- A solver method returning an infeasible or partial schedule that gets read as a completed
  makespan: if any of CP, LNS_CP, LP, GA, LS, or PILE terminates early (timeout, iteration cap) and
  the harness records the best-found-so-far schedule's length as if it were a verified-feasible
  final makespan, without checking precedence and resource-capacity feasibility on that returned
  schedule, the reported makespan (and therefore gap) for that instance is unverified, not scored.
- Reference-table drift: if `cp_reference_makespans` itself was populated from a source other than
  the canonical published PSPLIB best-known/optimal values (e.g. a locally recomputed value, or an
  outdated version of the table), every gap computed above compares against the wrong baseline.
- Wall-clock cap masking a correctness or performance regression: LNS_CP's 92.15s single-instance
  time on `j1201_1.sm` is reported as measured fact, but if that duration reflects a bug (e.g. an
  infinite or near-infinite improvement loop) rather than expected LNS behavior, treating the
  620s-cap cutoff as merely "ran out of time" rather than "may not converge" would overstate
  LNS_CP's practical standing.
- Double-counting or stale caching: if the 173-row result set includes cached results from a prior
  run rather than a fresh 2026-08-07 execution, the "real local run, no mocks" claim in this report
  is false.

## Final standing

On this session's local run, **CP matched or beat the published reference on 30/30 attempted
instances (mean gap -2.59%, max gap 0.00%)** — the closest fully-attempted solver to the published
RCPSP reference; LNS_CP matched or beat the reference on 23/23 attempted instances with a
numerically better mean gap (-2.80%) but was not attempted on the remaining 7 of the full 30.
