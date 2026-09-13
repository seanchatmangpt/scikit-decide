# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style execution court for the autonomic-life planning case study."""

from autofde_lab.agent.life_autonomic_case_study import (
    LifeObservation,
    admit_life_observations,
    build_candidate_frontier,
    run_case_study,
)


def test_case_study_executes_real_planning_kernel_and_replays() -> None:
    first = run_case_study()
    second = run_case_study()

    assert first.receipt_sha256 == second.receipt_sha256
    assert first.observation_digest == second.observation_digest
    assert first.frontier_keys == second.frontier_keys
    assert len(first.frontier_keys) == 3
    assert len(set(first.frontier_keys)) == 3

    assert first.exact_reuse_disposition == "EXACT_REUSE"
    assert first.repair_disposition == "REPAIR"
    assert first.repair_affected_paths == ("1", "3")
    assert first.continue_disposition == "CONTINUE"
    assert first.fresh_goal_disposition == "FRESH_PLAN"


def test_unknown_observation_is_not_silently_admitted() -> None:
    context = admit_life_observations(
        (
            LifeObservation("observed-fact", "case:observed", True),
            LifeObservation("unknown-fact", "case:unknown", False),
        )
    )

    assert "observed-fact" in context.facts
    assert "unknown-fact" not in context.facts


def test_frontier_is_candidate_only_and_non_actuating() -> None:
    receipt = run_case_study()

    assert receipt.authority == "NONE"
    assert receipt.do_authority is False
    assert receipt.evidence_kind == "PLANNING_EVIDENCE_ONLY"

    for plan in build_candidate_frontier():
        assert plan.required_authority_classes == ()
        assert not hasattr(plan, "execute")
        assert not hasattr(plan, "grant")
        assert not hasattr(plan, "actuate")
