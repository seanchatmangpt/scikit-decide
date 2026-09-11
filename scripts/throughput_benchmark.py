#!/usr/bin/env python
# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.
"""Real, minimal reproducible throughput benchmark for autofde-lab.

Runs the real Astar solver against two real, already-proven domains:
  1. Maze (src/autofde_lab/hub/domain/maze/maze.py) -- small grid domain.
  2. PDDLDomain / blocks-3-0 (tests/domains/python/pddl_domains/blocks) --
     PDDL blocksworld domain, same fixture used by
     tests/domains/python/test_pddl_domain.py::test_astar_solve_blocks.

Each solve is timed with time.perf_counter(). Reports solves/sec and
mean/median/p95 latency per domain. The two domains are NOT averaged
together -- they have very different state-space complexity (Maze is a
small deterministic grid; blocksworld involves PDDL grounding/parsing on
every fresh domain construction), so a single combined number would be
misleading.

Usage:
    python scripts/throughput_benchmark.py
"""
from __future__ import annotations

import json
import os
import statistics
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "src"))

PDDL_DIR = os.path.join(REPO_ROOT, "tests", "domains", "python", "pddl_domains")
BLOCKS_DOMAIN = os.path.join(PDDL_DIR, "blocks", "domain.pddl")
BLOCKS_PROBLEM = os.path.join(PDDL_DIR, "blocks", "probBLOCKS-3-0.pddl")


def _percentile(sorted_values: list[float], pct: float) -> float:
    """Nearest-rank percentile over an already-sorted list."""
    if not sorted_values:
        return float("nan")
    k = max(0, min(len(sorted_values) - 1, int(round(pct / 100 * (len(sorted_values) - 1)))))
    return sorted_values[k]


def _summarize(name: str, latencies_s: list[float]) -> dict:
    sorted_lat = sorted(latencies_s)
    total = sum(latencies_s)
    n = len(latencies_s)
    summary = {
        "domain": name,
        "n": n,
        "total_wall_s": total,
        "solves_per_sec": n / total if total > 0 else float("nan"),
        "mean_ms": statistics.mean(latencies_s) * 1000,
        "median_ms": statistics.median(latencies_s) * 1000,
        "p95_ms": _percentile(sorted_lat, 95) * 1000,
        "min_ms": min(latencies_s) * 1000,
        "max_ms": max(latencies_s) * 1000,
    }
    return summary


def bench_maze(n: int) -> dict:
    from autofde_lab.hub.domain.maze.maze import Maze
    from autofde_lab.hub.solver.astar.astar import Astar

    latencies = []
    for _ in range(n):
        domain = Maze()
        t0 = time.perf_counter()
        with Astar(domain_factory=lambda: domain) as solver:
            solver.solve()
        t1 = time.perf_counter()
        latencies.append(t1 - t0)
    return _summarize("maze/Astar", latencies)


def bench_blocksworld(n: int) -> dict:
    from autofde_lab.hub.domain.pddl import PDDLDomain
    from autofde_lab.hub.solver.astar.astar import Astar

    latencies = []
    for _ in range(n):
        domain = PDDLDomain(BLOCKS_DOMAIN, BLOCKS_PROBLEM)
        t0 = time.perf_counter()
        with Astar(domain_factory=lambda: domain) as solver:
            solver.solve()
        t1 = time.perf_counter()
        latencies.append(t1 - t0)
    return _summarize("pddl-blocksworld/Astar", latencies)


def main() -> None:
    n_maze = int(os.environ.get("N_MAZE", "50"))
    n_blocks = int(os.environ.get("N_BLOCKS", "10"))

    print(f"=== autofde-lab throughput benchmark ===")
    print(f"python: {sys.version.split()[0]}  platform: {sys.platform}")
    print(f"repo: {REPO_ROOT}")
    print()

    print(f"[1/2] Maze + Astar, N={n_maze}")
    maze_result = bench_maze(n_maze)
    print(json.dumps(maze_result, indent=2))
    print()

    print(f"[2/2] PDDLDomain (blocks-3-0) + Astar, N={n_blocks}")
    blocks_result = bench_blocksworld(n_blocks)
    print(json.dumps(blocks_result, indent=2))
    print()

    print("NOTE: maze and blocksworld results are reported separately and")
    print("must not be averaged together -- different domains, different")
    print("state-space complexity, different per-solve construction cost.")

    print()
    print("=== RESULTS_JSON ===")
    print(json.dumps({"maze": maze_result, "blocksworld": blocks_result}, indent=2))


if __name__ == "__main__":
    main()
