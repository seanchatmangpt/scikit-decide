from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable, Sequence

from .compiler import CompiledExperimentSet, ExperimentCompiler
from .done import DefinitionOfDone, DefinitionOfDoneReport
from .learning import LearningCompiler, LearningSignal
from .models import (
    BenchmarkScore,
    BenchmarkTarget,
    DecisionBasis,
    ExperimentBasis,
    ExperimentPlan,
    SelectionStrategy,
    TrialResult,
)
from .score import ScoreLaw
from .scoreboard import Scoreboard
from .space import DecisionSpace, hamming_distance


@dataclass(frozen=True, slots=True)
class FactorySnapshot:
    target: BenchmarkTarget
    compiled_plan_count: int
    result_count: int
    scoreboard: Scoreboard
    learning_signals: tuple[LearningSignal, ...]
    definition_of_done: DefinitionOfDoneReport

    @property
    def terminal(self) -> bool:
        return self.definition_of_done.done

    def to_dict(self) -> dict[str, object]:
        return {
            "target": self.target.to_dict(),
            "compiled_plan_count": self.compiled_plan_count,
            "result_count": self.result_count,
            "terminal": self.terminal,
            "definition_of_done": self.definition_of_done.to_dict(),
            "scoreboard": self.scoreboard.to_dict(),
            "learning_signals": [
                {"action": signal.action, "cluster": signal.cluster.to_dict()}
                for signal in self.learning_signals
            ],
        }


class SOTAFactory:
    """SELECT/LEARN control plane for benchmark-score optimization.

    The factory compiles experiment identities, ingests externally produced
    terminal results, derives aggregate benchmark score, prunes architectures
    that mathematically cannot beat the frontier, and selects the next batch.

    It has no DO path. Execution remains behind the benchmark/GymAct/runtime
    boundary. This prevents the optimization controller from silently gaining
    actuation authority.
    """

    def __init__(
        self,
        *,
        target: BenchmarkTarget,
        decision_space: DecisionSpace,
        experiment_bases: Sequence[ExperimentBasis] = (ExperimentBasis(),),
        baseline: DecisionBasis | None = None,
        strategy: SelectionStrategy = SelectionStrategy.PAIRWISE_COVERING,
        candidate_limit: int = 100_000,
        max_architectures: int | None = None,
    ):
        self.target = target
        self.decision_space = decision_space
        self.experiment_bases = tuple(experiment_bases)
        self.baseline = baseline
        self.strategy = strategy
        self._compiler = ExperimentCompiler()
        self._scorer = ScoreLaw()
        self._learning = LearningCompiler()
        self._done = DefinitionOfDone()
        self._compiled = self._compiler.compile(
            target=target,
            decision_space=decision_space,
            experiment_bases=self.experiment_bases,
            strategy=strategy,
            baseline=baseline,
            candidate_limit=candidate_limit,
            max_architectures=max_architectures,
        )
        self._plans = {plan.plan_id: plan for plan in self._compiled.plans}
        self._results: dict[str, TrialResult] = {}

    @property
    def compiled(self) -> CompiledExperimentSet:
        return self._compiled

    @property
    def plans(self) -> tuple[ExperimentPlan, ...]:
        return self._compiled.plans

    @property
    def results(self) -> tuple[TrialResult, ...]:
        return tuple(self._results[key] for key in sorted(self._results))

    def ingest(self, results: Iterable[TrialResult]) -> None:
        for result in results:
            plan = self._plans.get(result.plan_id)
            if plan is None:
                raise ValueError(f"REFUSED:UNKNOWN_EXPERIMENT_PLAN:{result.plan_id}")
            if result.architecture_digest != plan.architecture_digest:
                raise ValueError(
                    f"REFUSED:ARCHITECTURE_IDENTITY_DRIFT:{result.plan_id}"
                )
            if result.task_id != plan.task_id:
                raise ValueError(f"REFUSED:TASK_IDENTITY_DRIFT:{result.plan_id}")
            if (
                result.benchmark_id != self.target.benchmark_id
                or result.benchmark_revision != self.target.revision
            ):
                raise ValueError(f"REFUSED:BENCHMARK_IDENTITY_DRIFT:{result.plan_id}")
            existing = self._results.get(result.plan_id)
            if existing is not None and existing != result:
                raise ValueError(f"REFUSED:RESULT_MUTATION:{result.plan_id}")
            self._results[result.plan_id] = result

    def scores(self) -> tuple[BenchmarkScore, ...]:
        architecture_digests = sorted({plan.architecture_digest for plan in self.plans})
        return tuple(
            self._scorer.score(self.target, digest, self.results)
            for digest in architecture_digests
        )

    def scoreboard(self) -> Scoreboard:
        return Scoreboard.from_scores(self.scores())

    def definition_of_done(self) -> DefinitionOfDoneReport:
        return self._done.evaluate(
            target=self.target,
            scoreboard=self.scoreboard(),
            results=self.results,
        )

    def snapshot(self) -> FactorySnapshot:
        return FactorySnapshot(
            target=self.target,
            compiled_plan_count=len(self.plans),
            result_count=len(self._results),
            scoreboard=self.scoreboard(),
            learning_signals=self._learning.signals(self.results),
            definition_of_done=self.definition_of_done(),
        )

    @property
    def terminal(self) -> bool:
        return self.definition_of_done().done

    def next_batch(self, batch_size: int) -> tuple[ExperimentPlan, ...]:
        if batch_size <= 0:
            raise ValueError("batch_size must be > 0")
        if self.terminal:
            return ()

        done = set(self._results)
        unrun = [plan for plan in self.plans if plan.plan_id not in done]
        if not unrun:
            return ()

        score_by_arch = {score.architecture_digest: score for score in self.scores()}
        viable = {
            digest
            for digest, score in score_by_arch.items()
            if self._scorer.can_still_beat(self.target, score)
        }
        unrun = [plan for plan in unrun if plan.architecture_digest in viable]
        if not unrun:
            return ()

        champion = self.scoreboard().champion
        champion_decision = None
        if champion is not None:
            for plan in self.plans:
                if plan.architecture_digest == champion.architecture_digest:
                    champion_decision = plan.architecture.decision
                    break

        attempted_by_arch: dict[str, int] = defaultdict(int)
        for result in self.results:
            attempted_by_arch[result.architecture_digest] += 1

        def priority(plan: ExperimentPlan) -> tuple[object, ...]:
            score = score_by_arch[plan.architecture_digest]
            distance = (
                hamming_distance(plan.architecture.decision, champion_decision)
                if champion_decision is not None
                else 0
            )
            return (
                -score.passed,
                attempted_by_arch[plan.architecture_digest],
                distance,
                plan.task_id,
                plan.architecture_digest,
            )

        return tuple(sorted(unrun, key=priority)[:batch_size])

    def architecture_for_digest(self, digest: str) -> DecisionBasis | None:
        for plan in self.plans:
            if plan.architecture_digest == digest:
                return plan.architecture.decision
        return None
