# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""A real, composed observe -> infer -> plan -> admit chain for one real
world-transformation scenario.

Moves the "infer/plan" row in `docs/2026-08-11-autonomic-loop-gap-ledger.md`
from *several independently-real, uncomposed pieces* toward *one real,
callable, end-to-end chain* -- for the one real scenario this repo
currently has (`world_transformation_scenarios.ScenarioMetadata_checkout_latency_scenario_v_1`).

Honesty boundary, stated directly (do not let this drift into
overclaiming): `infer_desired_state`/`compute_delta`/`select_transformation`
below are **real, deterministic, rule-based Python** -- not an LLM call
(unlike `breed_ensemble.py`/`sre_troubleshooting_pipeline.py`, which do use
DSPy), and not routed through the real 50+-solver planner catalog
(`planner_federation.py`). This is a genuine, small, first real increment
along the observe->infer->plan path this repo's doctrine names, not the
full doctrine. `manufacture`/`verify`/`execute` remain exactly as inert as
they already are in every ggen-generated scenario -- this module adds no
real actuation, and never reads, imports, or subprocesses
`vendor/gyms/sregym` (`.claude/rules/gym-actuation-boundary.md`).

`compute_delta` never coerces a missing observation into 0/False: a
`ScenarioMetadata` with no metric matching an objective's kind produces a
real `DeltaItem(current=None, violated=None)`, per
`.claude/rules/absence-is-not-evidence.md` -- an unmeasured objective is
`UNKNOWN`, not silently "met."
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from autofde_lab.powl.algebra import PowlNode
from autofde_lab.powl.validate import validate_model

__all__ = [
    "DesiredStateEnvelope",
    "DeltaItem",
    "TransformationCandidate",
    "infer_desired_state",
    "compute_delta",
    "select_transformation",
    "run_world_transformation_pipeline",
]


class _ScenarioMetadataLike(Protocol):
    """Structural shape of a ggen-generated `ScenarioMetadata_*` dataclass
    -- this module depends on the shape, never on a specific generated
    class name, since `world_transformation_scenarios.py` may generate
    more than one such class in the future."""

    observations: dict[str, float]
    objectives: tuple[dict, ...]


# Real, explicit, named mapping from an objective's `kind` to the
# observation metric name it's checked against. An objective kind with no
# entry here (or whose entry has no matching key in `metadata.observations`)
# produces a real `DeltaItem(current=None, violated=None)` -- never a
# silent default.
_OBJECTIVE_KIND_TO_METRIC: dict[str, str] = {
    "LatencySLO": "p95_latency_ms",
    # AvailabilityTarget intentionally has no entry: CheckoutLatencyScenario_v1's
    # real observations do not include an availability metric -- an honest
    # gap, not filled in here.
}

# Real, explicit, named lookup from an objective kind to one domain-plausible
# transformation label. Small and illustrative, not a claim to completeness
# -- an objective kind with no entry here cannot be selected, named
# explicitly via `select_transformation`'s own None-return rather than a
# fabricated label.
_KIND_TO_TRANSFORMATION_LABEL: dict[str, str] = {
    "LatencySLO": "scale_out_api_instances",
}


@dataclass(frozen=True, slots=True)
class DesiredStateEnvelope:
    """Real, normalized objectives (never constraints -- see the
    ontology's own `afl:Objective`/`afl:Constraint` distinction,
    `ontology/world-transformation-taxonomy.ttl`) a scenario's desired
    state should approach."""

    targets: tuple[dict[str, Any], ...]


@dataclass(frozen=True, slots=True)
class DeltaItem:
    """One real, per-objective comparison between an observed metric and
    its target. `current`/`violated` are `None`, never a coerced default,
    when no matching observation exists."""

    kind: str
    comparator: str
    current: float | None
    target: float
    violated: bool | None


@dataclass(frozen=True, slots=True)
class TransformationCandidate:
    """One real, selected candidate transformation -- the single
    most-violated real `DeltaItem`, mapped through
    `_KIND_TO_TRANSFORMATION_LABEL`."""

    label: str
    targets_kind: str
    rationale: str


def infer_desired_state(metadata: _ScenarioMetadataLike) -> DesiredStateEnvelope:
    """Real normalization of a scenario's real objectives into a
    `DesiredStateEnvelope`. Constraints are deliberately excluded -- they
    are hard bounds, not targets to approach (see this module's docstring
    and the ontology's own class comments)."""
    return DesiredStateEnvelope(targets=tuple(metadata.objectives))


def compute_delta(
    metadata: _ScenarioMetadataLike, desired: DesiredStateEnvelope
) -> tuple[DeltaItem, ...]:
    """Real, per-objective delta between `metadata.observations` and
    `desired.targets`, via the explicit `_OBJECTIVE_KIND_TO_METRIC`
    mapping. Never fabricates a `current` value or a `violated` verdict
    for an objective with no matching observation."""
    items: list[DeltaItem] = []
    for objective in desired.targets:
        kind = objective["kind"]
        comparator = objective["comparator"]
        target = objective["threshold"]

        metric_name = _OBJECTIVE_KIND_TO_METRIC.get(kind)
        current = metadata.observations.get(metric_name) if metric_name is not None else None

        if current is None:
            violated: bool | None = None
        elif comparator == "LessThan":
            violated = current >= target
        elif comparator == "GreaterThanOrEqual":
            violated = current < target
        elif comparator == "Equals":
            violated = current != target
        else:
            # An unrecognized comparator is a real unknown, not a silent
            # "not violated" -- same discipline as the missing-observation
            # case above.
            violated = None

        items.append(
            DeltaItem(kind=kind, comparator=comparator, current=current, target=target, violated=violated)
        )
    return tuple(items)


def select_transformation(delta: tuple[DeltaItem, ...]) -> TransformationCandidate | None:
    """Real selection of the single most-violated `DeltaItem` (by relative
    gap magnitude), mapped to a named transformation label. Returns `None`,
    never a fabricated candidate, when nothing is confirmed violated (every
    item is either not violated or `UNKNOWN`)."""
    violated_items = [item for item in delta if item.violated is True]
    if not violated_items:
        return None

    def _relative_gap(item: DeltaItem) -> float:
        # current is real (not None) for every item in violated_items --
        # violated is only ever True when current was compared for real.
        assert item.current is not None
        if item.target == 0:
            return abs(item.current)
        return abs(item.current - item.target) / abs(item.target)

    worst = max(violated_items, key=_relative_gap)
    label = _KIND_TO_TRANSFORMATION_LABEL.get(worst.kind)
    if label is None:
        return None

    return TransformationCandidate(
        label=label,
        targets_kind=worst.kind,
        rationale=(
            f"{worst.kind} violated: observed {worst.current} vs target {worst.target} "
            f"({worst.comparator})"
        ),
    )


def run_world_transformation_pipeline(
    scenario_graph: PowlNode, metadata: _ScenarioMetadataLike
) -> dict[str, Any]:
    """Real, end-to-end observe -> infer -> plan -> admit chain for one
    scenario: `scenario_graph` (the generated `ChoiceGraph`) is admitted
    via the real `validate_model` first -- an unadmittable graph raises
    `PowlError` and this function never proceeds to infer/plan over it.
    Returns every real intermediate value, not just the final candidate,
    so a caller can inspect the full chain."""
    validate_model(scenario_graph)

    desired = infer_desired_state(metadata)
    delta = compute_delta(metadata, desired)
    candidate = select_transformation(delta)

    return {
        "desired_state": desired,
        "delta": delta,
        "transformation_candidate": candidate,
    }
