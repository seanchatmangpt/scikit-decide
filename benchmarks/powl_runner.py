#!/usr/bin/env python3
"""Deterministic benchmark harness for the AutoFDE POWL V2 concurrent runner.

The benchmark measures execution of real POWL models through ``PowlV2Runner``.
Every timed sample is first required to satisfy semantic completion and activity
count invariants. Timing a wrong or incomplete run is therefore a benchmark
failure, not a fast result.

The delayed workloads intentionally model FDE-style external/I/O work. They do
not claim CPU-parallel Python bytecode execution under CPython.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import statistics
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter_ns, sleep
from typing import Callable

from autofde_lab.powl.algebra import Atom, NodeId, OrderEdge, PartialOrder
from autofde_lab.powl.executor import is_final
from autofde_lab.powl.runner import (
    ActivityIntent,
    ActivityOutcome,
    PowlV2Runner,
    RunnerConfig,
    RunStatus,
)


class DelayDriver:
    """Concrete authority-neutral driver for deterministic I/O-like work."""

    def __init__(self, delay_seconds: float) -> None:
        self.delay_seconds = delay_seconds

    def execute(self, intent: ActivityIntent) -> ActivityOutcome:
        if self.delay_seconds:
            sleep(self.delay_seconds)
        return ActivityOutcome(metadata={"benchmark": True})


class NoopDriver:
    def execute(self, intent: ActivityIntent) -> ActivityOutcome:
        return ActivityOutcome(metadata={"benchmark": True})


@dataclass(frozen=True, slots=True)
class SampleSummary:
    name: str
    topology: str
    activities: int
    work_ms_per_activity: float
    verify_replay: bool
    workers: int
    repetitions: int
    warmups: int
    median_ms: float
    p95_ms: float
    min_ms: float
    max_ms: float
    throughput_activities_per_second: float
    peak_concurrency: int


@dataclass(frozen=True, slots=True)
class Comparison:
    name: str
    baseline: str
    candidate: str
    speedup: float


def git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return os.environ.get("GITHUB_SHA", "UNKNOWN")


def serial_model(size: int) -> PartialOrder:
    atoms = tuple(Atom(f"a{i}") for i in range(size))
    order = frozenset(
        OrderEdge(NodeId(index), NodeId(index + 1)) for index in range(size - 1)
    )
    return PartialOrder(atoms, order)


def parallel_model(size: int) -> PartialOrder:
    return PartialOrder(tuple(Atom(f"a{i}") for i in range(size)))


def percentile95(values: list[float]) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * 0.95) - 1)
    return ordered[index]


def benchmark_scenario(
    *,
    name: str,
    topology: str,
    model: PartialOrder,
    driver_factory: Callable[[], object],
    activity_count: int,
    work_ms: float,
    workers: int,
    warmups: int,
    repetitions: int,
    verify_replay: bool,
) -> SampleSummary:
    samples_ms: list[float] = []
    observed_peak = 0
    config = RunnerConfig(
        max_workers=workers,
        verify_replay=verify_replay,
        eager_start=True,
    )
    with PowlV2Runner(config) as runner:
        for ordinal in range(warmups + repetitions):
            driver = driver_factory()
            started = perf_counter_ns()
            evidence = runner.run(
                model,
                driver,  # type: ignore[arg-type]
                run_id=f"bench:{name}:{ordinal}",
            )
            elapsed_ms = (perf_counter_ns() - started) / 1_000_000

            if evidence.status is not RunStatus.COMPLETED:
                raise RuntimeError(
                    f"{name}: non-completed sample: {evidence.status}: {evidence.detail}"
                )
            if not is_final(model, evidence.final_marking):
                raise RuntimeError(f"{name}: sample did not reach final marking")
            if len(evidence.activity_records) != activity_count:
                raise RuntimeError(
                    f"{name}: expected {activity_count} activity records, "
                    f"observed {len(evidence.activity_records)}"
                )
            if evidence.failed_activities:
                raise RuntimeError(
                    f"{name}: observed {evidence.failed_activities} failed activities"
                )
            if topology == "serial" and evidence.peak_concurrency != 1:
                raise RuntimeError(
                    f"{name}: serial topology reached peak={evidence.peak_concurrency}"
                )
            if topology == "parallel":
                expected = min(workers, activity_count)
                # Zero-work tasks can finish before all workers are occupied, so
                # only delayed scenarios require saturation of the configured pool.
                if work_ms > 0 and evidence.peak_concurrency != expected:
                    raise RuntimeError(
                        f"{name}: expected saturated peak={expected}, "
                        f"observed {evidence.peak_concurrency}"
                    )
            observed_peak = max(observed_peak, evidence.peak_concurrency)
            if ordinal >= warmups:
                samples_ms.append(elapsed_ms)

    median_ms = statistics.median(samples_ms)
    return SampleSummary(
        name=name,
        topology=topology,
        activities=activity_count,
        work_ms_per_activity=work_ms,
        verify_replay=verify_replay,
        workers=workers,
        repetitions=repetitions,
        warmups=warmups,
        median_ms=median_ms,
        p95_ms=percentile95(samples_ms),
        min_ms=min(samples_ms),
        max_ms=max(samples_ms),
        throughput_activities_per_second=(activity_count * 1000.0) / median_ms,
        peak_concurrency=observed_peak,
    )


def pool_startup_benchmark(
    *, workers: int, warmups: int, repetitions: int
) -> dict[str, float]:
    samples_ms: list[float] = []
    for ordinal in range(warmups + repetitions):
        started = perf_counter_ns()
        runner = PowlV2Runner(RunnerConfig(max_workers=workers, eager_start=True))
        elapsed_ms = (perf_counter_ns() - started) / 1_000_000
        runner.close()
        if ordinal >= warmups:
            samples_ms.append(elapsed_ms)
    return {
        "median_ms": statistics.median(samples_ms),
        "p95_ms": percentile95(samples_ms),
        "min_ms": min(samples_ms),
        "max_ms": max(samples_ms),
    }


def format_table(summaries: list[SampleSummary]) -> str:
    header = (
        f"{'scenario':<24} {'median ms':>10} {'p95 ms':>10} {'act/s':>11} {'peak':>6}"
    )
    rows = [header, "-" * len(header)]
    for item in summaries:
        rows.append(
            f"{item.name:<24} {item.median_ms:>10.3f} {item.p95_ms:>10.3f} "
            f"{item.throughput_activities_per_second:>11.1f} "
            f"{item.peak_concurrency:>6}"
        )
    return "\n".join(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--warmups", type=int, default=2)
    parser.add_argument("--repetitions", type=int, default=9)
    parser.add_argument("--json", type=Path, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.workers < 1 or args.warmups < 0 or args.repetitions < 1:
        raise SystemExit("workers >= 1, warmups >= 0, repetitions >= 1 required")

    scenarios: list[SampleSummary] = []

    def add_pair(size: int, work_ms: float) -> None:
        delay_seconds = work_ms / 1000.0
        suffix = f"{size}x{work_ms:g}ms"
        scenarios.append(
            benchmark_scenario(
                name=f"serial-{suffix}",
                topology="serial",
                model=serial_model(size),
                driver_factory=lambda: DelayDriver(delay_seconds),
                activity_count=size,
                work_ms=work_ms,
                workers=args.workers,
                warmups=args.warmups,
                repetitions=args.repetitions,
                verify_replay=True,
            )
        )
        scenarios.append(
            benchmark_scenario(
                name=f"parallel-{suffix}",
                topology="parallel",
                model=parallel_model(size),
                driver_factory=lambda: DelayDriver(delay_seconds),
                activity_count=size,
                work_ms=work_ms,
                workers=args.workers,
                warmups=args.warmups,
                repetitions=args.repetitions,
                verify_replay=True,
            )
        )

    add_pair(8, 10.0)
    add_pair(64, 5.0)

    no_op_model = parallel_model(128)
    for verify_replay in (False, True):
        scenarios.append(
            benchmark_scenario(
                name=f"noop-128-replay-{'on' if verify_replay else 'off'}",
                topology="parallel",
                model=no_op_model,
                driver_factory=NoopDriver,
                activity_count=128,
                work_ms=0.0,
                workers=args.workers,
                warmups=args.warmups,
                repetitions=args.repetitions,
                verify_replay=verify_replay,
            )
        )

    by_name = {item.name: item for item in scenarios}

    def speedup(name: str, baseline: str, candidate: str) -> Comparison:
        return Comparison(
            name=name,
            baseline=baseline,
            candidate=candidate,
            speedup=by_name[baseline].median_ms / by_name[candidate].median_ms,
        )

    comparisons = [
        speedup("8-way I/O speedup", "serial-8x10ms", "parallel-8x10ms"),
        speedup("64-way I/O speedup", "serial-64x5ms", "parallel-64x5ms"),
    ]
    replay_off = by_name["noop-128-replay-off"].median_ms
    replay_on = by_name["noop-128-replay-on"].median_ms
    replay_tax_percent = ((replay_on / replay_off) - 1.0) * 100.0

    startup = pool_startup_benchmark(
        workers=args.workers,
        warmups=args.warmups,
        repetitions=args.repetitions,
    )
    report = {
        "schema": "autofde.powl.runner-benchmark.v1",
        "subject": {
            "git_sha": git_sha(),
            "workers": args.workers,
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "cpu_count": os.cpu_count(),
        },
        "method": {
            "warmups": args.warmups,
            "repetitions": args.repetitions,
            "timer": "time.perf_counter_ns",
            "delayed_workload": (
                "time.sleep; external/I/O-like, not CPU-parallel Python"
            ),
            "semantic_gate": (
                "COMPLETED + final marking + exact activity count + zero failures"
            ),
        },
        "pool_startup": startup,
        "scenarios": [asdict(item) for item in scenarios],
        "comparisons": [asdict(item) for item in comparisons],
        "replay_verification_tax_percent": replay_tax_percent,
    }

    print(format_table(scenarios))
    print()
    for comparison in comparisons:
        print(f"{comparison.name}: {comparison.speedup:.3f}x")
    print(f"replay verification tax: {replay_tax_percent:+.2f}%")
    print(f"8-worker eager pool startup median: {startup['median_ms']:.3f} ms")
    print(
        "POWL_BENCHMARK_JSON="
        + json.dumps(report, sort_keys=True, separators=(",", ":"))
    )

    if args.json is not None:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
