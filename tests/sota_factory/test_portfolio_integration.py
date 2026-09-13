import pytest

from autofde_lab.sota_factory import (
    BasisChoice,
    BenchmarkTarget,
    BudgetPolicy,
    DecisionSpace,
    SelectionStrategy,
    SOTAFactory,
    SOTAPortfolio,
    TrialOutcome,
    TrialResult,
)


def _space() -> DecisionSpace:
    one = (BasisChoice("current"),)
    return DecisionSpace(
        models=one,
        planners=one,
        tool_policies=one,
        repair_policies=one,
        replanning_policies=one,
        verification_policies=(BasisChoice("oracle"),),
        projection_policies=(BasisChoice("gymact"),),
        memory_policies=one,
        budgets=(BudgetPolicy("budget"),),
    )


def _factory(benchmark_id: str) -> SOTAFactory:
    space = _space()
    baseline = next(space.iter_decisions(limit=1))
    return SOTAFactory(
        target=BenchmarkTarget(
            benchmark_id=benchmark_id,
            revision="r1",
            published_sota=50.0,
            primary_metric="e2e_success_percent",
            task_ids=("t1",),
            expected_task_count=1,
            evaluator_ref=f"evaluator:{benchmark_id}:r1",
            frontier_source_ref=f"frontier:{benchmark_id}:r1",
        ),
        decision_space=space,
        strategy=SelectionStrategy.BASELINE_FIRST,
        baseline=baseline,
    )


def _pass(plan) -> TrialResult:
    return TrialResult(
        plan_id=plan.plan_id,
        benchmark_id=plan.benchmark_id,
        benchmark_revision=plan.benchmark_revision,
        task_id=plan.task_id,
        architecture_digest=plan.architecture_digest,
        outcome=TrialOutcome.PASS,
        evidence_refs=(f"receipt:{plan.plan_id}",),
    )


def test_portfolio_round_robins_benchmark_targets_and_finishes_only_when_all_done() -> (
    None
):
    portfolio = SOTAPortfolio((_factory("b2"), _factory("b1")))

    batch = portfolio.next_batch(2)
    assert len(batch) == 2
    assert {plan.benchmark_id for plan in batch} == {"b1", "b2"}
    assert not portfolio.terminal

    portfolio.ingest(_pass(plan) for plan in batch)

    assert portfolio.terminal
    snapshot = portfolio.snapshot()
    assert snapshot.done_count == 2
    assert snapshot.target_count == 2
    assert snapshot.terminal


def test_portfolio_refuses_result_for_unknown_benchmark_target() -> None:
    portfolio = SOTAPortfolio((_factory("b1"),))
    plan = portfolio.factories[0].plans[0]
    unknown = TrialResult(
        plan_id=plan.plan_id,
        benchmark_id="other",
        benchmark_revision=plan.benchmark_revision,
        task_id=plan.task_id,
        architecture_digest=plan.architecture_digest,
        outcome=TrialOutcome.PASS,
        evidence_refs=("receipt:unknown",),
    )
    with pytest.raises(ValueError, match="UNKNOWN_BENCHMARK_TARGET"):
        portfolio.ingest([unknown])
