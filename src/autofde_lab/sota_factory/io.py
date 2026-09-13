from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from .models import (
    BasisChoice,
    BenchmarkTarget,
    BudgetPolicy,
    DecisionBasis,
    ExperimentBasis,
    FailureKind,
    OptimizationDirection,
    SelectionStrategy,
    TrialOutcome,
    TrialResult,
)
from .space import CompatibilityRule, DecisionSpace


@dataclass(frozen=True, slots=True)
class FactorySpec:
    target: BenchmarkTarget
    decision_space: DecisionSpace
    experiment_bases: tuple[ExperimentBasis, ...]
    baseline: DecisionBasis | None
    strategy: SelectionStrategy
    candidate_limit: int
    max_architectures: int | None


def _choice(payload: str | Mapping[str, Any]) -> BasisChoice:
    if isinstance(payload, str):
        return BasisChoice(payload)
    return BasisChoice.from_mapping(str(payload["name"]), payload.get("parameters"))


def _budget(payload: str | Mapping[str, Any]) -> BudgetPolicy:
    if isinstance(payload, str):
        return BudgetPolicy(payload)
    return BudgetPolicy(
        name=str(payload["name"]),
        max_steps=payload.get("max_steps"),
        max_seconds=payload.get("max_seconds"),
        max_tokens=payload.get("max_tokens"),
        max_repairs=payload.get("max_repairs"),
        max_cost_usd=payload.get("max_cost_usd"),
    )


def _decision_from_payload(payload: Mapping[str, Any]) -> DecisionBasis:
    return DecisionBasis(
        model=_choice(payload["model"]),
        planner=_choice(payload["planner"]),
        tool_policy=_choice(payload["tool_policy"]),
        repair_policy=_choice(payload["repair_policy"]),
        replanning_policy=_choice(payload["replanning_policy"]),
        verification_policy=_choice(payload["verification_policy"]),
        projection_policy=_choice(payload["projection_policy"]),
        memory_policy=_choice(payload["memory_policy"]),
        budget=_budget(payload["budget"]),
    )


def load_spec(path: str | Path) -> FactorySpec:
    payload = json.loads(Path(path).read_text())
    target_payload = payload["target"]
    target = BenchmarkTarget(
        benchmark_id=target_payload["benchmark_id"],
        revision=target_payload["revision"],
        published_sota=float(target_payload["published_sota"]),
        primary_metric=target_payload["primary_metric"],
        task_ids=tuple(target_payload.get("task_ids", ())),
        expected_task_count=int(target_payload["expected_task_count"]),
        direction=OptimizationDirection(target_payload.get("direction", "MAXIMIZE")),
        score_scale=float(target_payload.get("score_scale", 100.0)),
        evaluator_ref=target_payload.get("evaluator_ref", ""),
        frontier_source_ref=target_payload.get("frontier_source_ref", ""),
    )

    space_payload = payload["decision_space"]
    rules = tuple(
        CompatibilityRule.from_mappings(
            when=rule.get("when"),
            require=rule.get("require"),
            forbid=rule.get("forbid"),
            reason=rule.get("reason", ""),
        )
        for rule in space_payload.get("rules", ())
    )
    space = DecisionSpace(
        models=tuple(_choice(value) for value in space_payload["models"]),
        planners=tuple(_choice(value) for value in space_payload["planners"]),
        tool_policies=tuple(_choice(value) for value in space_payload["tool_policies"]),
        repair_policies=tuple(
            _choice(value) for value in space_payload["repair_policies"]
        ),
        replanning_policies=tuple(
            _choice(value) for value in space_payload["replanning_policies"]
        ),
        verification_policies=tuple(
            _choice(value) for value in space_payload["verification_policies"]
        ),
        projection_policies=tuple(
            _choice(value) for value in space_payload["projection_policies"]
        ),
        memory_policies=tuple(
            _choice(value) for value in space_payload["memory_policies"]
        ),
        budgets=tuple(_budget(value) for value in space_payload["budgets"]),
        rules=rules,
    )

    experiments = tuple(
        ExperimentBasis.with_weights(
            seed=int(item.get("seed", 0)),
            probe_budget=int(item.get("probe_budget", 0)),
            time_limit_s=item.get("time_limit_s"),
            horizon=item.get("horizon"),
            replication=int(item.get("replication", 0)),
            objective_weights=item.get("objective_weights", {"score": 1.0}),
        )
        for item in payload.get("experiment_bases", ({},))
    )
    baseline_payload = payload.get("baseline")
    baseline = _decision_from_payload(baseline_payload) if baseline_payload else None

    return FactorySpec(
        target=target,
        decision_space=space,
        experiment_bases=experiments,
        baseline=baseline,
        strategy=SelectionStrategy(payload.get("strategy", "PAIRWISE_COVERING")),
        candidate_limit=int(payload.get("candidate_limit", 100_000)),
        max_architectures=payload.get("max_architectures"),
    )


def load_results(path: str | Path) -> tuple[TrialResult, ...]:
    rows: list[TrialResult] = []
    for line_number, line in enumerate(Path(path).read_text().splitlines(), 1):
        if not line.strip():
            continue
        payload = json.loads(line)
        try:
            rows.append(
                TrialResult(
                    plan_id=payload["plan_id"],
                    benchmark_id=payload["benchmark_id"],
                    benchmark_revision=payload["benchmark_revision"],
                    task_id=payload["task_id"],
                    architecture_digest=payload["architecture_digest"],
                    outcome=TrialOutcome(payload["outcome"]),
                    primary_score=payload.get("primary_score"),
                    cost_usd=float(payload.get("cost_usd", 0.0)),
                    latency_s=float(payload.get("latency_s", 0.0)),
                    tokens=int(payload.get("tokens", 0)),
                    failure_kind=FailureKind(payload.get("failure_kind", "NONE")),
                    blocker=payload.get("blocker", ""),
                    evidence_refs=tuple(payload.get("evidence_refs", ())),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"invalid result at {path}:{line_number}: {exc}") from exc
    return tuple(rows)


def dump_jsonl(
    rows: Iterable[Mapping[str, Any]], path: str | Path | None = None
) -> str:
    text = "".join(json.dumps(dict(row), sort_keys=True) + "\n" for row in rows)
    if path is not None:
        Path(path).write_text(text)
    return text
