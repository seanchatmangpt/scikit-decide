"""Types and deterministic identity for the Fortune-5 SAFe simulation."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, fields, is_dataclass
from enum import Enum
from functools import cached_property
from typing import Mapping

APS_SOURCE_REPOSITORY = "seanchatmangpt/agile-protocol-specification"
APS_SOURCE_SHA = "b5916330905195b124409ca0e857f43b897ffc80"
AUTOFDE_TARGET_REPOSITORY = "seanchatmangpt/autofde-lab"
AUTOFDE_BASE_SHA = "61840ec86b05f5542267421d015f3f2d7c1c5ce9"
RECEIPT_SCHEMA = "autofde-lab.simulation.fortune5-safe/v1"


class PriorityRule(str, Enum):
    WSJF = "wsjf"
    COST_OF_DELAY = "cost_of_delay"
    DEPENDENCY_FIRST = "dependency_first"
    RISK_FIRST = "risk_first"
    ARCHITECTURE_FIRST = "architecture_first"


class FundingRule(str, Enum):
    FIXED_GUARDRAILS = "fixed_guardrails"
    PROPORTIONAL_VALUE = "proportional_value"
    DYNAMIC_CAPACITY = "dynamic_capacity"
    OPTION_RESERVE = "option_reserve"


class CapacityRule(str, Enum):
    BALANCED = "balanced"
    FLOW_FIRST = "flow_first"
    RELIABILITY_RESERVE = "reliability_reserve"
    INNOVATION_RESERVE = "innovation_reserve"


class CadenceRule(str, Enum):
    SYNCHRONIZED = "synchronized"
    STAGGERED = "staggered"
    EVENT_DRIVEN = "event_driven"


class ArchitectureRule(str, Enum):
    RUNWAY_FIRST = "runway_first"
    JUST_IN_TIME = "just_in_time"
    PLATFORM_FIRST = "platform_first"


class RiskRule(str, Enum):
    COMPLIANCE_FIRST = "compliance_first"
    BALANCED = "balanced"
    FAST_FEEDBACK = "fast_feedback"


class ScenarioName(str, Enum):
    BASELINE = "baseline"
    DEMAND_BURST = "demand_burst"
    FUNDING_SHOCK = "funding_shock"
    SUPPLIER_DELAY = "supplier_delay"
    COMPLIANCE_HOLD = "compliance_hold"
    RELIABILITY_INCIDENT = "reliability_incident"
    ATTRITION = "attrition"
    DEPENDENCY_CASCADE = "dependency_cascade"
    REORG = "reorg"
    CYBER_INCIDENT = "cyber_incident"


@dataclass(frozen=True)
class Fortune5Config:
    portfolios: int = 4
    value_streams_per_portfolio: int = 5
    value_streams_per_solution_train: int = 2
    arts_per_value_stream: int = 3
    teams_per_art: int = 12
    people_per_team: int = 10
    annual_budget_usd: float = 1_200_000_000.0
    planning_intervals: int = 6
    iterations_per_pi: int = 5
    working_days_per_iteration: int = 10
    base_team_capacity: float = 100.0
    base_team_demand: float = 96.0
    strategic_themes_per_portfolio: int = 2
    epics_per_theme: int = 5
    capabilities_per_epic: int = 4
    features_per_capability: int = 6
    stories_per_feature: int = 9
    seed: int = 2030

    def __post_init__(self) -> None:
        for name in (
            "portfolios",
            "value_streams_per_portfolio",
            "value_streams_per_solution_train",
            "arts_per_value_stream",
            "teams_per_art",
            "people_per_team",
            "planning_intervals",
            "iterations_per_pi",
            "working_days_per_iteration",
            "strategic_themes_per_portfolio",
            "epics_per_theme",
            "capabilities_per_epic",
            "features_per_capability",
            "stories_per_feature",
        ):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        if self.annual_budget_usd <= 0:
            raise ValueError("annual_budget_usd must be positive")
        if self.value_streams % self.value_streams_per_solution_train != 0:
            raise ValueError("value streams must divide evenly into solution trains")

    @property
    def value_streams(self) -> int:
        return self.portfolios * self.value_streams_per_portfolio

    @property
    def solution_trains(self) -> int:
        return self.value_streams // self.value_streams_per_solution_train

    @property
    def arts(self) -> int:
        return self.value_streams * self.arts_per_value_stream

    @property
    def teams(self) -> int:
        return self.arts * self.teams_per_art

    @property
    def personnel(self) -> int:
        return self.teams * self.people_per_team

    @property
    def strategic_themes(self) -> int:
        return self.portfolios * self.strategic_themes_per_portfolio

    @property
    def epics(self) -> int:
        return self.strategic_themes * self.epics_per_theme

    @property
    def capabilities(self) -> int:
        return self.epics * self.capabilities_per_epic

    @property
    def features(self) -> int:
        return self.capabilities * self.features_per_capability

    @property
    def stories(self) -> int:
        return self.features * self.stories_per_feature

    @property
    def pi_days(self) -> int:
        return self.iterations_per_pi * self.working_days_per_iteration


@dataclass(frozen=True)
class Portfolio:
    id: str
    budget_usd: float
    value_stream_ids: tuple[str, ...]


@dataclass(frozen=True)
class ValueStream:
    id: str
    portfolio_id: str
    solution_train_id: str
    budget_usd: float
    art_ids: tuple[str, ...]


@dataclass(frozen=True)
class SolutionTrain:
    id: str
    portfolio_ids: tuple[str, ...]
    value_stream_ids: tuple[str, ...]
    art_ids: tuple[str, ...]


@dataclass(frozen=True)
class AgileReleaseTrain:
    id: str
    value_stream_id: str
    solution_train_id: str
    budget_usd: float
    team_ids: tuple[str, ...]


@dataclass(frozen=True)
class AgileTeam:
    id: str
    art_id: str
    seat_ids: tuple[str, ...]


@dataclass(frozen=True)
class PersonnelSeat:
    id: str
    team_id: str
    role: str


@dataclass(frozen=True)
class RoleAssignment:
    scope_kind: str
    scope_id: str
    role: str
    person_id: str


@dataclass(frozen=True)
class Dependency:
    source_id: str
    target_id: str
    kind: str
    criticality: float


@dataclass(frozen=True)
class WorkItem:
    id: str
    kind: str
    parent_id: str | None
    scope_id: str
    business_value: float
    cost_of_delay: float
    estimate: float
    enabler: bool = False


@dataclass(frozen=True)
class CadenceBucket:
    event: str
    count_per_pi: int
    scope: str


@dataclass(frozen=True)
class EnterpriseTopology:
    portfolios: tuple[Portfolio, ...]
    value_streams: tuple[ValueStream, ...]
    solution_trains: tuple[SolutionTrain, ...]
    arts: tuple[AgileReleaseTrain, ...]
    teams: tuple[AgileTeam, ...]
    personnel: tuple[PersonnelSeat, ...]
    roles: tuple[RoleAssignment, ...]
    work_items: tuple[WorkItem, ...]
    dependencies: tuple[Dependency, ...]
    cadence: tuple[CadenceBucket, ...]

    @cached_property
    def counts(self) -> Mapping[str, int]:
        return {
            "portfolios": len(self.portfolios),
            "value_streams": len(self.value_streams),
            "solution_trains": len(self.solution_trains),
            "arts": len(self.arts),
            "teams": len(self.teams),
            "personnel": len(self.personnel),
            "role_assignments": len(self.roles),
            "work_items": len(self.work_items),
            "strategic_themes": sum(
                item.kind == "strategic_theme" for item in self.work_items
            ),
            "epics": sum(item.kind == "epic" for item in self.work_items),
            "capabilities": sum(item.kind == "capability" for item in self.work_items),
            "features": sum(item.kind == "feature" for item in self.work_items),
            "stories": sum(item.kind == "story" for item in self.work_items),
            "enablers": sum(item.enabler for item in self.work_items),
            "dependencies": len(self.dependencies),
            "cadence_events_per_pi": sum(
                bucket.count_per_pi for bucket in self.cadence
            ),
        }

    @property
    def annual_budget_usd(self) -> float:
        return sum(portfolio.budget_usd for portfolio in self.portfolios)

    @cached_property
    def digest(self) -> str:
        return stable_digest(self)


@dataclass(frozen=True)
class PolicyVector:
    priority: PriorityRule
    funding: FundingRule
    capacity: CapacityRule
    cadence: CadenceRule
    architecture: ArchitectureRule
    risk: RiskRule

    @property
    def id(self) -> str:
        return "|".join(
            item.value
            for item in (
                self.priority,
                self.funding,
                self.capacity,
                self.cadence,
                self.architecture,
                self.risk,
            )
        )

    @property
    def digest(self) -> str:
        return stable_digest(self)


@dataclass(frozen=True)
class Scenario:
    name: ScenarioName
    demand_multiplier: float = 1.0
    capacity_multiplier: float = 1.0
    budget_multiplier: float = 1.0
    dependency_multiplier: float = 1.0
    compliance_multiplier: float = 1.0
    reliability_multiplier: float = 1.0
    coordination_multiplier: float = 1.0
    architecture_multiplier: float = 1.0
    change_load: float = 0.0


@dataclass(frozen=True)
class PIMetrics:
    pi: int
    demand: float
    completed: float
    throughput: float
    wip: float
    lead_time_days: float
    business_value: float
    predictability: float
    reliability: float
    compliance_risk: float
    architecture_runway: float
    coordination_overhead: float
    spend_usd: float
    budget_variance: float
    employee_load: float
    dependency_age_days: float
    recovery_time_days: float


@dataclass(frozen=True)
class EpisodeMetrics:
    throughput: float
    lead_time_days: float
    business_value: float
    predictability: float
    reliability: float
    compliance_risk: float
    architecture_runway: float
    coordination_overhead: float
    budget_variance: float
    employee_load: float
    dependency_age_days: float
    recovery_time_days: float
    terminal_wip: float


@dataclass(frozen=True)
class SimulationReceipt:
    schema: str
    authority: str
    standing: str
    source_repository: str
    source_sha: str
    target_repository: str
    target_base_sha: str
    topology_digest: str
    policy_digest: str
    scenario: str
    seed: int
    input_digest: str
    output_digest: str
    trace_digest: str
    replay_digest: str


@dataclass(frozen=True)
class EpisodeResult:
    policy: PolicyVector
    scenario: Scenario
    trace: tuple[PIMetrics, ...]
    metrics: EpisodeMetrics
    receipt: SimulationReceipt


@dataclass(frozen=True)
class PolicyAggregate:
    policy: PolicyVector
    feasible: bool
    scenario_count: int
    mean_throughput: float
    mean_business_value: float
    mean_predictability: float
    worst_reliability: float
    worst_compliance_risk: float
    mean_lead_time_days: float
    mean_coordination_overhead: float
    mean_budget_variance: float
    worst_employee_load: float


@dataclass(frozen=True)
class ExperimentResult:
    policy_count: int
    scenario_count: int
    episode_count: int
    feasible_policy_ids: tuple[str, ...]
    pareto_policy_ids: tuple[str, ...]
    diversity_score: float
    matrix_digest: str
    aggregates: tuple[PolicyAggregate, ...]


def _canonical(value):
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {
            field.name: _canonical(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, Mapping):
        return {
            str(key): _canonical(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (tuple, list)):
        return [_canonical(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted(_canonical(item) for item in value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite floats are not receiptable")
        return round(value, 12)
    return value


def stable_digest(value) -> str:
    payload = json.dumps(
        _canonical(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
