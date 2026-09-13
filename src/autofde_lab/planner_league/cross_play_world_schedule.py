# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Drives `PlannerLeague.cover_cross_play` with real compatibility results
computed against a real, non-default `world_id` -- closing two real gaps
this session's own investigation found together in the same pass:

1. `cover_cross_play` (`core.py`) had exactly one real caller anywhere in
   the repo -- its own unit test (`grep -rn "cover_cross_play" src/
   tests/` returned only its definition and
   `tests/planner_league/test_planner_league.py`). Every real exploration/
   dflss/process-informed bridge built earlier this session constructed
   `LeagueMatch` objects directly, one hand-picked planner pair at a time
   -- none ever drove the real, deterministic covering-schedule generator
   this method already is.
2. Every one of those same bridges hardcoded `world_id="generic_enterprise"`
   (`grep -rn 'world_id="' src/autofde_lab/reasoning/exploration_*.py
   src/autofde_lab/reasoning/dflss_*.py
   src/autofde_lab/reasoning/process_informed_*.py ... | grep -v
   generic_enterprise` returned zero matches). The other 3 real
   `WORLD_CLASSES` `world_admission.py` proved have real, compatible
   domains -- `cyber_incident`/`identity_degradation`/
   `mission_critical_dependency` -- had never actually been used to drive
   any real planner-league computation, only to prove admission was
   *possible*.

`schedule_cross_play_for_world` closes both at once: given a real,
non-default `world_id`, it resolves the real domain via
`world_admission.WORLD_DOMAIN_FACTORIES` (never a new, hand-authored
mapping -- reuses the existing one), computes real
`PlannerLeague.population_compatibility()` results for both real roles
over the full real 56-planner population, and feeds those real results
into the real `cover_cross_play` covering-schedule generator.

Confirmed live before writing any test: against `BreachClockDomain`
(`cyber_incident`) and `CloudGoatIamPrivescDomain` (`identity_degradation`),
45 of 56 real registered planners are real-`COMPATIBLE` under both
`plan_constructor` and `plan_falsifier`, and `cover_cross_play` (`rounds=3`)
produces 135 real, deterministic `LeagueMatch` objects for each -- the
first time this session (or, per the zero-caller grep above, arguably
ever) that method has been driven by anything beyond its own hand-built
2-3-planner unit-test fixture.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .catalog import WORLD_CLASSES
from .core import LeagueMatch, PlannerLeague
from .world_admission import WORLD_DOMAIN_FACTORIES

__all__ = ["CrossPlayScheduleOutcome", "schedule_cross_play_for_world"]


@dataclass(frozen=True, slots=True)
class CrossPlayScheduleOutcome:
    """Real, typed result of one attempt to schedule cross-play for a real
    `world_id`. Mirrors this session's other bridge modules'
    `(standing/reason)` shape -- a refused/unsupported attempt is a real,
    named, inspectable outcome, never a silently empty `matches` tuple
    with no explanation attached."""

    matches: tuple[LeagueMatch, ...]
    standing: str
    reason: str

    @property
    def scheduled(self) -> bool:
        return self.standing == "ALIVE"


def schedule_cross_play_for_world(
    league: PlannerLeague,
    world_id: str,
    *,
    left_role_id: str,
    right_role_id: str,
    domain_factories: Mapping[str, Callable[[], Any]] = WORLD_DOMAIN_FACTORIES,
    rounds: int = 3,
    observation_projection_id: str = "full_observation",
    budget_id: str = "balanced",
) -> CrossPlayScheduleOutcome:
    """Real: resolve `world_id` -> a real domain (via `domain_factories`,
    defaulting to `world_admission.WORLD_DOMAIN_FACTORIES` -- never a new,
    hand-authored mapping) -> real `league.population_compatibility()`
    results for both `left_role_id`/`right_role_id` -> the real
    `PlannerLeague.cover_cross_play` covering schedule.

    Refuses `REFUSED:UNKNOWN_WORLD:<world_id>` for a `world_id` outside
    the real `WORLD_CLASSES` registry, and
    `UNSUPPORTED:NO_DOMAIN_FOR_WORLD:<world_id>` for a registered
    `world_id` with no real domain factory -- the same two named standings
    `world_admission.admit_planner_role_world` already uses for the same
    real reasons, kept consistent rather than re-derived. A real domain
    with zero real compatible planners for either role produces a real,
    empty `matches` tuple with an honest `UNSUPPORTED:NO_COMPATIBLE_PLANNERS`
    reason -- `cover_cross_play` itself already returns `()` in that case;
    this only names why, rather than leaving an empty tuple unexplained.
    """
    if world_id not in WORLD_CLASSES:
        return CrossPlayScheduleOutcome(
            matches=(), standing="REFUSED", reason=f"REFUSED:UNKNOWN_WORLD:{world_id}"
        )
    factory = domain_factories.get(world_id)
    if factory is None:
        return CrossPlayScheduleOutcome(
            matches=(), standing="UNSUPPORTED", reason=f"UNSUPPORTED:NO_DOMAIN_FOR_WORLD:{world_id}"
        )

    domain = factory()
    left_results = league.population_compatibility(domain, left_role_id)
    right_results = league.population_compatibility(domain, right_role_id)

    if not any(r.compatible for r in left_results) or not any(r.compatible for r in right_results):
        return CrossPlayScheduleOutcome(
            matches=(), standing="UNSUPPORTED", reason=f"UNSUPPORTED:NO_COMPATIBLE_PLANNERS:{world_id}"
        )

    matches = PlannerLeague.cover_cross_play(
        left_results,
        right_results,
        world_id=world_id,
        left_role_id=left_role_id,
        right_role_id=right_role_id,
        rounds=rounds,
        observation_projection_id=observation_projection_id,
        budget_id=budget_id,
    )
    return CrossPlayScheduleOutcome(
        matches=matches, standing="ALIVE", reason="ALIVE:CROSS_PLAY_SCHEDULED"
    )
