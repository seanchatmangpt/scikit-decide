from autofde_lab.fabric.self_play import (
    manufacture_boundary_adversaries,
    manufacture_scenarios,
)


def admits(values):
    return not (values.get("authority") == "none" and values.get("effect") == "write")


def test_cartesian_self_play_preserves_all_lawful_combinations():
    rows = manufacture_scenarios(
        {
            "authority": ("read", "write", "none"),
            "effect": ("read", "write"),
        },
        admits=admits,
    )
    assert len(rows) == 5
    assert len({row.scenario_id for row in rows}) == 5
    assert all(admits(row.values) for row in rows)


def test_generation_is_deterministic_and_explicitly_bounded():
    dimensions = {"b": (2, 1), "a": ("x", "y")}
    first = manufacture_scenarios(dimensions, max_scenarios=3)
    second = manufacture_scenarios(dimensions, max_scenarios=3)
    assert first == second
    assert len(first) == 3


def test_adversaries_are_rejected_boundary_subjects_not_executable_authority():
    lawful = manufacture_scenarios(
        {"authority": ("read",), "effect": ("read", "write")}, admits=admits
    )
    adversaries = manufacture_boundary_adversaries(
        lawful,
        forbidden_mutations={"authority": "none"},
        admits=admits,
    )
    assert adversaries
    assert all(row.adversarial for row in adversaries)
    assert all(not admits(row.values) for row in adversaries)
