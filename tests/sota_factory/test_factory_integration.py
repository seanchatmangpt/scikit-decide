import pytest

from autofde_lab.sota_factory import (
    BasisChoice,
    BenchmarkTarget,
    BudgetPolicy,
    DecisionSpace,
    FailureKind,
    FrontierStanding,
    SelectionStrategy,
    SOTAFactory,
    TrialOutcome,
    TrialResult,
)


def _space() -> DecisionSpace:
    one = (BasisChoice("current"),)
    return DecisionSpace(
        models=(BasisChoice("m1"), BasisChoice("m2")),
        planners=one,
        tool_policies=one,
        repair_policies=one,
        replanning_policies=one,
        verification_policies=(BasisChoice("oracle"),),
        projection_policies=(BasisChoice("gymact"),),
        memory_policies=one,
        budgets=(BudgetPolicy("budget"),),
    )


def _target(frontier: float = 50.0) -> BenchmarkTarget:
    return BenchmarkTarget(
        benchmark_id="real-shape",
        revision="r1",
        published_sota=frontier,
        primary_metric="e2e_success_percent",
        task_ids=("t1", "t2", "t3", "t4"),
        expected_task_count=4,
        evaluator_ref="official-evaluator:r1",
        frontier_source_ref="published-frontier:r1",
    )


def _result(
    plan,
    outcome: TrialOutcome,
    kind: FailureKind = FailureKind.NONE,
    blocker: str = "",
    *,
    evidence: bool = True,
):
    return TrialResult(
        plan_id=plan.plan_id,
        benchmark_id=plan.benchmark_id,
        benchmark_revision=plan.benchmark_revision,
        task_id=plan.task_id,
        architecture_digest=plan.architecture_digest,
        outcome=outcome,
        failure_kind=kind,
        blocker=blocker,
        evidence_refs=(f"receipt:{plan.plan_id}",) if evidence else (),
    )


def test_factory_reaches_terminal_only_from_own_complete_score_above_frontier() -> None:
    factory = SOTAFactory(
        target=_target(),
        decision_space=_space(),
        strategy=SelectionStrategy.FULL_FACTORIAL,
    )
    by_arch = {}
    for plan in factory.plans:
        by_arch.setdefault(plan.architecture_digest, []).append(plan)
    winner_plans = next(iter(by_arch.values()))
    factory.ingest(_result(plan, TrialOutcome.PASS) for plan in winner_plans)

    winner = factory.scoreboard().champion
    assert winner is not None
    assert winner.standing is FrontierStanding.SOTA_SURPASSED
    assert winner.score == 100.0
    assert factory.terminal
    assert factory.definition_of_done().done
    assert factory.next_batch(4) == ()


def test_score_above_frontier_without_receipts_is_not_definition_of_done() -> None:
    factory = SOTAFactory(
        target=_target(),
        decision_space=_space(),
        strategy=SelectionStrategy.BASELINE_FIRST,
        baseline=next(_space().iter_decisions(limit=1)),
    )
    factory.ingest(
        _result(plan, TrialOutcome.PASS, evidence=False) for plan in factory.plans
    )

    assert factory.scoreboard().champion.standing is FrontierStanding.SOTA_SURPASSED
    assert not factory.terminal
    missing = {item.obligation_id for item in factory.definition_of_done().missing}
    assert missing == {"DOD-005"}


def test_identity_drift_is_refused() -> None:
    factory = SOTAFactory(
        target=_target(),
        decision_space=_space(),
        strategy=SelectionStrategy.FULL_FACTORIAL,
    )
    plan = factory.plans[0]
    bad = TrialResult(
        plan_id=plan.plan_id,
        benchmark_id=plan.benchmark_id,
        benchmark_revision=plan.benchmark_revision,
        task_id=plan.task_id,
        architecture_digest="architecture:wrong",
        outcome=TrialOutcome.FAIL,
        failure_kind=FailureKind.MODEL,
    )
    with pytest.raises(ValueError, match="ARCHITECTURE_IDENTITY_DRIFT"):
        factory.ingest([bad])


def test_next_batch_prunes_architecture_that_cannot_mathematically_beat_frontier() -> (
    None
):
    factory = SOTAFactory(
        target=_target(frontier=75.0),
        decision_space=_space(),
        strategy=SelectionStrategy.FULL_FACTORIAL,
    )
    by_arch = {}
    for plan in factory.plans:
        by_arch.setdefault(plan.architecture_digest, []).append(plan)
    arch_a, arch_b = list(by_arch.values())

    factory.ingest(
        _result(plan, TrialOutcome.FAIL, FailureKind.MODEL, "MODEL_NO_VALID_ACTION")
        for plan in arch_a[:2]
    )
    factory.ingest([_result(arch_b[0], TrialOutcome.PASS)])

    batch = factory.next_batch(20)
    assert batch
    assert all(
        plan.architecture_digest == arch_b[0].architecture_digest for plan in batch
    )
    signals = factory.snapshot().learning_signals
    assert signals[0].action == "VARY_DECISION_DIMENSION:model"
