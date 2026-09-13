# tests/e2e

Real, mock-free tests of the *pipeline contract*:

```
load_registered_domain → load_registered_solver → check_domain → solve → rollout
```

for one representative domain+solver combination per domain family (toy/
game, scheduling, flight planning). See `docs/jtbd/end-to-end-testing.md`
for why this suite exists and who needs it.

This directory intentionally does **not** attempt full domain-internal
coverage — that is owned by `tests/domains/`, `tests/scheduling/`,
`tests/flight_planning/`, and `tests/solvers/`. It also does not attempt an
exhaustive domain × solver matrix: one primary, representative pairing per
family keeps the suite reviewable and its CI cost bounded.

Every test here goes through `skdecide.utils.load_registered_domain` /
`load_registered_solver` by *name*, the same way `CLAUDE.md`'s documented
client usage pattern does — never a hand-imported class bypassing the
registration mechanism, except where a file's own docstring says otherwise.

## Files

- `conftest.py` — shared skip markers for optional dependencies
  (`discrete-optimization`, flight-planning geo/perf packages).
- `test_simple_pipeline.py` — `Maze` + `Astar`, `RockPaperScissors`
  self-play. No optional dependencies; still requires the compiled
  `skdecide.hub.__skdecide_hub_cpp` extension for the `Astar` test.
- `test_scheduling_pipeline.py` — `RCPSP` + `PilePolicy` (pure Python) and
  `RCPSP` + `DOSolver` (via `discrete-optimization`).
- `test_flight_planning_pipeline.py` — `FlightPlanningDomain` + `pAstar`.

## CI

This suite runs inside `ci.yml`'s `integration` job (the full-qualification
rail), against the already-built wheel with all optional dependencies
installed. It is deliberately **not** wired into `pr-ci.yml`: several of
these tests need the compiled C++ extension, and building that on every PR
is exactly the cost `docs/ci.md`'s two-rail design keeps off the PR rail.
See `docs/jtbd/end-to-end-testing.md`'s non-goals for the rationale.
