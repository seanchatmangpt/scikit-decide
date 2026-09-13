# Chicago-style, no mocks: see .claude/rules/testing-chicago-style.md
"""Chicago-style test for the real ggen-manufactured evidence dataclasses.

Exercises the real, generated module `src/autofde_lab/constitution/evidence.py`,
manufactured by `ggen sync run` from the source ontology `ontology/evidence.ttl`
(part of the merged working-backwards Lab constitution, PR #37). No test doubles
anywhere: no `unittest.mock`, no `Mock`/`MagicMock`, no `patch`, no `monkeypatch`.
Every class named in `evidence.__all__` is retrieved via a real `getattr` on the
really-imported module and constructed with real, representative field values;
assertions check the real constructed instance's real field values (not merely
that construction succeeded), and frozen-ness is verified by provoking a real
`dataclasses.FrozenInstanceError` on attempted mutation.
"""
from __future__ import annotations

import dataclasses

import pytest

from autofde_lab.constitution import evidence


def test_real_import_succeeds_and_exposes_all_thirteen_names():
    assert evidence.__name__ == "autofde_lab.constitution.evidence"
    assert hasattr(evidence, "__all__")
    assert evidence.__all__ == [
        "Artifact",
        "ArtifactManifest",
        "DependencyRevision",
        "EvidenceWitness",
        "Level4Witness",
        "Observer",
        "Postcondition",
        "PostconditionObservation",
        "Receipt",
        "ReceiptDAG",
        "Replay",
        "SourceRevision",
        "VerifierRun",
    ]


def test_artifact_marker_class_has_no_fields_and_constructs():
    cls = getattr(evidence, "Artifact")
    instance = cls()
    assert isinstance(instance, cls)
    assert dataclasses.fields(instance) == ()


def test_dependency_revision_marker_class_has_no_fields_and_constructs():
    cls = getattr(evidence, "DependencyRevision")
    instance = cls()
    assert isinstance(instance, cls)
    assert dataclasses.fields(instance) == ()


def test_level4_witness_marker_class_has_no_fields_and_constructs():
    cls = getattr(evidence, "Level4Witness")
    instance = cls()
    assert isinstance(instance, cls)
    assert dataclasses.fields(instance) == ()


def test_observer_marker_class_has_no_fields_and_constructs():
    cls = getattr(evidence, "Observer")
    instance = cls()
    assert isinstance(instance, cls)
    assert dataclasses.fields(instance) == ()


def test_postcondition_marker_class_has_no_fields_and_constructs():
    cls = getattr(evidence, "Postcondition")
    instance = cls()
    assert isinstance(instance, cls)
    assert dataclasses.fields(instance) == ()


def test_source_revision_marker_class_has_no_fields_and_constructs():
    cls = getattr(evidence, "SourceRevision")
    instance = cls()
    assert isinstance(instance, cls)
    assert dataclasses.fields(instance) == ()


def test_artifact_manifest_real_fields_round_trip():
    cls = getattr(evidence, "ArtifactManifest")
    instance = cls(
        binds_entity=("urn:example:entity:1",),
        dependency_revision=("urn:example:dependencyrevision:1",),
        manifests_artifact=("urn:example:artifact:1",),
        source_revision=("urn:example:sourcerevision:1",),
    )
    assert instance.binds_entity == ("urn:example:entity:1",)
    assert instance.dependency_revision == ("urn:example:dependencyrevision:1",)
    assert instance.manifests_artifact == ("urn:example:artifact:1",)
    assert instance.source_revision == ("urn:example:sourcerevision:1",)


