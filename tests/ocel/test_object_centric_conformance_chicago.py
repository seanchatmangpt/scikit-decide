# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for `object_centric_conformance`.

Real collaborators: a real `OcelLog` produced by
`execute_with_ocel`/`OcelExecutionRecorder` against the real
`world_transformation_orchestrator` scenario -- the same chain a prior
turn ran live and inspected. No `unittest.mock` / `Mock` / `MagicMock` /
`patch` / `monkeypatch` anywhere in this file.
"""

from __future__ import annotations

from dataclasses import replace

from autofde_lab.ocel.log import OcelLog
from autofde_lab.ocel.model import EventObjectLink, OcelObject
from autofde_lab.ocel.object_centric_conformance import (
    check_object_centric_conformance,
    flattened_trace,
    project_object_trace,
)
from autofde_lab.powl.ocel_bridge import OcelExecutionRecorder, execute_with_ocel
from autofde_lab.powl.validate import validate_model
from autofde_lab.reasoning.scenarios.world_transformation_scenarios import (
    scenario_checkout_latency_scenario_v_1,
)

_INTENDED_EXECUTION_TRACE = (
    "observe_checkout_latency_scenario_v_1",
    "infer_desired_state_checkout_latency_scenario_v_1",
    "compute_delta_checkout_latency_scenario_v_1",
    "select_transformation_checkout_latency_scenario_v_1",
    "manufacture_checkout_latency_scenario_v_1",
    "verify_checkout_latency_scenario_v_1",
)

_EXECUTION_OBJECT_ID = "checkout-latency-v1-conformance-run"


def _run_real_scenario_to_ocel() -> OcelLog:
    graph = scenario_checkout_latency_scenario_v_1()
    validate_model(graph)

    recorder = OcelExecutionRecorder(execution_id=_EXECUTION_OBJECT_ID)
    execute_with_ocel(
        graph,
        guard_evaluator=lambda name, args: True,
        atom_invoker=lambda atom: None,
        max_choice_transitions=10,
        recorder=recorder,
    )
    return recorder.close()


def test_the_real_untampered_log_conforms_per_object() -> None:
    log = _run_real_scenario_to_ocel()

    per_activity_intended = {
        obj.id: (obj.attributes[0].value.value,)  # each PowlActivity's own single-event trace
        for obj in log.objects
        if obj.object_type == "PowlActivity"
    }
    intended = {_EXECUTION_OBJECT_ID: _INTENDED_EXECUTION_TRACE, **per_activity_intended}

    result = check_object_centric_conformance(log, intended_traces_by_object_id=intended)

    assert result.all_conform is True
    assert result.overall_fitness == 1.0
    execution_fitness = next(o for o in result.per_object if o.object_id == _EXECUTION_OBJECT_ID)
    assert execution_fitness.observed_trace == _INTENDED_EXECUTION_TRACE


def test_an_unknown_object_id_raises_rather_than_silently_scoring_zero() -> None:
    log = _run_real_scenario_to_ocel()

    try:
        check_object_centric_conformance(log, intended_traces_by_object_id={"not-a-real-object": ("x",)})
        raised = False
    except KeyError:
        raised = True

    assert raised is True


def test_a_crossed_object_identity_link_produces_a_real_detectable_gap_and_extra_event() -> None:
    """Falsifiability check: re-link one real event (select_transformation)
    to point at a second, decoy PowlExecution object instead of the real
    one -- the exact 'dangling or crossed' failure mode
    level4_process_fitness.py names. The real execution object's projected
    trace must show a gap; the decoy's trace must show an unexpected
    extra event neither object was intended to have."""
    log = _run_real_scenario_to_ocel()

    def _label(event) -> str:
        return next(str(a.value.value) for a in event.attributes if a.key == "label")

    crossed_event = next(
        e for e in log.events
        if any(
            link.object_id == _EXECUTION_OBJECT_ID
            for link in log.event_object_links
            if link.event_id == e.id
        )
        and _label(e) == "select_transformation_checkout_latency_scenario_v_1"
    )

    decoy_object = OcelObject(id="decoy-execution", object_type="PowlExecution")
    broken_log = log.with_objects(decoy_object)
    new_links = tuple(
        EventObjectLink(link.event_id, "decoy-execution", link.qualifier)
        if link.event_id == crossed_event.id and link.object_id == _EXECUTION_OBJECT_ID
        else link
        for link in broken_log.event_object_links
    )
    broken_log = replace(broken_log, event_object_links=new_links)

    per_activity_intended = {
        obj.id: (obj.attributes[0].value.value,)
        for obj in log.objects
        if obj.object_type == "PowlActivity"
    }
    intended = {
        _EXECUTION_OBJECT_ID: _INTENDED_EXECUTION_TRACE,
        "decoy-execution": (),  # the decoy was never intended to have any events
        **per_activity_intended,
    }

    result = check_object_centric_conformance(broken_log, intended_traces_by_object_id=intended)

    execution_result = next(o for o in result.per_object if o.object_id == _EXECUTION_OBJECT_ID)
    decoy_result = next(o for o in result.per_object if o.object_id == "decoy-execution")

    assert execution_result.conforms is False
    assert "select_transformation_checkout_latency_scenario_v_1" not in execution_result.observed_trace
    assert decoy_result.conforms is False
    assert decoy_result.observed_trace == ("select_transformation_checkout_latency_scenario_v_1",)

    # The concrete demonstration: a flattened, object-blind check over the
    # SAME broken log still reports the full intended sequence present
    # somewhere in the flattened trace -- it cannot see the crossed link.
    flattened = flattened_trace(broken_log)
    assert set(_INTENDED_EXECUTION_TRACE).issubset(set(flattened))
    assert result.all_conform is False


def test_project_object_trace_is_empty_for_an_object_with_no_real_events() -> None:
    log = _run_real_scenario_to_ocel()
    assert project_object_trace(log, "no-such-object-but-not-checked-here") == ()
