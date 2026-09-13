from __future__ import annotations

import hashlib
import json

import pytest

from autofde_lab.sota_factory.autopilot import AutopilotPolicy, SOTAAutopilot
from autofde_lab.sota_factory.execution import (
    ExecutionProfileRefused,
    ExperimentExecutionPort,
    GgenExecutionProfileBundleResolver,
    GymActExecutionProfile,
)
from autofde_lab.sota_factory.factory import SOTAFactory
from autofde_lab.sota_factory.models import (
    BasisChoice,
    BenchmarkTarget,
    BudgetPolicy,
    ExperimentPlan,
    FailureKind,
    TrialOutcome,
    TrialResult,
)
from autofde_lab.sota_factory.space import DecisionSpace


def _space() -> DecisionSpace:
    one = (BasisChoice("one"),)
    return DecisionSpace(
        models=one,
        planners=one,
        tool_policies=one,
        repair_policies=one,
        replanning_policies=one,
        verification_policies=one,
        projection_policies=one,
        memory_policies=one,
        budgets=(BudgetPolicy("one"),),
    )


def _factory() -> SOTAFactory:
    target = BenchmarkTarget(
        benchmark_id="urn:test:benchmark",
        revision="sha256:benchmark",
        published_sota=66.0,
        primary_metric="success-rate",
        task_ids=("t1", "t2", "t3"),
        expected_task_count=3,
        evaluator_ref="urn:test:evaluator",
        frontier_source_ref="urn:test:frontier",
    )
    return SOTAFactory(target=target, decision_space=_space())


def _ggen_bundle(
    plan: ExperimentPlan,
    *,
    revision: str | None = None,
    config_json: str | None = None,
) -> bytes:
    document = {
        "schema": "urn:autofde:execution-profile:v1",
        "generated_by": "ggen:autofde-execution-profile-pack",
        "authority_mode": "external-only",
        "profiles": [
            {
                "profile_id": plan.plan_id,
                "source_ref": "urn:test:benchmark-source",
                "derived_from": f"urn:test:experiment:{plan.plan_id}",
                "provider": "memory",
                "benchmark_revision": revision or plan.benchmark_revision,
                "scenario": None,
                "config_json": config_json
                if config_json is not None
                else json.dumps({"initial": {"counter": 0}}, sort_keys=True),
                "capability_ref": None,
                "capability_binding": "increment",
                "payload_json": json.dumps(
                    {"key": "counter", "amount": 1}, sort_keys=True
                ),
                "expected_json": json.dumps({"counter": 1}, sort_keys=True),
                "input_schema_json": json.dumps({"type": "object"}, sort_keys=True),
                "authority_ref": "urn:test:authority",
                "action_ref": "urn:test:action:increment",
            }
        ],
    }
    return json.dumps(document, sort_keys=True).encode("utf-8")


class PassingExecutionPort:
    """Real deterministic implementation of the execution-port contract."""

    async def execute(self, plan: ExperimentPlan) -> TrialResult:
        return TrialResult(
            plan_id=plan.plan_id,
            benchmark_id=plan.benchmark_id,
            benchmark_revision=plan.benchmark_revision,
            task_id=plan.task_id,
            architecture_digest=plan.architecture_digest,
            outcome=TrialOutcome.PASS,
            primary_score=1.0,
            evidence_refs=(f"urn:test:receipt:{plan.plan_id}",),
        )


class BlockingExecutionPort:
    async def execute(self, plan: ExperimentPlan) -> TrialResult:
        return TrialResult(
            plan_id=plan.plan_id,
            benchmark_id=plan.benchmark_id,
            benchmark_revision=plan.benchmark_revision,
            task_id=plan.task_id,
            architecture_digest=plan.architecture_digest,
            outcome=TrialOutcome.BLOCKED,
            primary_score=0.0,
            failure_kind=FailureKind.DEPENDENCY,
            blocker="BLOCKED:DEPENDENCY_UNAVAILABLE",
            evidence_refs=(f"urn:test:blocker:{plan.plan_id}",),
        )


