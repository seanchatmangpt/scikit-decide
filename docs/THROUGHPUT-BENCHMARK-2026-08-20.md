# Throughput Benchmark — 2026-08-20

Real, minimal reproducible benchmark of the Astar solver against two real
autofde-lab domains, run on this machine. Numbers below are copied from the
real captured log at `logs/throughput-benchmark-2026-08-20.log` (also
reproduced inline as `RESULTS_JSON` at the end of that log).

## Machine

- Darwin Mac.lan 25.2.0, arm64
- Apple M3 Max, 16 cores
- Python 3.13.9, repo venv (`.venv`)

## Method

Script: `scripts/throughput_benchmark.py`

For each domain: construct a fresh domain instance, time
`Astar(domain_factory=...).solve()` with `time.perf_counter()`, repeat N
times in a loop. Reports solves/sec (N / total wall time) and
mean/median/p95/min/max per-solve latency in ms.

Run:

```
python scripts/throughput_benchmark.py
```

## Results

### Domain 1: Maze + Astar (N=50)

Small deterministic grid domain (`src/autofde_lab/hub/domain/maze/maze.py`),
same domain used in `examples/optuna_maze*.py`.

| metric | value |
|---|---|
| N | 50 |
| total wall time | 0.2502 s |
| solves/sec | 199.80 |
| mean latency | 5.00 ms |
| median latency | 4.87 ms |
| p95 latency | 5.87 ms |
| min / max | 4.70 ms / 7.40 ms |

### Domain 2: PDDLDomain (blocks-3-0) + Astar (N=10)

PDDL blocksworld domain (`autofde_lab.hub.domain.pddl.PDDLDomain`), problem
`tests/domains/python/pddl_domains/blocks/probBLOCKS-3-0.pddl` — the same
fixture used in `tests/domains/python/test_pddl_domain.py::test_astar_solve_blocks`.
Each repeat re-parses the PDDL domain/problem files from disk (real per-solve
construction cost, not amortized).

| metric | value |
|---|---|
| N | 10 |
| total wall time | 0.02774 s |
| solves/sec | 360.53 |
| mean latency | 2.77 ms |
| median latency | 2.60 ms |
| p95 latency | 3.89 ms |
| min / max | 2.48 ms / 3.89 ms |

## Do not average these two numbers

Maze and blocksworld are different domains with very different
state-space/construction complexity: Maze's `solve()` includes a small grid
BFS-like A* over its own state space with no external parsing; blocksworld's
per-repeat cost includes reparsing/regrounding a real PDDL domain+problem
file pair from disk on every repeat. The higher "solves/sec" for blocksworld
here reflects this specific tiny 3-block problem's tiny search space, not
that blocksworld is a "faster" domain class than Maze in general. Report
each domain's number on its own; do not compute a combined ops/sec across
domains.

## Raw log

Full captured output (including real solver debug logging) is at
`logs/throughput-benchmark-2026-08-20.log`.
