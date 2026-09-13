from __future__ import annotations

import asyncio
from dataclasses import dataclass
from time import monotonic

from .execution import ExperimentExecutionPort
from .models import ExperimentPlan, TrialResult
from .portfolio import PortfolioSnapshot, SOTAPortfolio


@dataclass(frozen=True, slots=True)
class PortfolioAutopilotPolicy:
    """Explicit resource envelope for cross-benchmark autonomous execution."""

    batch_size: int = 32
    max_rounds: int = 64
    max_trials: int = 4096
    max_concurrency: int = 8
    max_cost_usd: float | None = None
    max_wall_time_s: float | None = None

    def __post_init__(self) -> None:
        for name in ("batch_size", "max_rounds", "max_trials", "max_concurrency"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be > 0")
        if self.max_cost_usd is not None and self.max_cost_usd < 0:
            raise ValueError("max_cost_usd must be >= 0")
        if self.max_wall_time_s is not None and self.max_wall_time_s < 0:
            raise ValueError("max_wall_time_s must be >= 0")


@dataclass(frozen=True, slots=True)
class PortfolioAutopilotRound:
    index: int
    plan_ids: tuple[str, ...]
    result_ids: tuple[str, ...]
    benchmark_ids: tuple[str, ...]
    terminal_after_round: bool


@dataclass(frozen=True, slots=True)
class PortfolioAutopilotRun:
    rounds: tuple[PortfolioAutopilotRound, ...]
    results: tuple[TrialResult, ...]
    snapshot: PortfolioSnapshot
    stop_reason: str

    @property
    def terminal(self) -> bool:
        return self.snapshot.terminal


class SOTAPortfolioAutopilot:
    """Fair bounded portfolio SELECT -> external DO -> INGEST -> LEARN loop.

    Benchmark remains an experimental dimension. This class contains no provider,
    authority, planner, agent, or raw actuation port. Consequence is possible only
    through the injected ExperimentExecutionPort, whose GymAct implementation routes
    EXECUTE through the autonomic BRCE boundary.
    """

    def __init__(
        self,
        portfolio: SOTAPortfolio,
        execution_port: ExperimentExecutionPort,
        *,
        policy: PortfolioAutopilotPolicy | None = None,
    ) -> None:
        if not isinstance(execution_port, ExperimentExecutionPort):
            raise TypeError("execution_port does not satisfy ExperimentExecutionPort")
        self.portfolio = portfolio
        self.execution_port = execution_port
        self.policy = policy or PortfolioAutopilotPolicy()

    async def _execute_batch(
        self, plans: tuple[ExperimentPlan, ...]
    ) -> tuple[TrialResult, ...]:
        semaphore = asyncio.Semaphore(self.policy.max_concurrency)

        async def execute(plan: ExperimentPlan) -> TrialResult:
            async with semaphore:
                return await self.execution_port.execute(plan)

        # asyncio.gather preserves input order, so evidence/result identity is stable
        # even when the underlying benchmark worlds complete out of order.
        return tuple(await asyncio.gather(*(execute(plan) for plan in plans)))

    async def run(self) -> PortfolioAutopilotRun:
        started = monotonic()
        rounds: list[PortfolioAutopilotRound] = []
        executed: list[TrialResult] = []
        stop_reason = "MAX_ROUNDS_REACHED"

        if self.portfolio.terminal:
            return PortfolioAutopilotRun(
                (), (), self.portfolio.snapshot(), "DEFINITION_OF_DONE"
            )

        for round_index in range(1, self.policy.max_rounds + 1):
            if len(executed) >= self.policy.max_trials:
                stop_reason = "MAX_TRIALS_REACHED"
                break
            if self.policy.max_wall_time_s is not None:
                if monotonic() - started >= self.policy.max_wall_time_s:
                    stop_reason = "MAX_WALL_TIME_REACHED"
                    break
            if self.policy.max_cost_usd is not None:
                if (
                    sum(result.cost_usd for result in executed)
                    >= self.policy.max_cost_usd
                ):
                    stop_reason = "MAX_COST_REACHED"
                    break

            remaining = self.policy.max_trials - len(executed)
            plans = self.portfolio.next_batch(min(self.policy.batch_size, remaining))
            if not plans:
                stop_reason = "NO_FRONTIER_VIABLE_PLANS"
                break

            results = await self._execute_batch(plans)
            executed.extend(results)
            self.portfolio.ingest(results)
            terminal = self.portfolio.terminal
            rounds.append(
                PortfolioAutopilotRound(
                    index=round_index,
                    plan_ids=tuple(plan.plan_id for plan in plans),
                    result_ids=tuple(result.plan_id for result in results),
                    benchmark_ids=tuple(plan.benchmark_id for plan in plans),
                    terminal_after_round=terminal,
                )
            )
            if terminal:
                stop_reason = "DEFINITION_OF_DONE"
                break
            if len(executed) >= self.policy.max_trials:
                stop_reason = "MAX_TRIALS_REACHED"
                break
            if self.policy.max_cost_usd is not None:
                if (
                    sum(result.cost_usd for result in executed)
                    >= self.policy.max_cost_usd
                ):
                    stop_reason = "MAX_COST_REACHED"
                    break

        return PortfolioAutopilotRun(
            rounds=tuple(rounds),
            results=tuple(executed),
            snapshot=self.portfolio.snapshot(),
            stop_reason=stop_reason,
        )
