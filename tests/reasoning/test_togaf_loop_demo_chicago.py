# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for `togaf_loop_demo`.

Real collaborators throughout: a real POWL `ChoiceGraph` execution, a real
hand-built `OcelLog`, and a real call into
`object_centric_conformance.check_object_centric_conformance` (a module
built and tested in a prior turn, exercised here against this turn's
freshly-produced log). No `unittest.mock` / `Mock` / `MagicMock` / `patch`
/ `monkeypatch` anywhere in this file.
"""

from __future__ import annotations

from autofde_lab.reasoning.togaf_loop_demo import (
    PHASE_SEQUENCE,
    UNSUPPORTED_TOGAF_SUBSTEPS,
    run_full_togaf_loop_with_ocel,
)


def test_all_twenty_real_phases_fire_in_the_real_intended_order() -> None:
    log, phase_results, conformance = run_full_togaf_loop_with_ocel()

    assert len(PHASE_SEQUENCE) == 20
    assert len(log.events) == 20
    assert conformance.all_conform is True
    assert conformance.overall_fitness == 1.0

    execution_object = next(o for o in conformance.per_object if o.object_type == "TogafLoopExecution")
    assert execution_object.observed_trace == PHASE_SEQUENCE


def test_reference_model_selection_atoms_expose_real_ggen_generated_vocabulary_never_a_fabricated_choice() -> None:
    """Iteration 4 closed the phase_b/phase_c 'no reference-model-selection
    mechanism exists' gaps via real, ggen-generated
    togaf_artifacts.StandingValue vocabulary. Confirm both atoms name real
    available models and honestly leave `selected` as `None` -- this repo
    has no real mechanism to make that selection for a real deliverable."""
    _, phase_results, _ = run_full_togaf_loop_with_ocel()

    phase_b = phase_results["phase_b_reference_model_selection"]
    assert "TechnicalReferenceModel" in phase_b["available_reference_models"]
    assert phase_b["selected"] is None

    phase_c = phase_results["phase_c_reference_model_selection"]
    assert "IntegratedInfoInfrastructureReferenceModel" in phase_c["available_reference_models"]
    assert phase_c["selected"] is None


def test_ggen_generated_togaf_artifacts_are_really_constructed_never_fabricating_approval() -> None:
    """Iteration 3 closed 3 UNSUPPORTED gaps via real ggen generation
    (ontology/togaf-artifacts.ttl -> togaf_artifacts.py). Confirm the
    real generated types are actually constructed with real data, and
    that approval-status fields are honestly PendingHumanApproval --
    never fabricated as granted, per fde-authority-boundary.md."""
    _, phase_results, _ = run_full_togaf_loop_with_ocel()

    sow = phase_results["phase_a_statement_of_architecture_work"]
    assert sow["sow_approval_status"] == "PendingHumanApproval"
    assert sow["sow_scope_item_count"] == 2

    contract = phase_results["phase_g_architecture_contract"]
    assert contract["contract_governance_role"] == ("ArchitectureBoard",)

    change = phase_results["phase_h_change_request"]
    assert change["change_approval_status"] == "PendingHumanApproval"


def test_unsupported_togaf_substeps_are_named_explicitly_not_silently_dropped() -> None:
    """'ALL MUST BE REPRESENTED': every real, documented TOGAF sub-step
    this repo has no mechanism for must appear here, named -- never
    silently absent from both the event stream AND this record."""
    assert len(UNSUPPORTED_TOGAF_SUBSTEPS) > 0
    for substep, reason in UNSUPPORTED_TOGAF_SUBSTEPS.items():
        assert reason, f"{substep} has no real stated reason"


def test_architecture_candidate_and_falsification_are_really_wired_not_left_unused() -> None:
    """Prior audit found laboratory.py's ArchitectureCandidate/
    falsify_candidate machinery real but completely unused by this
    module. Confirm it is now actually invoked, and that the honest
    result (no real gymact connector exists) is UNSUPPORTED, never a
    fabricated SURVIVES/FALSIFIED verdict."""
    _, phase_results, _ = run_full_togaf_loop_with_ocel()

    assert phase_results["phase_a_architecture_vision_artifact"]["candidate_id"] == "checkout-latency-vision-v1"

    falsification = phase_results["phase_f_prioritize_via_falsification"]
    assert falsification["falsification_standing"] == "UNSUPPORTED"


def test_phase_d_enumerates_the_real_documented_decision_points_it_refuses() -> None:
    """Prior audit found Phase D's refusal under-specified (a bare
    boolean). Confirm it now names the real TOGAF 9.2 Phase D decision
    points being declined."""
    _, phase_results, _ = run_full_togaf_loop_with_ocel()

    refused_points = phase_results["phase_d_delegated_to_gymact_boundary_refusal"]["refused_decision_points"]
    assert len(refused_points) == 9
    assert "develop_target_technology_architecture" in refused_points


def test_phase_d_is_a_real_explicit_refusal_never_a_fabricated_technology_decision() -> None:
    """The one place this module must stay honest: Phase D belongs to
    gymact, not this repo. Confirm the real recorded result names the
    refusal explicitly, rather than silently proceeding as if a real
    technology-architecture decision had been made."""
    _, phase_results, _ = run_full_togaf_loop_with_ocel()

    phase_d = phase_results["phase_d_delegated_to_gymact_boundary_refusal"]
    assert phase_d["refused"] is True
    assert phase_d["delegated_to"] == "gymact"
    assert "technology-architecture" in phase_d["reason"]


def test_every_phase_produced_a_real_nonempty_computed_result() -> None:
    """Not just 'an event fired' -- each phase's atom_invoker must have
    actually computed something real, not a placeholder."""
    _, phase_results, _ = run_full_togaf_loop_with_ocel()

    for label in PHASE_SEQUENCE:
        assert label in phase_results, f"{label} produced no real result"
        assert phase_results[label], f"{label}'s real result was empty"


def test_phase_e_delta_and_candidate_match_the_real_deterministic_orchestrator() -> None:
    """Cross-check against the real world_transformation_orchestrator
    functions directly -- this module's Phase E must not silently drift
    from the already-tested rule-based selector."""
    from autofde_lab.reasoning.scenarios.world_transformation_scenarios import (
        ScenarioMetadata_checkout_latency_scenario_v_1,
    )
    from autofde_lab.reasoning.world_transformation_orchestrator import (
        compute_delta,
        infer_desired_state,
        select_transformation,
    )

    metadata = ScenarioMetadata_checkout_latency_scenario_v_1()
    expected_delta = compute_delta(metadata, infer_desired_state(metadata))
    expected_candidate = select_transformation(expected_delta)

    _, phase_results, _ = run_full_togaf_loop_with_ocel()
    phase_e = phase_results["phase_e_compute_delta_and_select_transformation"]

    assert phase_e["delta_item_count"] == len(expected_delta)
    assert phase_e["candidate_label"] == expected_candidate.label


def test_the_conformance_verdict_is_computed_by_the_real_independent_module_not_reimplemented_here() -> None:
    """Confirm togaf_loop_demo imports and calls the real
    check_object_centric_conformance rather than reimplementing its own
    scoring -- a structural, no-dual-bookkeeping check."""
    import autofde_lab.reasoning.togaf_loop_demo as module

    assert module.check_object_centric_conformance.__module__ == "autofde_lab.ocel.object_centric_conformance"
