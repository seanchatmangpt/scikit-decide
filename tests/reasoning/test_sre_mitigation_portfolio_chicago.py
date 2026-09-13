# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for `autofde_lab.reasoning.sre_mitigation_portfolio`.

Real collaborators throughout: a real, pure step-line parser exercised
directly; a real, hand-written `dspy.Module` subclass (a genuine
implementation of the `dspy.Module.__call__` contract with real,
deterministic, varied output per call -- the one legitimate test-double
pattern this repo already uses for offline/structural DSPy tests, see
`gepa_train.py`'s own reasoning-only modules) standing in for a live LM in
the structural test; and, for the one live case, a real `dspy.LM` call
against Groq -- named `skipif` on `GROQ_API_KEY`, never a mock substitute,
per `.claude/rules/testing-chicago-style.md`.

No `unittest.mock` / `Mock` / `MagicMock` / `patch` / `monkeypatch` anywhere
in this file -- verified by
`grep -rn "unittest.mock\\|Mock(\\|MagicMock\\|patch(\\|monkeypatch" tests/reasoning/test_sre_mitigation_portfolio_chicago.py`.
"""

from __future__ import annotations

import os

import dspy
import pytest

from autofde_lab.powl.algebra import Atom, PartialOrder
from autofde_lab.powl.validate import validate_model
from autofde_lab.reasoning.sre_mitigation_portfolio import (
    MitigationPortfolioCandidate,
    MitigationProcessParseError,
    construct_mitigation_portfolio,
    parse_process_steps,
)
# ---------------------------------------------------------------------------
# Pure, LLM-free unit tests of the step-parser
# ---------------------------------------------------------------------------


def test_parse_process_steps_builds_real_partial_order_of_atoms() -> None:
    text = (
        "READ: describe the current deployment spec\n"
        "DO: patch the deployment memory limit to 512Mi\n"
        "VERIFY: confirm the rollout status is complete\n"
        "VERIFY: confirm the target workload is no longer OOMKilled\n"
    )

    node = parse_process_steps(text)

    assert isinstance(node, PartialOrder)
    assert len(node.children) == 4
    assert all(isinstance(child, Atom) for child in node.children)

    consequences = [child.consequence for child in node.children]
    assert consequences == ["READ", "DO", "VERIFY", "VERIFY"]

    labels = [child.label for child in node.children]
    assert labels == [
        "describe the current deployment spec",
        "patch the deployment memory limit to 512Mi",
        "confirm the rollout status is complete",
        "confirm the target workload is no longer OOMKilled",
    ]

    # Real total chain: step 0 must precede every later step (transitive
    # reduction keeps only the direct 0->1, 1->2, 2->3 edges).
    from autofde_lab.powl.algebra import OrderEdge

    assert node.order == frozenset(
        {OrderEdge(0, 1), OrderEdge(1, 2), OrderEdge(2, 3)}
    )
    assert (0, 3) in {(e.src, e.dst) for e in node.closure}

    # And it is genuinely admitted by the real, independent validator.
    validate_model(node)


def test_parse_process_steps_ignores_blank_lines() -> None:
    text = "\nREAD: check current state\n\nDO: apply the fix\n\n"

    node = parse_process_steps(text)

    assert len(node.children) == 2


def test_parse_process_steps_rejects_fewer_than_two_steps() -> None:
    with pytest.raises(MitigationProcessParseError):
        parse_process_steps("READ: only one step\n")


def test_parse_process_steps_rejects_missing_colon() -> None:
    text = "READ: check current state\nDO patch the deployment\n"

    with pytest.raises(MitigationProcessParseError, match="missing '<CONSEQUENCE>: ' prefix"):
        parse_process_steps(text)


def test_parse_process_steps_rejects_unknown_consequence_tag() -> None:
    text = "READ: check current state\nMAYBE: patch the deployment\n"

    with pytest.raises(MitigationProcessParseError, match="MAYBE"):
        parse_process_steps(text)


def test_parse_process_steps_rejects_empty_description() -> None:
    text = "READ: check current state\nDO: \n"

    with pytest.raises(MitigationProcessParseError, match="empty description"):
        parse_process_steps(text)


def test_parse_process_steps_never_silently_drops_a_malformed_line() -> None:
    """A malformed line among otherwise-valid lines must raise, not be
    quietly skipped while the well-formed lines are kept."""
    text = "READ: check current state\nBOGUS LINE WITH NO TAG\nVERIFY: confirm fixed\n"

    with pytest.raises(MitigationProcessParseError):
        parse_process_steps(text)


# ---------------------------------------------------------------------------
# Structural: construct_mitigation_portfolio using a real, hand-written fake
# dspy.Module (NOT unittest.mock) with real, deterministic, varied output.
# ---------------------------------------------------------------------------


class _RealVariedMitigationProcessModule(dspy.Module):
    """A real `dspy.Module` implementing `ConstructSreMitigationProcess`'s
    contract by hand, returning real, deterministic, but varied
    `process_steps` text per call (cycling through a fixed set of real
    candidate processes). This is the one legitimate test-double pattern
    already used in this repo for offline/structural DSPy tests (see
    `gepa_train.py`'s reasoning-only modules) -- a real object genuinely
    implementing the collaborator's interface, never an
    interaction-verifying mock."""

    _CANDIDATES: tuple[str, ...] = (
        "READ: describe the current deployment spec\n"
        "DO: patch the deployment memory limit to 512Mi\n"
        "VERIFY: confirm the rollout status is complete\n",
        "READ: describe the current pod resource requests\n"
        "DO: increase the memory request to 256Mi\n"
        "DO: increase the memory limit to 512Mi\n"
        "VERIFY: confirm no further OOMKilled restarts occur\n",
        # This third candidate is deliberately malformed to exercise the
        # real skip-on-inadmissible-candidate path in
        # construct_mitigation_portfolio.
        "NOT_A_REAL_TAG: this line cannot be parsed\n",
    )

    def __init__(self) -> None:
        super().__init__()
        self._call_count = 0

    def forward(self, *, root_cause: str, relevant_resource_spec: str, capability_catalog: str) -> dspy.Prediction:
        text = self._CANDIDATES[self._call_count % len(self._CANDIDATES)]
        self._call_count += 1
        return dspy.Prediction(
            process_steps=text,
            expected_consequence="the OOMKilled restarts stop",
            rollback_plan="revert the deployment memory limit/request change",
            safe_to_actuate=True,
        )

    def __call__(self, **kwargs):
        return self.forward(**kwargs)


def test_construct_mitigation_portfolio_returns_real_admitted_candidates() -> None:
    program = _RealVariedMitigationProcessModule()

    portfolio = construct_mitigation_portfolio(
        root_cause="container exceeded its memory limit and was OOMKilled",
        relevant_resource_spec='{"memory_limit": "128Mi", "memory_request": "64Mi"}',
        capability_catalog="read_deployment_spec, patch_deployment_resources, verify_rollout_status",
        portfolio_size=3,
        program=program,
    )

    # Candidate 3 (index 2 -> the malformed one) is skipped, leaving 2 real
    # admitted candidates from the 3 real calls made.
    assert program._call_count == 3
    assert len(portfolio) == 2

    for candidate in portfolio:
        assert isinstance(candidate, MitigationPortfolioCandidate)
        assert isinstance(candidate.node, PartialOrder)
        validate_model(candidate.node)  # each returned candidate is independently admitted
        # The real prediction's safety fields survive, not discarded.
        assert candidate.safe_to_actuate is True
        assert candidate.expected_consequence == "the OOMKilled restarts stop"
        assert candidate.rollback_plan == "revert the deployment memory limit/request change"

    # The two admitted candidates are genuinely different processes (a real
    # portfolio, not padded duplicates).
    assert portfolio[0].node.children != portfolio[1].node.children


def test_construct_mitigation_portfolio_makes_exactly_portfolio_size_real_calls() -> None:
    program = _RealVariedMitigationProcessModule()

    construct_mitigation_portfolio(
        root_cause="x",
        relevant_resource_spec="y",
        capability_catalog="z",
        portfolio_size=5,
        program=program,
    )

    assert program._call_count == 5


def test_construct_mitigation_portfolio_rejects_invalid_portfolio_size() -> None:
    with pytest.raises(ValueError):
        construct_mitigation_portfolio(
            root_cause="x",
            relevant_resource_spec="y",
            capability_catalog="z",
            portfolio_size=0,
        )


# ---------------------------------------------------------------------------
# Live Groq end-to-end
# ---------------------------------------------------------------------------

_GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

requires_real_groq_key = pytest.mark.skipif(
    not _GROQ_API_KEY,
    reason=(
        "GROQ_API_KEY is not set in this environment -- a real live Groq "
        "call is required for this test and no mock substitute is used "
        "per .claude/rules/testing-chicago-style.md."
    ),
)


@requires_real_groq_key
def test_live_construct_mitigation_portfolio_produces_real_admitted_candidates() -> None:
    """Real, live: makes real Groq LM calls (model
    'groq/openai/gpt-oss-120b', max_tokens=16000 -- this exact combination
    was found necessary this session; gpt-oss-20b has a confirmed
    tool-choice incompatibility bug) and asserts the real portfolio is
    non-empty and every member independently passes `validate_model`."""
    lm = dspy.LM("groq/openai/gpt-oss-120b", api_key=_GROQ_API_KEY, cache=False, max_tokens=16000)

    with dspy.context(lm=lm):
        portfolio = construct_mitigation_portfolio(
            root_cause="the geo service container exceeded its memory limit and was OOMKilled",
            relevant_resource_spec='{"memory_limit": "128Mi", "memory_request": "64Mi", "restartCount": 12}',
            capability_catalog="read_deployment_spec, patch_deployment_resources, verify_rollout_status",
            portfolio_size=3,
        )

    assert len(portfolio) > 0
    for candidate in portfolio:
        assert isinstance(candidate, MitigationPortfolioCandidate)
        validate_model(candidate.node)
