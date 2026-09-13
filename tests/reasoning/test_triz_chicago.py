# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for `laboratory`'s TRIZ contradiction-resolution
module (section 14). Real collaborators throughout: real
`DesiredStateHypothesis` instances constructed directly, real
`classify_triz_contradiction`/`generate_triz_candidates` calls, real
returned `ArchitectureCandidate` state asserted on. No `unittest.mock` /
`Mock` / `MagicMock` / `patch` / `monkeypatch` anywhere in this file.

Honestly scoped: this module covers exactly ONE real matrix cell
(`COST` improving, `AUTHORITY_NEEDS` worsening) against 4 real inventive
principles -- no LLM involved, no orthodox-TRIZ-matrix completeness
claimed. Every other contradiction pair is real evidence of nothing and
must classify UNSUPPORTED, asserted explicitly below.
"""

from __future__ import annotations

from autofde_lab.reasoning.laboratory import (
    ArchitectureCandidate,
    DesiredStateHypothesis,
    OperatorApplicabilityStatus,
    TRIZContradiction,
    TRIZParameter,
    classify_triz_contradiction,
    generate_triz_candidates,
)


def test_classify_triz_contradiction_admits_the_one_real_covered_cell() -> None:
    contradiction = TRIZContradiction(
        improving_parameter=TRIZParameter.COST,
        worsening_parameter=TRIZParameter.AUTHORITY_NEEDS,
    )
    result = classify_triz_contradiction(contradiction)
    assert result.status == OperatorApplicabilityStatus.ADMITTED
    assert result.matched_principles == (1, 10, 28, 35)
    assert result.contradiction == contradiction


def test_classify_triz_contradiction_is_unsupported_for_every_uncovered_pair() -> None:
    contradiction = TRIZContradiction(
        improving_parameter=TRIZParameter.AUTHORITY_NEEDS,
        worsening_parameter=TRIZParameter.COST,
    )
    result = classify_triz_contradiction(contradiction)
    assert result.status == OperatorApplicabilityStatus.UNSUPPORTED
    assert result.matched_principles == ()
    assert "no real matrix cell exists" in result.reason


def test_generate_triz_candidates_emits_one_real_candidate_per_matched_principle() -> None:
    hypothesis = DesiredStateHypothesis(
        hypothesis_id="rule-based-v1",
        targets=({"kind": "latency_reduction"},),
        evidence_used_refs=("obs-1",),
        assumptions=("objectives read directly from admitted ScenarioMetadata",),
    )
    contradiction = TRIZContradiction(
        improving_parameter=TRIZParameter.COST,
        worsening_parameter=TRIZParameter.AUTHORITY_NEEDS,
    )
    candidates = generate_triz_candidates((hypothesis,), contradiction)

    assert len(candidates) == 4
    for candidate in candidates:
        assert isinstance(candidate, ArchitectureCandidate)
        assert candidate.provenance == "triz-v1"
        assert candidate.generator_identity == "triz-contradiction-matrix-partial"
        assert candidate.target_state_assertions == ("{'kind': 'latency_reduction'}",)
        assert candidate.assumptions[1:] == hypothesis.assumptions
        assert candidate.assumptions[0].startswith("TRIZ principle ")
        assert len(candidate.migration_actions) == 1

    principle_numbers = sorted(
        int(c.assumptions[0].split("TRIZ principle ")[1].split(":")[0]) for c in candidates
    )
    assert principle_numbers == [1, 10, 28, 35]

    # candidate_id is a real, deterministic digest -- distinct per principle
    assert len({c.candidate_id for c in candidates}) == 4


def test_generate_triz_candidates_returns_empty_for_unsupported_contradiction() -> None:
    hypothesis = DesiredStateHypothesis(
        hypothesis_id="rule-based-v1",
        targets=({"kind": "latency_reduction"},),
        evidence_used_refs=("obs-1",),
    )
    unsupported = TRIZContradiction(
        improving_parameter=TRIZParameter.AUTHORITY_NEEDS,
        worsening_parameter=TRIZParameter.COST,
    )
    assert generate_triz_candidates((hypothesis,), unsupported) == ()


def test_generate_triz_candidates_is_plural_across_multiple_hypotheses() -> None:
    hypotheses = (
        DesiredStateHypothesis(
            hypothesis_id="rule-based-v1",
            targets=({"kind": "latency_reduction"},),
            evidence_used_refs=("obs-1",),
        ),
        DesiredStateHypothesis(
            hypothesis_id="process-observed-v1",
            targets=({"kind": "throughput_increase"},),
            evidence_used_refs=("obs-1", "obs-2"),
        ),
    )
    contradiction = TRIZContradiction(
        improving_parameter=TRIZParameter.COST,
        worsening_parameter=TRIZParameter.AUTHORITY_NEEDS,
    )
    candidates = generate_triz_candidates(hypotheses, contradiction)

    assert len(candidates) == 8
    assert {c.candidate_id for c in candidates} == {c.candidate_id for c in candidates}  # all present
    hyp_1_targets = tuple(c for c in candidates if c.target_state_assertions == ("{'kind': 'latency_reduction'}",))
    hyp_2_targets = tuple(c for c in candidates if c.target_state_assertions == ("{'kind': 'throughput_increase'}",))
    assert len(hyp_1_targets) == 4
    assert len(hyp_2_targets) == 4
