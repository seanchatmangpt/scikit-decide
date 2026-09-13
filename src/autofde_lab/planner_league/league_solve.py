# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Run a `LeagueMatch`'s two real policies' `solve()` on the admitted world
domain and return one typed outcome per side (`V2030.1.1-PRD-ARD.md`
required capability 1: "materially different planners can run against the
same admitted gym subject").

Confirmed as a real, previously-unclosed gap: `PlannerLeague` populates the
league, checks `compatibility()` and schedules `LeagueMatch` candidates, but
no `solve()` was invoked anywhere under `src/autofde_lab/planner_league`
until `disturbance_episode.py` solved *one* constructor side. This module
closes the *pairwise* half of the PRD's falsifier -- "one planner's output
is treated as the answer without comparison where alternatives exist" --
with real collaborators only:

- the real domain resolved via `world_admission.WORLD_DOMAIN_FACTORIES`;
- the real registered solver via the same `utils.load_registered_solver`
  path `PlannerLeague.compatibility()` uses, its real `solve()` and
  `get_plan()` under a real wall-clock bound (`concurrent.futures`, the
  same shape as `reasoning/planner_federation.py`);
- the domain's own real `get_initial_state()` / `get_next_state()` /
  `is_goal()` for the replay that establishes `goal_reached` -- never the
  planner's own claim.

Both sides are solved independently and the pair is always returned, even
when one side is `UNSUPPORTED:*` / `REFUSED:*`: a pair with one refusal is
still a comparison result, not an error.

Status vocabulary, exact strings (`.claude/rules/absence-is-not-evidence.md`):

- `PLAN_CANDIDATE` -- a real plan was produced and replayed through the
  domain; `goal_reached` is the domain's verdict over that replay.
- `UNSUPPORTED:NOT_REGISTERED` / `UNSUPPORTED:REQUIRES_CONFIGURATION` /
  `UNSUPPORTED:INCOMPATIBLE` -- the planner could not lawfully run here;
  `reason` carries the underlying `compatibility()` / `unmet_required_args`
  detail.
- `TIMEOUT` -- `solve()` exceeded `timeout_s` real seconds (still running
  at the bound, or measured to have completed past it); no verdict.
- `SOLVE_FAILED:<ExceptionType>` -- the solver raised, named by type.
- `EMPTY_PLAN` -- `get_plan()` returned nothing.
- `UNKNOWN:PLAN_SHAPE_*` / `UNKNOWN:UNDISTURBED_PLAN_UNREPLAYABLE:*` --
  from the shared `_plan_shape` normaliser.
- `REFUSED:LLM_NOVELTY_BOUNDARY` -- any `catalog.NOVELTY_ORACLES` planner,
  returned *without loading it*: the same boundary `PlannerLeague` already
  enforces on the population, made visible per side rather than raised.

Receipt boundary (`CLAUDE.md`, `.claude/rules/no-dual-bookkeeping.md`):
a `LeagueSolveOutcome` carries no receipt, is not a `PayoffObservation`,
and nothing here writes a `PayoffHypergraph`. `core.py`'s
`REFUSED:UNRECEIPTED_PAYOFF` gate stays the only door; this module computes
candidate plans and nothing else.
"""

from __future__ import annotations

import concurrent.futures
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from ._plan_shape import _plan_shape, _PlanShapeUnknown
from .catalog import NOVELTY_ORACLES
from .core import LeagueMatch, PlannerLeague, PolicySpec
from .world_admission import WORLD_DOMAIN_FACTORIES

__all__ = ["LeagueSolveOutcome", "solve_league_match", "solve_league_side"]

STATUS_PLAN_CANDIDATE = "PLAN_CANDIDATE"
STATUS_NOT_REGISTERED = "UNSUPPORTED:NOT_REGISTERED"
STATUS_REQUIRES_CONFIGURATION = "UNSUPPORTED:REQUIRES_CONFIGURATION"
STATUS_INCOMPATIBLE = "UNSUPPORTED:INCOMPATIBLE"
STATUS_TIMEOUT = "TIMEOUT"
STATUS_EMPTY_PLAN = "EMPTY_PLAN"
STATUS_LLM_REFUSED = "REFUSED:LLM_NOVELTY_BOUNDARY"


@dataclass(frozen=True, slots=True)
class LeagueSolveOutcome:
    """One side's real outcome. `actions` is the plan as the domain replayed
    it; `goal_reached` is the domain's own `is_goal()` over that replay and
    is `None` whenever no plan was replayed -- never coerced to `False`.
    Deliberately carries no `receipt_id`, `standing` or `alive` field."""

    planner_id: str
    role_id: str
    world_id: str
    status: str
    actions: tuple[Any, ...]
    plan_length: int
    goal_reached: bool | None
    wall_s: float
    reason: str


def _no_plan(
    policy: PolicySpec, role_id: str, world_id: str, status: str, reason: str, t0: float
) -> LeagueSolveOutcome:
    return LeagueSolveOutcome(
        planner_id=policy.planner_id,
        role_id=role_id,
        world_id=world_id,
        status=status,
        actions=(),
        plan_length=0,
        goal_reached=None,
        wall_s=time.perf_counter() - t0,
        reason=reason,
    )


def solve_league_side(
    policy: PolicySpec,
    role_id: str,
    world_id: str,
    *,
    league: PlannerLeague,
    domain_factories: Mapping[str, Callable[[], Any]] = WORLD_DOMAIN_FACTORIES,
    timeout_s: float = 30.0,
    solver_kwargs: Mapping[str, Any] | None = None,
) -> LeagueSolveOutcome:
    """Solve one side of a match on a fresh domain instance and replay the
    plan through that domain's own transition/goal methods."""
    t0 = time.perf_counter()
    if policy.planner_id in NOVELTY_ORACLES:
        # Returned before any import: the oracle is never loaded here.
        return _no_plan(
            policy, role_id, world_id, STATUS_LLM_REFUSED, STATUS_LLM_REFUSED, t0
        )
    factory = domain_factories.get(world_id)
    if factory is None:
        return _no_plan(
            policy,
            role_id,
            world_id,
            STATUS_INCOMPATIBLE,
            f"NO_DOMAIN_FOR_WORLD:{world_id}",
            t0,
        )
    domain = factory()

    compat = league.compatibility(domain, policy.planner_id, role_id)
    if not compat.compatible:
        status = (
            STATUS_NOT_REGISTERED
            if compat.reason
            in ("UNSUPPORTED:PLANNER_LOAD_FAILED", "UNSUPPORTED:UNKNOWN_PLANNER")
            else STATUS_INCOMPATIBLE
        )
        return _no_plan(policy, role_id, world_id, status, compat.reason, t0)

    # Same lazy-import path `PlannerLeague.compatibility()` uses.
    from autofde_lab.hub.domain.gym_procedure.planner_federation import (
        unmet_required_args,
    )
    from autofde_lab.utils import load_registered_solver

    solver_type = load_registered_solver(policy.planner_id)
    if solver_type is None:
        return _no_plan(
            policy,
            role_id,
            world_id,
            STATUS_NOT_REGISTERED,
            "UNSUPPORTED:PLANNER_LOAD_FAILED",
            t0,
        )
    kwargs = dict(solver_kwargs or {})
    missing = unmet_required_args(solver_type, kwargs)
    if missing:
        return _no_plan(
            policy,
            role_id,
            world_id,
            STATUS_REQUIRES_CONFIGURATION,
            "UNSUPPORTED:REQUIRES_CONFIGURATION:" + ",".join(missing),
            t0,
        )
    if not hasattr(solver_type, "get_plan"):
        return _no_plan(
            policy,
            role_id,
            world_id,
            STATUS_INCOMPATIBLE,
            "UNSUPPORTED:NO_PLAN_SURFACE",
            t0,
        )

    initial_state = domain.get_initial_state()
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        solver = solver_type(domain_factory=lambda: domain, **kwargs)
        solve_t0 = time.perf_counter()
        future = executor.submit(solver.solve)
        try:
            future.result(timeout=timeout_s)
        except concurrent.futures.TimeoutError:
            return _no_plan(
                policy,
                role_id,
                world_id,
                STATUS_TIMEOUT,
                f"TIMEOUT:SOLVE_STILL_RUNNING_AFTER:{timeout_s}s",
                t0,
            )
        solve_s = time.perf_counter() - solve_t0
        if solve_s > timeout_s:
            # Measured: a native (C++) solve() holds the GIL, so the
            # pre-emptive wait above cannot observe a budget smaller than
            # one GIL hold -- the completed solve is checked against the
            # same real clock afterwards. A plan produced outside its
            # budget is not a within-budget candidate; it is not admitted.
            return _no_plan(
                policy,
                role_id,
                world_id,
                STATUS_TIMEOUT,
                f"TIMEOUT:SOLVE_COMPLETED_AFTER_BUDGET:{solve_s:.6f}s>{timeout_s}s",
                t0,
            )
        plan = list(solver.get_plan(initial_state))
    except Exception as exc:  # noqa: BLE001 -- same guard as PlannerLeague.compatibility(): a solver raise is typed, named by type, never a verdict
        return _no_plan(
            policy,
            role_id,
            world_id,
            f"SOLVE_FAILED:{type(exc).__name__}",
            f"SOLVE_FAILED:{type(exc).__name__}:{exc}",
            t0,
        )
    finally:
        # Non-blocking, as in `reasoning/planner_federation.py`: a timed-out
        # solve()'s worker may still be inside the C++ engine.
        executor.shutdown(wait=False)
    if not plan:
        return _no_plan(
            policy, role_id, world_id, STATUS_EMPTY_PLAN, STATUS_EMPTY_PLAN, t0
        )

    try:
        actions, _expected_after = _plan_shape(domain, initial_state, plan)
    except _PlanShapeUnknown as unknown:
        return _no_plan(policy, role_id, world_id, unknown.reason, unknown.reason, t0)

    # `goal_reached` comes from the domain's own replay, never from the plan.
    state = initial_state
    try:
        for action in actions:
            state = domain.get_next_state(state, action)
        goal_reached = bool(domain.is_goal(state))
    except Exception as exc:  # noqa: BLE001 -- the domain refused a replayed state: no goal verdict was earned
        return _no_plan(
            policy,
            role_id,
            world_id,
            f"UNKNOWN:PLAN_UNREPLAYABLE:{type(exc).__name__}",
            f"UNKNOWN:PLAN_UNREPLAYABLE:{type(exc).__name__}:{exc}",
            t0,
        )
    return LeagueSolveOutcome(
        planner_id=policy.planner_id,
        role_id=role_id,
        world_id=world_id,
        status=STATUS_PLAN_CANDIDATE,
        actions=tuple(actions),
        plan_length=len(actions),
        goal_reached=goal_reached,
        wall_s=time.perf_counter() - t0,
        reason="PLAN_CANDIDATE:REPLAYED_THROUGH_DOMAIN",
    )


def solve_league_match(
    match: LeagueMatch,
    *,
    league: PlannerLeague | None = None,
    domain_factories: Mapping[str, Callable[[], Any]] = WORLD_DOMAIN_FACTORIES,
    timeout_s: float = 30.0,
    solver_kwargs: Mapping[str, Mapping[str, Any]] | None = None,
) -> tuple[LeagueSolveOutcome, LeagueSolveOutcome]:
    """Solve both sides of `match` independently on the same admitted world
    and return `(left, right)`. `solver_kwargs` is keyed by `planner_id`.
    Neither outcome is a payoff and no hypergraph write happens here."""
    league = league if league is not None else PlannerLeague()
    per_planner = solver_kwargs or {}
    sides = (
        (match.left_policy, match.left_role_id),
        (match.right_policy, match.right_role_id),
    )
    left, right = (
        solve_league_side(
            policy,
            role_id,
            match.world_id,
            league=league,
            domain_factories=domain_factories,
            timeout_s=timeout_s,
            solver_kwargs=per_planner.get(policy.planner_id),
        )
        for policy, role_id in sides
    )
    return left, right
