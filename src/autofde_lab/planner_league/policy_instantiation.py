# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Refuse an unlawful `PolicySpec` and make `PolicySpec.parameters` a real,
outcome-affecting axis instead of an identity-only string tuple.

Scoped narrowly (`V2030.1.1-PRD-ARD.md` required capability 3: policy =
Planner x Parameters x Objective x ObservationProjection x
ActionProjection), against a real, previously-unclosed gap: `PolicySpec`
(direct constructor and `for_role`) admits an unknown `planner_id` /
`objective_id` / `action_projection_id` without refusal (`for_role` only
validates `role_id`, `observation_projection_id`, `budget_id` -- confirmed
by adversarial probe this session, `PolicySpec(planner_id="NotAPlanner",
...)` and `PolicySpec.for_role("NotAPlanner", "blue_defender")` are both
accepted), and `PolicySpec.parameters` is carried in `LeagueMatch` identity
but never reaches a real solver -- `league_solve.solve_league_side` builds
its own `kwargs` from a caller-supplied `solver_kwargs` mapping keyed by
`planner_id`, never from `policy.parameters`.

This module does not re-derive solver loading, timeout handling, plan
replay, or the `PLAN_CANDIDATE` / `TIMEOUT` / `SOLVE_FAILED:*` /
`EMPTY_PLAN` vocabulary -- `league_solve.py` (`#114`) already owns that,
adversarially verified. `instantiate_policy` below stops at real solver
*construction* with `dict(spec.parameters)` as constructor kwargs, which is
exactly the step upstream of `solve_league_side` where `spec.parameters`
today never arrives; it does not call `solve()` and does not replay a plan.
A caller that wants a full parameterized solve should thread the real
solver instance this function returns (or `dict(spec.parameters)` as
`league_solve`'s `solver_kwargs[spec.planner_id]`) into
`league_solve.solve_league_side` / `solve_league_match` itself -- that
wiring is a separate, single-cause step, not duplicated here.

Projection executable semantics (applying `partial_observation` /
`stale_observation` to a real domain observation, or mapping a real solver
output onto `disturbance_intent` / `falsification_intent` / ...) are
explicitly out of scope for this step -- a separate single-cause step per
the required-capability record.

Status vocabulary, exact strings (`.claude/rules/absence-is-not-evidence.md`):

- `validate_policy_spec` raises `ValueError("REFUSED:UNKNOWN_PLANNER:<id>")`
  / `REFUSED:UNKNOWN_OBJECTIVE:<id>` / `REFUSED:UNKNOWN_OBSERVATION_PROJECTION:<id>`
  / `REFUSED:UNKNOWN_ACTION_PROJECTION:<id>` -- named, typed, never a bare
  `ValueError`.
- `instantiate_policy` returns `PolicyInstantiation` with `status` one of:
  `INSTANTIATED` (a real solver instance was constructed against the real
  domain factory), `UNSUPPORTED:NOT_REGISTERED` (no entry point for
  `planner_id`), `REFUSED:PARAMETER_REJECTED:<ExceptionType>` (the real
  constructor raised on `dict(spec.parameters)` as kwargs -- named by type,
  never swallowed), `REFUSED:LLM_NOVELTY_BOUNDARY` (any
  `catalog.NOVELTY_ORACLES` planner, returned without loading it, same
  boundary `PlannerLeague`/`league_solve` already enforce).

No receipt, admission, or actuation semantics (`CLAUDE.md`): this module
constructs a candidate solver instance in-process; it does not solve, does
not actuate a gym, and nothing here writes a `PayoffHypergraph`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .catalog import (
    ACTION_PROJECTIONS,
    NOVELTY_ORACLES,
    OBSERVATION_PROJECTIONS,
    PRIMARY_PLANNERS,
    ROLE_SPECS,
)
from .core import PolicySpec

__all__ = ["PolicyInstantiation", "instantiate_policy", "validate_policy_spec"]

STATUS_INSTANTIATED = "INSTANTIATED"
STATUS_NOT_REGISTERED = "UNSUPPORTED:NOT_REGISTERED"
STATUS_LLM_REFUSED = "REFUSED:LLM_NOVELTY_BOUNDARY"

_KNOWN_OBJECTIVES: frozenset[str] = frozenset(
    role["objective"] for role in ROLE_SPECS.values()
)


def validate_policy_spec(spec: PolicySpec) -> PolicySpec:
    """Refuse a `PolicySpec` naming a policy that cannot exist.

    Returns `spec` unchanged on success (so callers can chain), never
    mutates it -- `PolicySpec` is frozen. Raises a typed `ValueError` naming
    the exact axis and value on refusal; never a bare `ValueError`.
    """
    if spec.planner_id not in PRIMARY_PLANNERS:
        if spec.planner_id in NOVELTY_ORACLES:
            raise ValueError(STATUS_LLM_REFUSED)
        raise ValueError(f"REFUSED:UNKNOWN_PLANNER:{spec.planner_id}")
    if spec.objective_id not in _KNOWN_OBJECTIVES:
        raise ValueError(f"REFUSED:UNKNOWN_OBJECTIVE:{spec.objective_id}")
    if spec.observation_projection_id not in OBSERVATION_PROJECTIONS:
        raise ValueError(
            f"REFUSED:UNKNOWN_OBSERVATION_PROJECTION:{spec.observation_projection_id}"
        )
    if spec.action_projection_id not in ACTION_PROJECTIONS:
        raise ValueError(
            f"REFUSED:UNKNOWN_ACTION_PROJECTION:{spec.action_projection_id}"
        )
    return spec


@dataclass(frozen=True, slots=True)
class PolicyInstantiation:
    """The real result of constructing `spec`'s registered solver with
    `dict(spec.parameters)` as kwargs. `solver` is the live instance on
    `INSTANTIATED`, `None` otherwise -- never a placeholder object standing
    in for a refusal."""

    planner_id: str
    status: str
    reason: str
    solver: Any | None = None


def instantiate_policy(
    spec: PolicySpec, domain_factory: Callable[[], Any]
) -> PolicyInstantiation:
    """Validate `spec`, then construct its registered solver against
    `domain_factory` with `dict(spec.parameters)` as constructor kwargs.

    Makes `Parameters` a real, outcome-affecting axis: two `PolicySpec`s
    differing only in `parameters` reach two really-differently-constructed
    solver instances here, rather than two identical solves keyed by
    `planner_id` alone.
    """
    validate_policy_spec(spec)
    if spec.planner_id in NOVELTY_ORACLES:
        # Unreachable given validate_policy_spec above (NOVELTY_ORACLES
        # planners raise there), kept as an explicit second gate so this
        # function stays safe to call standalone against a mutated spec.
        return PolicyInstantiation(
            planner_id=spec.planner_id,
            status=STATUS_LLM_REFUSED,
            reason=STATUS_LLM_REFUSED,
        )

    # Same lazy-import path `PlannerLeague.compatibility()` / `league_solve`
    # use -- keeps league construction independent of optional solver extras.
    from autofde_lab.utils import load_registered_solver

    solver_type = load_registered_solver(spec.planner_id)
    if solver_type is None:
        return PolicyInstantiation(
            planner_id=spec.planner_id,
            status=STATUS_NOT_REGISTERED,
            reason="UNSUPPORTED:PLANNER_LOAD_FAILED",
        )

    kwargs = dict(spec.parameters)
    try:
        solver = solver_type(domain_factory=domain_factory, **kwargs)
    except Exception as exc:  # noqa: BLE001 -- a rejected/mistyped parameter is typed, named by type, never a verdict
        return PolicyInstantiation(
            planner_id=spec.planner_id,
            status=f"REFUSED:PARAMETER_REJECTED:{type(exc).__name__}",
            reason=f"REFUSED:PARAMETER_REJECTED:{type(exc).__name__}:{exc}",
        )
    return PolicyInstantiation(
        planner_id=spec.planner_id,
        status=STATUS_INSTANTIATED,
        reason="INSTANTIATED:REAL_SOLVER_CONSTRUCTED",
        solver=solver,
    )
