# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Real `red_disturbance` episode -- the adversarial branch of
`V2030.1.1-PRD-ARD.md`'s "repeated episodes + adversarial episodes ->
metric/constraint evaluation" (required capability 6).

Confirmed as a real, previously-unclosed gap: `catalog.ROLE_SPECS` names
`red_disturbance` (`manufacture_admitted_disturbance` /
`disturbance_intent`), but before this module nothing in
`src/autofde_lab/planner_league` or `src/autofde_lab/reasoning` constructed
a disturbance and replayed a constructor's plan against it. The
`plan_falsifier` in `reasoning/exploration_payoff_bridge.py` is only
checked for compatibility; the `FALSIFIED` verdict there comes solely from
receipt postconditions. This module closes the *league-level* adversarial
episode with real collaborators only:

- the real domain resolved via `world_admission.WORLD_DOMAIN_FACTORIES`
  (no new `world_id -> domain` mapping);
- the real registered solver via the same `utils.load_registered_solver`
  path `PlannerLeague.compatibility()` already uses, its real `solve()` and
  `get_plan()`;
- the domain's own real `get_initial_state()` / `get_next_state()` /
  `is_goal()` for the replay -- never a re-derived transition model.

Standing vocabulary (`.claude/rules/absence-is-not-evidence.md`):

- `SURVIVES` -- the admitted goal is reached after the perturbation.
- `FALSIFIED` -- the plan no longer reaches the goal; `failed_at_step`
  and `counterexample_state` are recorded.
- `UNKNOWN` -- nothing was tested: the solver produced no plan (planner
  not loadable, domain refused, empty plan), its plan had a shape this
  replay does not interpret, or the disturbance could not be applied
  (its transform raised, or produced a state the domain refuses). Never
  coerced into either verdict, and never an uncaught exception either --
  the adversarial refute pass on this module found `IDAstar`/`LRTAstar`
  (bare-`Action` plans) crashing where `Astar`/`EHC` (state/action tuples)
  did not; both shapes are now normalised in `_plan_shape`.

Receipt boundary (`CLAUDE.md`, `.claude/rules/no-dual-bookkeeping.md`):
this repo computes candidate plans and is never given receipt/admission/
actuation semantics. A result therefore carries a `trajectory_digest` --
evidence *identity* over what was actually replayed -- and never a receipt.
`disturbance_result_to_payoff` requires an externally supplied
`receipt_id` (the gymact court's) and refuses, with a named reason, rather
than minting one: a self-issued receipt would be `SELF_CERTIFIED`.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

from ._plan_shape import _plan_shape, _PlanShapeUnknown
from .catalog import ROLE_SPECS
from .core import LeagueMatch, PayoffObservation, PlannerLeague, PolicySpec
from .world_admission import WORLD_DOMAIN_FACTORIES

__all__ = [
    "Disturbance",
    "DisturbanceEpisodeResult",
    "DisturbanceStanding",
    "disturbance_result_to_payoff",
    "run_disturbance_episode",
]

CONSTRUCTOR_ROLE_ID = "plan_constructor"
DISTURBANCE_ROLE_ID = "red_disturbance"


class DisturbanceStanding(str, Enum):
    SURVIVES = "SURVIVES"
    FALSIFIED = "FALSIFIED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class Disturbance:
    """One typed, admitted disturbance: a pure `state -> state` transform
    applied exactly once, at plan step index `at_step`, before that step's
    action is replayed. `identity` is the stable name that enters the
    trajectory digest -- the callable itself has no stable identity."""

    identity: str
    at_step: int
    transform: Callable[[Any], Any]

    def __post_init__(self) -> None:
        if self.at_step < 0:
            raise ValueError(f"REFUSED:NEGATIVE_AT_STEP:{self.at_step}")
        if not self.identity.strip():
            raise ValueError("REFUSED:EMPTY_DISTURBANCE_IDENTITY")


@dataclass(frozen=True, slots=True)
class DisturbanceEpisodeResult:
    """The real outcome of replaying one constructor plan against one
    disturbance. `trajectory` is the actual replayed `(state, action)`
    sequence (the action taken *from* that state; the final entry carries
    `None` as its action). `trajectory_digest` is evidence identity over
    `(world_id, constructor_planner_id, disturbance identity/at_step,
    trajectory)` -- explicitly not a receipt."""

    world_id: str
    constructor_planner_id: str
    disturbance_identity: str
    at_step: int
    standing: DisturbanceStanding
    reason: str
    plan_length: int
    trajectory: tuple[tuple[Any, Any], ...]
    trajectory_digest: str
    failed_at_step: int | None = None
    counterexample_state: Any = None


def _canonical(value: Any) -> Any:
    """Deterministic, JSON-representable projection of a domain state or
    action: enums by name, named tuples/tuples/lists element-wise, mappings
    key-sorted, everything else via `repr`."""
    if isinstance(value, Enum):
        return f"{type(value).__name__}.{value.name}"
    if isinstance(value, tuple) and hasattr(value, "_asdict"):
        return {k: _canonical(v) for k, v in value._asdict().items()}
    if isinstance(value, (tuple, list)):
        return [_canonical(v) for v in value]
    if isinstance(value, Mapping):
        return {
            str(k): _canonical(v)
            for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))
        }
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return repr(value)


