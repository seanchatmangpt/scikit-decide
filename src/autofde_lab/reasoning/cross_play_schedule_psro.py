# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Drive a real PSRO step from bounded, observed cross-play payoffs.

``cover_cross_play`` deliberately produces a covering schedule rather than a
full N x N sweep.  The evidence-preserving default therefore seeds PSRO over
the union of every opponent observed in the bounded subset; when candidates
do not all have payoff coverage against that union, PSRO correctly refuses
with ``REFUSED:PSRO_MISSING_PAYOFF_CLOSURE``.

This module also exposes one explicit, reversible alternative:
``OBSERVED_COMMON_CLOSURE``.  It computes the maximal opponent population
that is *actually observed for every candidate in the bounded subset* and
seeds PSRO over that deterministic intersection.  It never interpolates a
missing payoff, never changes the covering schedule, and never becomes the
default.  An empty intersection is a typed refusal, not permission to invent
an edge.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Sequence

from autofde_lab.planner_league import PayoffHypergraph
from autofde_lab.planner_league.cross_play_world_schedule import (
    CrossPlayScheduleOutcome,
)
from autofde_lab.planner_league.psro import (
    PolicySpaceResponseOracle,
    PsroState,
    PsroStep,
)

from .cross_play_schedule_payoff import (
    ScheduledMatchPayoffOutcome,
    admit_cross_play_schedule_payoffs,
)

__all__ = [
    "CrossPlaySchedulePsroOutcome",
    "OpponentPopulationStrategy",
    "run_cross_play_schedule_psro_round",
]


class OpponentPopulationStrategy(str, Enum):
    """How to derive a PSRO opponent population from observed payoffs only."""

    OBSERVED_UNION = "observed_union"
    OBSERVED_COMMON_CLOSURE = "observed_common_closure"


@dataclass(frozen=True, slots=True)
class CrossPlaySchedulePsroOutcome:
    """Typed result preserving the real payoff graph and real PSRO step."""

    payoff_outcomes: tuple[ScheduledMatchPayoffOutcome, ...]
    hypergraph: PayoffHypergraph
    psro_step: PsroStep


def _observed_opponent_population(
    payoff_outcomes: tuple[ScheduledMatchPayoffOutcome, ...],
    constructor_planner_ids: tuple[str, ...],
    strategy: OpponentPopulationStrategy,
) -> tuple[str, ...]:
    """Derive an opponent population without manufacturing payoff edges.

    Ordering is always the first-observed schedule order so repeated runs over
    the same bounded schedule replay byte-for-byte through ``PsroState.seed``.
    """

    observed_order = tuple(
        dict.fromkeys(
            outcome.match.right_policy.planner_id for outcome in payoff_outcomes
        )
    )
    if strategy is OpponentPopulationStrategy.OBSERVED_UNION:
        return observed_order

    opponents_by_constructor: dict[str, set[str]] = {
        planner_id: set() for planner_id in constructor_planner_ids
    }
    for outcome in payoff_outcomes:
        constructor_id = outcome.match.left_policy.planner_id
        if constructor_id in opponents_by_constructor:
            opponents_by_constructor[constructor_id].add(
                outcome.match.right_policy.planner_id
            )

    common = set(observed_order)
    for planner_id in constructor_planner_ids:
        common.intersection_update(opponents_by_constructor[planner_id])

    selected = tuple(
        opponent_id for opponent_id in observed_order if opponent_id in common
    )
    if not selected:
        raise ValueError("REFUSED:NO_COMMON_OBSERVED_OPPONENTS")
    return selected


def run_cross_play_schedule_psro_round(
    schedule: CrossPlayScheduleOutcome,
    domain: object,
    *,
    limit: int,
    role_id: str,
    opponent_role_id: str,
    world_id: str,
    opponent_ids: Sequence[str] | None = None,
    opponent_population_strategy: OpponentPopulationStrategy
    | str = OpponentPopulationStrategy.OBSERVED_UNION,
    observation_projection_id: str = "full_observation",
    budget_id: str = "balanced",
) -> CrossPlaySchedulePsroOutcome:
    """Score a bounded real schedule and run one evidence-bounded PSRO step.

    With no override, ``opponent_population_strategy`` controls how the
    opponent population is derived from *observed* payoff edges:

    - ``OBSERVED_UNION`` (default) preserves the existing fail-closed
      behavior and can legitimately return ``PSRO_MISSING_PAYOFF_CLOSURE``.
    - ``OBSERVED_COMMON_CLOSURE`` uses the deterministic intersection of
      opponents observed for every candidate.  This can advance without an
      N x N sweep while still requiring every payoff edge PSRO consumes to
      exist in the real hypergraph.

    ``opponent_ids`` remains the highest-precedence explicit caller override
    for backward compatibility.  It is never widened or repaired here; an
    invalid override reaches the existing PSRO validation/coverage checks.

    Raises ``REFUSED:NO_SCHEDULED_MATCHES`` when no candidate exists and
    ``REFUSED:NO_COMMON_OBSERVED_OPPONENTS`` when the opt-in common-closure
    strategy has no non-empty observed intersection.
    """

    hypergraph = PayoffHypergraph()
    payoff_outcomes = admit_cross_play_schedule_payoffs(
        schedule, domain, hypergraph=hypergraph, limit=limit
    )

    constructor_planner_ids = tuple(
        dict.fromkeys(
            outcome.match.left_policy.planner_id for outcome in payoff_outcomes
        )
    )
    if not constructor_planner_ids:
        raise ValueError("REFUSED:NO_SCHEDULED_MATCHES")

    strategy = OpponentPopulationStrategy(opponent_population_strategy)
    real_opponent_ids = (
        tuple(dict.fromkeys(opponent_ids))
        if opponent_ids is not None
        else _observed_opponent_population(
            payoff_outcomes, constructor_planner_ids, strategy
        )
    )

    state = PsroState.seed(real_opponent_ids)
    oracle = PolicySpaceResponseOracle(
        hypergraph,
        role_id=role_id,
        opponent_role_id=opponent_role_id,
        world_id=world_id,
        observation_projection_id=observation_projection_id,
        budget_id=budget_id,
    )
    psro_step = oracle.step(state, candidates=constructor_planner_ids)

    return CrossPlaySchedulePsroOutcome(
        payoff_outcomes=payoff_outcomes,
        hypergraph=hypergraph,
        psro_step=psro_step,
    )
