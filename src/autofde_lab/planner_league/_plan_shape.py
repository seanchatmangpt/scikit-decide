# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Shared normaliser for the two real `get_plan()` shapes registered solvers
return. Extracted from `disturbance_episode.py` (where it was first
manufactured after a refute pass found `IDAstar`/`LRTAstar` bare-`Action`
plans crashing code written against `Astar`/`EHC` tuple plans) so that
`league_solve.py` replays through the same one interpretation rather than a
second, drifting copy. Private to `planner_league`."""

from __future__ import annotations

from typing import Any

__all__ = ["_PlanShapeUnknown", "_plan_shape"]


class _PlanShapeUnknown(Exception):
    """The registered solver's `get_plan()` returned something this replay
    cannot interpret as a sequence of domain actions; carries the typed
    `UNKNOWN:...` reason."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _plan_shape(
    domain: Any, initial_state: Any, plan: list[Any]
) -> tuple[list[Any], list[Any]]:
    """Normalise the two real `get_plan()` shapes registered solvers return.

    Real, measured on this repo's own solvers: `Astar`/`EHC` yield
    `(state, action, value)` tuples; `IDAstar`/`LRTAstar` yield bare
    `Action`s. Both are lawful plans. Returns `(actions, expected_after)`
    where `expected_after[i]` is the state the constructor's plan expects
    *after* step i (`None` for the final step, whose only expectation is
    the domain's own `is_goal()`).

    For tuple plans that expectation is the planner's own claim
    (`plan[i + 1][0]`). For bare-action plans the planner makes no state
    claim, so the expectation is the domain's own undisturbed replay of the
    same actions -- the real transition model, not a second one. Anything
    else (mixed shapes, an undisturbed replay the domain refuses) is
    `UNKNOWN`: it is not coerced into an interpretation.
    """
    tupled = [isinstance(step, tuple) and len(step) >= 2 for step in plan]
    if all(tupled):
        actions = [step[1] for step in plan]
        expected_after = [plan[i + 1][0] for i in range(len(plan) - 1)] + [None]
        return actions, expected_after
    if any(tupled):
        raise _PlanShapeUnknown("UNKNOWN:PLAN_SHAPE_MIXED")
    actions = list(plan)
    expected_after: list[Any] = []
    state = initial_state
    try:
        for action in actions[:-1]:
            state = domain.get_next_state(state, action)
            expected_after.append(state)
    except Exception as exc:
        raise _PlanShapeUnknown(
            f"UNKNOWN:UNDISTURBED_PLAN_UNREPLAYABLE:{type(exc).__name__}"
        ) from exc
    expected_after.append(None)
    return actions, expected_after
