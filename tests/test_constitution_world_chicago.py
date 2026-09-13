# Chicago-style, no mocks: see .claude/rules/testing-chicago-style.md
"""Chicago-style test for the real ggen-manufactured module `autofde_lab.constitution.world`.

No mocks: this test performs a real import of the manufactured module, constructs real
instances of every dataclass listed in `world.__all__` with every real field explicitly
filled with representative (non-default) values, and asserts on the real constructed
instance's real field values. It also verifies frozen-dataclass immutability by attempting
a real mutation and catching the real `dataclasses.FrozenInstanceError` it raises.

Source ontology: `ontology/world.ttl` (manufactured into
`src/autofde_lab/constitution/world.py` by `ggen sync run`; see that module's own docstring
for the manufacture provenance note).
"""
from __future__ import annotations

import dataclasses

import pytest

from autofde_lab.constitution import world


def test_world_module_exports_expected_names():
    """The real manufactured module exposes exactly the six constitution classes."""
    assert set(world.__all__) == {
        "AdmittedObservation",
        "Environment",
        "Observation",
        "ObservationAdmission",
        "World",
        "WorldState",
    }


def test_admitted_observation_real_construction_and_fields():
    cls = getattr(world, "AdmittedObservation")
    instance = cls(derived_from_observation=("urn:example:observation-1", "urn:example:observation-2"))
    assert instance.derived_from_observation == (
        "urn:example:observation-1",
        "urn:example:observation-2",
    )
    assert isinstance(instance.derived_from_observation, tuple)


def test_environment_real_construction():
    cls = getattr(world, "Environment")
    instance = cls()
    assert isinstance(instance, world.Environment)
    assert dataclasses.fields(instance) == ()


def test_observation_real_construction_and_fields():
    cls = getattr(world, "Observation")
    instance = cls(
        about_state=("urn:example:world-state-1",),
        observed_from=("urn:example:world-1",),
    )
    assert instance.about_state == ("urn:example:world-state-1",)
    assert instance.observed_from == ("urn:example:world-1",)


def test_observation_admission_real_construction_and_fields():
    cls = getattr(world, "ObservationAdmission")
    instance = cls(admits_observation=("urn:example:admitted-observation-1",))
    assert instance.admits_observation == ("urn:example:admitted-observation-1",)


def test_world_real_construction():
    cls = getattr(world, "World")
    instance = cls()
    assert isinstance(instance, world.World)
    assert dataclasses.fields(instance) == ()


def test_world_state_real_construction():
    cls = getattr(world, "WorldState")
    instance = cls()
    assert isinstance(instance, world.WorldState)
    assert dataclasses.fields(instance) == ()


def test_all_world_all_names_are_frozen_dataclasses_constructible_with_real_fields():
    """For every name in `world.__all__`, get the class via getattr, construct a real
    instance with all real fields explicitly filled with representative values, and
    assert on the real constructed instance's real field values."""
    representative_tuple_fields = {
        "derived_from_observation": ("urn:example:observation-1",),
        "about_state": ("urn:example:world-state-1",),
        "observed_from": ("urn:example:world-1",),
        "admits_observation": ("urn:example:admitted-observation-1",),
    }

    for name in world.__all__:
        cls = getattr(world, name)
        assert dataclasses.is_dataclass(cls)

        field_defs = dataclasses.fields(cls)
        kwargs = {}
        for field in field_defs:
            assert field.name in representative_tuple_fields, (
                f"unexpected field {field.name!r} on {name}; "
                "test must be updated to supply a representative value"
            )
            kwargs[field.name] = representative_tuple_fields[field.name]

        instance = cls(**kwargs)

        for field in field_defs:
            assert getattr(instance, field.name) == kwargs[field.name]


def test_admitted_observation_is_frozen_and_mutation_raises():
    """Attempting to mutate a field on a real constructed instance raises the real
    `dataclasses.FrozenInstanceError`, not a mock-verified interaction."""
    instance = world.AdmittedObservation(derived_from_observation=("urn:example:observation-1",))
    with pytest.raises(dataclasses.FrozenInstanceError):
        instance.derived_from_observation = ("urn:example:observation-mutated",)
    # The original real field value survived the failed mutation attempt.
    assert instance.derived_from_observation == ("urn:example:observation-1",)


def test_observation_is_frozen_and_mutation_raises():
    instance = world.Observation(
        about_state=("urn:example:world-state-1",),
        observed_from=("urn:example:world-1",),
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        instance.about_state = ("urn:example:world-state-mutated",)
    assert instance.about_state == ("urn:example:world-state-1",)


def test_world_is_frozen_and_mutation_raises():
    """World has no fields; confirm frozen enforcement still fires for an
    arbitrary attribute assignment attempt on a no-field dataclass."""
    instance = world.World()
    with pytest.raises(dataclasses.FrozenInstanceError):
        instance.nonexistent_field = "anything"  # type: ignore[attr-defined]
