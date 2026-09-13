from __future__ import annotations

import asyncio

import pytest

from autofde_lab.sota_factory.factory import SOTAFactory
from autofde_lab.sota_factory.models import (
    BasisChoice,
    BenchmarkTarget,
    BudgetPolicy,
    ExperimentPlan,
    TrialOutcome,
    TrialResult,
)
from autofde_lab.sota_factory.portfolio import SOTAPortfolio
from autofde_lab.sota_factory.portfolio_autopilot import (
    PortfolioAutopilotPolicy,
    SOTAPortfolioAutopilot,
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


def _factory(name: str) -> SOTAFactory:
    return SOTAFactory(
        target=BenchmarkTarget(
            benchmark_id=f"urn:test:{name}",
            revision=f"sha256:{name}",
            published_sota=49.0,
            primary_metric="success-rate",
            task_ids=(f"{name}-1", f"{name}-2"),
            expected_task_count=2,
            evaluator_ref=f"urn:test:evaluator:{name}",
            frontier_source_ref=f"urn:test:frontier:{name}",
        ),
        decision_space=_space(),
    )


class ConcurrentPassingPort:
    def __init__(self) -> None:
        self.active = 0
        self.max_active = 0

    async def execute(self, plan: ExperimentPlan) -> TrialResult:
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            # Deliberately vary completion order; gather must still return plan order.
            await asyncio.sleep(0.02 if plan.task_id.endswith("-1") else 0.005)
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
        finally:
            self.active -= 1


@pytest.mark.asyncio
async def test_portfolio_autopilot_finishes_all_targets_with_bounded_concurrency() -> (
    None
):
    portfolio = SOTAPortfolio((_factory("alpha"), _factory("beta")))
    port = ConcurrentPassingPort()
    run = await SOTAPortfolioAutopilot(
        portfolio,
        port,
        policy=PortfolioAutopilotPolicy(
            batch_size=4,
            max_rounds=2,
            max_trials=4,
            max_concurrency=2,
        ),
    ).run()

    assert run.terminal is True
    assert run.stop_reason == "DEFINITION_OF_DONE"
    assert run.snapshot.target_count == 2
    assert run.snapshot.done_count == 2
    assert len(run.results) == 4
    assert port.max_active == 2
    assert all(result.evidence_refs for result in run.results)
    assert run.rounds[0].result_ids == run.rounds[0].plan_ids
    assert set(run.rounds[0].benchmark_ids) == {"urn:test:alpha", "urn:test:beta"}


@pytest.mark.asyncio
async def test_portfolio_autopilot_trial_bound_cannot_false_complete_portfolio() -> (
    None
):
    portfolio = SOTAPortfolio((_factory("alpha"), _factory("beta")))
    run = await SOTAPortfolioAutopilot(
        portfolio,
        ConcurrentPassingPort(),
        policy=PortfolioAutopilotPolicy(
            batch_size=4,
            max_rounds=8,
            max_trials=2,
            max_concurrency=2,
        ),
    ).run()

    assert run.terminal is False
    assert run.stop_reason == "MAX_TRIALS_REACHED"
    assert len(run.results) == 2
    assert run.snapshot.done_count < run.snapshot.target_count
