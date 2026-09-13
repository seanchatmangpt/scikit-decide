"""DfCM feasibility, diversity, Pareto preservation, and full experiment matrix."""

from __future__ import annotations

from statistics import fmean
from typing import Sequence

from .engine import run_episode
from .model import (
    ExperimentResult,
    Fortune5Config,
    PolicyAggregate,
    PolicyVector,
    Scenario,
    stable_digest,
)
from .space import SCENARIOS, all_policies
from .topology import build_topology


def _is_feasible(item: PolicyAggregate) -> bool:
    return (
        item.worst_reliability >= 0.54
        and item.worst_compliance_risk <= 0.40
        and item.mean_predictability >= 0.52
        and item.mean_budget_variance <= 0.24
        and item.worst_employee_load <= 1.55
    )


def _dominates(left: PolicyAggregate, right: PolicyAggregate) -> bool:
    left_values = (
        left.mean_throughput,
        left.mean_business_value,
        left.mean_predictability,
        left.worst_reliability,
        -left.worst_compliance_risk,
        -left.mean_lead_time_days,
        -left.mean_coordination_overhead,
        -left.mean_budget_variance,
    )
    right_values = (
        right.mean_throughput,
        right.mean_business_value,
        right.mean_predictability,
        right.worst_reliability,
        -right.worst_compliance_risk,
        -right.mean_lead_time_days,
        -right.mean_coordination_overhead,
        -right.mean_budget_variance,
    )
    return all(a >= b for a, b in zip(left_values, right_values)) and any(
        a > b for a, b in zip(left_values, right_values)
    )


def _pareto_frontier(feasible: Sequence[PolicyAggregate]) -> tuple[str, ...]:
    return tuple(
        sorted(
            candidate.policy.id
            for candidate in feasible
            if not any(
                other.policy.id != candidate.policy.id and _dominates(other, candidate)
                for other in feasible
            )
        )
    )


def _hamming(left: PolicyVector, right: PolicyVector) -> float:
    a = (
        left.priority,
        left.funding,
        left.capacity,
        left.cadence,
        left.architecture,
        left.risk,
    )
    b = (
        right.priority,
        right.funding,
        right.capacity,
        right.cadence,
        right.architecture,
        right.risk,
    )
    return sum(x != y for x, y in zip(a, b)) / len(a)


def _diversity(policies: Sequence[PolicyVector]) -> float:
    if len(policies) < 2:
        return 0.0
    return fmean(
        _hamming(left, right)
        for index, left in enumerate(policies)
        for right in policies[index + 1 :]
    )


def run_full_matrix(
    config: Fortune5Config = Fortune5Config(),
    policies: Sequence[PolicyVector] | None = None,
    scenarios: Sequence[Scenario] = SCENARIOS,
) -> ExperimentResult:
    """Evaluate the lawful policy × disruption product without selecting a winner."""
    topology = build_topology(config)
    policy_space = tuple(policies or all_policies())
    if not policy_space:
        raise ValueError("policy space must be non-empty")
    if not scenarios:
        raise ValueError("scenario space must be non-empty")

    aggregates: list[PolicyAggregate] = []
    episode_receipts: list[str] = []
    for policy in policy_space:
        results = tuple(
            run_episode(policy, scenario, config, topology) for scenario in scenarios
        )
        provisional = PolicyAggregate(
            policy,
            False,
            len(results),
            fmean(r.metrics.throughput for r in results),
            fmean(r.metrics.business_value for r in results),
            fmean(r.metrics.predictability for r in results),
            min(r.metrics.reliability for r in results),
            max(r.metrics.compliance_risk for r in results),
            fmean(r.metrics.lead_time_days for r in results),
            fmean(r.metrics.coordination_overhead for r in results),
            fmean(r.metrics.budget_variance for r in results),
            max(r.metrics.employee_load for r in results),
        )
        aggregates.append(
            PolicyAggregate(
                provisional.policy,
                _is_feasible(provisional),
                provisional.scenario_count,
                provisional.mean_throughput,
                provisional.mean_business_value,
                provisional.mean_predictability,
                provisional.worst_reliability,
                provisional.worst_compliance_risk,
                provisional.mean_lead_time_days,
                provisional.mean_coordination_overhead,
                provisional.mean_budget_variance,
                provisional.worst_employee_load,
            )
        )
        episode_receipts.extend(result.receipt.replay_digest for result in results)

    feasible = tuple(item for item in aggregates if item.feasible)
    feasible_policies = tuple(item.policy for item in feasible)
    frontier = _pareto_frontier(feasible)
    matrix_digest = stable_digest(
        {
            "topology": topology.digest,
            "policy_ids": [policy.id for policy in policy_space],
            "scenario_names": [scenario.name.value for scenario in scenarios],
            "episode_receipts": episode_receipts,
            "frontier": frontier,
        }
    )
    return ExperimentResult(
        len(policy_space),
        len(scenarios),
        len(policy_space) * len(scenarios),
        tuple(sorted(policy.id for policy in feasible_policies)),
        frontier,
        _diversity(feasible_policies),
        matrix_digest,
        tuple(aggregates),
    )
