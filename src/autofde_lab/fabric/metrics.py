"""Closed-loop metrics for AutoFDE experiments.

The metrics in this module score verified consequence rather than model output.
They are deliberately small and dependency-free so every experiment can emit
them, including environments where an LLM is absent from the hot path.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Mapping

from autofde_lab.fabric.selection import DecisionRegime


@dataclass(frozen=True, slots=True)
class ConsequenceReceipt:
    """One observed closed-loop transition used for aggregate metrics."""

    verified: bool
    value: float
    wall_time_s: float
    cost_usd: float
    human_attention_s: float
    frontier_tokens: int
    regime: DecisionRegime

    def __post_init__(self) -> None:
        if self.value < 0:
            raise ValueError("value must be non-negative")
        for name in ("wall_time_s", "cost_usd", "human_attention_s"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be non-negative")
        if self.frontier_tokens < 0:
            raise ValueError("frontier_tokens must be non-negative")


@dataclass(frozen=True, slots=True)
class ConsequenceMetrics:
    verified_value: float
    verified_transitions: int
    wall_time_s: float
    cost_usd: float
    human_attention_s: float
    frontier_tokens: int
    vct: float
    reuse_ratio: float
    verified_per_frontier_token: float
    tokens_per_verified_consequence: float


def _safe_ratio(numerator: float, denominator: float) -> float:
    if denominator > 0:
        return numerator / denominator
    if numerator > 0:
        return math.inf
    return 0.0


def compute_consequence_metrics(
    receipts: Iterable[ConsequenceReceipt],
) -> ConsequenceMetrics:
    """Aggregate closed-loop evidence.

    VCT keeps the conversation's exact multiplicative denominator:

        verified value / (wall time * cost * human attention)

    A zero denominator with positive verified value therefore yields ``inf``
    instead of silently adding an arbitrary epsilon. Experiments that need a
    non-zero normalization floor must declare it before calling this function.
    """

    rows = tuple(receipts)
    verified = tuple(row for row in rows if row.verified)
    verified_value = sum(row.value for row in verified)
    verified_transitions = len(verified)
    wall_time_s = sum(row.wall_time_s for row in rows)
    cost_usd = sum(row.cost_usd for row in rows)
    human_attention_s = sum(row.human_attention_s for row in rows)
    frontier_tokens = sum(row.frontier_tokens for row in rows)
    denominator = wall_time_s * cost_usd * human_attention_s
    vct = _safe_ratio(verified_value, denominator)
    reusable = sum(
        1 for row in verified if row.regime in (DecisionRegime.HOT, DecisionRegime.WARM)
    )
    reuse_ratio = _safe_ratio(float(reusable), float(verified_transitions))
    verified_per_frontier_token = _safe_ratio(
        float(verified_transitions), float(frontier_tokens)
    )
    tokens_per_verified = _safe_ratio(
        float(frontier_tokens), float(verified_transitions)
    )
    return ConsequenceMetrics(
        verified_value=verified_value,
        verified_transitions=verified_transitions,
        wall_time_s=wall_time_s,
        cost_usd=cost_usd,
        human_attention_s=human_attention_s,
        frontier_tokens=frontier_tokens,
        vct=vct,
        reuse_ratio=reuse_ratio,
        verified_per_frontier_token=verified_per_frontier_token,
        tokens_per_verified_consequence=tokens_per_verified,
    )


@dataclass(frozen=True, slots=True)
class CausalLatency:
    """Measured components of a closed causal loop."""

    observe_s: float = 0.0
    propagate_observation_s: float = 0.0
    admit_s: float = 0.0
    decide_s: float = 0.0
    propagate_command_s: float = 0.0
    actuate_s: float = 0.0
    observe_consequence_s: float = 0.0
    verify_s: float = 0.0

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be non-negative")

    @property
    def causal_diameter_s(self) -> float:
        return sum(getattr(self, name) for name in self.__dataclass_fields__)

    @property
    def cognition_fraction(self) -> float:
        total = self.causal_diameter_s
        return _safe_ratio(self.decide_s, total)

    @property
    def infinite_cognition_speedup_bound(self) -> float:
        """Amdahl bound if decision cognition were made infinitely fast."""
        total = self.causal_diameter_s
        if total == 0:
            return 1.0
        non_cognition = total - self.decide_s
        if non_cognition == 0:
            return math.inf
        return total / non_cognition


def first_persistent_crossover(
    baseline_cost: Mapping[int, float], autofde_cost: Mapping[int, float]
) -> int | None:
    """Return first N after which AutoFDE remains strictly cheaper.

    Only shared repetition counts are compared. This avoids claiming a
    crossover from incomparable measurements.
    """

    points = sorted(set(baseline_cost) & set(autofde_cost))
    for i, n in enumerate(points):
        tail = points[i:]
        if tail and all(autofde_cost[k] < baseline_cost[k] for k in tail):
            return n
    return None


@dataclass(frozen=True, slots=True)
class LittleLawMetrics:
    """Flow quantities for L = lambda * W."""

    work_in_progress: float
    throughput_per_s: float
    mean_wait_s: float

    @property
    def residual(self) -> float:
        if math.isinf(self.mean_wait_s):
            return (
                0.0
                if self.throughput_per_s == 0 and self.work_in_progress > 0
                else math.inf
            )
        return self.work_in_progress - self.throughput_per_s * self.mean_wait_s


def little_law_from_wip_and_throughput(
    work_in_progress: float, throughput_per_s: float
) -> LittleLawMetrics:
    """Derive W from measured L and lambda without hiding a zero-throughput queue."""
    if work_in_progress < 0 or throughput_per_s < 0:
        raise ValueError("Little's Law quantities must be non-negative")
    if throughput_per_s == 0:
        wait = math.inf if work_in_progress > 0 else 0.0
    else:
        wait = work_in_progress / throughput_per_s
    return LittleLawMetrics(work_in_progress, throughput_per_s, wait)
