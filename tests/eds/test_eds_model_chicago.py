# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for `autofde_lab.eds` -- the Executable Research
Claim (ERC) model from `docs/2026-09-12-executable-design-science.md`.

Real collaborators throughout: a real `git` subprocess for source identity,
a real `pytest` subprocess for the bound receipt (this session's actual
cap-11 test suite, `tests/planning/test_fond_hddl_product.py`, already
merged to master), and real callables for every falsifier -- no
`unittest.mock` / `Mock` / `MagicMock` / `patch` / `monkeypatch` anywhere in
this file.

This file is itself a worked ERC: the hypothesis is "this module correctly
distinguishes IMPLEMENTED / BLOCKED / UNKNOWN / VERIFIED / FALSIFIED given
real receipts and real falsifiers, never collapsing them" -- and every test
below is a real execution against that hypothesis, not a description of one.
"""

from __future__ import annotations

import subprocess

import pytest

from autofde_lab.eds import (
    EvidenceState,
    ExecutableResearchClaim,
    Falsifier,
    git_commit_identity,
    run_shell_receipt,
    verify_claim,
)


def test_proposed_state_has_no_artifact_and_no_receipts():
    claim = ExecutableResearchClaim(hypothesis="a bare hypothesis", artifact_ref="")
    state, results = verify_claim(claim)
    assert state == EvidenceState.PROPOSED
    assert results == ()  # no falsifiers were even declared


def test_implemented_state_has_artifact_but_no_receipts():
    """An artifact existing in this real repo is not, by itself, evidence
    for a claim about it -- IMPLEMENTED, never VERIFIED, until a receipt is
    bound."""

    claim = ExecutableResearchClaim(
        hypothesis="the FOND x HDDL product module exists",
        artifact_ref="src/autofde_lab/planning/fond_hddl_product.py",
    )
    state, _ = verify_claim(claim)
    assert state == EvidenceState.IMPLEMENTED


def test_real_receipt_binds_exact_git_commit_identity():
    """git_commit_identity runs a real `git rev-parse HEAD` against this
    real repo -- a real 40-hex-char SHA (optionally +dirty), not a
    placeholder."""

    identity = git_commit_identity(".")
    sha_part = identity.removesuffix("+dirty")
    assert len(sha_part) == 40
    assert all(c in "0123456789abcdef" for c in sha_part)

    # Cross-checked against the real git CLI directly, independent of the
    # module under test.
    real_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    assert sha_part == real_sha


def test_verified_state_from_a_real_passing_receipt_and_real_falsifiers():
    """A real receipt from actually running this session's cap-11 test
    suite (already merged to master, 5 real Chicago tests), plus real
    falsifiers that genuinely hold against this repo right now, must
    produce VERIFIED -- not IMPLEMENTED, not UNKNOWN."""

    receipt = run_shell_receipt(
        [
            ".venv/bin/python",
            "-m",
            "pytest",
            "tests/planning/test_fond_hddl_product.py",
            "-q",
        ],
        repo_root=".",
        timeout_s=120,
    )
    assert receipt.succeeded, f"real pytest run failed: {receipt.stderr_tail}"

    falsifiers = (
        Falsifier(
            description="pytest reported a real, observed pass (0 failures)",
            check=lambda: "failed" not in receipt.stdout_tail.lower(),
        ),
        Falsifier(
            description="the bound receipt's source commit is a real 40-char SHA",
            check=lambda: len(receipt.source_commit.removesuffix("+dirty")) == 40,
        ),
    )

    claim = ExecutableResearchClaim(
        hypothesis=(
            "the FOND x HDDL product's deterministic-reduction, flat-FOND-reduction, "
            "frontier-rejection, and fairness-typing falsifiers hold on real master"
        ),
        artifact_ref="src/autofde_lab/planning/fond_hddl_product.py",
        falsifiers=falsifiers,
    ).with_receipt(receipt)

    state, falsifier_results = verify_claim(claim)
    assert state == EvidenceState.VERIFIED
    assert all(r.ran and r.survived for r in falsifier_results)


def test_blocked_state_from_a_real_failing_receipt():
    """A real subprocess that genuinely fails (a real nonzero exit code)
    must produce BLOCKED, regardless of any falsifier -- a broken execution
    is never silently reported as a passing or unknown claim."""

    receipt = run_shell_receipt(
        [".venv/bin/python", "-c", "import sys; sys.exit(7)"],
        repo_root=".",
        timeout_s=10,
    )
    assert receipt.exit_code == 7  # real, observed exit code

    claim = ExecutableResearchClaim(
        hypothesis="a deliberately failing command still yields honest evidence",
        artifact_ref="n/a",
    ).with_receipt(receipt)

    state, _ = verify_claim(claim)
    assert state == EvidenceState.BLOCKED


def test_falsified_state_beats_a_clean_receipt():
    """A real passing receipt combined with a real falsifier that genuinely
    fails must report FALSIFIED, not VERIFIED -- a green test suite never
    overrules a real falsifier that fired (paper S19's central point)."""

    receipt = run_shell_receipt(
        [".venv/bin/python", "-c", "print('ok')"], repo_root=".", timeout_s=10
    )
    assert receipt.succeeded

    claim = ExecutableResearchClaim(
        hypothesis="2 + 2 == 5 (a deliberately false claim to prove FALSIFIED wins)",
        artifact_ref="n/a",
        falsifiers=(Falsifier(description="2 + 2 == 5", check=lambda: 2 + 2 == 5),),
    ).with_receipt(receipt)

    state, falsifier_results = verify_claim(claim)
    assert state == EvidenceState.FALSIFIED
    assert falsifier_results[0].ran is True
    assert falsifier_results[0].survived is False


def test_unknown_state_when_a_falsifier_cannot_be_evaluated():
    """A falsifier whose real check() raises must yield UNKNOWN, never be
    silently treated as surviving (absence-is-not-evidence.md's law,
    applied to research claims: an unevaluated falsifier is not a
    passed falsifier)."""

    receipt = run_shell_receipt(
        [".venv/bin/python", "-c", "print('ok')"], repo_root=".", timeout_s=10
    )
    assert receipt.succeeded

    def _broken_check() -> bool:
        raise RuntimeError("cannot evaluate this falsifier in this environment")

    claim = ExecutableResearchClaim(
        hypothesis="a claim whose one falsifier cannot currently be checked",
        artifact_ref="n/a",
        falsifiers=(
            Falsifier(description="an unevaluable check", check=_broken_check),
        ),
    ).with_receipt(receipt)

    state, falsifier_results = verify_claim(claim)
    assert state == EvidenceState.UNKNOWN
    assert falsifier_results[0].ran is False
    assert falsifier_results[0].survived is None
    assert falsifier_results[0].error is not None


def test_falsifier_rejects_a_non_callable_check():
    """Paper S9: a falsifier with no real executable check is a
    description, not a falsifier. This type refuses to represent one."""

    with pytest.raises(TypeError):
        Falsifier(description="not actually checkable", check="not a function")  # type: ignore[arg-type]


def test_with_receipt_never_mutates_the_original_claim():
    """Frozen-by-extension: appending a receipt returns a new claim object;
    the original's receipt tuple is untouched (no-dual-bookkeeping applied
    to a claim's own evidence history)."""

    receipt = run_shell_receipt(
        [".venv/bin/python", "-c", "print('ok')"], repo_root=".", timeout_s=10
    )
    original = ExecutableResearchClaim(hypothesis="h", artifact_ref="a")
    extended = original.with_receipt(receipt)

    assert original.receipts == ()
    assert extended.receipts == (receipt,)
    assert original is not extended
