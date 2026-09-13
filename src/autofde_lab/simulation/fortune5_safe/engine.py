"""Deterministic planning-interval transition engine and replay receipt."""

from __future__ import annotations

import hashlib
import random
from statistics import fmean
from typing import Mapping

from .model import (
    APS_SOURCE_REPOSITORY,
    APS_SOURCE_SHA,
    AUTOFDE_BASE_SHA,
    AUTOFDE_TARGET_REPOSITORY,
    RECEIPT_SCHEMA,
    ArchitectureRule,
    CadenceRule,
    CapacityRule,
    EnterpriseTopology,
    EpisodeMetrics,
    EpisodeResult,
    Fortune5Config,
    FundingRule,
    PIMetrics,
    PolicyVector,
    PriorityRule,
    RiskRule,
    Scenario,
    SimulationReceipt,
    stable_digest,
)
from .topology import build_topology

PRIORITY_EFFECTS: Mapping[PriorityRule, tuple[float, float, float, float]] = {
    PriorityRule.WSJF: (1.04, 0.98, 0.98, 1.03),
    PriorityRule.COST_OF_DELAY: (1.06, 1.00, 1.02, 1.05),
    PriorityRule.DEPENDENCY_FIRST: (1.01, 0.78, 0.97, 0.99),
    PriorityRule.RISK_FIRST: (0.97, 0.92, 0.72, 0.96),
    PriorityRule.ARCHITECTURE_FIRST: (0.95, 0.88, 0.90, 1.00),
}
FUNDING_EFFECTS: Mapping[FundingRule, tuple[float, float, float]] = {
    FundingRule.FIXED_GUARDRAILS: (1.00, 0.98, 0.78),
    FundingRule.PROPORTIONAL_VALUE: (1.04, 1.01, 0.92),
    FundingRule.DYNAMIC_CAPACITY: (1.06, 1.04, 1.06),
    FundingRule.OPTION_RESERVE: (0.94, 0.93, 0.64),
}
CAPACITY_EFFECTS: Mapping[CapacityRule, tuple[float, float, float, float]] = {
    CapacityRule.BALANCED: (1.00, 1.00, 1.00, 1.00),
    CapacityRule.FLOW_FIRST: (1.08, 0.96, 0.97, 1.05),
    CapacityRule.RELIABILITY_RESERVE: (0.92, 1.12, 0.96, 0.90),
    CapacityRule.INNOVATION_RESERVE: (0.90, 1.02, 1.12, 0.88),
}
CADENCE_EFFECTS: Mapping[CadenceRule, tuple[float, float, float]] = {
    CadenceRule.SYNCHRONIZED: (1.00, 0.94, 1.05),
    CadenceRule.STAGGERED: (1.02, 1.00, 0.94),
    CadenceRule.EVENT_DRIVEN: (1.05, 1.08, 0.86),
}
ARCH_EFFECTS: Mapping[ArchitectureRule, tuple[float, float, float]] = {
    ArchitectureRule.RUNWAY_FIRST: (1.13, 0.90, 0.94),
    ArchitectureRule.JUST_IN_TIME: (0.94, 1.03, 1.04),
    ArchitectureRule.PLATFORM_FIRST: (1.09, 0.94, 1.00),
}
RISK_EFFECTS: Mapping[RiskRule, tuple[float, float, float]] = {
    RiskRule.COMPLIANCE_FIRST: (0.68, 1.08, 0.92),
    RiskRule.BALANCED: (0.88, 1.00, 1.00),
    RiskRule.FAST_FEEDBACK: (1.02, 0.96, 1.04),
}


def _episode_rng(seed: int, policy: PolicyVector, scenario: Scenario) -> random.Random:
    material = f"{seed}|{policy.id}|{scenario.name.value}".encode()
    return random.Random(int.from_bytes(hashlib.sha256(material).digest()[:8], "big"))


