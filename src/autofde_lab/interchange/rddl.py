"""Observed RDDL rollout export."""

from __future__ import annotations

import math
from typing import Any, Iterable

from .model import Builder, ExportLimits, PlanningExport, canonical, digest, short_label


def export_rddl_rollout(
    domain: Any,
    actions: Iterable[Any],
    *,
    subject: str,
    limits: ExportLimits = ExportLimits(),
) -> PlanningExport:
    """Export observed stochastic consequences without claiming full enumeration."""

    limits.validate()
    builder = Builder(
        "rddl",
        subject,
        {"source": "autofde-lab:RDDLDomain", "export_mode": "observed-bounded-rollout"},
    )
    observation = domain.reset()
    previous_id = _state(builder, observation, step=0, initial=True)
    steps, terminated = 0, False
    for step, action in enumerate(actions, start=1):
        if step > limits.max_steps:
            break
        action_id = builder.node(
            f"action_{digest({'step': step, 'action': canonical(action)})[:20]}",
            "action",
            str(action),
            {
                "start": step - 1,
                "duration": 1,
                "step": step,
                "ground": canonical(action),
            },
        )
        builder.edge(previous_id, action_id, "precondition", "selected-policy-action")
        outcome = domain.step(action)
        next_id = _state(builder, getattr(outcome, "observation"), step=step)
        attrs = _value_attrs(getattr(outcome, "value", None))
        builder.edge(action_id, next_id, "effect", "observed-outcome", attrs)
        builder.edge(previous_id, next_id, "transition", str(action), attrs)
        previous_id, steps = next_id, step
        terminated = bool(getattr(outcome, "termination", False))
        if terminated:
            break
    builder.metadata.update(
        {
            "steps": steps,
            "terminated": terminated,
            "truncated": steps >= limits.max_steps and not terminated,
            "limits": limits.as_dict(),
        }
    )
    return builder.finish()


def _state(
    builder: Builder, observation: Any, *, step: int, initial: bool = False
) -> str:
    node_id = (
        f"state_{digest({'step': step, 'observation': canonical(observation)})[:20]}"
    )
    attrs: dict[str, Any] = {"time": step, "step": step}
    if initial:
        attrs["initial"] = True
    return builder.node(node_id, "state", short_label(observation), attrs)


def _value_attrs(value: Any) -> dict[str, Any]:
    attrs: dict[str, Any] = {}
    for name in ("reward", "cost"):
        candidate = getattr(value, name, None)
        if (
            isinstance(candidate, (int, float))
            and not isinstance(candidate, bool)
            and math.isfinite(float(candidate))
        ):
            attrs[name] = float(candidate)
    return attrs
