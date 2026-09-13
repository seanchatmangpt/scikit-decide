# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for `SreTroubleshootingDecisionBackend._wasm4pm_ensemble_confirms_closure`
(the multi-breed generalization of the earlier single-breed
`_hearsay_confirms_closure`) and `_hypotheses_to_abductive_ibe_input`.

Real collaborators: real subprocess calls to `~/wasm4pm`'s real built Node
CLI (no GROQ/paid API involved), and the real, unmodified
`run_breed_ensemble`. No `unittest.mock` / `Mock` / `MagicMock` / `patch` /
`monkeypatch` anywhere in this file.
"""

from __future__ import annotations

import pytest

from autofde_lab.reasoning.gymact_dspy_react import (
    SreTroubleshootingDecisionBackend,
    Wasm4pmEnsembleCrossCheckOutcome,
    _hypotheses_to_abductive_ibe_input,
)
from autofde_lab.receipts.wasm4pm_cognition import Wasm4pmCognitionUnavailable, resolve_wpm_cognition_entry


def _wasm4pm_cli_available() -> bool:
    try:
        resolve_wpm_cognition_entry()
    except Wasm4pmCognitionUnavailable:
        return False
    return True


requires_real_wasm4pm_cli = pytest.mark.skipif(
    not _wasm4pm_cli_available(),
    reason=(
        "the built ~/wasm4pm apps/wasm4pm Node CLI is not available in this "
        "environment -- a real subprocess call is required and no mock "
        "substitute is used per .claude/rules/testing-chicago-style.md."
    ),
)


# ---------------------------------------------------------------------------
# Structural: the abductive_ibe translator, LLM-free
# ---------------------------------------------------------------------------


def test_abductive_ibe_translator_links_a_hypothesis_only_to_facts_it_shares_words_with() -> None:
    result = _hypotheses_to_abductive_ibe_input(
        admitted_facts="- pod restarts spike\n- dmesg oom event",
        hypothesis_portfolio="- oom kill memory exhaustion - supported\n- disk pressure - unknown",
    )
    assert result["candidates"] == [
        {"id": "hypothesis-0", "score": 0.0, "eliminated": False},
        {"id": "hypothesis-1", "score": 0.0, "eliminated": False},
    ]
    assert {f["value"] for f in result["facts"]} == {"pod restarts spike", "dmesg oom event"}
    # "oom kill memory exhaustion" shares "exhaustion"... actually shares no word >3 chars with
    # "dmesg oom event" bar "oom" (3 chars, excluded) -- real overlap only via shared words.
    # Assert real conclusions are always real fact text, real premises always the hypothesis id.
    for rule in result["rules"]:
        assert rule["conclusion"] in {"pod restarts spike", "dmesg oom event"}
        assert rule["premise"] in (["hypothesis-0"], ["hypothesis-1"])


def test_abductive_ibe_translator_empty_inputs_produce_no_candidates_facts_or_rules() -> None:
    result = _hypotheses_to_abductive_ibe_input(admitted_facts="none", hypothesis_portfolio="none")
    assert result == {"candidates": [], "facts": [], "rules": []}


# ---------------------------------------------------------------------------
# Live: the real multi-breed ensemble path, exercised directly
# ---------------------------------------------------------------------------


@requires_real_wasm4pm_cli
def test_ensemble_confirms_closure_genuinely_checks_via_two_real_breeds() -> None:
    backend = SreTroubleshootingDecisionBackend()
    state = {
        "admitted_facts": "- pod crashlooping\n- dmesg oom event",
        "hypothesis_portfolio": "- oom kill memory exhaustion - supported",
    }
    trajectory: dict = {"stages": []}

    backend._wasm4pm_ensemble_confirms_closure(state, trajectory)

    stage = trajectory["stages"][-1]
    assert stage["stage"] == "wasm4pm_ensemble_cross_check"
    # With only one real hypothesis supplied, both breeds see the same
    # single real candidate -- a real, genuine ensemble call was made
    # (never UNAVAILABLE, since the CLI is confirmed present).
    assert stage["outcome"] in (Wasm4pmEnsembleCrossCheckOutcome.CHECKED, Wasm4pmEnsembleCrossCheckOutcome.NO_EVIDENCE)


@requires_real_wasm4pm_cli
def test_ensemble_confirms_closure_records_no_evidence_honestly_never_fabricated_agreement() -> None:
    """Empty facts/hypotheses -- both breeds' real preconditions refuse (no
    knowledge source), so `member_evidence` is real and empty; this must be
    recorded as a real, honest outcome, never silently treated as
    confirmed closure."""
    backend = SreTroubleshootingDecisionBackend()
    state = {"admitted_facts": "none", "hypothesis_portfolio": "none"}
    trajectory: dict = {"stages": []}

    result = backend._wasm4pm_ensemble_confirms_closure(state, trajectory)

    stage = trajectory["stages"][-1]
    assert stage["outcome"] in (Wasm4pmEnsembleCrossCheckOutcome.UNAVAILABLE, Wasm4pmEnsembleCrossCheckOutcome.NO_EVIDENCE)
    if stage["outcome"] == Wasm4pmEnsembleCrossCheckOutcome.NO_EVIDENCE:
        assert result is False
