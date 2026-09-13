from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable, Sequence

from .factory import FactorySnapshot, SOTAFactory
from .models import ExperimentPlan, TrialResult


@dataclass(frozen=True, slots=True)
class PortfolioSnapshot:
    factories: tuple[FactorySnapshot, ...]

    @property
    def target_count(self) -> int:
        return len(self.factories)

    @property
    def done_count(self) -> int:
        return sum(snapshot.terminal for snapshot in self.factories)

    @property
    def terminal(self) -> bool:
        return bool(self.factories) and self.done_count == self.target_count

    def to_dict(self) -> dict[str, object]:
        return {
            "terminal": self.terminal,
            "target_count": self.target_count,
            "done_count": self.done_count,
            "factories": [snapshot.to_dict() for snapshot in self.factories],
        }


class SOTAPortfolio:
    """Fair SELECT/LEARN scheduler across independent benchmark targets.

    Benchmark is an outer experimental dimension, not a software fork. Each
    target retains its own score law and Definition-of-Done court while this
    object multiplexes bounded next-batch selection across them.
    """

    def __init__(self, factories: Sequence[SOTAFactory]):
        if not factories:
            raise ValueError("SOTAPortfolio requires at least one factory")
        by_key = {}
        for factory in factories:
            key = (factory.target.benchmark_id, factory.target.revision)
            if key in by_key:
                raise ValueError(f"duplicate benchmark target in portfolio: {key!r}")
            by_key[key] = factory
        self._factories = by_key

    @property
    def factories(self) -> tuple[SOTAFactory, ...]:
        return tuple(self._factories[key] for key in sorted(self._factories))

    @property
    def terminal(self) -> bool:
        return all(factory.terminal for factory in self.factories)

    def snapshot(self) -> PortfolioSnapshot:
        return PortfolioSnapshot(
            tuple(factory.snapshot() for factory in self.factories)
        )

    def ingest(self, results: Iterable[TrialResult]) -> None:
        grouped: dict[tuple[str, str], list[TrialResult]] = defaultdict(list)
        for result in results:
            key = (result.benchmark_id, result.benchmark_revision)
            if key not in self._factories:
                raise ValueError(f"REFUSED:UNKNOWN_BENCHMARK_TARGET:{key!r}")
            grouped[key].append(result)
        for key, items in grouped.items():
            self._factories[key].ingest(items)

    def next_batch(self, batch_size: int) -> tuple[ExperimentPlan, ...]:
        if batch_size <= 0:
            raise ValueError("batch_size must be > 0")
        if self.terminal:
            return ()

        queues = {
            (factory.target.benchmark_id, factory.target.revision): list(
                factory.next_batch(batch_size)
            )
            for factory in self.factories
            if not factory.terminal
        }
        selected: list[ExperimentPlan] = []
        while len(selected) < batch_size:
            progressed = False
            for key in sorted(queues):
                if queues[key]:
                    selected.append(queues[key].pop(0))
                    progressed = True
                    if len(selected) >= batch_size:
                        break
            if not progressed:
                break
        return tuple(selected)