def test_evidence_witness_real_fields_round_trip():
    cls = getattr(evidence, "EvidenceWitness")
    instance = cls(
        actuation="urn:example:actuation:1",
        authority="urn:example:authorityenvelope:1",
        commitment="urn:example:powlcommitment:1",
        derived_by_verifier="urn:example:verifierrun:1",
        governed_candidate="urn:example:governedcandidate:1",
        manifest="urn:example:artifactmanifest:1",
        postcondition_observation="urn:example:postconditionobservation:1",
        receipt_dag="urn:example:receiptdag:1",
        replay="urn:example:replay:1",
        witness_for="urn:example:trial:1",
    )
    assert instance.actuation == "urn:example:actuation:1"
    assert instance.authority == "urn:example:authorityenvelope:1"
    assert instance.commitment == "urn:example:powlcommitment:1"
    assert instance.derived_by_verifier == "urn:example:verifierrun:1"
    assert instance.governed_candidate == "urn:example:governedcandidate:1"
    assert instance.manifest == "urn:example:artifactmanifest:1"
    assert instance.postcondition_observation == "urn:example:postconditionobservation:1"
    assert instance.receipt_dag == "urn:example:receiptdag:1"
    assert instance.replay == "urn:example:replay:1"
    assert instance.witness_for == "urn:example:trial:1"


def test_postcondition_observation_real_fields_round_trip():
    cls = getattr(evidence, "PostconditionObservation")
    instance = cls(
        asserts_postcondition=("urn:example:postcondition:1",),
        observes_actuation="urn:example:actuation:1",
        performed_by="urn:example:observer:1",
    )
    assert instance.asserts_postcondition == ("urn:example:postcondition:1",)
    assert instance.observes_actuation == "urn:example:actuation:1"
    assert instance.performed_by == "urn:example:observer:1"


def test_receipt_real_fields_round_trip():
    cls = getattr(evidence, "Receipt")
    instance = cls(
        caused_by_receipt=("urn:example:receipt:0",),
        evidences_actuation=("urn:example:actuation:1",),
        evidences_observation=("urn:example:postconditionobservation:1",),
    )
    assert instance.caused_by_receipt == ("urn:example:receipt:0",)
    assert instance.evidences_actuation == ("urn:example:actuation:1",)
    assert instance.evidences_observation == ("urn:example:postconditionobservation:1",)


def test_receipt_dag_real_fields_round_trip():
    cls = getattr(evidence, "ReceiptDAG")
    instance = cls(
        contains_receipt=("urn:example:receipt:1", "urn:example:receipt:2"),
    )
    assert instance.contains_receipt == ("urn:example:receipt:1", "urn:example:receipt:2")


def test_replay_real_fields_round_trip():
    cls = getattr(evidence, "Replay")
    instance = cls(
        replay_of_trial="urn:example:trial:1",
        replays_receipt=("urn:example:receipt:1",),
    )
    assert instance.replay_of_trial == "urn:example:trial:1"
    assert instance.replays_receipt == ("urn:example:receipt:1",)


def test_verifier_run_real_fields_round_trip():
    cls = getattr(evidence, "VerifierRun")
    instance = cls(reads_manifest=("urn:example:artifactmanifest:1",))
    assert instance.reads_manifest == ("urn:example:artifactmanifest:1",)