def _trajectory_digest(
    world_id: str,
    constructor_planner_id: str,
    disturbance: Disturbance,
    trajectory: tuple[tuple[Any, Any], ...],
) -> str:
    payload = json.dumps(
        {
            "world_id": world_id,
            "constructor_planner_id": constructor_planner_id,
            "disturbance_identity": disturbance.identity,
            "at_step": disturbance.at_step,
            "trajectory": [[_canonical(s), _canonical(a)] for s, a in trajectory],
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(
        ("disturbance-episode-v1|" + payload).encode("utf-8")
    ).hexdigest()


def _unknown(
    world_id: str,
    constructor_planner_id: str,
    disturbance: Disturbance,
    reason: str,
) -> DisturbanceEpisodeResult:
    return DisturbanceEpisodeResult(
        world_id=world_id,
        constructor_planner_id=constructor_planner_id,
        disturbance_identity=disturbance.identity,
        at_step=disturbance.at_step,
        standing=DisturbanceStanding.UNKNOWN,
        reason=reason,
        plan_length=0,
        trajectory=(),
        trajectory_digest=_trajectory_digest(
            world_id, constructor_planner_id, disturbance, ()
        ),
    )


def run_disturbance_episode(
    world_id: str,
    constructor_planner_id: str,
    disturbance: Disturbance,
    *,
    league: PlannerLeague | None = None,
    solver_kwargs: Mapping[str, Any] | None = None,
    domain_factories: Mapping[str, Callable[[], Any]] = WORLD_DOMAIN_FACTORIES,
) -> DisturbanceEpisodeResult:
    """Solve the real `world_id` domain with the real registered
    `constructor_planner_id` solver, then replay the returned plan through
    the domain's own transition/goal methods, applying `disturbance` once
    at `disturbance.at_step`.

    Replay semantics, stated so they are inspectable rather than implied:
    steps before `at_step` replay the plan's actions from the real initial
    state; at `at_step` the current state is replaced by
    `disturbance.transform(state)`; every remaining plan action is then
    replayed from there. `SURVIVES` iff the domain's real `is_goal()` holds
    for some replayed state at or after the perturbation. Otherwise
    `FALSIFIED`, with `failed_at_step` = the first step at or after
    `at_step` whose real successor differs from the state the constructor's
    plan expected there (the goal, for the final step) and
    `counterexample_state` = the state that step was replayed from.

    A disturbance whose `at_step` lies beyond the plan is `UNKNOWN`: it was
    never applied, so nothing was tested.
    """
    league = league if league is not None else PlannerLeague()
    factory = domain_factories.get(world_id)
    if factory is None:
        return _unknown(
            world_id,
            constructor_planner_id,
            disturbance,
            f"UNKNOWN:NO_DOMAIN_FOR_WORLD:{world_id}",
        )
    domain = factory()

    compat = league.compatibility(domain, constructor_planner_id, CONSTRUCTOR_ROLE_ID)
    if not compat.compatible:
        return _unknown(
            world_id, constructor_planner_id, disturbance, f"UNKNOWN:{compat.reason}"
        )

    # Same lazy-import path `PlannerLeague.compatibility()` uses.
    from autofde_lab.utils import load_registered_solver

    solver_type = load_registered_solver(constructor_planner_id)
    if solver_type is None:
        return _unknown(
            world_id, constructor_planner_id, disturbance, "UNKNOWN:PLANNER_LOAD_FAILED"
        )
    if not hasattr(solver_type, "get_plan"):
        return _unknown(
            world_id,
            constructor_planner_id,
            disturbance,
            "UNKNOWN:PLANNER_HAS_NO_PLAN_SURFACE",
        )

    initial_state = domain.get_initial_state()
    try:
        solver = solver_type(domain_factory=factory, **dict(solver_kwargs or {}))
        solver.solve()
        plan = list(solver.get_plan(initial_state))
    except Exception as exc:  # noqa: BLE001 -- same guard as PlannerLeague.compatibility(): a solver raise is UNKNOWN, named by type
        return _unknown(
            world_id,
            constructor_planner_id,
            disturbance,
            f"UNKNOWN:SOLVE_FAILED:{type(exc).__name__}",
        )
    if not plan:
        return _unknown(
            world_id, constructor_planner_id, disturbance, "UNKNOWN:EMPTY_PLAN"
        )
    if disturbance.at_step >= len(plan):
        return _unknown(
            world_id,
            constructor_planner_id,
            disturbance,
            f"UNKNOWN:AT_STEP_BEYOND_PLAN:{disturbance.at_step}>={len(plan)}",
        )

    try:
        actions, expected_after = _plan_shape(domain, initial_state, plan)
    except _PlanShapeUnknown as unknown:
        return _unknown(world_id, constructor_planner_id, disturbance, unknown.reason)

    trajectory: list[tuple[Any, Any]] = []
    state = initial_state
    standing = DisturbanceStanding.FALSIFIED
    reason = "FALSIFIED:GOAL_NOT_REACHED_AFTER_DISTURBANCE"
    failed_at_step: int | None = None
    counterexample_state: Any = None
    try:
        for i in range(disturbance.at_step):
            trajectory.append((state, actions[i]))
            state = domain.get_next_state(state, actions[i])

        try:
            state = disturbance.transform(state)
        except Exception as exc:  # noqa: BLE001 -- a disturbance that cannot be applied tested nothing: UNKNOWN, named by type
            return _unknown(
                world_id,
                constructor_planner_id,
                disturbance,
                f"UNKNOWN:DISTURBANCE_TRANSFORM_FAILED:{type(exc).__name__}",
            )

        if domain.is_goal(state):
            standing = DisturbanceStanding.SURVIVES
            reason = "SURVIVES:GOAL_REACHED_AFTER_DISTURBANCE"
        for i in range(disturbance.at_step, len(plan)):
            trajectory.append((state, actions[i]))
            next_state = domain.get_next_state(state, actions[i])
            expected = expected_after[i]
            diverged = (
                not domain.is_goal(next_state)
                if expected is None
                else next_state != expected
            )
            if diverged and failed_at_step is None:
                failed_at_step = i
                counterexample_state = state
            state = next_state
            if domain.is_goal(state):
                standing = DisturbanceStanding.SURVIVES
                reason = "SURVIVES:GOAL_REACHED_AFTER_DISTURBANCE"
                break
    except Exception as exc:  # noqa: BLE001 -- the domain refused a replayed (possibly disturbed) state: no verdict was earned, so UNKNOWN, named by type
        return _unknown(
            world_id,
            constructor_planner_id,
            disturbance,
            f"UNKNOWN:DISTURBED_STATE_REJECTED_BY_DOMAIN:{type(exc).__name__}",
        )
    trajectory.append((state, None))
    if standing is DisturbanceStanding.SURVIVES:
        failed_at_step = None
        counterexample_state = None
    elif failed_at_step is None:
        # Every step matched the plan's expectation yet the goal was never
        # reached: the planner-side goal claim itself is the counterexample.
        failed_at_step = len(plan) - 1
        counterexample_state = state

    frozen_trajectory = tuple(trajectory)
    return DisturbanceEpisodeResult(
        world_id=world_id,
        constructor_planner_id=constructor_planner_id,
        disturbance_identity=disturbance.identity,
        at_step=disturbance.at_step,
        standing=standing,
        reason=reason,
        plan_length=len(plan),
        trajectory=frozen_trajectory,
        trajectory_digest=_trajectory_digest(
            world_id, constructor_planner_id, disturbance, frozen_trajectory
        ),
        failed_at_step=failed_at_step,
        counterexample_state=counterexample_state,
    )


def disturbance_result_to_payoff(
    result: DisturbanceEpisodeResult,
    *,
    league: PlannerLeague,
    disturbance_planner_id: str,
    receipt_id: str,
    observation_projection_id: str = "full_observation",
    budget_id: str = "balanced",
) -> tuple[PayoffObservation | None, str]:
    """Project a real episode result onto a `(plan_constructor,
    red_disturbance)` `PayoffObservation`, or refuse with a named reason --
    the same `(None, reason)` shape `reasoning/exploration_payoff_bridge.py`
    uses. `SURVIVES` -> constructor `(1.0, 0.0)`; `FALSIFIED` -> disturbance
    `(0.0, 1.0)`; `UNKNOWN` -> refused, never a `0.0/0.0` placeholder.

    `receipt_id` is the external execution court's receipt, supplied by the
    caller. A missing/blank one is refused as `REFUSED:UNRECEIPTED_PAYOFF`
    *before* construction -- this function never derives a receipt from
    `result.trajectory_digest`, which is evidence identity, not a receipt.
    """
    if result.standing is DisturbanceStanding.UNKNOWN:
        return None, f"REFUSED:UNKNOWN_STANDING_HAS_NO_PAYOFF:{result.reason}"
    if not receipt_id or not receipt_id.strip():
        return None, "REFUSED:UNRECEIPTED_PAYOFF:EXTERNAL_RECEIPT_ID_REQUIRED"
    if disturbance_planner_id not in league.planners:
        return None, f"REFUSED:UNKNOWN_DISTURBANCE_PLANNER:{disturbance_planner_id}"
    if DISTURBANCE_ROLE_ID not in ROLE_SPECS or CONSTRUCTOR_ROLE_ID not in ROLE_SPECS:
        return None, "REFUSED:ROLE_NOT_IN_CATALOG"

    match = LeagueMatch(
        world_id=result.world_id,
        left_role_id=CONSTRUCTOR_ROLE_ID,
        left_policy=PolicySpec.for_role(
            result.constructor_planner_id,
            CONSTRUCTOR_ROLE_ID,
            observation_projection_id=observation_projection_id,
            budget_id=budget_id,
        ),
        right_role_id=DISTURBANCE_ROLE_ID,
        right_policy=PolicySpec.for_role(
            disturbance_planner_id,
            DISTURBANCE_ROLE_ID,
            parameters={
                "disturbance_identity": result.disturbance_identity,
                "at_step": result.at_step,
            },
            observation_projection_id=observation_projection_id,
            budget_id=budget_id,
        ),
    )
    left_score, right_score = (
        (1.0, 0.0) if result.standing is DisturbanceStanding.SURVIVES else (0.0, 1.0)
    )
    try:
        observation = PayoffObservation(
            match, left_score, right_score, receipt_id=receipt_id
        )
    except ValueError as exc:
        # Defensive only: the real `PayoffObservation.__post_init__` gate,
        # never bypassed or re-derived here.
        return None, str(exc)
    return observation, f"ALIVE:DISTURBANCE_PAYOFF:{result.standing.value}"
