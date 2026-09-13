import math

import pytest

from autofde_lab.fabric.metrics import (
    CausalLatency,
    ConsequenceReceipt,
    compute_consequence_metrics,
    first_persistent_crossover,
    little_law_from_wip_and_throughput,
)
from autofde_lab.fabric.selection import DecisionRegime


def r(
    *,
    verified=True,
    value=1.0,
    wall=2.0,
    cost=0.5,
    attention=3.0,
    tokens=10,
    regime=DecisionRegime.COLD,
):
    return ConsequenceReceipt(
        verified=verified,
        value=value,
        wall_time_s=wall,
        cost_usd=cost,
        human_attention_s=attention,
        frontier_tokens=tokens,
        regime=regime,
    )


def test_vct_counts_only_verified_value_but_all_resource_cost():
    metrics = compute_consequence_metrics([r(), r(verified=False, value=100.0)])
    assert metrics.verified_value == 1.0
    assert metrics.verified_transitions == 1
    assert metrics.vct == pytest.approx(1.0 / (4.0 * 1.0 * 6.0))


def test_reuse_ratio_is_warm_plus_hot_over_verified():
    metrics = compute_consequence_metrics(
        [
            r(regime=DecisionRegime.HOT),
            r(regime=DecisionRegime.WARM),
            r(regime=DecisionRegime.COLD),
            r(regime=DecisionRegime.HOT, verified=False),
        ]
    )
    assert metrics.reuse_ratio == pytest.approx(2 / 3)


def test_zero_frontier_tokens_proves_model_optional_hot_path_without_epsilon():
    metrics = compute_consequence_metrics([r(tokens=0, regime=DecisionRegime.HOT)])
    assert math.isinf(metrics.verified_per_frontier_token)
    assert metrics.tokens_per_verified_consequence == 0.0


def test_zero_resource_denominator_is_explicit_infinity_not_hidden_floor():
    metrics = compute_consequence_metrics([r(cost=0.0)])
    assert math.isinf(metrics.vct)


def test_causal_diameter_and_amdahl_bound():
    latency = CausalLatency(
        observe_s=1,
        propagate_observation_s=1,
        admit_s=1,
        decide_s=1,
        propagate_command_s=1,
        actuate_s=1,
        observe_consequence_s=1,
        verify_s=1,
    )
    assert latency.causal_diameter_s == 8
    assert latency.cognition_fraction == pytest.approx(1 / 8)
    assert latency.infinite_cognition_speedup_bound == pytest.approx(8 / 7)


def test_causal_latency_rejects_negative_time():
    with pytest.raises(ValueError):
        CausalLatency(actuate_s=-1)


def test_persistent_crossover_requires_remaining_curve_to_stay_better():
    baseline = {1: 1.0, 10: 5.0, 100: 50.0, 1000: 500.0}
    autofde = {1: 4.0, 10: 6.0, 100: 20.0, 1000: 30.0}
    assert first_persistent_crossover(baseline, autofde) == 100


def test_transient_win_is_not_crossover():
    baseline = {1: 1.0, 10: 10.0, 100: 100.0}
    autofde = {1: 2.0, 10: 9.0, 100: 120.0}
    assert first_persistent_crossover(baseline, autofde) is None


def test_littles_law_exposes_wait_time_from_wip_and_throughput():
    flow = little_law_from_wip_and_throughput(12, 0.5)
    assert flow.mean_wait_s == 24
    assert flow.residual == pytest.approx(0)


def test_littles_law_zero_throughput_with_wip_is_infinite_wait_not_zero():
    flow = little_law_from_wip_and_throughput(3, 0)
    assert math.isinf(flow.mean_wait_s)
    assert flow.residual == 0
