from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping

Scalar = str | int | float | bool | None


class StringEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class OptimizationDirection(StringEnum):
    MAXIMIZE = "MAXIMIZE"
    MINIMIZE = "MINIMIZE"


class FrontierStanding(StringEnum):
    INCOMPLETE_EVALUATION = "INCOMPLETE_EVALUATION"
    BELOW_FRONTIER = "BELOW_FRONTIER"
    FRONTIER_MATCHED = "FRONTIER_MATCHED"
    SOTA_SURPASSED = "SOTA_SURPASSED"


class TrialOutcome(StringEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    UNSUPPORTED = "UNSUPPORTED"
    REFUSED = "REFUSED"
    ERROR = "ERROR"


class FailureKind(StringEnum):
    NONE = "NONE"
    MODEL = "MODEL"
    PLANNER = "PLANNER"
    TOOL_POLICY = "TOOL_POLICY"
    REPAIR_POLICY = "REPAIR_POLICY"
    REPLANNING_POLICY = "REPLANNING_POLICY"
    PROJECTION = "PROJECTION"
    VERIFICATION = "VERIFICATION"
    BUDGET = "BUDGET"
    WORLD_MODEL = "WORLD_MODEL"
    AUTHORITY = "AUTHORITY"
    DEPENDENCY = "DEPENDENCY"
    EXECUTION = "EXECUTION"
    ORACLE = "ORACLE"
    UNKNOWN = "UNKNOWN"


class SelectionStrategy(StringEnum):
    FULL_FACTORIAL = "FULL_FACTORIAL"
    BASELINE_FIRST = "BASELINE_FIRST"
    ONE_FACTOR_AT_A_TIME = "ONE_FACTOR_AT_A_TIME"
    PAIRWISE_COVERING = "PAIRWISE_COVERING"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(prefix: str, payload: Mapping[str, Any]) -> str:
    body = _canonical_json(payload).encode("utf-8")
    return f"{prefix}:{hashlib.sha256(body).hexdigest()}"


def _validate_scalar(value: Scalar) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("non-finite scalar values are not allowed")


@dataclass(frozen=True, slots=True)
class BasisChoice:
    name: str
    parameters: tuple[tuple[str, Scalar], ...] = ()

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("basis choice name must be non-empty")
        keys = [key for key, _ in self.parameters]
        if keys != sorted(keys) or len(keys) != len(set(keys)):
            raise ValueError("basis choice parameters must be unique and sorted")
        for key, value in self.parameters:
            if not key:
                raise ValueError("parameter key must be non-empty")
            _validate_scalar(value)

    @classmethod
    def from_mapping(
        cls, name: str, parameters: Mapping[str, Scalar] | None = None
    ) -> "BasisChoice":
        pairs = tuple(sorted((str(k), v) for k, v in (parameters or {}).items()))
        return cls(name=name, parameters=pairs)

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "parameters": dict(self.parameters)}


@dataclass(frozen=True, slots=True)
class BudgetPolicy:
    name: str
    max_steps: int | None = None
    max_seconds: float | None = None
    max_tokens: int | None = None
    max_repairs: int | None = None
    max_cost_usd: float | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("budget policy name must be non-empty")
        for attr in ("max_steps", "max_tokens", "max_repairs"):
            value = getattr(self, attr)
            if value is not None and value < 0:
                raise ValueError(f"{attr} must be >= 0")
        for attr in ("max_seconds", "max_cost_usd"):
            value = getattr(self, attr)
            if value is not None and (not math.isfinite(value) or value < 0):
                raise ValueError(f"{attr} must be finite and >= 0")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "max_steps": self.max_steps,
            "max_seconds": self.max_seconds,
            "max_tokens": self.max_tokens,
            "max_repairs": self.max_repairs,
            "max_cost_usd": self.max_cost_usd,
        }


@dataclass(frozen=True, slots=True)
class DecisionBasis:
    model: BasisChoice
    planner: BasisChoice
    tool_policy: BasisChoice
    repair_policy: BasisChoice
    replanning_policy: BasisChoice
    verification_policy: BasisChoice
    projection_policy: BasisChoice
    memory_policy: BasisChoice
    budget: BudgetPolicy

    DIMENSIONS = (
        "model",
        "planner",
        "tool_policy",
        "repair_policy",
        "replanning_policy",
        "verification_policy",
        "projection_policy",
        "memory_policy",
        "budget",
    )

    @classmethod
    def current_behavior(
        cls,
        *,
        model: str,
        planner: str,
        tool_policy: str = "current-tool-policy",
        repair_policy: str = "current-repair-policy",
        replanning_policy: str = "current-replanning-policy",
        verification_policy: str = "benchmark-oracle",
        projection_policy: str = "gymact-default",
        memory_policy: str = "current-memory-policy",
        budget: BudgetPolicy | None = None,
    ) -> "DecisionBasis":
        return cls(
            model=BasisChoice(model),
            planner=BasisChoice(planner),
            tool_policy=BasisChoice(tool_policy),
            repair_policy=BasisChoice(repair_policy),
            replanning_policy=BasisChoice(replanning_policy),
            verification_policy=BasisChoice(verification_policy),
            projection_policy=BasisChoice(projection_policy),
            memory_policy=BasisChoice(memory_policy),
            budget=budget or BudgetPolicy("current-budget"),
        )

    def dimension_values(self) -> dict[str, str]:
        return {
            "model": self.model.name,
            "planner": self.planner.name,
            "tool_policy": self.tool_policy.name,
            "repair_policy": self.repair_policy.name,
            "replanning_policy": self.replanning_policy.name,
            "verification_policy": self.verification_policy.name,
            "projection_policy": self.projection_policy.name,
            "memory_policy": self.memory_policy.name,
            "budget": self.budget.name,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model.to_dict(),
            "planner": self.planner.to_dict(),
            "tool_policy": self.tool_policy.to_dict(),
            "repair_policy": self.repair_policy.to_dict(),
            "replanning_policy": self.replanning_policy.to_dict(),
            "verification_policy": self.verification_policy.to_dict(),
            "projection_policy": self.projection_policy.to_dict(),
            "memory_policy": self.memory_policy.to_dict(),
            "budget": self.budget.to_dict(),
        }

    @property
    def digest(self) -> str:
        return _digest("decision", self.to_dict())


