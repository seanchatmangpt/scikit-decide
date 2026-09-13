from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .models import BenchmarkTarget, TrialResult
from .scoreboard import Scoreboard


@dataclass(frozen=True, slots=True)
class ProofObligation:
    obligation_id: str
    statement: str
    satisfied: bool
    detail: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "obligation_id": self.obligation_id,
            "statement": self.statement,
            "satisfied": self.satisfied,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class DefinitionOfDoneReport:
    obligations: tuple[ProofObligation, ...]

    @property
    def done(self) -> bool:
        return bool(self.obligations) and all(
            item.satisfied for item in self.obligations
        )

    @property
    def missing(self) -> tuple[ProofObligation, ...]:
        return tuple(item for item in self.obligations if not item.satisfied)

    def to_dict(self) -> dict[str, object]:
        return {
            "done": self.done,
            "obligations": [item.to_dict() for item in self.obligations],
        }


class DefinitionOfDone:
    """Evidence court for declaring a benchmark SOTA target complete.

    Score is necessary but not sufficient. The target population, evaluator,
    frontier observation, and per-task evidence must also be bound before the
    factory is allowed to stop as DONE.
    """

    def evaluate(
        self,
        *,
        target: BenchmarkTarget,
        scoreboard: Scoreboard,
        results: Iterable[TrialResult],
    ) -> DefinitionOfDoneReport:
        winner = scoreboard.sota_winners[0] if scoreboard.sota_winners else None
        terminal_results = tuple(results)
        winner_results = (
            tuple(
                result
                for result in terminal_results
                if winner is not None
                and result.benchmark_id == target.benchmark_id
                and result.benchmark_revision == target.revision
                and result.architecture_digest == winner.architecture_digest
            )
            if winner is not None
            else ()
        )
        winner_task_ids = {result.task_id for result in winner_results}
        evidence_bound = (
            winner is not None
            and len(winner_task_ids) == target.expected_task_count
            and all(result.evidence_refs for result in winner_results)
        )

        obligations = (
            ProofObligation(
                "DOD-001",
                "The complete benchmark population is declared.",
                target.population_declared,
                f"declared={len(target.task_ids)} expected={target.expected_task_count}",
            ),
            ProofObligation(
                "DOD-002",
                "The benchmark evaluator identity is bound.",
                bool(target.evaluator_ref.strip()),
                target.evaluator_ref or "missing evaluator_ref",
            ),
            ProofObligation(
                "DOD-003",
                "The published frontier observation is source-bound.",
                bool(target.frontier_source_ref.strip()),
                target.frontier_source_ref or "missing frontier_source_ref",
            ),
            ProofObligation(
                "DOD-004",
                "At least one architecture surpasses the declared frontier.",
                winner is not None,
                winner.architecture_digest if winner is not None else "no SOTA winner",
            ),
            ProofObligation(
                "DOD-005",
                "Every winner task has terminal evidence references.",
                evidence_bound,
                (
                    f"evidence_bound_tasks={len(winner_task_ids)}/"
                    f"{target.expected_task_count}"
                ),
            ),
        )
        return DefinitionOfDoneReport(obligations)
