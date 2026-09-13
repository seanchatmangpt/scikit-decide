from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from .models import (
    FailureCluster,
    FailureKind,
    RepairLeverage,
    TrialOutcome,
    TrialResult,
)

_FAILURE_DIMENSION = {
    FailureKind.MODEL: "model",
    FailureKind.PLANNER: "planner",
    FailureKind.TOOL_POLICY: "tool_policy",
    FailureKind.REPAIR_POLICY: "repair_policy",
    FailureKind.REPLANNING_POLICY: "replanning_policy",
    FailureKind.PROJECTION: "projection_policy",
    FailureKind.VERIFICATION: "verification_policy",
    FailureKind.ORACLE: "verification_policy",
    FailureKind.BUDGET: "budget",
    FailureKind.WORLD_MODEL: None,
    FailureKind.AUTHORITY: None,
    FailureKind.DEPENDENCY: None,
    FailureKind.EXECUTION: None,
    FailureKind.UNKNOWN: None,
    FailureKind.NONE: None,
}


@dataclass(frozen=True, slots=True)
class FailureRouter:
    """Routes explicit typed failures without pretending to infer hidden causes."""

    def target_dimension(self, failure_kind: FailureKind) -> str | None:
        return _FAILURE_DIMENSION[failure_kind]

    def cluster(self, results: Iterable[TrialResult]) -> tuple[FailureCluster, ...]:
        grouped: dict[tuple[FailureKind, str], list[TrialResult]] = defaultdict(list)
        for result in results:
            if result.outcome is TrialOutcome.PASS:
                continue
            kind = result.failure_kind
            signature = result.blocker.strip() or result.outcome.value
            grouped[(kind, signature)].append(result)

        clusters = []
        for (kind, signature), rows in grouped.items():
            clusters.append(
                FailureCluster(
                    failure_kind=kind,
                    signature=signature,
                    count=len(rows),
                    task_ids=tuple(sorted({row.task_id for row in rows})),
                    architecture_digests=tuple(
                        sorted({row.architecture_digest for row in rows})
                    ),
                    target_dimension=self.target_dimension(kind),
                )
            )
        return tuple(
            sorted(
                clusters,
                key=lambda item: (-item.count, item.failure_kind.value, item.signature),
            )
        )


@dataclass(frozen=True, slots=True)
class LearningSignal:
    cluster: FailureCluster
    action: str


class LearningCompiler:
    """Turns verified result rows into bounded next-step signals.

    It does not manufacture a semantic repair from thin air. If a failure maps
    to a DecisionBasis dimension, it asks the experiment selector to vary that
    dimension. World/authority/dependency/execution defects are routed out of
    DecisionBasis instead of being disguised as agent tuning.
    """

    def __init__(self, router: FailureRouter | None = None):
        self._router = router or FailureRouter()

    def signals(self, results: Iterable[TrialResult]) -> tuple[LearningSignal, ...]:
        signals: list[LearningSignal] = []
        for cluster in self._router.cluster(results):
            if cluster.target_dimension is None:
                action = f"ROUTE_EXTERNAL:{cluster.failure_kind.value}"
            else:
                action = f"VARY_DECISION_DIMENSION:{cluster.target_dimension}"
            signals.append(LearningSignal(cluster=cluster, action=action))
        return tuple(signals)

    @staticmethod
    def leverage(
        before_score: float, after_score: float, repair_count: int = 1
    ) -> RepairLeverage:
        if repair_count <= 0:
            raise ValueError("repair_count must be > 0")
        return RepairLeverage(before_score, after_score, repair_count)
