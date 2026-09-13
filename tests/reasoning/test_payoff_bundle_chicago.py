from __future__ import annotations

import hashlib
import json

import pytest

from autofde_lab.planner_league import (
    LeagueMatch,
    PayoffHypergraph,
    PayoffObservation,
    PolicySpec,
)
from autofde_lab.reasoning.payoff_bundle import (
    decode_payoff_bundle,
    encode_payoff_bundle,
)


def _observation(
    left: str,
    right: str,
    left_score: float,
    right_score: float,
    receipt_id: str,
) -> PayoffObservation:
    role_id = "plan_constructor"
    return PayoffObservation(
        match=LeagueMatch(
            world_id="generic_enterprise",
            left_role_id=role_id,
            left_policy=PolicySpec.for_role(left, role_id),
            right_role_id=role_id,
            right_policy=PolicySpec.for_role(right, role_id),
        ),
        left_score=left_score,
        right_score=right_score,
        receipt_id=receipt_id,
    )


def _rebind_digest(bundle: dict[str, object]) -> None:
    observations = bundle["observations"]
    canonical = json.dumps(
        observations,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    bundle["observations_sha256"] = hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()


def test_payoff_bundle_round_trips_and_replays_deterministically() -> None:
    observations = (
        _observation("Astar", "BFWS", 1.0, 0.0, "receipt-a-b"),
        _observation("LRTAstar", "BFWS", 0.5, 0.0, "receipt-l-b"),
    )

    first = encode_payoff_bundle(observations)
    replayed = decode_payoff_bundle(first)
    second = encode_payoff_bundle(replayed)

    assert first == second
    assert replayed == observations

    hypergraph = PayoffHypergraph()
    for observation in replayed:
        hypergraph.add(observation)
    assert (
        hypergraph.empirical_best_response(
            candidates=("Astar", "LRTAstar"),
            opponent_mixture={"BFWS": 1.0},
            role_id="plan_constructor",
            opponent_role_id="plan_constructor",
            world_id="generic_enterprise",
        )
        == "Astar"
    )


def test_payoff_bundle_refuses_digest_tampering() -> None:
    bundle = json.loads(
        encode_payoff_bundle((_observation("Astar", "BFWS", 1.0, 0.0, "receipt-a-b"),))
    )
    bundle["observations"][0]["left_score"] = 0.0

    with pytest.raises(ValueError, match="REFUSED:PAYOFF_BUNDLE_DIGEST_MISMATCH"):
        decode_payoff_bundle(json.dumps(bundle))


def test_payoff_bundle_refuses_unreceipted_recomputed_payload() -> None:
    bundle = json.loads(
        encode_payoff_bundle((_observation("Astar", "BFWS", 1.0, 0.0, "receipt-a-b"),))
    )
    bundle["observations"][0]["receipt_id"] = ""
    _rebind_digest(bundle)

    with pytest.raises(ValueError, match="REFUSED:UNRECEIPTED_PAYOFF"):
        decode_payoff_bundle(json.dumps(bundle))


def test_payoff_bundle_refuses_objective_drift_even_with_valid_digest() -> None:
    bundle = json.loads(
        encode_payoff_bundle((_observation("Astar", "BFWS", 1.0, 0.0, "receipt-a-b"),))
    )
    bundle["observations"][0]["match"]["left_policy"]["objective_id"] = (
        "invented-objective"
    )
    _rebind_digest(bundle)

    with pytest.raises(
        ValueError, match="REFUSED:INVALID_PAYOFF_BUNDLE:OBJECTIVE_DRIFT"
    ):
        decode_payoff_bundle(json.dumps(bundle))


def test_payoff_bundle_refuses_nonfinite_observation_before_receipt_manufacture() -> (
    None
):
    observation = _observation("Astar", "BFWS", float("nan"), 0.0, "receipt-a-b")

    with pytest.raises(
        ValueError, match="REFUSED:INVALID_PAYOFF_BUNDLE:LEFT_SCORE_NONFINITE"
    ):
        encode_payoff_bundle((observation,))


def test_payoff_bundle_refuses_nonfinite_json_before_digest_admission() -> None:
    payload = (
        '{"schema_version":1,"observations_sha256":"irrelevant",'
        '"observations":[{"left_score":NaN}]}'
    )

    with pytest.raises(
        ValueError, match="REFUSED:INVALID_PAYOFF_BUNDLE:NONFINITE_NUMBER:NaN"
    ):
        decode_payoff_bundle(payload)
