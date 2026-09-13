# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Real, explicitly-bounded scoring of `cross_play_world_schedule.py`'s
real scheduled `LeagueMatch`es -- closing the gap this pass's own
investigation confirmed: `schedule_cross_play_for_world` produces real
match schedules (135 per world, confirmed live in a prior pass) but
nothing executes or scores any of them (`grep -rln
"schedule_cross_play_for_world|CrossPlayScheduleOutcome" src/ tests/`
found only its own definition and test file before this module).

`admit_cross_play_schedule_payoffs` closes this by real-solving both
planners named in each of the first `limit` real scheduled matches (via
`generic_domain_solve.attempt_solve_domain`, against the same real
`domain` the caller already used to build the schedule -- never a second,
possibly-inconsistent domain construction) and admitting a real
`PayoffObservation` per match, scored with `dflss_solve_payoff_bridge`'s
own established `1.0 ALIVE / 0.0 otherwise` contract (imported and reused,
never re-derived). Each admitted observation carries that match's own
real `world_id`/roles exactly as `cover_cross_play` scheduled them --
never coerced back to `"generic_enterprise"`/`"plan_constructor"` the way
`dflss_solve_payoff_bridge.admit_dflss_solve_payoff` itself hardcodes for
its own, narrower two-planner-argument use case.

`limit` is required and explicit, never defaulted to "all matches" --
real-solving is not free (each match costs up to two independent solver
rollouts), and this module never silently commits to scoring all 135 real
scheduled matches in one call. A caller wanting broader coverage passes a
larger `limit` deliberately, in full view of the real cost.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from autofde_lab.planner_league import LeagueMatch, PayoffHypergraph, PayoffObservation
from autofde_lab.planner_league.cross_play_world_schedule import CrossPlayScheduleOutcome

from .dflss_planner_solve import PlannerSolveOutcome
from .dflss_solve_payoff_bridge import _outcome_score
from .generic_domain_solve import attempt_solve_domain

__all__ = ["ScheduledMatchPayoffOutcome", "admit_cross_play_schedule_payoffs"]


@dataclass(frozen=True, slots=True)
class ScheduledMatchPayoffOutcome:
    """Real, typed result of one attempted real-solve-and-score of a real
    scheduled `LeagueMatch`. Carries both real, independently-computed
    `PlannerSolveOutcome`s alongside the real `PayoffObservation` (if
    admitted) -- never only a summary derived from them."""

    match: LeagueMatch
    left_outcome: PlannerSolveOutcome
    right_outcome: PlannerSolveOutcome
    observation: PayoffObservation | None
    standing: str
    reason: str

    @property
    def admitted(self) -> bool:
        return self.observation is not None


def admit_cross_play_schedule_payoffs(
    schedule: CrossPlayScheduleOutcome,
    domain: object,
    *,
    hypergraph: PayoffHypergraph,
    limit: int,
) -> tuple[ScheduledMatchPayoffOutcome, ...]:
    """Real-solve and score the first `limit` real matches of `schedule.matches`
    against `domain` (the same real domain instance the schedule was built
    from), admitting one real `PayoffObservation` per match to `hypergraph`.

    Raises `ValueError("REFUSED:LIMIT_MUST_BE_POSITIVE")` for a
    non-positive `limit` -- an explicit refusal, never a silent no-op.
    """
    if limit <= 0:
        raise ValueError("REFUSED:LIMIT_MUST_BE_POSITIVE")

    outcomes: list[ScheduledMatchPayoffOutcome] = []
    for match in schedule.matches[:limit]:
        left_outcome = attempt_solve_domain(match.left_policy.planner_id, domain)
        right_outcome = attempt_solve_domain(match.right_policy.planner_id, domain)

        # A real, deterministic digest over the real match identity and
        # both real solve outcomes -- never a fabricated/synthetic
        # receipt id.
        receipt_id = hashlib.sha256(
            "|".join(
                (
                    "cross-play-schedule-payoff-v1",
                    match.identity_sha256,
                    left_outcome.planner_id,
                    left_outcome.standing,
                    left_outcome.reason,
                    right_outcome.planner_id,
                    right_outcome.standing,
                    right_outcome.reason,
                )
            ).encode("utf-8")
        ).hexdigest()

        left_score = _outcome_score(left_outcome)
        right_score = _outcome_score(right_outcome)
        try:
            observation = PayoffObservation(match, left_score, right_score, receipt_id=receipt_id)
        except ValueError as exc:
            # Defensive only -- receipt_id is always real and non-empty
            # above. Never bypassed: the same real
            # PayoffObservation.__post_init__ fail-closed check every
            # other bridge in this session relies on.
            outcomes.append(
                ScheduledMatchPayoffOutcome(
                    match=match,
                    left_outcome=left_outcome,
                    right_outcome=right_outcome,
                    observation=None,
                    standing="REFUSED",
                    reason=str(exc),
                )
            )
            continue

        hypergraph.add(observation)
        outcomes.append(
            ScheduledMatchPayoffOutcome(
                match=match,
                left_outcome=left_outcome,
                right_outcome=right_outcome,
                observation=observation,
                standing="ALIVE",
                reason="ALIVE:SCHEDULED_MATCH_PAYOFF_ADMITTED",
            )
        )

    return tuple(outcomes)
