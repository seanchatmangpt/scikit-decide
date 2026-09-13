# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Deterministic sequential stability stopping for Monte Carlo EXPLORE runs.

This module adds a reversible stopping alternative to the fixed-``n`` Monte
Carlo generator in :mod:`autofde_lab.reasoning.laboratory`. It deliberately
makes no claim of statistical significance or distributional convergence.
Instead it implements a bounded engineering falsifier: continue drawing until
successive checkpoint means remain within an explicit absolute tolerance for a
caller-chosen number of consecutive checkpoints, or stop at ``max_samples``.

The rule is deterministic for a fixed seed/configuration, uses only the real
``MonteCarloCostModel.sample`` collaborator, rejects non-finite evidence before
it enters a stopping claim, and never changes authority or actuation semantics.
"""

from __future__ import annotations

import math
import random
import statistics
from dataclasses import dataclass
from enum import StrEnum

from autofde_lab.reasoning.laboratory import (
    DETERMINISTIC_SEED,
    MonteCarloCostModel,
    MonteCarloSample,
)


class StabilityStoppingReason(StrEnum):
    STABLE = "STABLE"
    MAX_SAMPLES = "MAX_SAMPLES"


@dataclass(frozen=True, slots=True)
class MonteCarloStabilityConfig:
    """Explicit bounds for the sequential engineering stability rule."""

    min_samples: int = 8
    checkpoint_every: int = 4
    absolute_mean_tolerance: float = 0.5
    consecutive_stable_checkpoints: int = 2
    max_samples: int = 64

    def __post_init__(self) -> None:
        if self.min_samples < 2:
            raise ValueError("min_samples must be >= 2")
        if self.checkpoint_every < 1:
            raise ValueError("checkpoint_every must be >= 1")
        if not math.isfinite(self.absolute_mean_tolerance):
            raise ValueError("absolute_mean_tolerance must be finite")
        if self.absolute_mean_tolerance < 0:
            raise ValueError("absolute_mean_tolerance must be >= 0")
        if self.consecutive_stable_checkpoints < 1:
            raise ValueError("consecutive_stable_checkpoints must be >= 1")
        if self.max_samples < self.min_samples:
            raise ValueError("max_samples must be >= min_samples")


@dataclass(frozen=True, slots=True)
class StabilityCheckpoint:
    sample_count: int
    mean: float
    previous_mean: float | None
    absolute_delta: float | None
    stable: bool
    stable_run_length: int


@dataclass(frozen=True, slots=True)
class MonteCarloStabilityOutcome:
    samples: tuple[MonteCarloSample, ...]
    checkpoints: tuple[StabilityCheckpoint, ...]
    reason: StabilityStoppingReason

    @property
    def sample_count(self) -> int:
        return len(self.samples)

    @property
    def stopped_early(self) -> bool:
        return self.reason is StabilityStoppingReason.STABLE


def draw_until_mean_stable(
    cost_model: MonteCarloCostModel,
    config: MonteCarloStabilityConfig,
    *,
    seed: int = DETERMINISTIC_SEED,
) -> MonteCarloStabilityOutcome:
    """Draw real samples until bounded checkpoint-mean stability or cap.

    Checkpoints start only once ``min_samples`` have been observed. Thereafter
    a checkpoint is taken every ``checkpoint_every`` samples and always at
    ``max_samples`` so the terminal state is observable even when the cap is
    not aligned to the cadence. A checkpoint is stable iff its mean differs
    from the immediately preceding checkpoint mean by no more than the caller's
    absolute tolerance. ``consecutive_stable_checkpoints`` such observations
    are required before early stop.
    """

    rng = random.Random(seed)
    samples: list[MonteCarloSample] = []
    checkpoints: list[StabilityCheckpoint] = []
    previous_mean: float | None = None
    stable_run_length = 0

    for draw_index in range(config.max_samples):
        cost_bound = cost_model.sample(rng)
        if not math.isfinite(cost_bound):
            raise ValueError("REFUSED:NONFINITE_MONTE_CARLO_SAMPLE")
        samples.append(MonteCarloSample(draw_index=draw_index, cost_bound=cost_bound))
        sample_count = len(samples)

        eligible = sample_count >= config.min_samples
        cadence_hit = (
            eligible
            and (sample_count - config.min_samples) % config.checkpoint_every == 0
        )
        terminal = sample_count == config.max_samples
        if not (cadence_hit or terminal):
            continue

        mean = statistics.fmean(sample.cost_bound for sample in samples)
        delta = None if previous_mean is None else abs(mean - previous_mean)
        stable = delta is not None and delta <= config.absolute_mean_tolerance
        stable_run_length = stable_run_length + 1 if stable else 0

        checkpoints.append(
            StabilityCheckpoint(
                sample_count=sample_count,
                mean=mean,
                previous_mean=previous_mean,
                absolute_delta=delta,
                stable=stable,
                stable_run_length=stable_run_length,
            )
        )
        previous_mean = mean

        if stable_run_length >= config.consecutive_stable_checkpoints:
            return MonteCarloStabilityOutcome(
                samples=tuple(samples),
                checkpoints=tuple(checkpoints),
                reason=StabilityStoppingReason.STABLE,
            )

    return MonteCarloStabilityOutcome(
        samples=tuple(samples),
        checkpoints=tuple(checkpoints),
        reason=StabilityStoppingReason.MAX_SAMPLES,
    )
