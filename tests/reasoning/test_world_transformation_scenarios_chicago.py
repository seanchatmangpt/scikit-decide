# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for the ggen-generated
`autofde_lab.reasoning.scenarios.world_transformation_scenarios` module.

Real collaborators: the real generated module (import, not a fixture built
by hand), the real `autofde_lab.powl.validate.validate_model` validator,
and the real `autofde_lab.powl.guard_executor.execute` runner. No
`unittest.mock` / `Mock` / `MagicMock` / `patch` / `monkeypatch` anywhere in
this file.
"""

from __future__ import annotations

from autofde_lab.powl.guard_executor import ExecutionContext, execute
from autofde_lab.powl.validate import validate_model
from autofde_lab.reasoning.scenarios.world_transformation_scenarios import (
    ScenarioMetadata_checkout_latency_scenario_v_1,
    scenario_checkout_latency_scenario_v_1,
)


def test_scenario_builder_returns_a_choicegraph_that_passes_validate_model() -> None:
    graph = scenario_checkout_latency_scenario_v_1()
    validate_model(graph)  # raises PowlError on failure -- no exception is the assertion


def test_scenario_has_the_real_seven_node_seven_edge_wider_frame_shape() -> None:
    graph = scenario_checkout_latency_scenario_v_1()
    assert len(graph.children) == 8  # Start, End, + 6 real activity Atoms
    assert len(graph.edges) == 7

    atom_labels = [c.label for c in graph.children if hasattr(c, "label")]
    assert [label.split("_checkout")[0] for label in atom_labels] == [
        "observe",
        "infer_desired_state",
        "compute_delta",
        "select_transformation",
        "manufacture",
        "verify",
    ]


def test_scenario_executes_end_to_end_through_the_real_guard_executor() -> None:
    graph = scenario_checkout_latency_scenario_v_1()
    executed: list[str] = []

    def atom_invoker(atom, ctx) -> None:  # noqa: ANN001 -- matches guard_executor's real signature
        executed.append(atom.label)

    trace = execute(
        graph,
        guard_evaluator=lambda name, args: True,
        atom_invoker=atom_invoker,
        max_choice_transitions=10,
        context=ExecutionContext(),
    )

    assert len(executed) == 6
    assert trace.steps  # a real, non-empty execution trace was produced


def test_scenario_metadata_threads_the_real_user_supplied_numbers() -> None:
    metadata = ScenarioMetadata_checkout_latency_scenario_v_1()

    assert metadata.observations["p95_latency_ms"] == 780.0
    assert metadata.observations["api_instance_count"] == 3.0
    assert metadata.observations["db_publicly_reachable"] == 1.0

    latency_objective = next(o for o in metadata.objectives if o["kind"] == "LatencySLO")
    assert latency_objective["comparator"] == "LessThan"
    assert latency_objective["threshold"] == 250.0
    assert latency_objective["unit"] == "ms"

    cost_constraint = next(c for c in metadata.constraints if c["kind"] == "CostCeiling")
    assert cost_constraint["comparator"] == "LessThan"
    assert cost_constraint["threshold"] == 18000.0
    assert cost_constraint["unit"] == "usd_per_month"

    residency_notes = {c["note"] for c in metadata.constraints if c["kind"] == "DataResidency"}
    assert residency_notes == {"customer data must remain private", "no cross-region requirement"}


def test_scenario_never_touches_actuation_atoms_are_inert() -> None:
    """The manufacture/verify Atoms carry no callable/side-effecting payload
    of their own -- executing the graph only records their labels via the
    caller-supplied atom_invoker, exactly like every other ggen-generated
    scenario in this repo (k8s_fault_universes.py's `remediate` step)."""
    graph = scenario_checkout_latency_scenario_v_1()
    manufacture_atom = next(c for c in graph.children if getattr(c, "label", "").startswith("manufacture_"))
    verify_atom = next(c for c in graph.children if getattr(c, "label", "").startswith("verify_"))

    assert manufacture_atom.consequence == "DO"
    assert verify_atom.consequence == "VERIFY"
    assert not hasattr(manufacture_atom, "side_effect")