def test_execution_port_protocol_is_structural() -> None:
    assert isinstance(PassingExecutionPort(), ExperimentExecutionPort)


def test_execution_profile_cannot_encode_vacuous_verification() -> None:
    with pytest.raises(ValueError, match="non-empty verification oracle"):
        GymActExecutionProfile(provider="memory", capability_binding="increment")


def test_ggen_bundle_resolver_binds_exact_plan_revision_and_digest() -> None:
    plan = _factory().plans[0]
    raw = _ggen_bundle(plan)
    expected = hashlib.sha256(raw).hexdigest()
    resolver = GgenExecutionProfileBundleResolver(raw, expected_sha256=expected)

    profile = resolver.resolve(plan)

    assert resolver.sha256 == expected
    assert profile.provider == "memory"
    assert profile.subject_revision == plan.benchmark_revision
    assert profile.config == {"initial": {"counter": 0}}
    assert profile.capability_binding == "increment"
    assert profile.expected == {"counter": 1}


def test_ggen_bundle_resolver_refuses_digest_revision_or_inner_json_drift() -> None:
    plan = _factory().plans[0]
    raw = _ggen_bundle(plan)
    with pytest.raises(ExecutionProfileRefused, match="BUNDLE_DIGEST_DRIFT"):
        GgenExecutionProfileBundleResolver(raw, expected_sha256="0" * 64)

    drifted = _ggen_bundle(plan, revision="sha256:wrong-benchmark")
    resolver = GgenExecutionProfileBundleResolver(
        drifted, expected_sha256=hashlib.sha256(drifted).hexdigest()
    )
    with pytest.raises(ExecutionProfileRefused, match="REVISION_DRIFT"):
        resolver.resolve(plan)

    malformed = _ggen_bundle(plan, config_json="{not-json}")
    resolver = GgenExecutionProfileBundleResolver(
        malformed, expected_sha256=hashlib.sha256(malformed).hexdigest()
    )
    with pytest.raises(ExecutionProfileRefused, match="JSON_INVALID:config_json"):
        resolver.resolve(plan)


@pytest.mark.asyncio
async def test_autopilot_reaches_evidence_bound_definition_of_done() -> None:
    factory = _factory()
    run = await SOTAAutopilot(
        factory,
        PassingExecutionPort(),
        policy=AutopilotPolicy(batch_size=3, max_rounds=2, max_trials=3),
    ).run()

    assert run.terminal is True
    assert run.stop_reason == "DEFINITION_OF_DONE"
    assert len(run.results) == 3
    assert all(result.evidence_refs for result in run.results)
    assert factory.definition_of_done().done is True
    assert factory.scoreboard().champion is not None
    assert factory.scoreboard().champion.score == 100.0


@pytest.mark.asyncio
async def test_autopilot_is_bounded_by_trial_budget() -> None:
    factory = _factory()
    run = await SOTAAutopilot(
        factory,
        PassingExecutionPort(),
        policy=AutopilotPolicy(batch_size=3, max_rounds=4, max_trials=2),
    ).run()

    assert run.terminal is False
    assert run.stop_reason == "MAX_TRIALS_REACHED"
    assert len(run.results) == 2
    assert len(factory.results) == 2


@pytest.mark.asyncio
async def test_blockers_are_ingested_as_learning_signals_not_hidden() -> None:
    factory = _factory()
    run = await SOTAAutopilot(
        factory,
        BlockingExecutionPort(),
        policy=AutopilotPolicy(batch_size=1, max_rounds=1, max_trials=1),
    ).run()

    assert run.terminal is False
    assert run.results[0].outcome is TrialOutcome.BLOCKED
    assert run.results[0].failure_kind is FailureKind.DEPENDENCY
    assert factory.snapshot().learning_signals
