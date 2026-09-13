# Chicago-style, no mocks: see .claude/rules/testing-chicago-style.md
"""Chicago-style test for the real ggen-manufactured `autofde_lab.constitution.planning`.

This exercises the real module manufactured by `ggen sync run` from the source
ontology file `ontology/planning.ttl` (see the module's own docstring,
`src/autofde_lab/constitution/planning.py`). No test doubles of any kind are
used anywhere in this file -- see .claude/rules/testing-chicago-style.md for
the full list of banned fakery mechanisms this file avoids. Every class in
`planning.__all__` is really imported and really instantiated with every
declared field explicitly filled with representative, non-default values, and
every assertion below is a state-based assertion on the real constructed
instance's real field values -- never an interaction/fakery assertion.
"""
from __future__ import annotations

import dataclasses

from autofde_lab.constitution import planning


def test_import_succeeds_and_all_is_exactly_the_ten_known_classes() -> None:
    """Real import; `__all__` names exactly the ten classes read from source."""
    expected = [
        "CandidateSet",
        "Critique",
        "Disagreement",
        "DiscriminatingProbe",
        "GovernedCandidate",
        "PlanCandidate",
        "Planner",
        "PlannerAttempt",
        "PlanningProblem",
        "Validation",
    ]
    assert list(planning.__all__) == expected


def test_candidate_set_fields() -> None:
    cls = getattr(planning, "CandidateSet")
    instance = cls(
        contains_candidate=("urn:example:plan-candidate-1", "urn:example:plan-candidate-2"),
        records_disagreement=("urn:example:disagreement-1",),
    )
    assert instance.contains_candidate == (
        "urn:example:plan-candidate-1",
        "urn:example:plan-candidate-2",
    )
    assert instance.records_disagreement == ("urn:example:disagreement-1",)


def test_critique_fields() -> None:
    cls = getattr(planning, "Critique")
    instance = cls(critiques_candidate=("urn:example:plan-candidate-1",))
    assert instance.critiques_candidate == ("urn:example:plan-candidate-1",)


def test_disagreement_has_no_fields_but_constructs_a_real_instance() -> None:
    cls = getattr(planning, "Disagreement")
    instance = cls()
    assert isinstance(instance, cls)
    assert dataclasses.fields(instance) == ()


def test_discriminating_probe_fields() -> None:
    cls = getattr(planning, "DiscriminatingProbe")
    instance = cls(designed_from_disagreement=("urn:example:disagreement-1",))
    assert instance.designed_from_disagreement == ("urn:example:disagreement-1",)


def test_governed_candidate_fields() -> None:
    cls = getattr(planning, "GovernedCandidate")
    instance = cls(
        admitted_from_candidate_set=("urn:example:candidate-set-1",),
        governs_candidate=("urn:example:plan-candidate-1", "urn:example:plan-candidate-3"),
    )
    assert instance.admitted_from_candidate_set == ("urn:example:candidate-set-1",)
    assert instance.governs_candidate == (
        "urn:example:plan-candidate-1",
        "urn:example:plan-candidate-3",
    )


def test_plan_candidate_fields() -> None:
    cls = getattr(planning, "PlanCandidate")
    instance = cls(candidate_for_trial=("urn:example:trial-1", "urn:example:trial-2"))
    assert instance.candidate_for_trial == ("urn:example:trial-1", "urn:example:trial-2")


def test_planner_has_no_fields_but_constructs_a_real_instance() -> None:
    cls = getattr(planning, "Planner")
    instance = cls()
    assert isinstance(instance, cls)
    assert dataclasses.fields(instance) == ()


def test_planner_attempt_fields() -> None:
    cls = getattr(planning, "PlannerAttempt")
    instance = cls(
        attempted_by=("urn:example:planner-1",),
        produced_candidate=("urn:example:plan-candidate-1",),
        solves_problem=("urn:example:planning-problem-1",),
    )
    assert instance.attempted_by == ("urn:example:planner-1",)
    assert instance.produced_candidate == ("urn:example:plan-candidate-1",)
    assert instance.solves_problem == ("urn:example:planning-problem-1",)


def test_planning_problem_has_no_fields_but_constructs_a_real_instance() -> None:
    cls = getattr(planning, "PlanningProblem")
    instance = cls()
    assert isinstance(instance, cls)
    assert dataclasses.fields(instance) == ()


def test_validation_fields() -> None:
    cls = getattr(planning, "Validation")
    instance = cls(validates_candidate=("urn:example:plan-candidate-1",))
    assert instance.validates_candidate == ("urn:example:plan-candidate-1",)


def test_every_name_in_all_is_constructible_with_all_fields_filled() -> None:
    """Generic sweep over `planning.__all__`: getattr the class, build a real
    instance with every real dataclass field explicitly filled with a
    representative (non-default) value, and assert on the real resulting
    field values -- not merely that construction succeeded."""
    for name in planning.__all__:
        cls = getattr(planning, name)
        assert dataclasses.is_dataclass(cls)

        kwargs = {}
        for field in dataclasses.fields(cls):
            if field.type == "tuple[str, ...]":
                kwargs[field.name] = (f"urn:example:{name.lower()}-{field.name}-1",)
            else:  # pragma: no cover - every field in this module is tuple[str, ...]
                raise AssertionError(
                    f"unexpected field type {field.type!r} on {name}.{field.name}; "
                    "this test must be extended, not skipped"
                )

        instance = cls(**kwargs)

        for field in dataclasses.fields(cls):
            assert getattr(instance, field.name) == kwargs[field.name]


def test_every_dataclass_in_all_is_frozen() -> None:
    """Every class in `planning.__all__` is a frozen dataclass: attempting to
    mutate any field after construction raises `dataclasses.FrozenInstanceError`
    for each and every one, not just a single representative class."""
    for name in planning.__all__:
        cls = getattr(planning, name)
        fields = dataclasses.fields(cls)
        if fields:
            kwargs = {f.name: (f"urn:example:{name.lower()}-{f.name}-frozen",) for f in fields}
            instance = cls(**kwargs)
            target_field = fields[0].name
        else:
            instance = cls()
            target_field = None

        if target_field is not None:
            try:
                setattr(instance, target_field, ("urn:example:mutated",))
            except dataclasses.FrozenInstanceError:
                pass
            else:
                raise AssertionError(f"{name} is not frozen: mutation of {target_field} succeeded")
        else:
            # No real field to mutate on this class; still prove frozen-ness
            # by attempting to set an attribute that isn't declared at all.
            try:
                setattr(instance, "not_a_real_field", "x")
            except dataclasses.FrozenInstanceError:
                pass
            else:
                raise AssertionError(f"{name} is not frozen: setattr of a new attribute succeeded")


def test_candidate_set_is_frozen_dataclasses_frozen_instance_error() -> None:
    """Explicit, single-class demonstration (in addition to the sweep above)
    that mutating a real constructed instance raises
    `dataclasses.FrozenInstanceError`, exactly as required."""
    instance = planning.CandidateSet(
        contains_candidate=("urn:example:plan-candidate-1",),
        records_disagreement=("urn:example:disagreement-1",),
    )
    try:
        instance.contains_candidate = ("urn:example:mutated",)
    except dataclasses.FrozenInstanceError:
        pass
    else:
        raise AssertionError("CandidateSet.contains_candidate mutation should have raised")

    # Real state is unchanged after the raised mutation attempt.
    assert instance.contains_candidate == ("urn:example:plan-candidate-1",)
