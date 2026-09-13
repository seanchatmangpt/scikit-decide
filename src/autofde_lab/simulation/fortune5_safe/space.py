"""DfCM policy product and Fortune-5 disruption scenario space."""

from __future__ import annotations

import itertools

from .model import (
    ArchitectureRule,
    CadenceRule,
    CapacityRule,
    FundingRule,
    PolicyVector,
    PriorityRule,
    RiskRule,
    Scenario,
    ScenarioName,
)


def all_policies() -> tuple[PolicyVector, ...]:
    return tuple(
        PolicyVector(*values)
        for values in itertools.product(
            PriorityRule,
            FundingRule,
            CapacityRule,
            CadenceRule,
            ArchitectureRule,
            RiskRule,
        )
    )


SCENARIOS: tuple[Scenario, ...] = (
    Scenario(ScenarioName.BASELINE),
    Scenario(
        ScenarioName.DEMAND_BURST, demand_multiplier=1.35, coordination_multiplier=1.08
    ),
    Scenario(
        ScenarioName.FUNDING_SHOCK,
        budget_multiplier=0.78,
        capacity_multiplier=0.90,
        change_load=0.06,
    ),
    Scenario(
        ScenarioName.SUPPLIER_DELAY,
        dependency_multiplier=1.45,
        capacity_multiplier=0.94,
    ),
    Scenario(
        ScenarioName.COMPLIANCE_HOLD,
        compliance_multiplier=1.70,
        capacity_multiplier=0.91,
    ),
    Scenario(
        ScenarioName.RELIABILITY_INCIDENT,
        reliability_multiplier=0.72,
        capacity_multiplier=0.88,
        change_load=0.08,
    ),
    Scenario(
        ScenarioName.ATTRITION,
        capacity_multiplier=0.82,
        coordination_multiplier=1.15,
        change_load=0.10,
    ),
    Scenario(
        ScenarioName.DEPENDENCY_CASCADE,
        dependency_multiplier=1.85,
        capacity_multiplier=0.90,
    ),
    Scenario(
        ScenarioName.REORG,
        coordination_multiplier=1.35,
        capacity_multiplier=0.92,
        change_load=0.15,
    ),
    Scenario(
        ScenarioName.CYBER_INCIDENT,
        reliability_multiplier=0.80,
        compliance_multiplier=1.35,
        capacity_multiplier=0.86,
        change_load=0.12,
    ),
)
