# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for `laboratory`'s DOE (Design of Experiments)
full-factorial candidate generation module (section 15). Real
collaborators throughout: real `DesiredStateHypothesis` instances
constructed directly, real `generate_full_factorial_design`/
`generate_doe_candidates` calls, real returned `DOEDesignPoint`/
`ArchitectureCandidate` state asserted on. No `unittest.mock` / `Mock` /
`MagicMock` / `patch` / `monkeypatch` anywhere in this file.

Honestly scoped: this module covers exactly ONE real design -- a 2^2
full factorial over `COST_BOUND` and `AUTHORITY_NEEDS`, both
caller-supplied. No fractional-factorial, Taguchi, or interaction-effect
analysis is covered; see the module-level NOT COVERED note in
`laboratory.py` section 15.
"""

from __future__ import annotations

from autofde_lab.reasoning.laboratory import (
    ArchitectureCandidate,
    DesiredStateHypothesis,
    DOEDesignPoint,
    DOEFactor,
    DOELevel,
    generate_doe_candidates,
    generate_full_factorial_design,
)

COST_LEVELS = (10.0, 100.0)
AUTHORITY_LEVELS = (("read",), ("read", "write", "admin"))


def test_generate_full_factorial_design_emits_exactly_four_real_points() -> None:
    design = generate_full_factorial_design(COST_LEVELS, AUTHORITY_LEVELS)

    assert len(design) == 4
    for point in design:
        assert isinstance(point, DOEDesignPoint)
        assert len(point.levels) == 2
        cost_level, authority_level = point.levels
        assert cost_level.factor == DOEFactor.COST_BOUND
        assert authority_level.factor == DOEFactor.AUTHORITY_NEEDS

    combos = {(p.levels[0].level_id, p.levels[1].level_id) for p in design}
    assert combos == {("LOW", "LOW"), ("LOW", "HIGH"), ("HIGH", "LOW"), ("HIGH", "HIGH")}

    # run_id is a real, deterministic digest -- distinct per combination
    assert len({p.run_id for p in design}) == 4


def test_generate_full_factorial_design_levels_carry_real_caller_values() -> None:
    design = generate_full_factorial_design(COST_LEVELS, AUTHORITY_LEVELS)

    by_combo = {(p.levels[0].level_id, p.levels[1].level_id): p for p in design}
    low_low = by_combo[("LOW", "LOW")]
    assert low_low.levels[0].cost_value == 10.0
    assert low_low.levels[1].authority_value == ("read",)

    high_high = by_combo[("HIGH", "HIGH")]
    assert high_high.levels[0].cost_value == 100.0
    assert high_high.levels[1].authority_value == ("read", "write", "admin")


def test_generate_full_factorial_design_is_deterministic() -> None:
    design_1 = generate_full_factorial_design(COST_LEVELS, AUTHORITY_LEVELS)
    design_2 = generate_full_factorial_design(COST_LEVELS, AUTHORITY_LEVELS)

    assert tuple(p.run_id for p in design_1) == tuple(p.run_id for p in design_2)


def test_generate_doe_candidates_emits_one_real_candidate_per_design_point() -> None:
    hypothesis = DesiredStateHypothesis(
        hypothesis_id="rule-based-v1",
        targets=({"kind": "latency_reduction"},),
        evidence_used_refs=("obs-1",),
        assumptions=("objectives read directly from admitted ScenarioMetadata",),
    )
    candidates = generate_doe_candidates((hypothesis,), COST_LEVELS, AUTHORITY_LEVELS)

    assert len(candidates) == 4
    for candidate in candidates:
        assert isinstance(candidate, ArchitectureCandidate)
        assert candidate.provenance == "doe-v1"
        assert candidate.generator_identity == "doe-full-factorial-2x2"
        assert candidate.target_state_assertions == ("{'kind': 'latency_reduction'}",)
        assert candidate.assumptions[1:] == hypothesis.assumptions
        assert candidate.assumptions[0].startswith("DOE design point ")
        assert candidate.cost_bound in COST_LEVELS
        assert candidate.authority_needs in AUTHORITY_LEVELS

    # candidate_id is a real, deterministic digest -- distinct per design point
    assert len({c.candidate_id for c in candidates}) == 4


def test_generate_doe_candidates_is_plural_across_multiple_hypotheses() -> None:
    hypotheses = (
        DesiredStateHypothesis(
            hypothesis_id="h1",
            targets=({"kind": "latency_reduction"},),
            evidence_used_refs=("obs-1",),
        ),
        DesiredStateHypothesis(
            hypothesis_id="h2",
            targets=({"kind": "cost_reduction"},),
            evidence_used_refs=("obs-2",),
        ),
    )
    candidates = generate_doe_candidates(hypotheses, COST_LEVELS, AUTHORITY_LEVELS)

    assert len(candidates) == 8
    assert len({c.candidate_id for c in candidates}) == 8


def test_doe_level_is_a_real_frozen_dataclass_instance() -> None:
    level = DOELevel(factor=DOEFactor.COST_BOUND, level_id="LOW", cost_value=10.0)
    assert level.factor == DOEFactor.COST_BOUND
    assert level.level_id == "LOW"
    assert level.cost_value == 10.0
    assert level.authority_value is None
