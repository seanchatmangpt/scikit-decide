"""Chicago-style TDD prep: real Pydantic round-trips for the GymAct kernel types.

`autofde_lab.gymact.models` does not exist yet -- this file is expected to fail
at collection (ModuleNotFoundError) until the next implementation pass adds
`ActuationIntent`, `Observation`, and `ActuationResult` as real `pydantic.BaseModel`
subclasses. No mocking: every assertion here is state-based equality on real
constructed/round-tripped objects, per .claude/rules/testing-chicago-style.md.
"""

from __future__ import annotations

import pytest

pydantic = pytest.importorskip("pydantic")

from autofde_lab.gymact.models import (  # noqa: E402
    ActuationIntent,
    ActuationResult,
    Observation,
)


def test_actuation_intent_round_trips_through_dump_and_validate() -> None:
    intent = ActuationIntent(
        subject="cloudgoat",
        operation="act",
        episode_id="episode-1",
        payload={"affordance": "restrict-ingress"},
        authority_ref="authority://incident-42",
        idempotency_key="idem-1",
    )

    dumped = intent.model_dump()
    restored = ActuationIntent.model_validate(dumped)

    assert restored == intent
    assert dumped["subject"] == "cloudgoat"
    assert dumped["operation"] == "act"


def test_actuation_intent_missing_required_field_raises_named_validation_error() -> None:
    with pytest.raises(pydantic.ValidationError) as excinfo:
        ActuationIntent.model_validate({"operation": "act"})

    assert "subject" in str(excinfo.value)


def test_observation_round_trips_and_is_read_only_by_construction() -> None:
    observation = Observation(
        episode_id="episode-1",
        subject="cloudgoat",
        result={"public_exposure": False},
    )

    restored = Observation.model_validate(observation.model_dump())

    assert restored == observation


def test_actuation_result_carries_standing_and_optional_receipt() -> None:
    result = ActuationResult(
        accepted=True,
        standing="ALIVE",
        episode_id="episode-1",
        observation=None,
        receipt=None,
    )

    restored = ActuationResult.model_validate(result.model_dump())

    assert restored == result
    assert restored.standing == "ALIVE"
