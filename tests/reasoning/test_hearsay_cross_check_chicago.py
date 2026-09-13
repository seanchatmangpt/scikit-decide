# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for `autofde_lab.reasoning.hearsay_cross_check`.

Real collaborators throughout: real bullet-line parsing, real
`hypotheses_agree` heuristic computation, and (for the live cases) a real
subprocess call to `~/wasm4pm`'s real, built Node CLI running the real
Hearsay-II breed -- named `skipif` when the CLI isn't built, never a mock
substitute, per `.claude/rules/testing-chicago-style.md`. No paid API is
involved (this is a local subprocess, not an LM call), so the live cases run
freely in this suite.

No `unittest.mock` / `Mock` / `MagicMock` / `patch` / `monkeypatch` anywhere
in this file.
"""

from __future__ import annotations

import asyncio

import pytest

from autofde_lab.reasoning.hearsay_cross_check import (
    AgreementOutcome,
    HypothesisState,
    NoEvidence,
    cross_check_via_hearsay,
    hypotheses_agree,
    hypotheses_to_breed_input,
)
from autofde_lab.receipts.wasm4pm_cognition import (
    CognitionEvidence,
    Wasm4pmCognitionUnavailable,
    resolve_wpm_cognition_entry,
)

# ---------------------------------------------------------------------------
# Structural: the pure, LLM-free translator, real wire grammar (see
# hearsay_cross_check.py's own module docstring for the real Rust contract
# this was built against, confirmed live -- not the earlier, non-firing
# design).
# ---------------------------------------------------------------------------


def test_translator_facts_share_one_blackboard_level() -> None:
    """Every admitted fact gets the SAME real key ("fact") so they share one
    blackboard level -- what makes the real "fact-hypotheses" wildcard
    trigger (see module docstring) match any of them."""
    result = hypotheses_to_breed_input(
        admitted_facts="- pod geo-0 exists\n- status is CrashLoopBackOff",
        hypothesis_portfolio="none",
    )

    assert result["facts"] == [
        {"key": "fact", "value": "pod geo-0 exists"},
        {"key": "fact", "value": "status is CrashLoopBackOff"},
    ]


def test_translator_emits_real_candidates_with_the_real_wire_schema() -> None:
    """The real `Candidate` Rust struct requires `{id, score, eliminated}`
    (confirmed live: `"missing field `score`"`, then `"missing field
    `eliminated`"`) -- passed through unused by Hearsay's own scheduling,
    kept for real schema compliance. `score` is derived from the line's own
    real `HypothesisState`, `eliminated=True` only for a real REFUTED
    classification."""
    result = hypotheses_to_breed_input(
        admitted_facts="- pod geo-0 exists",
        hypothesis_portfolio="- OOMKill - supported\n- config drift - refuted\n- disk pressure - unclear",
    )

    assert result["candidates"] == [
        {"id": "hypothesis-0", "score": 1.0, "eliminated": False},
        {"id": "hypothesis-1", "score": 0.0, "eliminated": True},
        # "unclear" is not one of the three real label words -> UNKNOWN, never SUPPORTED/eliminated.
        {"id": "hypothesis-2", "score": 0.5, "eliminated": False},
    ]


def test_translator_emits_one_real_wildcard_triggered_rule_per_hypothesis() -> None:
    """Each rule's premise is the real "fact-hypotheses" wildcard (fires
    once ANY real fact is seeded, per the real trigger grammar read
    directly from hearsay.rs), its conclusion carries the real hypothesis
    text directly (no separate id-to-text resolution needed), and its
    certainty is derived from the line's own real HypothesisState -- never
    an invented number, and never outside the real Rust `[0,1]` clamp
    range (confirmed live; the TypeScript schema's `-1..1` comment does not
    match the real Rust behavior)."""
    result = hypotheses_to_breed_input(
        admitted_facts="- pod geo-0 exists",
        hypothesis_portfolio="- OOMKill - supported\n- config drift - refuted\n- disk pressure - unclear",
    )

    assert result["rules"] == [
        {"id": "rule-0", "premise": ["fact-hypotheses"], "conclusion": "hypothesis:OOMKill - supported", "certainty": 1.0},
        {"id": "rule-1", "premise": ["fact-hypotheses"], "conclusion": "hypothesis:config drift - refuted", "certainty": 0.0},
        {"id": "rule-2", "premise": ["fact-hypotheses"], "conclusion": "hypothesis:disk pressure - unclear", "certainty": 0.5},
    ]


def test_translator_emits_no_rules_when_there_are_no_facts_to_trigger_on() -> None:
    """The wildcard trigger only ever matches once a real fact exists --
    emitting a rule with nothing to ever trigger it would be dishonest
    (a rule that can never fire), so no rules are emitted at all when
    there are no admitted facts, even if hypotheses are present."""
    result = hypotheses_to_breed_input(admitted_facts="none", hypothesis_portfolio="- OOMKill - supported")
    assert result["rules"] == []


def test_translator_strips_leading_bullet_markers_not_just_whitespace() -> None:
    result = hypotheses_to_breed_input(admitted_facts="- - double-dash edge case", hypothesis_portfolio="none")
    assert result["facts"][0]["value"] == "- double-dash edge case"


def test_translator_ignores_non_bullet_lines() -> None:
    result = hypotheses_to_breed_input(
        admitted_facts="Some preamble text.\n- a real fact\nTrailing note.",
        hypothesis_portfolio="none",
    )
    assert result["facts"] == [{"key": "fact", "value": "a real fact"}]


def test_translator_none_sentinel_produces_no_facts_candidates_or_rules() -> None:
    result = hypotheses_to_breed_input(admitted_facts="none", hypothesis_portfolio="none")
    assert result == {"facts": [], "candidates": [], "rules": []}


def test_translator_empty_string_produces_no_facts_candidates_or_rules() -> None:
    result = hypotheses_to_breed_input(admitted_facts="", hypothesis_portfolio="")
    assert result == {"facts": [], "candidates": [], "rules": []}


# ---------------------------------------------------------------------------
# Structural: the real, approximate agreement heuristic (returns a real
# AgreementOutcome StrEnum, never a bare bool)
# ---------------------------------------------------------------------------


def test_hypotheses_agree_strips_the_real_hypothesis_prefix_before_comparing() -> None:
    """A real Hearsay `selected` value carries the "hypothesis:" prefix
    (see module docstring) -- it must not count as a spurious shared word
    and must not prevent a real match on the remaining text."""
    assert hypotheses_agree(
        hearsay_selected="hypothesis:memory pressure exhaustion",
        committed_root_cause="root cause is memory pressure exhaustion in the container",
    ) == AgreementOutcome.AGREES


def test_hypotheses_agree_agrees_on_partial_but_sufficient_word_overlap() -> None:
    """"OOMKill" (selected) never matches "OOMKilled" (root cause)
    verbatim -- this is a real, literal word check, not stemming/fuzzy
    matching -- but "memory"/"pressure" both do, giving 2/3 real shared
    words, above the real 0.3 overlap threshold."""
    assert hypotheses_agree(
        hearsay_selected="hypothesis:OOMKill memory pressure",
        committed_root_cause="the container was OOMKilled due to memory pressure exhaustion",
    ) == AgreementOutcome.AGREES


def test_hypotheses_agree_disagrees_below_the_real_overlap_threshold() -> None:
    assert hypotheses_agree(
        hearsay_selected="hypothesis:OOMKill readiness timeout scheduler",
        committed_root_cause="the container was OOMKilled due to memory pressure exhaustion",
    ) == AgreementOutcome.DISAGREES  # only 0/4 words match verbatim


def test_hypotheses_agree_disagrees_on_unrelated_text() -> None:
    assert hypotheses_agree(
        hearsay_selected="hypothesis:network dns resolution failure",
        committed_root_cause="the container was OOMKilled due to memory exhaustion",
    ) == AgreementOutcome.DISAGREES


def test_hypotheses_agree_disagrees_on_empty_inputs() -> None:
    assert hypotheses_agree(hearsay_selected=None, committed_root_cause="something") == AgreementOutcome.DISAGREES
    assert hypotheses_agree(hearsay_selected="something", committed_root_cause="") == AgreementOutcome.DISAGREES


# ---------------------------------------------------------------------------
# Structural: HypothesisState classification is a real string enum
# ---------------------------------------------------------------------------


def test_hypothesis_state_is_a_real_string_enum_not_a_bare_string() -> None:
    assert HypothesisState.SUPPORTED == "SUPPORTED"
    assert isinstance(HypothesisState.SUPPORTED, str)


# ---------------------------------------------------------------------------
# Live: real subprocess calls to the real Hearsay-II breed (no paid API)
# ---------------------------------------------------------------------------


def _hearsay_cli_available() -> bool:
    try:
        resolve_wpm_cognition_entry()
    except Wasm4pmCognitionUnavailable:
        return False
    return True


requires_real_hearsay_cli = pytest.mark.skipif(
    not _hearsay_cli_available(),
    reason=(
        "the built ~/wasm4pm apps/wasm4pm Node CLI is not available in this "
        "environment -- a real subprocess call is required and no mock "
        "substitute is used per .claude/rules/testing-chicago-style.md."
    ),
)


@requires_real_hearsay_cli
def test_live_cross_check_genuinely_reasons_and_selects_the_supported_hypothesis() -> None:
    """The real, corrected integration test: Hearsay's real rule-firing
    (not a seed-only tie-break, per this module's earlier, confirmed-broken
    design) genuinely selects the hypothesis this module marked SUPPORTED
    over ones marked UNKNOWN/REFUTED, because that hypothesis's real rule
    posts the highest real certainty."""
    admitted_facts = "- pod geo-0 exists\n- status is CrashLoopBackOff"
    hypothesis_portfolio = (
        "- OOMKill memory exhaustion - supported\n"
        "- config drift - unknown\n"
        "- liveness probe failure - refuted"
    )

    evidence = asyncio.run(
        cross_check_via_hearsay(admitted_facts=admitted_facts, hypothesis_portfolio=hypothesis_portfolio)
    )

    assert isinstance(evidence, CognitionEvidence)
    assert evidence.breed == "hearsay"
    assert evidence.status == "ok"
    assert evidence.run_id
    assert evidence.output_hash

    # Real evidence of genuine rule-firing, not a seed-only tie-break.
    kinds = {step["kind"] for step in evidence.inference_trace}
    assert "post-hypothesis" in kinds

    # The real selection is the real SUPPORTED hypothesis, not an
    # alphabetically-tied raw fact.
    assert evidence.selected == "hypothesis:OOMKill memory exhaustion - supported"

    agreement = hypotheses_agree(
        hearsay_selected=evidence.selected,
        committed_root_cause="the geo pod is crash-looping due to OOMKill memory exhaustion",
    )
    assert agreement == AgreementOutcome.AGREES


@requires_real_hearsay_cli
def test_live_cross_check_with_no_facts_or_hypotheses_raises_no_evidence() -> None:
    """Real, confirmed live behavior: Hearsay refuses an empty BreedInput
    with a real precondition error ('requires at least one knowledge
    source') -- the 'none' sentinel this backend uses before any real
    evidence has been gathered genuinely has nothing for Hearsay to reason
    over, so this must surface as a real `NoEvidence`, not a fabricated
    success."""
    with pytest.raises(NoEvidence):
        asyncio.run(cross_check_via_hearsay(admitted_facts="none", hypothesis_portfolio="none"))
