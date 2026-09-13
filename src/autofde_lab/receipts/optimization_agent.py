"""A performance-optimizing agent that decides between candidate plan runs using
real OCEL-derived aggregate metrics (total cost, step count, whether the goal was
reached) computed from a real ``OcelLog`` (see ``ocel_adapter.py``).

This is the deterministic decision core an LLM-driven agent's tool-call would
invoke — e.g. "given these candidate rollouts' OCEL logs, pick the best one and say
why." It is deliberately **not** a live LLM call: an LLM call is nondeterministic and
needs network/credentials, neither of which belongs in a classicist (Chicago-school)
test — those tests need real, repeatable state, not a live network dependency. What
*is* real and testable is the scoring/selection logic an LLM-driven agent would
delegate to as a tool, and that is what this module and its tests exercise: real
OCEL logs in, a real, inspectable, state-based decision out.
"""

from __future__ import annotations

from dataclasses import dataclass

from autofde_lab.standing import Blocked

from .wasm4pm_types import OcelLog


@dataclass(frozen=True)
class OcelPerformanceScore:
    """Real aggregate metrics computed from one candidate's OCEL event stream —
    nothing here is estimated or asserted without walking the actual events."""

    run_id: str
    step_count: int
    total_cost: float
    total_reward: float
    reached_goal: bool


@dataclass(frozen=True)
class OptimizationDecision:
    winner_run_id: str
    scores: tuple[OcelPerformanceScore, ...]
    reason: str


def score_log(run_id: str, log: OcelLog) -> OcelPerformanceScore:
    """Walk a real OCEL log's events and compute real performance aggregates —
    this is the "read the process log" half of what a process-mining-informed
    optimization agent does before it can compare candidates at all."""
    total_cost = 0.0
    total_reward = 0.0
    reached_goal = False
    for event in log.events:
        for attr in event.attributes:
            if attr.name == "cost":
                total_cost += float(attr.value)
            elif attr.name == "reward":
                total_reward += float(attr.value)
            elif attr.name == "termination" and attr.value:
                reached_goal = True
    return OcelPerformanceScore(
        run_id=run_id,
        step_count=len(log.events),
        total_cost=total_cost,
        total_reward=total_reward,
        reached_goal=reached_goal,
    )


class PlanPerformanceAgent:
    """Selects the best of several candidate plan runs by real OCEL-derived cost,
    preferring any run that reached the goal over one that didn't, and the lowest
    total cost among goal-reaching runs. Raises ``Blocked`` (not a bare exception)
    naming the reason when no candidate qualifies — no candidate to optimize over is
    a standing claim, not a Python error."""

    def select_best(self, candidates: dict[str, OcelLog]) -> OptimizationDecision:
        if not candidates:
            raise Blocked("no candidate OCEL logs were supplied to optimize over")

        scores = tuple(
            score_log(run_id, log) for run_id, log in candidates.items()
        )
        goal_reaching = [s for s in scores if s.reached_goal]
        if not goal_reaching:
            raise Blocked(
                "no candidate reached the goal; refusing to optimize over "
                f"non-terminating runs: {[s.run_id for s in scores]}"
            )

        winner = min(goal_reaching, key=lambda s: s.total_cost)
        reason = (
            f"{winner.run_id} reached the goal in {winner.step_count} steps at "
            f"total_cost={winner.total_cost}, the lowest among "
            f"{[s.run_id for s in goal_reaching]}"
        )
        return OptimizationDecision(
            winner_run_id=winner.run_id, scores=scores, reason=reason
        )


__all__ = [
    "OcelPerformanceScore",
    "OptimizationDecision",
    "PlanPerformanceAgent",
    "score_log",
]
