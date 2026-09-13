#!/usr/bin/env python3
"""Real, measured benchmark of `autofde_lab.powl.guard_executor.execute`'s
`max_workers` concurrency (see `guard_executor.py`'s "Real concurrency for
independent `PartialOrder` branches" design section).

Two real workloads, because the answer to "what's the max useful
concurrency" is workload-dependent, not a single number:

- I/O-bound (`--workload io`, default): each atom sleeps for
  `--work-seconds`, simulating a real gated tool call (network round-trip,
  subprocess wait). The GIL is released during `time.sleep`, so real
  wall-clock speedup up to `max_workers == ready_set_width` is expected.
- CPU-bound (`--workload cpu`): each atom runs a real, un-vectorized Python
  busy loop for `--cpu-iterations` iterations. CPython's GIL serializes
  bytecode execution across threads, so this workload is expected to show
  little or no real speedup, and thread-pool overhead can make it *worse*
  past a small `max_workers` -- the benchmark measures and reports this
  real number, not an assumption.

Every timing here is a real `time.perf_counter()` measurement of a real
`execute()` call against a real `PartialOrder` of independent `Atom`s (no
`OrderEdge`s -- one single ready set of the requested width) -- never
estimated or interpolated.

`--fixture {running-example,hospital,pools-and-lanes}` swaps the synthetic
flat ready set for one of the real, structurally rich fixtures hand-ported
from `~/POWL`'s published example topology (see
`tests/powl/fixtures_upstream_powl_reference.py`'s own licensing-boundary
docstring -- `~/POWL` itself is never imported, here or anywhere in this
repo) -- a genuine combined-capability stress run (choice + concurrency +
loop together for `running-example`; pure concurrency for `hospital`;
choice + concurrency for `pools-and-lanes`), not just a synthetic flat
`PartialOrder`.

Usage:
    .venv/bin/python scripts/powl_runner_concurrency_benchmark.py
    .venv/bin/python scripts/powl_runner_concurrency_benchmark.py --workload cpu
    .venv/bin/python scripts/powl_runner_concurrency_benchmark.py --ready-width 64 --max-workers 1 2 4 8 16 32 64
    .venv/bin/python scripts/powl_runner_concurrency_benchmark.py --fixture running-example --max-workers 1 2 4 8
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from autofde_lab.powl.algebra import Atom, PartialOrder, PowlNode  # noqa: E402
from autofde_lab.powl.guard_executor import execute  # noqa: E402
from tests.powl.fixtures_upstream_powl_reference import (  # noqa: E402
    hospital_concurrent_shape,
    pools_and_lanes_choice_shape,
    running_example_choice_concurrency_loop_shape,
)

#: Deterministic guard resolutions for the two ChoiceGraph-shaped fixtures --
#: always the branch that reaches End without looping, so a benchmark run's
#: wall-clock time measures real concurrent atom work, not an intentionally
#: long/looping walk.
_FIXTURE_GUARD_RESOLUTIONS: dict[str, dict[str, bool]] = {
    "running-example": {"approved": True, "rejected": False, "needs_more_info": False},
    "pools-and-lanes": {"wants_to_pay_first": True},
}

_FIXTURE_BUILDERS = {
    "running-example": running_example_choice_concurrency_loop_shape,
    "hospital": hospital_concurrent_shape,
    "pools-and-lanes": pools_and_lanes_choice_shape,
}


def _io_invoker(work_seconds: float):
    def invoker(atom: Atom) -> str:
        time.sleep(work_seconds)
        return atom.label

    return invoker


def _cpu_invoker(iterations: int):
    def invoker(atom: Atom) -> str:
        total = 0
        for i in range(iterations):
            total += i * i
        return f"{atom.label}:{total}"

    return invoker


def _build_ready_set(width: int) -> PartialOrder:
    """`width` fully independent atoms -- no `OrderEdge`s, so the executor's
    real Kahn's-algorithm walk sees exactly one ready set of size `width`."""
    return PartialOrder(children=tuple(Atom(label=f"a{i}") for i in range(width)))