@dataclass(frozen=True, slots=True)
class ExperimentBasis:
    seed: int = 0
    probe_budget: int = 0
    time_limit_s: float | None = None
    horizon: int | None = None
    replication: int = 0
    objective_weights: tuple[tuple[str, float], ...] = (("score", 1.0),)

    def __post_init__(self) -> None:
        if self.probe_budget < 0 or self.replication < 0:
            raise ValueError("probe_budget and replication must be >= 0")
        if self.time_limit_s is not None and (
            not math.isfinite(self.time_limit_s) or self.time_limit_s < 0
        ):
            raise ValueError("time_limit_s must be finite and >= 0")
        if self.horizon is not None and self.horizon < 0:
            raise ValueError("horizon must be >= 0")
        keys = [key for key, _ in self.objective_weights]
        if keys != sorted(keys) or len(keys) != len(set(keys)):
            raise ValueError("objective_weights must be unique and sorted")
        for _, value in self.objective_weights:
            if not math.isfinite(value):
                raise ValueError("objective weights must be finite")

    @classmethod
    def with_weights(cls, **kwargs: Any) -> "ExperimentBasis":
        weights = kwargs.pop("objective_weights", {"score": 1.0})
        if isinstance(weights, Mapping):
            weights = tuple(sorted((str(k), float(v)) for k, v in weights.items()))
        return cls(objective_weights=weights, **kwargs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "probe_budget": self.probe_budget,
            "time_limit_s": self.time_limit_s,
            "horizon": self.horizon,
            "replication": self.replication,
            "objective_weights": dict(self.objective_weights),
        }

    @property
    def digest(self) -> str:
        return _digest("experiment", self.to_dict())


@dataclass(frozen=True, slots=True)
class ArchitecturePoint:
    decision: DecisionBasis
    experiment: ExperimentBasis = field(default_factory=ExperimentBasis)

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.to_dict(),
            "experiment": self.experiment.to_dict(),
        }

    @property
    def digest(self) -> str:
        return _digest("architecture", self.to_dict())


@dataclass(frozen=True, slots=True)
class BenchmarkTarget:
    benchmark_id: str
    revision: str
    published_sota: float
    primary_metric: str
    task_ids: tuple[str, ...]
    expected_task_count: int
    direction: OptimizationDirection = OptimizationDirection.MAXIMIZE
    score_scale: float = 100.0
    evaluator_ref: str = ""
    frontier_source_ref: str = ""

    def __post_init__(self) -> None:
        if (
            not self.benchmark_id.strip()
            or not self.revision.strip()
            or not self.primary_metric.strip()
        ):
            raise ValueError("benchmark_id, revision, and primary_metric are required")
        if not math.isfinite(self.published_sota):
            raise ValueError("published_sota must be finite")
        if not math.isfinite(self.score_scale) or self.score_scale <= 0:
            raise ValueError("score_scale must be finite and > 0")
        if self.expected_task_count <= 0:
            raise ValueError("expected_task_count must be > 0")
        if len(set(self.task_ids)) != len(self.task_ids):
            raise ValueError("task_ids must be unique")
        if len(self.task_ids) > self.expected_task_count:
            raise ValueError("task_ids cannot exceed expected_task_count")

    @property
    def population_declared(self) -> bool:
        return len(self.task_ids) == self.expected_task_count

    def to_dict(self) -> dict[str, Any]:
        return {
            "benchmark_id": self.benchmark_id,
            "revision": self.revision,
            "published_sota": self.published_sota,
            "primary_metric": self.primary_metric,
            "task_ids": list(self.task_ids),
            "expected_task_count": self.expected_task_count,
            "direction": self.direction.value,
            "score_scale": self.score_scale,
            "evaluator_ref": self.evaluator_ref,
            "frontier_source_ref": self.frontier_source_ref,
        }


