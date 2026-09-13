# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for `laboratory`'s Monte Carlo simulation
candidate generation module (section 16). Real collaborators throughout:
a real `random.Random(DETERMINISTIC_SEED)` instance driving real
`MonteCarloCostModel.sample()` draws, real `DesiredStateHypothesis`
instances constructed directly, real `draw_monte_carlo_samples`/
`generate_montecarlo_candidates` calls, real returned `MonteCarloSample`/
`ArchitectureCandidate` state asserted on. No `unittest.mock` / `Mock` /
`MagicMock` / `patch` / `monkeypatch` anywhere in this file.

Honestly scoped: this module covers exactly TWO real, named distributions
(`UNIFORM`, `TRIANGULAR`) over exactly ONE `ArchitectureCandidate` field
(`cost_bound`) -- explicitly NOT a full Bayesian/MCMC framework (no
posterior, no Markov chain, no convergence diagnostics); see the
module-level NOT COVERED note in `laboratory.py` section 16.
"""

from __future__ import annotations

import statistics

import pytest

from autofde_lab.reasoning.laboratory import (
    DETERMINISTIC_SEED,
    ArchitectureCandidate,
    DesiredStateHypothesis,
    MonteCarloCostModel,
    MonteCarloDistribution,
    MonteCarloSample,
    draw_monte_carlo_samples,
    generate_montecarlo_candidates,
)

UNIFORM_MODEL = MonteCarloCostModel(distribution=MonteCarloDistribution.UNIFORM, low=10.0, high=100.0)
TRIANGULAR_MODEL = MonteCarloCostModel(
    distribution=MonteCarloDistribution.TRIANGULAR, low=10.0, high=100.0, mode=25.0
)


def test_draw_monte_carlo_samples_emits_n_real_seeded_draws_within_range() -> None:
    samples = draw_monte_carlo_samples(UNIFORM_MODEL, 5, seed=DETERMINISTIC_SEED)

    assert len(samples) == 5
    for i, sample in enumerate(samples):
        assert isinstance(sample, MonteCarloSample)
        assert sample.draw_index == i
        assert 10.0 <= sample.cost_bound <= 100.0

    # real, deterministic per-draw digest -- distinct per sample
    assert len({s.sample_id for s in samples}) == 5


def test_draw_monte_carlo_samples_is_deterministic_across_two_real_runs() -> None:
    samples_1 = draw_monte_carlo_samples(UNIFORM_MODEL, 8, seed=DETERMINISTIC_SEED)
    samples_2 = draw_monte_carlo_samples(UNIFORM_MODEL, 8, seed=DETERMINISTIC_SEED)

    assert tuple(s.cost_bound for s in samples_1) == tuple(s.cost_bound for s in samples_2)
    assert tuple(s.sample_id for s in samples_1) == tuple(s.sample_id for s in samples_2)

    # a real different seed must not (in this fixed case, does not) collide
    samples_other_seed = draw_monte_carlo_samples(UNIFORM_MODEL, 8, seed=DETERMINISTIC_SEED + 1)
    assert tuple(s.cost_bound for s in samples_1) != tuple(s.cost_bound for s in samples_other_seed)


def test_generate_montecarlo_candidates_candidate_id_sequence_is_deterministic_across_two_real_runs() -> None:
    """The explicit determinism test: same seed and n, called for real
    twice, must produce a byte-identical candidate_id sequence."""
    hypothesis = DesiredStateHypothesis(
        hypothesis_id="rule-based-v1",
        targets=({"kind": "latency_reduction"},),
        evidence_used_refs=("obs-1",),
    )

    run_1 = generate_montecarlo_candidates((hypothesis,), UNIFORM_MODEL, 6, seed=DETERMINISTIC_SEED)
    run_2 = generate_montecarlo_candidates((hypothesis,), UNIFORM_MODEL, 6, seed=DETERMINISTIC_SEED)

    assert tuple(c.candidate_id for c in run_1) == tuple(c.candidate_id for c in run_2)
    assert tuple(c.cost_bound for c in run_1) == tuple(c.cost_bound for c in run_2)
    assert len(run_1) == 6
    assert len({c.candidate_id for c in run_1}) == 6


def test_generate_montecarlo_candidates_emits_one_real_candidate_per_sample_with_real_summary_stats() -> None:
    hypothesis = DesiredStateHypothesis(
        hypothesis_id="rule-based-v1",
        targets=({"kind": "latency_reduction"},),
        evidence_used_refs=("obs-1",),
        assumptions=("objectives read directly from admitted ScenarioMetadata",),
    )
    n = 10
    candidates = generate_montecarlo_candidates((hypothesis,), UNIFORM_MODEL, n, seed=DETERMINISTIC_SEED)

    assert len(candidates) == n
    expected_mean = statistics.fmean(c.cost_bound for c in candidates)
    expected_std = statistics.stdev(c.cost_bound for c in candidates)

    for candidate in candidates:
        assert isinstance(candidate, ArchitectureCandidate)
        assert candidate.provenance == "montecarlo-v1"
        assert candidate.generator_identity == "montecarlo-uniform-seeded"
        assert candidate.target_state_assertions == ("{'kind': 'latency_reduction'}",)
        assert candidate.cost_bound is not None
        assert 10.0 <= candidate.cost_bound <= 100.0
        # every candidate maps to one real individual draw, never a summary value
        assert candidate.assumptions[0].startswith("Monte Carlo draw ")
        assert f"cost_bound={candidate.cost_bound:.4f}" in candidate.assumptions[0]
        assert candidate.assumptions[1].startswith("Monte Carlo summary over 10 real seeded draws")
        assert f"mean cost_bound={expected_mean:.4f}" in candidate.assumptions[1]
        assert f"std cost_bound={expected_std:.4f}" in candidate.assumptions[1]
        assert candidate.assumptions[2:] == hypothesis.assumptions

    # candidate_id is a real, deterministic digest -- distinct per draw
    assert len({c.candidate_id for c in candidates}) == n


def test_generate_montecarlo_candidates_is_plural_across_multiple_hypotheses() -> None:
    hypotheses = (
        DesiredStateHypothesis(
            hypothesis_id="h1",
            targets=({"kind": "latency_reduction"},),
            evidence_used_refs=("obs-1",),
        ),
        DesiredStateHypothesis(
            hypothesis_id="h2",
            targets=({"kind": "cost_reduction"},),
            evidence_used_refs=("obs-2",),
        ),
    )
    candidates = generate_montecarlo_candidates(hypotheses, UNIFORM_MODEL, 4, seed=DETERMINISTIC_SEED)

    assert len(candidates) == 8
    assert len({c.candidate_id for c in candidates}) == 8
    hyp_1 = tuple(c for c in candidates if c.target_state_assertions == ("{'kind': 'latency_reduction'}",))
    hyp_2 = tuple(c for c in candidates if c.target_state_assertions == ("{'kind': 'cost_reduction'}",))
    assert len(hyp_1) == 4
    assert len(hyp_2) == 4
    # same underlying 4 real draws feed both hypotheses -- real, equal cost_bound sequences
    assert tuple(c.cost_bound for c in hyp_1) == tuple(c.cost_bound for c in hyp_2)


def test_montecarlo_cost_model_rejects_invalid_ranges_missing_mode_and_out_of_range_mode() -> None:
    with pytest.raises(ValueError, match="low .* must be <= high"):
        MonteCarloCostModel(distribution=MonteCarloDistribution.UNIFORM, low=100.0, high=10.0)

    with pytest.raises(ValueError, match="requires a real mode value"):
        MonteCarloCostModel(distribution=MonteCarloDistribution.TRIANGULAR, low=10.0, high=100.0)

    with pytest.raises(ValueError, match="must lie within"):
        MonteCarloCostModel(distribution=MonteCarloDistribution.TRIANGULAR, low=10.0, high=100.0, mode=200.0)

    # a real, valid TRIANGULAR model draws within [low, high]
    samples = draw_monte_carlo_samples(TRIANGULAR_MODEL, 5, seed=DETERMINISTIC_SEED)
    for sample in samples:
        assert 10.0 <= sample.cost_bound <= 100.0


def test_draw_monte_carlo_samples_rejects_non_positive_n() -> None:
    with pytest.raises(ValueError, match="n must be >= 1"):
        draw_monte_carlo_samples(UNIFORM_MODEL, 0, seed=DETERMINISTIC_SEED)