def _fixture_guard_evaluator(fixture: str):
    resolutions = _FIXTURE_GUARD_RESOLUTIONS.get(fixture, {})

    def evaluator(predicate_name: str, _predicate_args: dict) -> bool:
        return resolutions.get(predicate_name, False)

    return evaluator


def _run_once(node: PowlNode, invoker, max_workers: int, *, guard_evaluator, max_choice_transitions: int) -> float:
    start = time.perf_counter()
    execute(node, guard_evaluator=guard_evaluator, atom_invoker=invoker, max_choice_transitions=max_choice_transitions, max_workers=max_workers)
    return time.perf_counter() - start


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--workload", choices=["io", "cpu"], default="io")
    parser.add_argument("--work-seconds", type=float, default=0.05, help="io workload: real sleep per atom")
    parser.add_argument("--cpu-iterations", type=int, default=2_000_000, help="cpu workload: real busy-loop iterations per atom")
    parser.add_argument("--ready-width", type=int, default=16, help="number of independent atoms in the one ready set (synthetic fixture only)")
    parser.add_argument("--fixture", choices=["synthetic", *_FIXTURE_BUILDERS], default="synthetic", help="use a real hand-ported ~/POWL-shaped fixture instead of a synthetic flat ready set")
    parser.add_argument("--max-workers", type=int, nargs="+", default=[1, 2, 4, 8, 16, 32, 64])
    parser.add_argument("--repeats", type=int, default=3, help="real repeats per max_workers value; report the median")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.fixture == "synthetic":
        node: PowlNode = _build_ready_set(args.ready_width)
        guard_evaluator = lambda n, a: True  # noqa: E731 -- synthetic fixture has no ChoiceGraph
        max_choice_transitions = 1
    else:
        node = _FIXTURE_BUILDERS[args.fixture]()
        guard_evaluator = _fixture_guard_evaluator(args.fixture)
        max_choice_transitions = 20

    invoker = _io_invoker(args.work_seconds) if args.workload == "io" else _cpu_invoker(args.cpu_iterations)

    results: list[dict[str, object]] = []
    baseline: float | None = None
    for mw in args.max_workers:
        samples = sorted(
            _run_once(node, invoker, mw, guard_evaluator=guard_evaluator, max_choice_transitions=max_choice_transitions)
            for _ in range(args.repeats)
        )
        median = samples[len(samples) // 2]
        if baseline is None:
            baseline = median
        results.append(
            {
                "max_workers": mw,
                "median_seconds": round(median, 6),
                "samples_seconds": [round(s, 6) for s in samples],
                "speedup_vs_max_workers_1": round(baseline / median, 3) if median > 0 else float("inf"),
            }
        )

    report = {
        "workload": args.workload,
        "fixture": args.fixture,
        "ready_width": args.ready_width if args.fixture == "synthetic" else None,
        "work_seconds": args.work_seconds if args.workload == "io" else None,
        "cpu_iterations": args.cpu_iterations if args.workload == "cpu" else None,
        "repeats": args.repeats,
        "results": results,
    }

    if args.json:
        print(json.dumps(report, indent=2))
        return

    print(f"workload={args.workload} fixture={args.fixture}", end="")
    if args.fixture == "synthetic":
        print(f" ready_width={args.ready_width}", end="")
    if args.workload == "io":
        print(f" work_seconds={args.work_seconds}")
    else:
        print(f" cpu_iterations={args.cpu_iterations}")
    print(f"{'max_workers':>12}  {'median_s':>10}  {'speedup':>8}  samples_s")
    for r in results:
        samples = ", ".join(f"{s:.4f}" for s in r["samples_seconds"])  # type: ignore[union-attr]
        print(f"{r['max_workers']:>12}  {r['median_seconds']:>10.4f}  {r['speedup_vs_max_workers_1']:>7.2f}x  [{samples}]")


if __name__ == "__main__":
    main()