@dataclass(frozen=True, slots=True)
class ExperimentPlan:
    benchmark_id: str
    benchmark_revision: str
    task_id: str
    architecture: ArchitecturePoint
    purpose: str

    @property
    def architecture_digest(self) -> str:
        return self.architecture.digest

    @property
    def plan_id(self) -> str:
        return _digest(
            "plan",
            {
                "benchmark_id": self.benchmark_id,
                "benchmark_revision": self.benchmark_revision,
                "task_id": self.task_id,
                "architecture_digest": self.architecture_digest,
                "purpose": self.purpose,
            },
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "benchmark_id": self.benchmark_id,
            "benchmark_revision": self.benchmark_revision,
            "task_id": self.task_id,
            "architecture_digest": self.architecture_digest,
            "architecture": self.architecture.to_dict(),
            "purpose": self.purpose,
        }


@dataclass(frozen=True, slots=True)
class TrialResult:
    plan_id: str
    benchmark_id: str
    benchmark_revision: str
    task_id: str
    architecture_digest: str
    outcome: TrialOutcome
    primary_score: float | None = None
    cost_usd: float = 0.0
    latency_s: float = 0.0
    tokens: int = 0
    failure_kind: FailureKind = FailureKind.NONE
    blocker: str = ""
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.plan_id or not self.task_id or not self.architecture_digest:
            raise ValueError("plan_id, task_id, and architecture_digest are required")
        if self.primary_score is not None and not math.isfinite(self.primary_score):
            raise ValueError("primary_score must be finite")
        if not math.isfinite(self.cost_usd) or self.cost_usd < 0:
            raise ValueError("cost_usd must be finite and >= 0")
        if not math.isfinite(self.latency_s) or self.latency_s < 0:
            raise ValueError("latency_s must be finite and >= 0")
        if self.tokens < 0:
            raise ValueError("tokens must be >= 0")
        if (
            self.outcome is TrialOutcome.PASS
            and self.failure_kind is not FailureKind.NONE
        ):
            raise ValueError("PASS cannot carry a failure_kind")

    @property
    def passed(self) -> bool:
        return self.outcome is TrialOutcome.PASS

    @property
    def terminal(self) -> bool:
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "benchmark_id": self.benchmark_id,
            "benchmark_revision": self.benchmark_revision,
            "task_id": self.task_id,
            "architecture_digest": self.architecture_digest,
            "outcome": self.outcome.value,
            "primary_score": self.primary_score,
            "cost_usd": self.cost_usd,
            "latency_s": self.latency_s,
            "tokens": self.tokens,
            "failure_kind": self.failure_kind.value,
            "blocker": self.blocker,
            "evidence_refs": list(self.evidence_refs),
        }


@dataclass(frozen=True, slots=True)
class BenchmarkScore:
    benchmark_id: str
    benchmark_revision: str
    architecture_digest: str
    attempted: int
    passed: int
    expected: int
    score: float
    optimistic_score: float
    published_sota: float
    margin: float
    coverage: float
    population_declared: bool
    standing: FrontierStanding
    cost_usd: float
    latency_s: float
    tokens: int

    @property
    def can_still_beat_frontier(self) -> bool:
        if self.standing is FrontierStanding.SOTA_SURPASSED:
            return True
        return self.optimistic_score > self.published_sota

    def to_dict(self) -> dict[str, Any]:
        return {
            "benchmark_id": self.benchmark_id,
            "benchmark_revision": self.benchmark_revision,
            "architecture_digest": self.architecture_digest,
            "attempted": self.attempted,
            "passed": self.passed,
            "expected": self.expected,
            "score": self.score,
            "optimistic_score": self.optimistic_score,
            "published_sota": self.published_sota,
            "margin": self.margin,
            "coverage": self.coverage,
            "population_declared": self.population_declared,
            "standing": self.standing.value,
            "can_still_beat_frontier": self.can_still_beat_frontier,
            "cost_usd": self.cost_usd,
            "latency_s": self.latency_s,
            "tokens": self.tokens,
        }


@dataclass(frozen=True, slots=True)
class FailureCluster:
    failure_kind: FailureKind
    signature: str
    count: int
    task_ids: tuple[str, ...]
    architecture_digests: tuple[str, ...]
    target_dimension: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "failure_kind": self.failure_kind.value,
            "signature": self.signature,
            "count": self.count,
            "task_ids": list(self.task_ids),
            "architecture_digests": list(self.architecture_digests),
            "target_dimension": self.target_dimension,
        }


@dataclass(frozen=True, slots=True)
class RepairLeverage:
    before_score: float
    after_score: float
    repair_count: int

    @property
    def delta_score(self) -> float:
        return self.after_score - self.before_score

    @property
    def delta_score_per_repair(self) -> float:
        if self.repair_count <= 0:
            raise ValueError("repair_count must be > 0")
        return self.delta_score / self.repair_count


def unique_results_by_task(results: Iterable[TrialResult]) -> dict[str, TrialResult]:
    by_task: dict[str, TrialResult] = {}
    for result in results:
        if result.task_id in by_task:
            raise ValueError(f"duplicate terminal result for task {result.task_id!r}")
        by_task[result.task_id] = result
    return by_task
