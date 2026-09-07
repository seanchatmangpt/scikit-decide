"""Design for Combinatorial Maximalism policy manufacture for the demo.

The module keeps SELECT separate from DO. It manufactures and evaluates a bounded
space of reversible ranking policies, formally refuses malformed policies, preserves
its Pareto frontier, selects late, and emits a deterministic replay receipt.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from itertools import product
from typing import Any, Iterable

import pandas as pd
from models import Intent, PolicyEvaluation, RankingPolicy
from recommender import HybridRecommender

OBJECTIVE_WEIGHTS = {
    "balanced": {
        "hit_rate_at_k": 0.40,
        "catalog_coverage": 0.15,
        "novelty": 0.10,
        "personalization": 0.20,
        "intent_responsiveness": 0.15,
    },
    "discovery": {
        "hit_rate_at_k": 0.10,
        "catalog_coverage": 0.25,
        "novelty": 0.40,
        "personalization": 0.10,
        "intent_responsiveness": 0.15,
    },
    "familiar": {
        "hit_rate_at_k": 0.35,
        "catalog_coverage": 0.05,
        "novelty": 0.05,
        "personalization": 0.45,
        "intent_responsiveness": 0.10,
    },
}


def manufacture_policy_space() -> list[RankingPolicy]:
    """Manufacture a bounded 2x2x2x2 policy graph before selecting one edge."""
    policies = []
    for content, co, intent, novelty in product(
        (0.35, 0.50),
        (0.20, 0.35),
        (0.20, 0.35),
        (0.00, 0.15),
    ):
        curated = 0.05
        raw = (content, co, intent, curated, novelty)
        total = sum(raw)
        normalized = tuple(value / total for value in raw)
        policy_id = (
            f"dfcm-c{int(content * 100):02d}"
            f"-k{int(co * 100):02d}"
            f"-i{int(intent * 100):02d}"
            f"-n{int(novelty * 100):02d}"
        )
        policies.append(
            RankingPolicy(
                policy_id=policy_id,
                content_weight=normalized[0],
                co_circulation_weight=normalized[1],
                intent_weight=normalized[2],
                curated_weight=normalized[3],
                novelty_weight=normalized[4],
            )
        )
    return policies


def admission_refusal(policy: RankingPolicy) -> str | None:
    """Return a typed refusal, or None when the policy is admitted."""
    weights = (
        policy.content_weight,
        policy.co_circulation_weight,
        policy.intent_weight,
        policy.curated_weight,
        policy.novelty_weight,
    )
    if not policy.policy_id:
        return "REFUSED:MISSING_POLICY_ID"
    if any(weight < 0.0 or weight > 1.0 for weight in weights):
        return "REFUSED:POLICY_WEIGHT_OUT_OF_RANGE"
    if abs(sum(weights) - 1.0) > 1e-9:
        return "REFUSED:POLICY_WEIGHTS_NOT_NORMALIZED"
    return None


def admitted_policy_space() -> list[RankingPolicy]:
    policies = manufacture_policy_space()
    refusals = [admission_refusal(policy) for policy in policies]
    if any(refusal is not None for refusal in refusals):
        raise ValueError(f"generated policy failed admission: {refusals}")
    return policies


def temporal_policy_court(
    catalog: pd.DataFrame,
    circulation: pd.DataFrame,
    policies: Iterable[RankingPolicy] | None = None,
    top_k: int = 3,
) -> list[PolicyEvaluation]:
    """Falsifier court using temporal replay plus bounded intent probes."""
    policies = list(policies or admitted_policy_space())
    ordered = circulation.sort_values(["student_id", "checkout_date"])
    holdout = ordered.groupby("student_id", sort=True).tail(1)
    train = ordered.drop(index=holdout.index)
    recommender = HybridRecommender(catalog, train)
    available_count = max(int(catalog.available.sum()), 1)

    evaluations = []
    for policy in policies:
        refusal = admission_refusal(policy)
        if refusal is not None:
            continue

        hits = 0
        recommended_ids = set()
        novelty_values = []
        personalization_values = []
        for row in holdout.itertuples(index=False):
            recommendations = recommender.recommend(
                row.student_id,
                Intent(themes=[]),
                top_k=top_k,
                policy=policy,
            )
            ids = {rec.book_id for rec in recommendations}
            hits += int(row.book_id in ids)
            recommended_ids.update(ids)
            novelty_values.extend(float(rec.signals["novelty"]) for rec in recommendations)
            personalization_values.extend(
                (
                    float(rec.signals["content_similarity"])
                    + float(rec.signals["co_circulation"])
                )
                / 2.0
                for rec in recommendations
            )

        intent_responsiveness = _intent_probe_score(recommender, policy, top_k=top_k)
        student_count = max(len(holdout), 1)
        evaluations.append(
            PolicyEvaluation(
                policy=policy,
                hit_rate_at_k=round(hits / student_count, 4),
                catalog_coverage=round(len(recommended_ids) / available_count, 4),
                novelty=round(_mean(novelty_values), 4),
                personalization=round(_mean(personalization_values), 4),
                intent_responsiveness=round(intent_responsiveness, 4),
            )
        )
    return evaluations


def pareto_frontier(evaluations: Iterable[PolicyEvaluation]) -> list[PolicyEvaluation]:
    """Keep every non-dominated lawful policy instead of collapsing early."""
    evaluations = list(evaluations)
    metrics = (
        "hit_rate_at_k",
        "catalog_coverage",
        "novelty",
        "personalization",
        "intent_responsiveness",
    )
    frontier = []
    for candidate in evaluations:
        dominated = False
        for other in evaluations:
            if other.policy.policy_id == candidate.policy.policy_id:
                continue
            not_worse = all(
                getattr(other, metric) >= getattr(candidate, metric) for metric in metrics
            )
            strictly_better = any(
                getattr(other, metric) > getattr(candidate, metric) for metric in metrics
            )
            if not_worse and strictly_better:
                dominated = True
                break
        if not dominated:
            frontier.append(candidate)
    return sorted(frontier, key=lambda item: item.policy.policy_id)


def select_policy(
    evaluations: Iterable[PolicyEvaluation], objective: str = "balanced"
) -> tuple[RankingPolicy, list[PolicyEvaluation]]:
    """Select late from the Pareto frontier using one admitted objective."""
    if objective not in OBJECTIVE_WEIGHTS:
        raise ValueError(f"REFUSED:UNKNOWN_OBJECTIVE:{objective}")
    frontier = pareto_frontier(evaluations)
    if not frontier:
        raise ValueError("REFUSED:NO_ADMITTED_POLICY")
    weights = OBJECTIVE_WEIGHTS[objective]

    def objective_score(evaluation: PolicyEvaluation) -> float:
        return sum(
            getattr(evaluation, metric) * weight for metric, weight in weights.items()
        )

    selected = sorted(
        frontier,
        key=lambda evaluation: (-objective_score(evaluation), evaluation.policy.policy_id),
    )[0]
    return selected.policy, frontier


def execute_dfcm(
    catalog: pd.DataFrame,
    circulation: pd.DataFrame,
    student_id: str,
    raw_request: str,
    intent: Intent,
    top_k: int = 5,
) -> dict[str, Any]:
    """Run manufacture -> admission -> court -> late select -> receipt."""
    policies = admitted_policy_space()
    evaluations = temporal_policy_court(
        catalog, circulation, policies, top_k=min(top_k, 3)
    )
    selected_policy, frontier = select_policy(evaluations, objective=intent.objective)
    recommender = HybridRecommender(catalog, circulation)
    recommendations, trace = recommender.recommend_with_trace(
        student_id,
        intent,
        top_k=top_k,
        policy=selected_policy,
    )

    receipt = {
        "receipt_version": "dfcm-school-library-v1",
        "technical_standing": "ALIVE",
        "scope": "synthetic-selection-only",
        "authority": "SELECT_ONLY:NO_ACTUATION",
        "actuation_performed": False,
        "demo_data": "synthetic",
        "input_identity": {
            "catalog_sha256": dataframe_digest(catalog),
            "circulation_sha256": dataframe_digest(circulation),
            "request_sha256": digest_json(
                {
                    "student_id": student_id,
                    "raw_request": raw_request,
                    "intent": asdict(intent),
                    "top_k": top_k,
                }
            ),
        },
        "request": {
            "student_id": student_id,
            "raw_request": raw_request,
            "structured_intent": asdict(intent),
            "top_k": top_k,
        },
        "dfcm": {
            "manufactured_policy_count": len(policies),
            "admitted_policy_count": len(evaluations),
            "pareto_frontier_policy_ids": [item.policy.policy_id for item in frontier],
            "selected_policy": asdict(selected_policy),
            "policy_evaluations": [evaluation_dict(item) for item in evaluations],
            "selection_objective": intent.objective,
            "falsifier": (
                "synthetic leave-last-out temporal holdout + fixed intent probes; "
                "court top_k is capped at 3 to avoid a trivially permissive synthetic metric"
            ),
        },
        "recommendations": [asdict(rec) for rec in recommendations],
        "candidate_trace": [asdict(decision) for decision in trace],
        "language_boundary": {
            "llm_changed_ranking": False,
            "llm_supplied_facts": False,
            "allowed_effect": "structured constraints + admitted objective enum",
        },
    }
    receipt["receipt_id"] = digest_json(receipt)
    return receipt


def verify_receipt(receipt: dict[str, Any]) -> bool:
    claimed = receipt.get("receipt_id")
    payload = dict(receipt)
    payload.pop("receipt_id", None)
    return bool(claimed) and claimed == digest_json(payload)


def evaluation_dict(evaluation: PolicyEvaluation) -> dict[str, Any]:
    payload = asdict(evaluation)
    payload["policy"] = asdict(evaluation.policy)
    return payload


def dataframe_digest(frame: pd.DataFrame) -> str:
    records = []
    ordered = frame.copy()
    ordered = ordered.sort_values(list(ordered.columns)).reset_index(drop=True)
    for record in ordered.to_dict(orient="records"):
        records.append({key: _json_value(value) for key, value in record.items()})
    return digest_json(records)


def digest_json(value: Any) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), default=str
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _json_value(value: Any) -> Any:
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value


def _intent_probe_score(
    recommender: HybridRecommender, policy: RankingPolicy, top_k: int
) -> float:
    probes = (
        Intent(themes=["humor", "mystery"]),
        Intent(themes=["graphic novel", "fantasy"]),
        Intent(themes=["animals", "empathy"]),
    )
    values = []
    for probe in probes:
        recommendations = recommender.recommend(
            "SYNTHETIC-COLD-START", probe, top_k=top_k, policy=policy
        )
        values.extend(
            float(rec.signals["intent_match"]) for rec in recommendations
        )
    return _mean(values)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0
