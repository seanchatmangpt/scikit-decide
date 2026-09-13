"""The OCEL adapter promised (but deliberately not built) in ``wasm4pm_types.py`` and
``planning_types.py``'s docstrings: maps a real ``list[PlanStepOutcome]`` trajectory
into a real ``OcelLog`` (``wasm4pm_types.OcelEvent``/``OcelObject``), so process-
mining-shaped tooling — including the optimization agent in ``optimization_agent.py``
— has real OCEL data to work over instead of raw rollout output.

One plan run becomes one OCEL object (type ``"PlanRun"``); each step becomes one
event of that object, related via an ``OcelRelationship``, carrying its
reward/cost/termination as real event attributes.
"""

from __future__ import annotations

from .planning_types import PlanStepOutcome
from .wasm4pm_types import (
    OcelEvent,
    OcelEventAttribute,
    OcelLog,
    OcelObject,
    OcelRelationship,
)


def trajectory_to_ocel_log(steps: list[PlanStepOutcome], run_id: str) -> OcelLog:
    """Build a real ``OcelLog`` from a real rollout trajectory. ``run_id`` becomes
    the id of the one ``PlanRun`` object every step-event relates to."""
    events = [
        OcelEvent(
            id=f"{run_id}-e{step.step_index}",
            type=step.action,
            time=step.step_index,
            attributes=[
                OcelEventAttribute(name="reward", value=step.reward),
                OcelEventAttribute(name="cost", value=step.cost),
                OcelEventAttribute(name="termination", value=step.termination),
                OcelEventAttribute(name="observation", value=step.observation),
            ],
            relationships=[OcelRelationship(objectId=run_id, qualifier="plan-run")],
        )
        for step in steps
    ]
    plan_run_object = OcelObject(id=run_id, type="PlanRun", attributes=[])
    return OcelLog(events=events, objects=[plan_run_object], eventTypes=[], objectTypes=[])


__all__ = ["trajectory_to_ocel_log"]
