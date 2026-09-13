# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for `world_transformation_orchestrator`.

Real collaborators: the real generated `world_transformation_scenarios`
module (import, not a hand-built fixture) and the real
`autofde_lab.powl.validate.validate_model` admission gate. No
`unittest.mock` / `Mock` / `MagicMock` / `patch` / `monkeypatch` anywhere in
this file.
"""

from __future__ import annotations

import pytest

from autofde_lab.powl.refusals import PowlError
from autofde_lab.reasoning.scenarios.world_transformation_scenarios import (
    ScenarioMetadata_checkout_latency_scenario_v_1,
    scenario_checkout_latency_scenario_v_1,
)
from autofde_lab.reasoning.world_transformation_orchestrator import (
    DeltaItem,
    compute_delta,
    infer_desired_state,
    run_world_transformation_pipeline,
    select_transformation,
)


def test_infer_desired_state_carries_only_real_objectives_not_constraints() -> None:
    metadata = ScenarioMetadata_checkout_latency_scenario_v_1()
    desired = infer_desired_state(metadata)

    kinds = {t["kind"] for t in desired.targets}
    assert kinds == {"LatencySLO", "AvailabilityTarget"}
    assert "CostCeiling" not in kinds  # a real constraint, never treated as a target


def test_compute_delta_finds_the_real_latency_slo_violation() -> None:
    metadata = ScenarioMetadata_checkout_latency_scenario_v_1()
    desired = infer_desired_state(metadata)
    delta = compute_delta(metadata, desired)

    latency_item = next(d for d in delta if d.kind == "LatencySLO")
    assert latency_item.current == 780.0
    assert latency_item.target == 250.0
    assert latency_item.comparator == "LessThan"
    assert latency_item.violated is True


def test_compute_delta_honestly_reports_unknown_for_an_unobserved_objective() -> None:
    """AvailabilityTarget has no matching real observation in this
    scenario -- must be current=None/violated=None, never coerced to a
    default that would silently read as 'met'."""
    metadata = ScenarioMetadata_checkout_latency_scenario_v_1()
    desired = infer_desired_state(metadata)
    delta = compute_delta(metadata, desired)

    availability_item = next(d for d in delta if d.kind == "AvailabilityTarget")
    assert availability_item.current is None
    assert availability_item.violated is None


def test_select_transformation_picks_the_real_violated_objective() -> None:
    metadata = ScenarioMetadata_checkout_latency_scenario_v_1()
    desired = infer_desired_state(metadata)
    delta = compute_delta(metadata, desired)

    candidate = select_transformation(delta)

    assert candidate is not None
    assert candidate.targets_kind == "LatencySLO"
    assert candidate.label == "scale_out_api_instances"
    assert "780" in candidate.rationale and "250" in candidate.rationale


def test_select_transformation_returns_none_when_nothing_is_confirmed_violated() -> None:
    all_unknown = (DeltaItem(kind="AvailabilityTarget", comparator="GreaterThanOrEqual", current=None, target=99.9, violated=None),)
    assert select_transformation(all_unknown) is None

    all_met = (DeltaItem(kind="LatencySLO", comparator="LessThan", current=100.0, target=250.0, violated=False),)
    assert select_transformation(all_met) is None


def test_run_world_transformation_pipeline_admits_first_then_chains_through_real_values() -> None:
    graph = scenario_checkout_latency_scenario_v_1()
    metadata = ScenarioMetadata_checkout_latency_scenario_v_1()

    result = run_world_transformation_pipeline(graph, metadata)

    assert result["desired_state"].targets
    assert result["delta"]
    assert result["transformation_candidate"].label == "scale_out_api_instances"


def test_run_world_transformation_pipeline_refuses_an_unadmittable_graph_before_inferring() -> None:
    """A structurally invalid graph -- constructible, but with an
    unreachable node -- must be refused by validate_model before
    infer/plan ever runs. Reachability/co-reachability is checked by the
    validator, not at construction time (per ChoiceGraph's own docstring),
    so this is a real test of the admission gate itself, not of
    dataclass __post_init__."""
    from autofde_lab.powl.algebra import Atom, ChoiceGraph, ChoiceGraphEdge, End, NodeId, Start

    orphan = Atom(label="unreachable_orphan", consequence="READ")
    invalid_graph = ChoiceGraph(
        children=(Start(), End(), orphan),
        edges=frozenset([ChoiceGraphEdge(NodeId(0), NodeId(1))]),  # Start->End directly; orphan connects to nothing
        start=0,
        end=1,
    )
    metadata = ScenarioMetadata_checkout_latency_scenario_v_1()

    with pytest.raises(PowlError):
        run_world_transformation_pipeline(invalid_graph, metadata)