def run_episode(
    policy: PolicyVector,
    scenario: Scenario,
    config: Fortune5Config = Fortune5Config(),
    topology: EnterpriseTopology | None = None,
) -> EpisodeResult:
    topology = topology or build_topology(config)
    rng = _episode_rng(config.seed, policy, scenario)
    priority_flow, priority_dependency, priority_risk, priority_value = (
        PRIORITY_EFFECTS[policy.priority]
    )
    funding_capacity, funding_spend, funding_variance = FUNDING_EFFECTS[policy.funding]
    capacity_flow, capacity_reliability, capacity_arch, capacity_load = (
        CAPACITY_EFFECTS[policy.capacity]
    )
    cadence_flow, cadence_coordination, cadence_predictability = CADENCE_EFFECTS[
        policy.cadence
    ]
    arch_runway, arch_dependency, arch_flow = ARCH_EFFECTS[policy.architecture]
    risk_compliance, risk_reliability, risk_flow = RISK_EFFECTS[policy.risk]

    dependency_density = len(topology.dependencies) / max(len(topology.teams), 1)
    coordination_density = topology.counts["cadence_events_per_pi"] / max(
        config.personnel, 1
    )
    budget_per_pi = config.annual_budget_usd / config.planning_intervals
    wip = config.base_team_demand * config.teams * 0.18
    architecture_runway = 0.72
    reliability = 0.94
    trace: list[PIMetrics] = []

    for pi in range(1, config.planning_intervals + 1):
        jitter = 0.985 + rng.random() * 0.03
        demand = (
            config.base_team_demand
            * config.teams
            * scenario.demand_multiplier
            * (1.0 + 0.012 * (pi - 1))
            * jitter
        )
        dependency_penalty = min(
            0.24,
            0.035
            * dependency_density
            * scenario.dependency_multiplier
            * priority_dependency
            * arch_dependency,
        )
        change_penalty = min(0.18, scenario.change_load * (1.0 - 0.20 * (pi - 1)))
        effective_capacity = (
            config.base_team_capacity
            * config.teams
            * scenario.capacity_multiplier
            * funding_capacity
            * capacity_flow
            * cadence_flow
            * priority_flow
            * arch_flow
            * risk_flow
            * (1.0 - dependency_penalty)
            * (1.0 - change_penalty)
            * jitter
        )
        completed = min(wip + demand, max(0.0, effective_capacity))
        wip = max(0.0, wip + demand - completed)
        throughput = completed / max(config.teams, 1)
        architecture_runway = min(
            1.25,
            max(
                0.20,
                architecture_runway
                + 0.028 * (arch_runway - 1.0)
                + 0.018 * (capacity_arch - 1.0)
                - 0.010 * scenario.architecture_multiplier * (wip / max(demand, 1.0)),
            ),
        )
        reliability = min(
            0.999,
            max(
                0.40,
                reliability
                * scenario.reliability_multiplier ** (1.0 / config.planning_intervals)
                * (1.0 + 0.012 * (capacity_reliability - 1.0))
                * (1.0 + 0.009 * (risk_reliability - 1.0)),
            ),
        )
        compliance_risk = min(
            1.0,
            max(
                0.0,
                0.19
                * scenario.compliance_multiplier
                * priority_risk
                * risk_compliance
                * (1.03 - 0.22 * min(architecture_runway, 1.0)),
            ),
        )
        coordination_overhead = min(
            0.45,
            0.045
            * coordination_density
            * scenario.coordination_multiplier
            * cadence_coordination
            * (1.0 + 0.20 * dependency_penalty),
        )
        predictability = min(
            1.0,
            max(
                0.0,
                completed
                / max(demand, 1.0)
                * cadence_predictability
                * (1.0 - 0.45 * compliance_risk)
                * (1.0 - 0.25 * change_penalty),
            ),
        )
        business_value = (
            completed * priority_value * (1.0 - compliance_risk * 0.35) * reliability
        )
        spend = budget_per_pi * scenario.budget_multiplier * funding_spend
        budget_variance = abs(spend - budget_per_pi) / budget_per_pi * funding_variance
        employee_load = min(
            1.65,
            max(
                0.45,
                (demand + wip * 0.35)
                / max(effective_capacity, 1.0)
                * capacity_load
                * (1.0 + coordination_overhead * 0.8),
            ),
        )
        lead_time = (
            config.pi_days
            * (1.0 + wip / max(completed, 1.0))
            * (1.0 + dependency_penalty)
        )
        dependency_age = (
            config.pi_days * dependency_penalty * (1.0 + wip / max(demand, 1.0)) * 2.5
        )
        recovery_time = (
            config.pi_days
            * max(0.0, 1.0 - reliability)
            * (1.0 + scenario.change_load * 2.0)
        )
        trace.append(
            PIMetrics(
                pi,
                demand,
                completed,
                throughput,
                wip,
                lead_time,
                business_value,
                predictability,
                reliability,
                compliance_risk,
                architecture_runway,
                coordination_overhead,
                spend,
                budget_variance,
                employee_load,
                dependency_age,
                recovery_time,
            )
        )

    metrics = EpisodeMetrics(
        fmean(p.throughput for p in trace),
        fmean(p.lead_time_days for p in trace),
        sum(p.business_value for p in trace),
        fmean(p.predictability for p in trace),
        min(p.reliability for p in trace),
        max(p.compliance_risk for p in trace),
        trace[-1].architecture_runway,
        fmean(p.coordination_overhead for p in trace),
        fmean(p.budget_variance for p in trace),
        max(p.employee_load for p in trace),
        fmean(p.dependency_age_days for p in trace),
        max(p.recovery_time_days for p in trace),
        trace[-1].wip,
    )
    input_material = {
        "config": config,
        "topology_digest": topology.digest,
        "policy": policy,
        "scenario": scenario,
    }
    input_digest = stable_digest(input_material)
    output_digest = stable_digest(metrics)
    trace_digest = stable_digest(trace)
    replay_digest = stable_digest(
        {"input": input_digest, "output": output_digest, "trace": trace_digest}
    )
    receipt = SimulationReceipt(
        RECEIPT_SCHEMA,
        "NON_ACTUATING_MODEL_ONLY",
        "MODEL_EXECUTED",
        APS_SOURCE_REPOSITORY,
        APS_SOURCE_SHA,
        AUTOFDE_TARGET_REPOSITORY,
        AUTOFDE_BASE_SHA,
        topology.digest,
        policy.digest,
        scenario.name.value,
        config.seed,
        input_digest,
        output_digest,
        trace_digest,
        replay_digest,
    )
    return EpisodeResult(policy, scenario, tuple(trace), metrics, receipt)


def replay(
    result: EpisodeResult,
    config: Fortune5Config = Fortune5Config(),
    topology: EnterpriseTopology | None = None,
) -> bool:
    repeated = run_episode(result.policy, result.scenario, config, topology)
    return (
        repeated.receipt == result.receipt
        and repeated.metrics == result.metrics
        and repeated.trace == result.trace
    )
