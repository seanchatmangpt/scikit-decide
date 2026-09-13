# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for the ``~/wasm4pm`` cognition kernel bridge
(:mod:`autofde_lab.receipts.wasm4pm_cognition`).

Real collaborators throughout: a real ``node`` subprocess running the real,
built ``apps/wasm4pm`` CLI, which loads and executes the real wasm-bindgen
cognition kernel (the ``ebl`` breed's actual Horn-clause/EBL implementation,
not a stub). No ``unittest.mock``/``monkeypatch`` substitution of the
subprocess, the CLI, or the WASM module anywhere in this file.

Skipped (not failed) when the sibling ``~/wasm4pm`` checkout isn't built --
mirrors ``test_mcp_ocel_instrumentation_chicago.py``'s
``pytest.importorskip("fastmcp")`` pattern for an optional real dependency.
"""

from __future__ import annotations

import asyncio

import pytest

from autofde_lab.receipts.wasm4pm_cognition import (
    CognitionEvidence,
    NoEvidence,
    Wasm4pmCognitionUnavailable,
    resolve_wpm_cognition_entry,
    run_cognition,
    verify_cognition_evidence,
)

try:
    resolve_wpm_cognition_entry()
    _WASM4PM_COGNITION_AVAILABLE = True
except Wasm4pmCognitionUnavailable:
    _WASM4PM_COGNITION_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not _WASM4PM_COGNITION_AVAILABLE,
    reason="no built ~/wasm4pm/apps/wasm4pm CLI found (build with 'pnpm build' there)",
)

# A real EBL (Explanation-Based Learning, Mitchell/Keller/Kedar-Cabelli 1986)
# problem: given the domain rules "cup(x) => drinkable(x)" and
# "has_handle(y) & concave(y) => cup(y)", and the fact that obj1 has a handle
# and is concave, EBL should operationalize a direct rule for the goal
# "drinkable(obj1)". Matches ``minimalEblInput`` in
# ``packages/cognition/src/__tests__/fixtures/breed-inputs.ts``.
_EBL_FACTS = [
    {"key": "has_handle(obj1)", "value": "true"},
    {"key": "concave(obj1)", "value": "true"},
]
_EBL_RULES = [
    {"id": "r1", "premise": ["cup(?x)"], "conclusion": "drinkable(?x)", "certainty": 1.0},
    {
        "id": "r2",
        "premise": ["has_handle(?y)", "concave(?y)"],
        "conclusion": "cup(?y)",
        "certainty": 1.0,
    },
]
_EBL_GOALS = [{"id": "g1", "predicate": "drinkable(obj1)", "value": "true"}]


def test_real_ebl_breed_run_returns_verifiable_evidence():
    """A real, successful cognition run returns typed evidence whose receipt
    verifies against a real BLAKE3 re-derivation -- not a canned fixture."""

    async def run():
        return await run_cognition(
            "ebl", intent="learn", facts=_EBL_FACTS, rules=_EBL_RULES, goals=_EBL_GOALS
        )

    evidence = asyncio.run(run())

    assert isinstance(evidence, CognitionEvidence)
    assert evidence.breed == "ebl"
    assert evidence.status == "ok"
    assert evidence.selected == "has_handle(?y_g1), concave(?y_g1) => drinkable(?y_g1)"
    assert len(evidence.run_id) == 64  # BLAKE3 hex digest
    assert evidence.replay_pointer == evidence.output_hash[:16]
    assert len(evidence.inference_trace) > 0

    # The bridge already verified internally (default verify=True) before
    # returning -- re-verify independently here as the test's own assertion,
    # not trust in the production code path under test.
    assert verify_cognition_evidence(evidence) is True


def test_tampered_receipt_fails_verification():
    """Mutate one byte of a real receipt's run_id -- verification must fail.

    Mirrors ``tests/autosystems_receipt_v2_collision.rs``'s tamper-proof
    pattern on the Rust side: a receipt is only trustworthy if re-deriving its
    hash from its own claimed inputs reproduces the stored value.
    """

    async def run():
        return await run_cognition(
            "ebl", intent="learn", facts=_EBL_FACTS, rules=_EBL_RULES, goals=_EBL_GOALS
        )

    real_evidence = asyncio.run(run())

    forged_run_id = ("0" if real_evidence.run_id[0] != "0" else "1") + real_evidence.run_id[1:]
    tampered = CognitionEvidence(
        breed=real_evidence.breed,
        run_id=forged_run_id,
        output_hash=real_evidence.output_hash,
        replay_pointer=real_evidence.replay_pointer,
        status=real_evidence.status,
        selected=real_evidence.selected,
        explanation=real_evidence.explanation,
    )

    assert verify_cognition_evidence(real_evidence) is True
    assert verify_cognition_evidence(tampered) is False


def test_unknown_breed_raises_no_evidence_not_empty_default():
    """'Absence is not evidence': an unknown breed must raise, never return a
    quietly-empty/default :class:`CognitionEvidence`."""

    async def run():
        await run_cognition("totally_not_a_real_breed", intent="", facts=[], rules=[], goals=[])

    with pytest.raises(NoEvidence, match="totally_not_a_real_breed"):
        asyncio.run(run())


def test_domain_precondition_failure_raises_no_evidence():
    """A real domain-level rejection (EBL with no goal to explain) surfaces
    as NoEvidence with the real WASM error message included, not a generic
    'process failed' with the actual reason silently dropped."""

    async def run():
        # Same facts/rules as the successful case, but no goal -- EBL's own
        # precondition ("EBL requires at least one goal") must reject this.
        await run_cognition("ebl", intent="learn", facts=_EBL_FACTS, rules=_EBL_RULES, goals=[])

    with pytest.raises(NoEvidence, match="at least one goal"):
        asyncio.run(run())
