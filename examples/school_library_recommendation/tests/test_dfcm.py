import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dfcm import (
    admission_refusal,
    admitted_policy_space,
    execute_dfcm,
    pareto_frontier,
    temporal_policy_court,
    verify_receipt,
)
from llm import parse_librarian_request
from recommender import HybridRecommender, load_data

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def test_policy_space_is_combinatorial_unique_and_admitted():
    policies = admitted_policy_space()
    assert len(policies) == 16
    assert len({policy.policy_id for policy in policies}) == 16
    assert all(admission_refusal(policy) is None for policy in policies)


def test_invalid_policy_is_typed_refusal():
    policy = admitted_policy_space()[0]
    invalid = replace(policy, content_weight=1.5)
    assert admission_refusal(invalid) == "REFUSED:POLICY_WEIGHT_OUT_OF_RANGE"


def test_temporal_court_preserves_a_nonempty_pareto_frontier():
    catalog, circulation = load_data(DATA_DIR)
    evaluations = temporal_policy_court(catalog, circulation, top_k=3)
    frontier = pareto_frontier(evaluations)
    assert len(evaluations) == 16
    assert frontier
    assert len(frontier) < len(evaluations)
    assert all(0.0 <= item.hit_rate_at_k <= 1.0 for item in evaluations)
    assert all(0.0 <= item.catalog_coverage <= 1.0 for item in evaluations)
    assert all(0.0 <= item.intent_responsiveness <= 1.0 for item in evaluations)


def test_dfcm_receipt_is_deterministic_and_self_verifying():
    catalog, circulation = load_data(DATA_DIR)
    request = "funny mystery"
    intent = parse_librarian_request(request)
    first = execute_dfcm(catalog, circulation, "S104", request, intent, top_k=5)
    second = execute_dfcm(catalog, circulation, "S104", request, intent, top_k=5)
    assert first["receipt_id"] == second["receipt_id"]
    assert verify_receipt(first)
    assert first["authority"] == "SELECT_ONLY:NO_ACTUATION"
    assert first["actuation_performed"] is False


def test_request_change_changes_receipt_identity():
    catalog, circulation = load_data(DATA_DIR)
    first_request = "funny mystery"
    second_request = "surprise me with something different"
    first = execute_dfcm(
        catalog,
        circulation,
        "S104",
        first_request,
        parse_librarian_request(first_request),
    )
    second = execute_dfcm(
        catalog,
        circulation,
        "S104",
        second_request,
        parse_librarian_request(second_request),
    )
    assert first["receipt_id"] != second["receipt_id"]
    assert second["dfcm"]["selection_objective"] == "discovery"


def test_candidate_trace_preserves_refusal_reasons():
    catalog, circulation = load_data(DATA_DIR)
    recommender = HybridRecommender(catalog, circulation)
    intent = parse_librarian_request("funny mystery and not part of a long series")
    _, trace = recommender.recommend_with_trace("S104", intent, top_k=5)
    refusals = {reason for decision in trace for reason in decision.reasons}
    assert "REFUSED:RECENTLY_BORROWED" in refusals
    assert "REFUSED:LONG_SERIES" in refusals
