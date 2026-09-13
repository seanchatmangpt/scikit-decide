# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for `laboratory` (sections 1-11/26 steps 1-11 of
`docs/2026-08-11-autofde-lab-togaf-autonomic-architecture-plan.md`).

Real collaborators throughout: the real
`world_transformation_orchestrator.infer_desired_state`, the real
`ScenarioMetadata_checkout_latency_scenario_v_1`. The `UnsupportedProcessScienceProvider`/
`UnsupportedWorldExperimentProvider` classes ARE the real objects under
test for their own honesty contract -- calling them and asserting a real
`UNSUPPORTED` result is the correct Chicago-style test for "no external
connector exists yet," not a mock standing in for a connector that would
otherwise exist. No `unittest.mock` / `Mock` / `MagicMock` / `patch` /
`monkeypatch` anywhere in this file.
"""

from __future__ import annotations

from autofde_lab.reasoning.laboratory import (
    ArchitectureCandidate,
    ArchitectureChangeTrigger,
    EnterpriseObservation,
    ExperimentIntent,
    ExperimentReceipt,
    FalsificationStanding,
    OperatorApplicabilityStatus,
    ProcessObservation,
    UnsupportedProcessScienceProvider,
    UnsupportedWorldExperimentProvider,
    admit_surviving_candidates,
    classify_operator_applicability,
    falsify_candidate,
    infer_desired_state_hypotheses,
)
from autofde_lab.reasoning.scenarios.world_transformation_scenarios import (
    ScenarioMetadata_checkout_latency_scenario_v_1,
)


def test_enterprise_observation_digest_is_deterministic_and_reference_only() -> None:
    obs = EnterpriseObservation(
        ontology_graph_ref="ontology:world-transformation-taxonomy",
        source_provenance_ref="scenario:checkout-latency-v1",
        enterprise_world_ref="world:checkout",
        observation_ids=("obs-1", "obs-2"),
    )
    other = EnterpriseObservation(
        ontology_graph_ref="ontology:world-transformation-taxonomy",
        source_provenance_ref="scenario:checkout-latency-v1",
        enterprise_world_ref="world:checkout",
        observation_ids=("obs-1", "obs-2"),
    )
    assert obs.observation_digest == other.observation_digest

    changed = EnterpriseObservation(
        ontology_graph_ref="ontology:world-transformation-taxonomy",
        source_provenance_ref="scenario:checkout-latency-v1",
        enterprise_world_ref="world:checkout",
        observation_ids=("obs-1", "obs-3"),
    )
    assert obs.observation_digest != changed.observation_digest


def test_unsupported_process_science_provider_is_real_and_honest() -> None:
    provider = UnsupportedProcessScienceProvider()
    obs = EnterpriseObservation(ontology_graph_ref="o", source_provenance_ref="s", enterprise_world_ref="w")

    result = provider.request_process_observation(obs)

    assert isinstance(result, ProcessObservation)
    assert result.evidence_standing == "UNSUPPORTED"


def test_infer_desired_state_hypotheses_returns_one_real_rule_based_hypothesis_by_default() -> None:
    metadata = ScenarioMetadata_checkout_latency_scenario_v_1()

    hypotheses = infer_desired_state_hypotheses(metadata)

    assert len(hypotheses) == 1
    assert hypotheses[0].provenance == "rule-based"
    assert set(hypotheses[0].objective_coverage) == {"LatencySLO", "AvailabilityTarget"}


def test_infer_desired_state_hypotheses_adds_a_second_hypothesis_only_when_process_observation_is_real() -> None:
    metadata = ScenarioMetadata_checkout_latency_scenario_v_1()

    unsupported = ProcessObservation(evidence_standing="UNSUPPORTED")
    only_one = infer_desired_state_hypotheses(metadata, process_observation=unsupported)
    assert len(only_one) == 1

    real = ProcessObservation(evidence_standing="ALIVE", performance_metric_refs=("metric-1",))
    two = infer_desired_state_hypotheses(metadata, process_observation=real)
    assert len(two) == 2
    assert two[1].provenance == "process-informed"


def test_classify_operator_applicability_admits_known_shapes_and_unknowns_unmapped_ones() -> None:
    results = classify_operator_applicability(("hard_constraints", "some_novel_shape_no_one_mapped"))

    admitted = next(r for r in results if r.operator_class == "SAT/CDCL")
    assert admitted.status == OperatorApplicabilityStatus.ADMITTED

    unknown = next(r for r in results if r.operator_class == "some_novel_shape_no_one_mapped")
    assert unknown.status == OperatorApplicabilityStatus.UNKNOWN


def test_unsupported_world_experiment_provider_is_real_and_honest() -> None:
    provider = UnsupportedWorldExperimentProvider()
    intent = ExperimentIntent(
        candidate_id="cand-1", target_world_ref="world:checkout", initial_state_evidence_ref="obs-1",
        proposed_actions=("scale_out_api_instances",),
    )

    receipt = provider.submit_experiment(intent)

    assert isinstance(receipt, ExperimentReceipt)
    assert receipt.standing == "UNSUPPORTED"
    assert receipt.intent_id == intent.intent_id


def test_falsify_candidate_is_unknown_with_zero_receipts_never_survives_by_default() -> None:
    candidate = ArchitectureCandidate(candidate_id="cand-1", target_state_assertions=("p95<250ms",))

    result = falsify_candidate(candidate, receipts=())

    assert result.standing == FalsificationStanding.UNKNOWN


def test_falsify_candidate_is_falsified_when_a_real_receipt_reports_a_violation() -> None:
    candidate = ArchitectureCandidate(candidate_id="cand-1", target_state_assertions=("p95<250ms",))
    receipt = ExperimentReceipt(
        intent_id="intent-1",
        observed_outcome_refs=("outcome-1",),
        standing="ALIVE",
        postconditions_violated=("cost_ceiling_exceeded",),
    )

    result = falsify_candidate(candidate, receipts=(receipt,))

    assert result.standing == FalsificationStanding.FALSIFIED
    assert "cost_ceiling_exceeded" in result.violated_constraints


def test_falsify_candidate_survives_only_when_real_receipts_confirm_postconditions_with_no_violations() -> None:
    candidate = ArchitectureCandidate(candidate_id="cand-1", target_state_assertions=("p95<250ms",))
    receipt = ExperimentReceipt(
        intent_id="intent-1",
        observed_outcome_refs=("outcome-1",),
        standing="ALIVE",
        postconditions_observed=("p95_reduced",),
    )

    result = falsify_candidate(candidate, receipts=(receipt,))

    assert result.standing == FalsificationStanding.SURVIVES


def test_admit_surviving_candidates_only_admits_real_survives_standing() -> None:
    from autofde_lab.reasoning.laboratory import FalsificationResult

    results = (
        FalsificationResult(candidate_id="a", standing=FalsificationStanding.SURVIVES),
        FalsificationResult(candidate_id="b", standing=FalsificationStanding.FALSIFIED),
        FalsificationResult(candidate_id="c", standing=FalsificationStanding.UNKNOWN),
        FalsificationResult(candidate_id="d", standing=FalsificationStanding.PARTIAL),
    )

    admitted = admit_surviving_candidates(results)

    assert [r.candidate_id for r in admitted] == ["a"]


def test_architecture_change_trigger_only_fires_above_its_real_confidence_threshold() -> None:
    low = ArchitectureChangeTrigger(
        evidence_refs=("ev-1",), detected_drift="latency regression", affected_requirement_refs=("req-1",),
        confidence=0.2, trigger_policy="threshold-0.5",
    )
    high = ArchitectureChangeTrigger(
        evidence_refs=("ev-1",), detected_drift="latency regression", affected_requirement_refs=("req-1",),
        confidence=0.8, trigger_policy="threshold-0.5",
    )

    assert low.fires is False
    assert high.fires is True
