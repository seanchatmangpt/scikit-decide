from __future__ import annotations

from dataclasses import dataclass
from time import monotonic

from .execution import ExperimentExecutionPort
from .factory import FactorySnapshot, SOTAFactory
from .models import TrialResult


@dataclass(frozen=True, slots=True)
class AutopilotPolicy:
    """Explicit bounds for autonomous experiment selection and execution."""

    batch_size: int = 8
    max_rounds: int = 32
    max_trials: int = 256
    max_cost_usd: float | None = None
    max_wall_time_s: float | None = None

    def __post_init__(self) -> None:
        if self.batch_size <= 0 or self.max_rounds <= 0 or self.max_trials <= 0:
            raise ValueError("batch_size, max_rounds and max_trials must be > 0")
        if self.max_cost_usd is not None and self.max_cost_usd < 0:
            raise ValueError("max_cost_usd must be >= 0")
        if self.max_wall_time_s is not None and self.max_wall_time_s < 0:
            raise ValueError("max_wall_time_s must be >= 0")


@dataclass(frozen=True, slots=True)
class AutopilotRound:
    index: int
    plan_ids: tuple[str, ...]
    result_ids: tuple[str, ...]
    terminal_after_round: bool


@dataclass(frozen=True, slots=True)
class AutopilotRun:
    rounds: tuple[AutopilotRound, ...]
    results: tuple[TrialResult, ...]
    snapshot: FactorySnapshot
    stop_reason: str

    @property
    def terminal(self) -> bool:
        return self.snapshot.terminal


class SOTAAutopilot:
    """Bounded SELECT -> external DO -> INGEST -> LEARN loop.

    The factory remains incapable of actuation. This orchestrator can call only the
    injected ExperimentExecutionPort; the GymAct implementation of that port routes DO
    through the autonomic controller and BRCE.
    """

    def __init__(
        self,
        factory: SOTAFactory,
        execution_port: ExperimentExecutionPort,
        *,
        policy: AutopilotPolicy | None = None,
    ) -> None:
        if not isinstance(execution_port, ExperimentExecutionPort):
            raise TypeError("execution_port does not satisfy ExperimentExecutionPort")
        self.factory = factory
        self.execution_port = execution_port
        self.policy = policy or AutopilotPolicy()

    async def run(self) -> AutopilotRun:
        started = monotonic()
        rounds: list[AutopilotRound] = []
        executed: list[TrialResult] = []
        stop_reason = "MAX_ROUNDS_REACHED"

        if self.factory.terminal:
            return AutopilotRun((), (), self.factory.snapshot(), "DEFINITION_OF_DONE")

        for round_index in range(1, self.policy.max_rounds + 1):
            if len(executed) >= self.policy.max_trials:
                stop_reason = "MAX_TRIALS_REACHED"
                break
            if self.policy.max_wall_time_s is not None:
                if monotonic() - started >= self.policy.max_wall_time_s:
                    stop_reason = "MAX_WALL_TIME_REACHED"
                    break
            if self.policy.max_cost_usd is not None:
                cost = sum(result.cost_usd for result in executed)
                if cost >= self.policy.max_cost_usd:
                    stop_reason = "MAX_COST_REACHED"
                    break

            remaining = self.policy.max_trials - len(executed)
            plans = self.factory.next_batch(min(self.policy.batch_size, remaining))
            if not plans:
                stop_reason = "NO_FRONTIER_VIABLE_PLANS"
                break

            round_results: list[TrialResult] = []
            for plan in plans:
                if self.policy.max_wall_time_s is not None:
                    if monotonic() - started >= self.policy.max_wall_time_s:
                        stop_reason = "MAX_WALL_TIME_REACHED"
                        break
                result = await self.execution_port.execute(plan)
                round_results.append(result)
                executed.append(result)
                if self.policy.max_cost_usd is not None:
                    if (
                        sum(item.cost_usd for item in executed)
                        >= self.policy.max_cost_usd
                    ):
                        stop_reason = "MAX_COST_REACHED"
                        break
                if len(executed) >= self.policy.max_trials:
                    stop_reason = "MAX_TRIALS_REACHED"
                    break

            if round_results:
                self.factory.ingest(round_results)
            terminal = self.factory.terminal
            rounds.append(
                AutopilotRound(
                    index=round_index,
                    plan_ids=tuple(
                        plan.plan_id for plan in plans[: len(round_results)]
                    ),
                    result_ids=tuple(result.plan_id for result in round_results),
                    terminal_after_round=terminal,
                )
            )
            if terminal:
                stop_reason = "DEFINITION_OF_DONE"
                break
            if stop_reason != "MAX_ROUNDS_REACHED":
                break

        return AutopilotRun(
            rounds=tuple(rounds),
            results=tuple(executed),
            snapshot=self.factory.snapshot(),
            stop_reason=stop_reason,
        )
