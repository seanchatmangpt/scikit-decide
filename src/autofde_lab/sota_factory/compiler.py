from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .models import (
    ArchitecturePoint,
    BenchmarkTarget,
    DecisionBasis,
    ExperimentBasis,
    ExperimentPlan,
    SelectionStrategy,
)
from .space import DecisionSpace, one_factor_at_a_time, pairwise_covering


@dataclass(frozen=True, slots=True)
class CompiledExperimentSet:
    target: BenchmarkTarget
    strategy: SelectionStrategy
    decisions: tuple[DecisionBasis, ...]
    experiment_bases: tuple[ExperimentBasis, ...]
    plans: tuple[ExperimentPlan, ...]

    @property
    def architecture_count(self) -> int:
        return len({plan.architecture_digest for plan in self.plans})

    @property
    def task_count(self) -> int:
        return len({plan.task_id for plan in self.plans})


class ExperimentCompiler:
    """SELECT-only compiler from basis space to deterministic experiment plans.

    This class never starts a subprocess, model server, benchmark, Kubernetes
    cluster, GymAct provider, or external evaluator. It manufactures candidate
    experiment identities for an execution layer to consume elsewhere.
    """

    def compile(
        self,
        *,
        target: BenchmarkTarget,
        decision_space: DecisionSpace,
        experiment_bases: Sequence[ExperimentBasis] = (ExperimentBasis(),),
        strategy: SelectionStrategy = SelectionStrategy.PAIRWISE_COVERING,
        baseline: DecisionBasis | None = None,
        candidate_limit: int = 100_000,
        max_architectures: int | None = None,
        task_ids: Sequence[str] | None = None,
    ) -> CompiledExperimentSet:
        if strategy is SelectionStrategy.PAIRWISE_COVERING:
            covering_baseline = baseline or next(
                decision_space.iter_decisions(limit=1), None
            )
            if covering_baseline is None:
                raise ValueError("REFUSED:NO_LAWFUL_DECISION_BASIS")
            selected = decision_space.combinatorial_pairwise_covering(
                baseline=covering_baseline,
                candidate_limit=candidate_limit,
                max_architectures=max_architectures,
            )
        else:
            lawful = decision_space.materialize(candidate_limit=candidate_limit)
            selected = self._select(
                lawful,
                strategy=strategy,
                baseline=baseline,
                max_architectures=max_architectures,
            )

        experiments = tuple(experiment_bases)
        if not experiments:
            raise ValueError("experiment_bases must be non-empty")

        tasks = tuple(task_ids if task_ids is not None else target.task_ids)
        if not tasks:
            raise ValueError(
                "REFUSED:BENCHMARK_TASK_POPULATION_EMPTY; load at least one task before compiling"
            )
        unknown = set(tasks) - set(target.task_ids)
        if unknown:
            raise ValueError(
                f"task_ids are not declared by BenchmarkTarget: {sorted(unknown)!r}"
            )

        purpose = strategy.value.lower()
        plans = tuple(
            ExperimentPlan(
                benchmark_id=target.benchmark_id,
                benchmark_revision=target.revision,
                task_id=task_id,
                architecture=ArchitecturePoint(
                    decision=decision, experiment=experiment
                ),
                purpose=purpose,
            )
            for decision in selected
            for experiment in experiments
            for task_id in tasks
        )
        return CompiledExperimentSet(
            target=target,
            strategy=strategy,
            decisions=selected,
            experiment_bases=experiments,
            plans=plans,
        )

    @staticmethod
    def _select(
        lawful: Sequence[DecisionBasis],
        *,
        strategy: SelectionStrategy,
        baseline: DecisionBasis | None,
        max_architectures: int | None,
    ) -> tuple[DecisionBasis, ...]:
        if strategy is SelectionStrategy.FULL_FACTORIAL:
            selected = tuple(lawful)
        elif strategy is SelectionStrategy.BASELINE_FIRST:
            if baseline is None:
                raise ValueError("BASELINE_FIRST requires baseline")
            selected = tuple(item for item in lawful if item.digest == baseline.digest)
            if not selected:
                raise ValueError("baseline does not exist in the lawful DecisionSpace")
        elif strategy is SelectionStrategy.ONE_FACTOR_AT_A_TIME:
            if baseline is None:
                raise ValueError("ONE_FACTOR_AT_A_TIME requires baseline")
            selected = one_factor_at_a_time(lawful, baseline)
        elif strategy is SelectionStrategy.PAIRWISE_COVERING:
            selected = pairwise_covering(lawful, max_architectures=max_architectures)
        else:
            raise ValueError(f"unknown strategy: {strategy}")

        if (
            max_architectures is not None
            and strategy is not SelectionStrategy.PAIRWISE_COVERING
        ):
            if max_architectures <= 0:
                raise ValueError("max_architectures must be > 0")
            selected = selected[:max_architectures]
        return tuple(selected)
