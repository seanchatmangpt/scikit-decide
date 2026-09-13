# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style: real `gymact.runtime.GymAct` episodes (real `MemoryProvider`, real
kernel machinery -- no mocks), proving `CrownReceipt.admit()` is a real, enforced gate,
not a decorative type.

Two real proofs (no external infra needed -- see `test_crown_receipt_live_chicago.py`
for the real, `require_standing`-gated SREGym attempt):
1. A `CrownReceipt` missing any single required field is refused, individually, for
   each field -- the literal enforcement of "we are not validating their SOTA until our
   architecture is complete."
2. A deliberately complete `CrownReceipt`, built from a real gymact episode's real OCEL
   log and Receipt trail, is admitted -- proving the schema is satisfiable, not
   always-refusing. A third variant proves the delegation to gymact's own
   `StandingEvidence.admit()` is real, not bypassed.
"""

from __future__ import annotations

import asyncio

import pytest
from gymact.authority import AllowListAuthorityResolver
from gymact.models import MaterializationIntent
from gymact.providers import MemoryProvider
from gymact.runtime import GymAct
from gymact.sota import StandingEvidence

from autofde_lab.sota.crown_receipt import (
    CrownReceipt,
    CrownReceiptAdmissionError,
    standing_evidence_from_gymact_episode,
)
from autofde_lab.sota.decision_basis import (
    Budget,
    DecisionBasis,
    Model,
    Planner,
    RepairPolicy,
    ToolPolicy,
    VerificationPolicy,
)

AUTHORITY = "urn:test:crown-receipt"


async def _real_memory_episode_standing_evidence() -> StandingEvidence:
    """One real, cheap gymact episode (real kernel, real MemoryProvider, no external
    infra) standing in as the "subject" for testing the crown-receipt materializer
    itself -- the materializer is generic, not SREGym-specific (see its own docstring)."""
    gym = GymAct(authority_resolver=AllowListAuthorityResolver({AUTHORITY}))
    gym.register_provider(MemoryProvider())
    materialization = await gym.materialize(
        MaterializationIntent(provider="memory", config={"initial": {"x": 1}})
    )
    assert materialization.accepted is True
    episode_id = materialization.episode.episode_id
    await gym.teardown(episode_id)
    return standing_evidence_from_gymact_episode(
        gym,
        episode_id,
        experiment_ref="test-decision-basis",
        verifier_ref="test-native-verifier",
    )


def _real_decision_basis() -> DecisionBasis:
    """A real, honestly-labeled DecisionBasis -- not fabricated data, just a minimal
    real point in the vocabulary this repo already defines and uses for real."""
    return DecisionBasis(
        model=Model(id="none", description="test fixture: no LLM calls"),
        planner=Planner(name="test:fixture-planner", description="test fixture"),
        tool_policy=ToolPolicy(tool_names=(), description="test fixture: no tools"),
        repair_policy=RepairPolicy(mode="none", description="test fixture: no retry"),
        verification_policy=VerificationPolicy(
            oracle_name="test-fixture-oracle", description="test fixture"
        ),
        budget=Budget(wall_clock_timeout_s=1, description="test fixture"),
    )


REQUIRED_FIELDS = (
    "benchmark_sha",
    "comparator_identity",
    "comparator_score",
    "autofde_repo_sha",
    "decision_basis",
    "execution_subject",
    "repeats",
    "native_verifier_name",
    "score",
    "cost_usd",
    "latency_s",
    "tokens",
    "actions",
    "refusals",
    "replay_command",
    "replay_exit_code",
    "standing_evidence",
)


async def _complete_receipt_kwargs() -> dict:
    return {
        "benchmark_sha": "dcc9947f713a719d9c0952f90b95b3f12a2f2cbe",
        "comparator_identity": "claude-code+sonnet-4.6",
        "comparator_score": 60.7,
        "autofde_repo_sha": "0" * 40,
        "decision_basis": _real_decision_basis(),
        "execution_subject": "misconfig_app_hotel_res",
        "repeats": 1,
        "native_verifier_name": "test-native-verifier",
        "score": 0.0,
        "cost_usd": 0.0,
        "latency_s": 0.1,
        "tokens": 0,
        "actions": 0,
        "refusals": 0,
        "replay_command": ("uv", "run", "python3", "main.py"),
        "replay_exit_code": 0,
        "standing_evidence": await _real_memory_episode_standing_evidence(),
    }


def test_crown_receipt_refuses_admission_for_each_individually_missing_field() -> None:
    complete = asyncio.run(_complete_receipt_kwargs())
    for missing_field in REQUIRED_FIELDS:
        kwargs = dict(complete)
        kwargs[missing_field] = None
        receipt = CrownReceipt(**kwargs)
        with pytest.raises(CrownReceiptAdmissionError, match=missing_field):
            receipt.admit()


def test_crown_receipt_with_every_field_present_is_admitted() -> None:
    complete = asyncio.run(_complete_receipt_kwargs())
    receipt = CrownReceipt(**complete)
    receipt.admit()  # must not raise


def test_crown_receipt_delegates_to_standing_evidences_own_refusal() -> None:
    """A crown receipt whose outer fields are all present but whose StandingEvidence
    itself is incomplete must still be refused, via gymact's own real admission logic
    -- not silently accepted just because this module's own fields are filled."""
    complete = asyncio.run(_complete_receipt_kwargs())
    complete["standing_evidence"] = StandingEvidence(
        subject_digest="",  # empty -- gymact's own admit() refuses this
        experiment_digest="real",
        receipt_digest="real",
        verifier_digest="real",
        replay_verified=True,
    )
    receipt = CrownReceipt(**complete)
    with pytest.raises(Exception, match="SOTA_MISSING_BINDING"):
        receipt.admit()
