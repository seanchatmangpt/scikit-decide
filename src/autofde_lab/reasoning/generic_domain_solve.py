# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Domain-agnostic generalization of `dflss_planner_solve.
attempt_solve_dflss_curriculum`'s real solve-attempt pattern -- built to
close a real gap found this session: `cross_play_world_schedule.py`'s real
`schedule_cross_play_for_world` produces real `LeagueMatch` *schedules*
against real, non-PDDL domains (`BreachClockDomain`/
`CloudGoatIamPrivescDomain`/`K8sGoatRBACEscalation`), but nothing scores
any of them -- and `dflss_planner_solve.py`'s own real rollout loop cannot
be reused unmodified, because it reads the goal via the PDDL-solver-
specific internal `domain._goal_checker.is_goal(obs.to_cpp())`, which
these domains do not have at all.

Confirmed live before writing this module: `BreachClockDomain()` has no
`_goal_checker` attribute (`AttributeError` on first attempt); the real,
generic scikit-decide three-tier public API `domain.is_goal(obs)` is what
every domain in this repo actually exposes (`dir(BreachClockDomain())`
shows `is_goal`/`_is_goal`/`_is_goal_`/`get_goals`/`_get_goals`/
`_get_goals_`, matching `.claude/rules/architecture.md`'s documented
three-tier convention). `attempt_solve_domain` uses that public method
instead, making it usable against any real domain in `hub/domain/`, not
only the DMEDI-curriculum PDDL pair.

Reuses `dflss_planner_solve.PlannerSolveOutcome` as-is (imported, never
redefined) -- an identical real solve-attempt outcome shape, whichever
real domain produced it.
"""

from __future__ import annotations

from typing import Any

from .dflss_planner_solve import PlannerSolveOutcome

__all__ = ["attempt_solve_domain"]


def attempt_solve_domain(planner_id: str, domain: Any, *, step_limit: int = 60) -> PlannerSolveOutcome:
    """Real attempt to solve `domain` (any real, already-constructed
    scikit-decide domain instance) with the real registered solver named
    `planner_id`. Mirrors `dflss_planner_solve.
    attempt_solve_dflss_curriculum`'s real standing taxonomy exactly
    (`ALIVE:GOAL_REACHED` / `REFUSED:DOMAIN_CONTRACT_MISMATCH` /
    `REFUSED:GOAL_NOT_REACHED` / `UNSUPPORTED:PLANNER_LOAD_FAILED` /
    `UNSUPPORTED:SOLVE_RAISED:<ExceptionType>`), the only real difference
    being the goal check itself (`domain.is_goal(obs)`, the generic public
    API, instead of a PDDL-specific internal)."""
    from autofde_lab import utils

    solver_type = utils.load_registered_solver(planner_id)
    if solver_type is None:
        return PlannerSolveOutcome(planner_id, "UNSUPPORTED", "UNSUPPORTED:PLANNER_LOAD_FAILED")

    try:
        compatible = bool(solver_type.check_domain(domain))
    except Exception as exc:
        return PlannerSolveOutcome(
            planner_id, "UNSUPPORTED", f"UNSUPPORTED:DOMAIN_CHECK_FAILED:{type(exc).__name__}"
        )
    if not compatible:
        return PlannerSolveOutcome(planner_id, "REFUSED", "REFUSED:DOMAIN_CONTRACT_MISMATCH")

    try:
        with solver_type(domain_factory=lambda: domain) as solver:
            solver.solve()
            obs = domain.reset()
            plan_length = 0
            for _ in range(step_limit):
                if domain._is_terminal(obs):
                    break
                action = solver.sample_action(obs)
                plan_length += 1
                outcome = domain.step(action)
                obs = outcome.observation
            reached_goal = bool(domain.is_goal(obs))
    except Exception as exc:
        return PlannerSolveOutcome(
            planner_id, "UNSUPPORTED", f"UNSUPPORTED:SOLVE_RAISED:{type(exc).__name__}:{exc}"
        )

    if not reached_goal:
        return PlannerSolveOutcome(planner_id, "REFUSED", "REFUSED:GOAL_NOT_REACHED", plan_length=plan_length)

    return PlannerSolveOutcome(planner_id, "ALIVE", "ALIVE:GOAL_REACHED", plan_length=plan_length)
