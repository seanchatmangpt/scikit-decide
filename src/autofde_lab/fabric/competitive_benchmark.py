"""Comparable closed-loop benchmark court for AutoFDE vs model-centric systems."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from autofde_lab.fabric.metrics import first_persistent_crossover


class BenchmarkStanding(str, Enum):
    COMPARABLE = "COMPARABLE"
    REFUSED_WORKLOAD_MISMATCH = "REFUSED:WORKLOAD_MISMATCH"
    REFUSED_VERIFIER_MISMATCH = "REFUSED:VERIFIER_MISMATCH"
    REFUSED_REPETITION_MISMATCH = "REFUSED:REPETITION_MISMATCH"
    REFUSED_INCOMPLETE_CURVE = "REFUSED:INCOMPLETE_CURVE"


@dataclass(frozen=True, slots=True)
class BenchmarkPoint:
    architecture: str
    workload_digest: str
    verifier_digest: str
    repetitions: int
    verified_transitions: int
    total_cost_usd: float
    wall_time_s: float
    human_attention_s: float
    frontier_tokens: int

    def __post_init__(self) -> None:
        if self.repetitions <= 0:
            raise ValueError("repetitions must be > 0")
        if not 0 <= self.verified_transitions <= self.repetitions:
            raise ValueError("verified_transitions must be within [0, repetitions]")
        for name in ("total_cost_usd", "wall_time_s", "human_attention_s"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be non-negative")
        if self.frontier_tokens < 0:
            raise ValueError("frontier_tokens must be non-negative")

    @property
    def cost_per_verified_transition(self) -> float:
        if self.verified_transitions == 0:
            return float("inf")
        return self.total_cost_usd / self.verified_transitions


@dataclass(frozen=True, slots=True)
class CompetitiveReport:
    standing: BenchmarkStanding
    baseline: str
    challenger: str
    repetitions: tuple[int, ...]
    cost_crossover_n: int | None
    reason: str


def compare_curves(
    baseline_points: Iterable[BenchmarkPoint],
    challenger_points: Iterable[BenchmarkPoint],
    *,
    required_repetitions: tuple[int, ...] = (1, 10, 100, 1000),
) -> CompetitiveReport:
    baseline = tuple(baseline_points)
    challenger = tuple(challenger_points)
    baseline_name = baseline[0].architecture if baseline else "UNKNOWN"
    challenger_name = challenger[0].architecture if challenger else "UNKNOWN"

    if not baseline or not challenger:
        return CompetitiveReport(
            BenchmarkStanding.REFUSED_INCOMPLETE_CURVE,
            baseline_name,
            challenger_name,
            (),
            None,
            "both architectures require measured benchmark points",
        )

    workload_ids = {p.workload_digest for p in baseline + challenger}
    if len(workload_ids) != 1:
        return CompetitiveReport(
            BenchmarkStanding.REFUSED_WORKLOAD_MISMATCH,
            baseline_name,
            challenger_name,
            (),
            None,
            "architectures were not measured on the exact same workload identity",
        )
    verifier_ids = {p.verifier_digest for p in baseline + challenger}
    if len(verifier_ids) != 1:
        return CompetitiveReport(
            BenchmarkStanding.REFUSED_VERIFIER_MISMATCH,
            baseline_name,
            challenger_name,
            (),
            None,
            "architectures were not judged by the exact same verifier identity",
        )

    by_baseline = {p.repetitions: p for p in baseline}
    by_challenger = {p.repetitions: p for p in challenger}
    if set(by_baseline) != set(by_challenger):
        return CompetitiveReport(
            BenchmarkStanding.REFUSED_REPETITION_MISMATCH,
            baseline_name,
            challenger_name,
            tuple(sorted(set(by_baseline) & set(by_challenger))),
            None,
            "benchmark curves do not contain identical repetition counts",
        )
    missing = tuple(n for n in required_repetitions if n not in by_baseline)
    if missing:
        return CompetitiveReport(
            BenchmarkStanding.REFUSED_INCOMPLETE_CURVE,
            baseline_name,
            challenger_name,
            tuple(sorted(by_baseline)),
            None,
            f"required repetition checkpoints are missing: {missing}",
        )

    baseline_cost = {
        n: point.cost_per_verified_transition for n, point in by_baseline.items()
    }
    challenger_cost = {
        n: point.cost_per_verified_transition for n, point in by_challenger.items()
    }
    crossover = first_persistent_crossover(baseline_cost, challenger_cost)
    return CompetitiveReport(
        BenchmarkStanding.COMPARABLE,
        baseline_name,
        challenger_name,
        tuple(sorted(by_baseline)),
        crossover,
        (
            "persistent cost-per-verified-transition crossover established"
            if crossover is not None
            else "curves are comparable but no persistent cost crossover is established"
        ),
    )
