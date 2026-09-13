# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Portable, deterministic transport for observed planner-payoff evidence.

A payoff bundle is evidence transport only. It cannot execute a planner,
actuate a gym, grant authority, or manufacture a missing payoff. Every
observation must already carry a non-empty receipt accepted by
``PayoffObservation``. The bundle adds a content digest so tampering is refused
before observations are admitted into a ``PayoffHypergraph``.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Iterable

from autofde_lab.planner_league import LeagueMatch, PayoffObservation, PolicySpec

PAYOFF_BUNDLE_SCHEMA_VERSION = 1

__all__ = [
    "PAYOFF_BUNDLE_SCHEMA_VERSION",
    "decode_payoff_bundle",
    "encode_payoff_bundle",
]


def _finite_score(value: Any, *, field: str) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"REFUSED:INVALID_PAYOFF_BUNDLE:{field}_NOT_NUMBER") from exc
    if not math.isfinite(score):
        raise ValueError(f"REFUSED:INVALID_PAYOFF_BUNDLE:{field}_NONFINITE")
    return score


def _policy_dict(policy: PolicySpec) -> dict[str, Any]:
    return {
        "planner_id": policy.planner_id,
        "parameters": list(policy.parameters),
        "objective_id": policy.objective_id,
        "observation_projection_id": policy.observation_projection_id,
        "action_projection_id": policy.action_projection_id,
        "budget_id": policy.budget_id,
    }


def _observation_dict(observation: PayoffObservation) -> dict[str, Any]:
    match = observation.match
    return {
        "match": {
            "world_id": match.world_id,
            "left_role_id": match.left_role_id,
            "left_policy": _policy_dict(match.left_policy),
            "right_role_id": match.right_role_id,
            "right_policy": _policy_dict(match.right_policy),
            "information_partition_id": match.information_partition_id,
            "authority_context_ref": match.authority_context_ref,
        },
        "left_score": _finite_score(observation.left_score, field="LEFT_SCORE"),
        "right_score": _finite_score(observation.right_score, field="RIGHT_SCORE"),
        "receipt_id": observation.receipt_id,
        "execution_observed": observation.execution_observed,
    }


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("REFUSED:INVALID_PAYOFF_BUNDLE:NONFINITE_NUMBER") from exc


def _canonical_observations(observations: Iterable[PayoffObservation]) -> str:
    payload = [_observation_dict(observation) for observation in observations]
    return _canonical_json(payload)


def encode_payoff_bundle(observations: Iterable[PayoffObservation]) -> str:
    """Encode observations as canonical JSON with a deterministic digest."""
    canonical_observations = _canonical_observations(observations)
    digest = hashlib.sha256(canonical_observations.encode("utf-8")).hexdigest()
    bundle = {
        "schema_version": PAYOFF_BUNDLE_SCHEMA_VERSION,
        "observations_sha256": digest,
        "observations": json.loads(canonical_observations),
    }
    return _canonical_json(bundle)


def _require_mapping(value: Any, reason: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(reason)
    return value


def _policy_from_dict(payload: Any, *, role_id: str) -> PolicySpec:
    data = _require_mapping(payload, "REFUSED:INVALID_PAYOFF_BUNDLE:POLICY_NOT_OBJECT")
    try:
        parameters_raw = data["parameters"]
        if not isinstance(parameters_raw, list):
            raise ValueError("REFUSED:INVALID_PAYOFF_BUNDLE:PARAMETERS_NOT_LIST")
        parameters = dict(parameters_raw)
        policy = PolicySpec.for_role(
            str(data["planner_id"]),
            role_id,
            parameters=parameters,
            observation_projection_id=str(data["observation_projection_id"]),
            budget_id=str(data["budget_id"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, ValueError) and str(exc).startswith("REFUSED:"):
            raise
        raise ValueError("REFUSED:INVALID_PAYOFF_BUNDLE:POLICY_FIELDS") from exc

    if policy.objective_id != data.get("objective_id"):
        raise ValueError("REFUSED:INVALID_PAYOFF_BUNDLE:OBJECTIVE_DRIFT")
    if policy.action_projection_id != data.get("action_projection_id"):
        raise ValueError("REFUSED:INVALID_PAYOFF_BUNDLE:ACTION_PROJECTION_DRIFT")
    return policy


def _observation_from_dict(payload: Any) -> PayoffObservation:
    data = _require_mapping(
        payload, "REFUSED:INVALID_PAYOFF_BUNDLE:OBSERVATION_NOT_OBJECT"
    )
    match_data = _require_mapping(
        data.get("match"), "REFUSED:INVALID_PAYOFF_BUNDLE:MATCH_NOT_OBJECT"
    )
    try:
        execution_observed = data["execution_observed"]
        if not isinstance(execution_observed, bool):
            raise ValueError("REFUSED:INVALID_PAYOFF_BUNDLE:EXECUTION_FLAG_NOT_BOOL")
        left_role_id = str(match_data["left_role_id"])
        right_role_id = str(match_data["right_role_id"])
        match = LeagueMatch(
            world_id=str(match_data["world_id"]),
            left_role_id=left_role_id,
            left_policy=_policy_from_dict(
                match_data["left_policy"], role_id=left_role_id
            ),
            right_role_id=right_role_id,
            right_policy=_policy_from_dict(
                match_data["right_policy"], role_id=right_role_id
            ),
            information_partition_id=str(
                match_data.get("information_partition_id", "shared")
            ),
            authority_context_ref=match_data.get("authority_context_ref"),
        )
        return PayoffObservation(
            match=match,
            left_score=_finite_score(data["left_score"], field="LEFT_SCORE"),
            right_score=_finite_score(data["right_score"], field="RIGHT_SCORE"),
            receipt_id=str(data["receipt_id"]),
            execution_observed=execution_observed,
        )
    except KeyError as exc:
        raise ValueError("REFUSED:INVALID_PAYOFF_BUNDLE:OBSERVATION_FIELDS") from exc


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"REFUSED:INVALID_PAYOFF_BUNDLE:NONFINITE_NUMBER:{value}")


def decode_payoff_bundle(payload: str) -> tuple[PayoffObservation, ...]:
    """Decode and verify a payoff bundle before returning observations.

    The digest covers the canonical observation list. Any altered score,
    planner identity, receipt, role, world, projection, or execution flag is
    therefore refused unless the producer recomputes the digest; structural
    validation then re-applies the repository's PolicySpec/LeagueMatch and
    receipt admission rules.
    """
    try:
        decoded = json.loads(payload, parse_constant=_reject_json_constant)
    except json.JSONDecodeError as exc:
        raise ValueError("REFUSED:INVALID_PAYOFF_BUNDLE:JSON") from exc
    bundle = _require_mapping(decoded, "REFUSED:INVALID_PAYOFF_BUNDLE:ROOT_NOT_OBJECT")
    if bundle.get("schema_version") != PAYOFF_BUNDLE_SCHEMA_VERSION:
        raise ValueError("REFUSED:INVALID_PAYOFF_BUNDLE:SCHEMA_VERSION")
    observations_raw = bundle.get("observations")
    if not isinstance(observations_raw, list):
        raise ValueError("REFUSED:INVALID_PAYOFF_BUNDLE:OBSERVATIONS_NOT_LIST")

    canonical = _canonical_json(observations_raw)
    actual_digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    if bundle.get("observations_sha256") != actual_digest:
        raise ValueError("REFUSED:PAYOFF_BUNDLE_DIGEST_MISMATCH")

    return tuple(_observation_from_dict(item) for item in observations_raw)
