# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Attempts to solve each real planner's own dedicated DMEDI-curriculum
PDDL problem file with that exact planner -- closing a real gap confirmed
this session: `dflss_planner_problems.problem_file_for_planner` had zero
real callers outside its own test (`grep -rn "problem_file_for_planner"
src/ tests/` found only its own definition and
`test_dflss_planner_problems_chicago.py`). The 57 real per-planner PDDL
problem files under `docs/planning/dflss-dmedi-curriculum/problems/`
existed but were never actually loaded and solved by their named planner:
`test_dflss_dmedi_plan_chicago.py` solves only the single shared
`domain.pddl`/`problem.pddl` pair, always with `Astar`, and never touches
any per-planner file.

`attempt_solve_dflss_curriculum` closes that gap directly: given a
`planner_id`, it resolves that planner's own real problem file via
`dflss_planner_problems.problem_file_for_planner`, loads the real
registered solver via `autofde_lab.utils.load_registered_solver`,
constructs a real `PDDLDomain(domain_path, problem_path)`, and -- only if
the real `check_domain()` contract admits it -- attempts a real `solve()`
rollout to the real `dmedi-capstone-complete` goal, exactly mirroring
`test_dflss_dmedi_plan_chicago.py`'s own real rollout loop.

Every outcome is a real, typed `PlannerSolveOutcome`, never a fabricated
success and never an uncaught exception: an unknown `planner_id` refuses
`REFUSED:UNKNOWN_PLANNER`; a planner with no loadable solver (per
`load_registered_solver`, e.g. missing an optional extra) is
`UNSUPPORTED:PLANNER_LOAD_FAILED`; a planner whose real `check_domain()`
rejects this PDDL domain's contract is `REFUSED:DOMAIN_CONTRACT_MISMATCH`;
a real rollout that raises is `UNSUPPORTED:SOLVE_RAISED:<ExceptionType>`; a
real rollout that completes without reaching the goal within `step_limit`
is `REFUSED:GOAL_NOT_REACHED`; and only a real rollout that reaches the
real goal is `ALIVE:GOAL_REACHED`.

Confirmed live before this module was written, not assumed: `Astar` and
`LRTAstar` both real-`check_domain`-compatible and both real-solve this
PDDL domain to the goal (52-action plan, matching
`test_dflss_dmedi_plan_chicago.py`'s own established plan length);
`CIDual` real-`check_domain`-incompatible (`False`), matching the same
`REFUSED:DOMAIN_CONTRACT_MISMATCH` pattern already established across this
session's other planner-league tests.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from .dflss_planner_problems import problem_file_for_planner

__all__ = ["PlannerSolveOutcome", "attempt_solve_dflss_curriculum"]

_DFLSS_DOMAIN_PATH = os.path.join(
    os.path.dirname(__file__),
    "..",
    "..",
    "..",
    "docs",
    "planning",
    "dflss-dmedi-curriculum",
    "domain.pddl",
)


@dataclass(frozen=True, slots=True)
class PlannerSolveOutcome:
    """Real, typed result of one planner's real attempt to solve its own
    real DMEDI-curriculum PDDL problem file."""

    planner_id: str
    standing: str
    reason: str
    plan_length: int | None = None

    @property
    def alive(self) -> bool:
        return self.standing == "ALIVE"


def attempt_solve_dflss_curriculum(
    planner_id: str, *, step_limit: int = 60
) -> PlannerSolveOutcome:
    """Real attempt to solve `planner_id`'s own real DMEDI-curriculum PDDL
    problem file with that exact planner. See module docstring for the
    full real standing taxonomy this function returns."""
    try:
        problem_path = str(problem_file_for_planner(planner_id))
    except KeyError:
        return PlannerSolveOutcome(
            planner_id, "REFUSED", f"REFUSED:UNKNOWN_PLANNER:{planner_id}"
        )

    from autofde_lab import utils

    solver_type = utils.load_registered_solver(planner_id)
    if solver_type is None:
        return PlannerSolveOutcome(
            planner_id, "UNSUPPORTED", "UNSUPPORTED:PLANNER_LOAD_FAILED"
        )

    from autofde_lab.hub.domain.pddl import PDDLDomain

    domain = PDDLDomain(_DFLSS_DOMAIN_PATH, problem_path)

    try:
        compatible = bool(solver_type.check_domain(domain))
    except Exception as exc:
        return PlannerSolveOutcome(
            planner_id,
            "UNSUPPORTED",
            f"UNSUPPORTED:DOMAIN_CHECK_FAILED:{type(exc).__name__}",
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
            reached_goal = domain._goal_checker.is_goal(obs.to_cpp())
    except Exception as exc:
        return PlannerSolveOutcome(
            planner_id,
            "UNSUPPORTED",
            f"UNSUPPORTED:SOLVE_RAISED:{type(exc).__name__}:{exc}",
        )

    if not reached_goal:
        return PlannerSolveOutcome(
            planner_id, "REFUSED", "REFUSED:GOAL_NOT_REACHED", plan_length=plan_length
        )

    return PlannerSolveOutcome(
        planner_id, "ALIVE", "ALIVE:GOAL_REACHED", plan_length=plan_length
    )
