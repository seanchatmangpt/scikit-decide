import pytest

from autofde_lab.fabric.world_model import WorldModelRecord


def record(**overrides):
    values = dict(
        subject_id="subject:1",
        observation_id="obs:1",
        state={"temperature": 42},
        capability_id="cap:set-point",
        authority_id="authority:1",
        intended_effect={"temperature": 40},
        evidence_ids=("evidence:1",),
    )
    values.update(overrides)
    return WorldModelRecord(**values)


def test_world_model_binds_all_consequence_dimensions_to_one_subject():
    row = record()
    assert row.subject_id == "subject:1"
    assert row.observation_id == "obs:1"
    assert row.state == {"temperature": 42}
    assert row.capability_id == "cap:set-point"
    assert row.authority_id == "authority:1"
    assert row.intended_effect == {"temperature": 40}
    assert row.evidence_ids == ("evidence:1",)


def test_world_model_identity_is_deterministic_and_content_bound():
    assert record().digest == record().digest
    assert record(state={"temperature": 41}).digest != record().digest


def test_world_model_without_evidence_or_identity_is_refused():
    with pytest.raises(ValueError):
        record(evidence_ids=())
    with pytest.raises(ValueError):
        record(authority_id="")
