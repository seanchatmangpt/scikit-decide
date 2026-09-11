# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for bounded cross-play -> PSRO population strategies.

Real collaborators throughout: a real ``BreachClockDomain``, real
``PlannerLeague``, real ``schedule_cross_play_for_world`` output, and real
installed solver entry points.  No mocks or interaction assertions.
"""

from __future__ import annotations

import pytest

from autofde_lab.hub.domain.breach_clock import BreachClockDomain
from autofde_lab.planner_league import PlannerLeague
from autofde_lab.planner_league.cross_play_world_schedule import (
    schedule_cross_play_for_world,
)
from autofde_lab.reasoning.cross_play_schedule_psro import (
    CrossPlaySchedulePsroOutcome,
    OpponentPopulationStrategy,
    run_cross_play_schedule_psro_round,
)


def _real_schedule():
    league = PlannerLeague()
    return schedule_cross_play_for_world(
        league,
        "cyber_incident",
        left_role_id="plan_constructor",
        right_role_id="plan_falsifier",
    )


def _run(schedule, *, limit: int, strategy=OpponentPopulationStrategy.OBSERVED_UNION):
    return run_cross_play_schedule_psro_round(
        schedule,
        BreachClockDomain(),
        limit=limit,
        role_id="plan_constructor",
        opponent_role_id="plan_falsifier",
        world_id="cyber_incident",
        opponent_population_strategy=strategy,
    )


def test_single_candidate_subset_advances_trivially() -> None:
    result = _run(_real_schedule(), limit=3)

    assert isinstance(result, CrossPlaySchedulePsroOutcome)
    assert len(result.payoff_outcomes) == 3
    assert len(result.hypergraph.observations) == 3
    assert result.psro_step.advanced
    assert result.psro_step.standing == "ALIVE"
    assert result.psro_step.receipt is not None
    assert result.psro_step.receipt.selected_best_response == "AOstar"


def test_default_union_seed_over_two_candidates_honestly_refuses() -> None:
    """The unchanged default must preserve the original fail-closed result."""
    result = _run(_real_schedule(), limit=6)

    assert len(result.payoff_outcomes) == 6
    assert len(result.hypergraph.observations) == 6
    assert not result.psro_step.advanced
    assert result.psro_step.standing == "REFUSED"
    assert result.psro_step.reason == "REFUSED:PSRO_MISSING_PAYOFF_CLOSURE"
    assert result.psro_step.receipt is None


def test_observed_common_closure_is_an_opt_in_real_two_candidate_advance() -> None:
    """Compare the rejected union alternative with the selected strategy.

    The exact same six observed matches refuse under the union population but
    advance under the maximal common observed population.  No missing payoff
    is interpolated: the selected population is the real intersection
    (Astar, BFWS), already present for both constructors.
    """
    schedule = _real_schedule()

    rejected = _run(schedule, limit=6)
    selected = _run(
        schedule,
        limit=6,
        strategy=OpponentPopulationStrategy.OBSERVED_COMMON_CLOSURE,
    )

    assert rejected.psro_step.reason == "REFUSED:PSRO_MISSING_PAYOFF_CLOSURE"
    assert not rejected.psro_step.advanced

    assert selected.psro_step.advanced
    assert selected.psro_step.standing == "ALIVE"
    assert selected.psro_step.receipt is not None
    assert selected.psro_step.receipt.prior_population == ("Astar", "BFWS")
    assert selected.psro_step.receipt.selected_best_response == "Astar"


def test_observed_common_closure_replays_deterministically() -> None:
    schedule = _real_schedule()
    first = _run(
        schedule,
        limit=6,
        strategy=OpponentPopulationStrategy.OBSERVED_COMMON_CLOSURE,
    )
    second = _run(
        schedule,
        limit=6,
        strategy=OpponentPopulationStrategy.OBSERVED_COMMON_CLOSURE,
    )

    assert first.psro_step.receipt is not None
    assert second.psro_step.receipt is not None
    assert (
        first.psro_step.receipt.prior_population
        == second.psro_step.receipt.prior_population
    )
    assert (
        first.psro_step.receipt.identity_sha256
        == second.psro_step.receipt.identity_sha256
    )


def test_common_closure_refuses_when_four_real_candidate_windows_do_not_intersect() -> (
    None
):
    """Negative fixture: four consecutive 3-opponent windows have no common edge."""
    with pytest.raises(ValueError, match="^REFUSED:NO_COMMON_OBSERVED_OPPONENTS$"):
        _run(
            _real_schedule(),
            limit=12,
            strategy=OpponentPopulationStrategy.OBSERVED_COMMON_CLOSURE,
        )


def test_explicit_intersecting_opponent_ids_remains_backward_compatible() -> None:
    result = run_cross_play_schedule_psro_round(
        _real_schedule(),
        BreachClockDomain(),
        limit=6,
        role_id="plan_constructor",
        opponent_role_id="plan_falsifier",
        world_id="cyber_incident",
        opponent_ids=("Astar", "BFWS"),
    )

    assert result.psro_step.advanced
    assert result.psro_step.standing == "ALIVE"
    assert result.psro_step.receipt is not None
    assert result.psro_step.receipt.prior_population == ("Astar", "BFWS")
    assert result.psro_step.receipt.selected_best_response == "Astar"


def test_refuses_when_the_bounded_subset_has_zero_real_matches() -> None:
    league = PlannerLeague()
    unsupported_schedule = schedule_cross_play_for_world(
        league,
        "cyber_incident",
        left_role_id="plan_constructor",
        right_role_id="plan_falsifier",
        domain_factories={},
    )
    assert unsupported_schedule.standing == "UNSUPPORTED"
    assert unsupported_schedule.matches == ()

    with pytest.raises(ValueError, match="^REFUSED:NO_SCHEDULED_MATCHES$"):
        run_cross_play_schedule_psro_round(
            unsupported_schedule,
            BreachClockDomain(),
            limit=5,
            role_id="plan_constructor",
            opponent_role_id="plan_falsifier",
            world_id="cyber_incident",
        )