# Representative, non-default construction kwargs for every name in
# `evidence.__all__`, keyed by class name. Marker classes with zero fields get
# an empty kwargs dict (there is nothing to fill); every other class fills
# every declared field with a real, non-default value -- tuples of reference
# strings for `tuple[str, ...]` fields, real strings for `str | None` fields.
REPRESENTATIVE_KWARGS_BY_CLASS_NAME = {
    "Artifact": {},
    "ArtifactManifest": {
        "binds_entity": ("urn:example:entity:1",),
        "dependency_revision": ("urn:example:dependencyrevision:1",),
        "manifests_artifact": ("urn:example:artifact:1",),
        "source_revision": ("urn:example:sourcerevision:1",),
    },
    "DependencyRevision": {},
    "EvidenceWitness": {
        "actuation": "urn:example:actuation:1",
        "authority": "urn:example:authorityenvelope:1",
        "commitment": "urn:example:powlcommitment:1",
        "derived_by_verifier": "urn:example:verifierrun:1",
        "governed_candidate": "urn:example:governedcandidate:1",
        "manifest": "urn:example:artifactmanifest:1",
        "postcondition_observation": "urn:example:postconditionobservation:1",
        "receipt_dag": "urn:example:receiptdag:1",
        "replay": "urn:example:replay:1",
        "witness_for": "urn:example:trial:1",
    },
    "Level4Witness": {},
    "Observer": {},
    "Postcondition": {},
    "PostconditionObservation": {
        "asserts_postcondition": ("urn:example:postcondition:1",),
        "observes_actuation": "urn:example:actuation:1",
        "performed_by": "urn:example:observer:1",
    },
    "Receipt": {
        "caused_by_receipt": ("urn:example:receipt:0",),
        "evidences_actuation": ("urn:example:actuation:1",),
        "evidences_observation": ("urn:example:postconditionobservation:1",),
    },
    "ReceiptDAG": {
        "contains_receipt": ("urn:example:receipt:1", "urn:example:receipt:2"),
    },
    "Replay": {
        "replay_of_trial": "urn:example:trial:1",
        "replays_receipt": ("urn:example:receipt:1",),
    },
    "SourceRevision": {},
    "VerifierRun": {
        "reads_manifest": ("urn:example:artifactmanifest:1",),
    },
}


def test_every_name_in_dunder_all_is_constructible_with_real_field_values():
    """Walk the real `__all__` export list end to end: for every name, fetch the
    class via `getattr` on the really-imported module, construct a real
    instance with every real declared field filled with a representative
    non-default value, and assert the constructed instance's real field
    values match what was passed in -- not just that construction succeeded.
    """
    assert set(evidence.__all__) == set(REPRESENTATIVE_KWARGS_BY_CLASS_NAME)

    for name in evidence.__all__:
        cls = getattr(evidence, name)
        kwargs = REPRESENTATIVE_KWARGS_BY_CLASS_NAME[name]

        instance = cls(**kwargs)

        declared_field_names = {f.name for f in dataclasses.fields(instance)}
        assert declared_field_names == set(kwargs), (
            f"{name}: declared dataclass fields {declared_field_names!r} do not "
            f"match the representative kwargs keys {set(kwargs)!r} -- the "
            "manufactured module's field set has drifted from this test."
        )
        for field_name, expected_value in kwargs.items():
            assert getattr(instance, field_name) == expected_value


def test_dataclasses_are_frozen_mutation_raises_frozen_instance_error():
    """Attempting to set a field after construction raises the real
    `dataclasses.FrozenInstanceError` -- verified for a zero-field marker class
    and for two real multi-field classes, and the pre-mutation value is shown
    to survive the failed attempt.
    """
    artifact = evidence.Artifact()
    with pytest.raises(dataclasses.FrozenInstanceError):
        artifact.some_field = "urn:example:should-not-be-settable"  # type: ignore[attr-defined]

    manifest = evidence.ArtifactManifest(
        binds_entity=("urn:example:entity:1",),
        dependency_revision=("urn:example:dependencyrevision:1",),
        manifests_artifact=("urn:example:artifact:1",),
        source_revision=("urn:example:sourcerevision:1",),
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        manifest.binds_entity = ("urn:example:entity:2",)
    assert manifest.binds_entity == ("urn:example:entity:1",)

    witness = evidence.EvidenceWitness(
        actuation="urn:example:actuation:1",
        authority="urn:example:authorityenvelope:1",
        commitment="urn:example:powlcommitment:1",
        derived_by_verifier="urn:example:verifierrun:1",
        governed_candidate="urn:example:governedcandidate:1",
        manifest="urn:example:artifactmanifest:1",
        postcondition_observation="urn:example:postconditionobservation:1",
        receipt_dag="urn:example:receiptdag:1",
        replay="urn:example:replay:1",
        witness_for="urn:example:trial:1",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        witness.actuation = "urn:example:actuation:2"
    assert witness.actuation == "urn:example:actuation:1"
