from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .models import (
    BenchmarkScore,
    BenchmarkTarget,
    FrontierStanding,
    OptimizationDirection,
    TrialResult,
    unique_results_by_task,
)


@dataclass(frozen=True, slots=True)
class ScoreLaw:
    """Primary benchmark-score law.

    The SOTA factory treats the published frontier as a target constant. It
    does not reproduce competitor runs. It *does* require the Lab's own score
    to be computed over the declared benchmark population before granting
    SOTA_SURPASSED standing.
    """

    def score(
        self,
        target: BenchmarkTarget,
        architecture_digest: str,
        results: Iterable[TrialResult],
    ) -> BenchmarkScore:
        selected = tuple(
            result
            for result in results
            if result.benchmark_id == target.benchmark_id
            and result.benchmark_revision == target.revision
            and result.architecture_digest == architecture_digest
        )
        by_task = unique_results_by_task(selected)

        declared_tasks = set(target.task_ids)
        undeclared = set(by_task) - declared_tasks
        if undeclared:
            raise ValueError(
                "results contain task IDs not declared by the benchmark target: "
                f"{sorted(undeclared)!r}"
            )

        attempted = len(by_task)
        passed = sum(result.passed for result in by_task.values())
        expected = target.expected_task_count
        coverage = attempted / expected
        score = target.score_scale * passed / expected
        optimistic = target.score_scale * (passed + (expected - attempted)) / expected

        population_complete = target.population_declared and attempted == expected
        if not population_complete:
            standing = FrontierStanding.INCOMPLETE_EVALUATION
        else:
            standing = self.compare(target, score)

        if target.direction is OptimizationDirection.MAXIMIZE:
            margin = score - target.published_sota
        else:
            margin = target.published_sota - score

        return BenchmarkScore(
            benchmark_id=target.benchmark_id,
            benchmark_revision=target.revision,
            architecture_digest=architecture_digest,
            attempted=attempted,
            passed=passed,
            expected=expected,
            score=score,
            optimistic_score=optimistic,
            published_sota=target.published_sota,
            margin=margin,
            coverage=coverage,
            population_declared=target.population_declared,
            standing=standing,
            cost_usd=sum(result.cost_usd for result in by_task.values()),
            latency_s=sum(result.latency_s for result in by_task.values()),
            tokens=sum(result.tokens for result in by_task.values()),
        )

    @staticmethod
    def compare(target: BenchmarkTarget, score: float) -> FrontierStanding:
        if target.direction is OptimizationDirection.MAXIMIZE:
            if score > target.published_sota:
                return FrontierStanding.SOTA_SURPASSED
            if score == target.published_sota:
                return FrontierStanding.FRONTIER_MATCHED
            return FrontierStanding.BELOW_FRONTIER

        if score < target.published_sota:
            return FrontierStanding.SOTA_SURPASSED
        if score == target.published_sota:
            return FrontierStanding.FRONTIER_MATCHED
        return FrontierStanding.BELOW_FRONTIER

    @staticmethod
    def can_still_beat(target: BenchmarkTarget, score: BenchmarkScore) -> bool:
        if score.standing is FrontierStanding.SOTA_SURPASSED:
            return True
        if target.direction is OptimizationDirection.MAXIMIZE:
            return score.optimistic_score > target.published_sota
        return True
