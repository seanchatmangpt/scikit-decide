# Chicago-style, no mocks: see .claude/rules/testing-chicago-style.md
"""Chicago-style test for the real, ggen-manufactured
``autofde_lab.constitution.interop`` module.

No test doubles of any kind are used anywhere in this file -- see
.claude/rules/testing-chicago-style.md for the discipline this follows. Every
class is imported for real from the manufactured module and constructed as a
real dataclass instance with real, explicit, representative field values;
every assertion below reads the real constructed instance's real field values
(state-based assertions), never "was it constructed" alone. Source ontology:
``ontology/interop.ttl`` (manufactured by ``ggen sync run`` per the module's
own docstring and PR #37).
"""
from __future__ import annotations

import dataclasses

import pytest

from autofde_lab.constitution import interop


def test_real_import_succeeds() -> None:
    """The manufactured module really imports; __all__ is populated and typed."""
    assert hasattr(interop, "__all__")
    assert isinstance(interop.__all__, list)
    assert len(interop.__all__) == 7
    assert interop.__all__ == [
        "ExternalRepresentation",
        "InteropAdapter",
        "InteropContract",
        "InteropContractReceipt",
        "LossReport",
        "Projection",
        "SemanticLoss",
    ]


def test_external_representation_constructs_with_no_fields() -> None:
    cls = getattr(interop, "ExternalRepresentation")
    instance = cls()
    assert dataclasses.is_dataclass(instance)
    assert dataclasses.fields(instance) == ()


def test_semantic_loss_constructs_with_no_fields() -> None:
    cls = getattr(interop, "SemanticLoss")
    instance = cls()
    assert dataclasses.is_dataclass(instance)
    assert dataclasses.fields(instance) == ()


def test_interop_adapter_real_fields() -> None:
    cls = getattr(interop, "InteropAdapter")
    instance = cls(uses_contract=("urn:example:contract:1", "urn:example:contract:2"))
    assert instance.uses_contract == (
        "urn:example:contract:1",
        "urn:example:contract:2",
    )
    field_names = {f.name for f in dataclasses.fields(instance)}
    assert field_names == {"uses_contract"}


def test_interop_contract_real_fields() -> None:
    cls = getattr(interop, "InteropContract")
    instance = cls(targets_representation=("urn:example:representation:1",))
    assert instance.targets_representation == ("urn:example:representation:1",)
    field_names = {f.name for f in dataclasses.fields(instance)}
    assert field_names == {"targets_representation"}


def test_interop_contract_receipt_real_fields() -> None:
    cls = getattr(interop, "InteropContractReceipt")
    instance = cls(
        adapter_revision=("urn:example:sourcerevision:abc123",),
        contract_receipt_for=("urn:example:contract:1",),
        external_revision=("urn:example:dependencyrevision:v2.3.4",),
    )
    assert instance.adapter_revision == ("urn:example:sourcerevision:abc123",)
    assert instance.contract_receipt_for == ("urn:example:contract:1",)
    assert instance.external_revision == ("urn:example:dependencyrevision:v2.3.4",)
    field_names = {f.name for f in dataclasses.fields(instance)}
    assert field_names == {
        "adapter_revision",
        "contract_receipt_for",
        "external_revision",
    }


def test_loss_report_real_fields() -> None:
    cls = getattr(interop, "LossReport")
    instance = cls(
        loss_report_for=("urn:example:projection:1",),
        reports_loss=("urn:example:semanticloss:1",),
        semantics_preserved=("false",),
    )
    assert instance.loss_report_for == ("urn:example:projection:1",)
    assert instance.reports_loss == ("urn:example:semanticloss:1",)
    assert instance.semantics_preserved == ("false",)
    field_names = {f.name for f in dataclasses.fields(instance)}
    assert field_names == {
        "loss_report_for",
        "reports_loss",
        "semantics_preserved",
    }


def test_projection_real_fields() -> None:
    cls = getattr(interop, "Projection")
    instance = cls(
        produced_by_adapter=("urn:example:interopadapter:1",),
        projects_representation=("urn:example:externalrepresentation:1",),
    )
    assert instance.produced_by_adapter == ("urn:example:interopadapter:1",)
    assert instance.projects_representation == (
        "urn:example:externalrepresentation:1",
    )
    field_names = {f.name for f in dataclasses.fields(instance)}
    assert field_names == {"produced_by_adapter", "projects_representation"}


def test_all_names_in_dunder_all_are_constructible_dataclasses_with_real_values() -> None:
    """Generic sweep over every name in __all__: getattr the class, build a
    representative kwargs dict from its real dataclasses.fields() (tuple[str, ...]
    fields get a real non-empty tuple of representative reference strings), construct
    a real instance, and assert the constructed instance's real field values match
    what was passed in -- not merely that construction succeeded.
    """
    for name in interop.__all__:
        cls = getattr(interop, name)
        assert dataclasses.is_dataclass(cls)
        kwargs = {}
        for field in dataclasses.fields(cls):
            if field.type == "tuple[str, ...]":
                kwargs[field.name] = (f"urn:example:{name.lower()}:{field.name}:1",)
            else:  # pragma: no cover - every field in this module is tuple[str, ...]
                raise AssertionError(
                    f"unexpected field type {field.type!r} on {name}.{field.name}; "
                    "test must be updated to cover this shape"
                )
        instance = cls(**kwargs)
        for field_name, expected_value in kwargs.items():
            assert getattr(instance, field_name) == expected_value


def test_interop_adapter_is_frozen() -> None:
    """Attempting to mutate a field after construction raises FrozenInstanceError."""
    instance = interop.InteropAdapter(uses_contract=("urn:example:contract:1",))
    with pytest.raises(dataclasses.FrozenInstanceError):
        instance.uses_contract = ("urn:example:contract:mutated",)


def test_loss_report_is_frozen() -> None:
    """A second class also verified frozen, for confidence beyond a single sample."""
    instance = interop.LossReport(
        loss_report_for=("urn:example:projection:1",),
        reports_loss=("urn:example:semanticloss:1",),
        semantics_preserved=("true",),
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        instance.semantics_preserved = ("false",)


def test_external_representation_is_frozen_even_with_no_fields() -> None:
    """A zero-field dataclass is still frozen; mutation of a non-declared attribute
    is still rejected by the dataclass-generated __setattr__.
    """
    instance = interop.ExternalRepresentation()
    with pytest.raises(dataclasses.FrozenInstanceError):
        instance.some_arbitrary_attribute = "not allowed"  # type: ignore[attr-defined]
