# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for deterministic Monte Carlo stability stopping.

Real ``MonteCarloCostModel`` collaborators and real seeded ``random.Random``
draws are used throughout. Collaborators remain real throughout.
"""

from __future__ import annotations

import pytest

from autofde_lab.reasoning.laboratory import (
    DETERMINISTIC_SEED,
    MonteCarloCostModel,
    MonteCarloDistribution,
)
from autofde_lab.reasoning.montecarlo_stopping import (
    MonteCarloStabilityConfig,
    StabilityStoppingReason,
    draw_until_mean_stable,
)

CONSTANT_MODEL = MonteCarloCostModel(
    distribution=MonteCarloDistribution.UNIFORM, low=42.0, high=42.0
)
WIDE_MODEL = MonteCarloCostModel(
    distribution=MonteCarloDistribution.UNIFORM, low=0.0, high=100.0
)


def test_constant_real_distribution_stops_after_required_stable_checkpoints() -> None:
    config = MonteCarloStabilityConfig(
        min_samples=4,
        checkpoint_every=2,
        absolute_mean_tolerance=0.0,
        consecutive_stable_checkpoints=2,
        max_samples=20,
    )

    outcome = draw_until_mean_stable(CONSTANT_MODEL, config, seed=DETERMINISTIC_SEED)

    assert outcome.reason is StabilityStoppingReason.STABLE
    assert outcome.sample_count == 8
    assert tuple(c.sample_count for c in outcome.checkpoints) == (4, 6, 8)
    assert tuple(c.stable_run_length for c in outcome.checkpoints) == (0, 1, 2)
    assert all(sample.cost_bound == 42.0 for sample in outcome.samples)


def test_zero_tolerance_wide_distribution_hits_max_samples_instead_of_claiming_convergence() -> (
    None
):
    config = MonteCarloStabilityConfig(
        min_samples=4,
        checkpoint_every=2,
        absolute_mean_tolerance=0.0,
        consecutive_stable_checkpoints=2,
        max_samples=12,
    )

    outcome = draw_until_mean_stable(WIDE_MODEL, config, seed=DETERMINISTIC_SEED)

    assert outcome.reason is StabilityStoppingReason.MAX_SAMPLES
    assert outcome.sample_count == 12
    assert outcome.checkpoints[-1].sample_count == 12
    assert outcome.stopped_early is False


def test_sequential_rule_is_deterministic_across_two_real_runs() -> None:
    config = MonteCarloStabilityConfig(
        min_samples=6,
        checkpoint_every=3,
        absolute_mean_tolerance=5.0,
        consecutive_stable_checkpoints=2,
        max_samples=30,
    )

    left = draw_until_mean_stable(WIDE_MODEL, config, seed=DETERMINISTIC_SEED)
    right = draw_until_mean_stable(WIDE_MODEL, config, seed=DETERMINISTIC_SEED)

    assert left == right
    assert tuple(s.sample_id for s in left.samples) == tuple(
        s.sample_id for s in right.samples
    )


def test_fixed_n_previous_alternative_and_stability_rule_share_identical_seed_prefix() -> (
    None
):
    """Compare against fixed-n without manufacturing a different RNG process."""
    from autofde_lab.reasoning.laboratory import draw_monte_carlo_samples

    config = MonteCarloStabilityConfig(
        min_samples=4,
        checkpoint_every=2,
        absolute_mean_tolerance=0.0,
        consecutive_stable_checkpoints=2,
        max_samples=12,
    )
    adaptive = draw_until_mean_stable(WIDE_MODEL, config, seed=DETERMINISTIC_SEED)
    fixed = draw_monte_carlo_samples(
        WIDE_MODEL, adaptive.sample_count, seed=DETERMINISTIC_SEED
    )

    assert adaptive.samples == fixed


def test_terminal_checkpoint_exists_when_max_samples_is_off_cadence() -> None:
    config = MonteCarloStabilityConfig(
        min_samples=5,
        checkpoint_every=4,
        absolute_mean_tolerance=0.0,
        consecutive_stable_checkpoints=3,
        max_samples=12,
    )

    outcome = draw_until_mean_stable(WIDE_MODEL, config, seed=DETERMINISTIC_SEED)

    assert outcome.reason is StabilityStoppingReason.MAX_SAMPLES
    assert tuple(c.sample_count for c in outcome.checkpoints) == (5, 9, 12)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"min_samples": 1}, "min_samples must be >= 2"),
        ({"checkpoint_every": 0}, "checkpoint_every must be >= 1"),
        ({"absolute_mean_tolerance": -0.1}, "absolute_mean_tolerance must be >= 0"),
        (
            {"absolute_mean_tolerance": float("nan")},
            "absolute_mean_tolerance must be finite",
        ),
        (
            {"absolute_mean_tolerance": float("inf")},
            "absolute_mean_tolerance must be finite",
        ),
        (
            {"consecutive_stable_checkpoints": 0},
            "consecutive_stable_checkpoints must be >= 1",
        ),
        ({"min_samples": 10, "max_samples": 9}, "max_samples must be >= min_samples"),
    ],
)
def test_invalid_stopping_configs_refuse_before_sampling(
    kwargs: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        MonteCarloStabilityConfig(**kwargs)


def test_nonfinite_real_sample_refuses_before_stability_claim() -> None:
    nonfinite_model = MonteCarloCostModel(
        distribution=MonteCarloDistribution.UNIFORM,
        low=float("nan"),
        high=float("nan"),
    )
    config = MonteCarloStabilityConfig(min_samples=2, max_samples=4)

    with pytest.raises(ValueError, match="^REFUSED:NONFINITE_MONTE_CARLO_SAMPLE$"):
        draw_until_mean_stable(nonfinite_model, config, seed=DETERMINISTIC_SEED)
