"""Wiring verification: autofde_lab.receipts.admission.admit_typed against real
wasm4pm-compat-py pydantic models (OcelEvent, Receipt, ConformanceVerdict).

Positive: a well-formed OcelEvent-shaped observation admits; the digest is stable
under model-normalized re-serialization.

Negative: a malformed observation is refused via Blocked, naming the real pydantic
validation error, not a bare exception.
"""

from __future__ import annotations

import pytest

from autofde_lab.receipts.admission import admit_typed
from autofde_lab.receipts.wasm4pm_types import ConformanceVerdict, OcelEvent, Receipt
from autofde_lab.standing import Blocked


def test_admit_typed_accepts_a_well_formed_ocel_event() -> None:
    observation = {
        "id": "e1",
        "type": "solve-blocks",
        "time": "2026-08-07T00:00:00Z",
        "attributes": [],
        "relationships": [],
    }
    result = admit_typed(observation, model=OcelEvent)
    assert result.admitted
    assert result.observation_digest


def test_admit_typed_digest_is_stable_across_key_order() -> None:
    a = {
        "id": "e1",
        "type": "solve-blocks",
        "time": "2026-08-07T00:00:00Z",
        "attributes": [],
        "relationships": [],
    }
    b = {
        "attributes": [],
        "time": "2026-08-07T00:00:00Z",
        "relationships": [],
        "type": "solve-blocks",
        "id": "e1",
    }
    assert admit_typed(a, model=OcelEvent).observation_digest == admit_typed(
        b, model=OcelEvent
    ).observation_digest


def test_admit_typed_accepts_a_well_formed_receipt() -> None:
    observation = {
        "final_hash_chain": "deadbeef",
        "model_id": "blocks-plan-1",
        "verdict": {"is_perfect": True},
    }
    result = admit_typed(observation, model=Receipt)
    assert result.admitted


def test_admit_typed_refuses_receipt_with_wrong_shaped_nested_verdict() -> None:
    observation = {
        "final_hash_chain": "deadbeef",
        "model_id": "blocks-plan-1",
        "verdict": "fits",  # ConformanceVerdict is a nested model, not a string
    }
    with pytest.raises(Blocked, match="verdict"):
        admit_typed(observation, model=Receipt)


def test_admit_typed_refuses_missing_required_field_with_named_reason() -> None:
    observation = {"id": "e1", "attributes": [], "relationships": []}  # no `type`, `time`
    with pytest.raises(Blocked, match="failed OcelEvent validation"):
        admit_typed(observation, model=OcelEvent)


def test_admit_typed_refuses_wrong_typed_field_with_named_reason() -> None:
    observation = {
        "id": "e1",
        "type": "solve-blocks",
        "time": "2026-08-07T00:00:00Z",
        "attributes": "not-a-list",  # wrong type
        "relationships": [],
    }
    with pytest.raises(Blocked, match="attributes"):
        admit_typed(observation, model=OcelEvent)
