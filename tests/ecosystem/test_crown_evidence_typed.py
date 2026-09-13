# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Hostile fixtures for the branchless, typed `Standing` evidence chain.

Mirrors `test_crown_factor_typed_acceptance.py`'s pattern: real
collaborators throughout (a real `gymact.GymAct` episode against the real
`switchboard` provider, a real `SQLiteReceiptLedger`, real
`receipts_to_ocel`/`validate_ocel_log`/`ConformanceChecker`/`replay_ledger`
output) and assertions on real returned state. No mocks.

`switchboard` is used rather than `cube_counter` because the cube gyms
require the optional `cube` extra
(`~/gymact/src/gymact/gyms/cube_counter.py` raises `ImportError` without
it), which this repo's own `.venv` does not install; `switchboard` has no
such dependency and exercises the identical real
materialize/act/teardown/receipt/OCEL/replay chain.
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import pytest

from autofde_lab.hub.domain.gym_procedure.crown_evidence import (
    GOAL_CONSEQUENCE_EVENT_TYPE,
    BlockedEvidence,
    ConformantButGoalUnmetEvidence,
    ConformantExecutionEvidence,
    GoalConsequenceEvidence,
    Level4AliveEvidence,
    RefusedEvidence,
    Standing,
    UnknownEvidence,
    UnsupportedEvidence,
    standing_from_episode,
)

gymact = pytest.importorskip("gymact")

from gymact import AllowListAuthorityResolver, GymAct, MaterializationIntent  # noqa: E402
from gymact.gyms.switchboard import SwitchboardProvider  # noqa: E402
from gymact.models import ActuationIntent, Operation  # noqa: E402
from gymact.ocel import receipts_to_ocel  # noqa: E402
from gymact.process import ConformanceChecker  # noqa: E402
from gymact.replay import ReplayExpectation, ReplayMode, replay_ledger  # noqa: E402
from gymact.sqlite_ledger import SQLiteReceiptLedger  # noqa: E402

_AUTH = "urn:autofde-lab:test-crown-evidence"


def _run_real_episode(tmp_path: Path) -> dict:
    """A real end-to-end GymAct episode against the real switchboard
    provider: real materialize, one real act, real teardown, real receipts,
    a real OCEL log, real conformance, and a real replay report. Returns
    everything a caller needs to exercise `standing_from_episode` against
    real evidence."""

    async def _run() -> dict:
        ledger = SQLiteReceiptLedger(str(tmp_path / "receipts.sqlite3"))
        gym = GymAct(receipt_ledger=ledger, authority_resolver=AllowListAuthorityResolver({_AUTH}))
        gym.register_provider(SwitchboardProvider())
        m = await gym.materialize(MaterializationIntent(provider="switchboard", config={}))
        episode_id = m.episode.episode_id
        cap = gym.capabilities(episode_id)[0]
        await gym.act(ActuationIntent(episode_id=episode_id, capability=cap.iri, authority_ref=_AUTH))
        await gym.teardown(episode_id)
        receipts = gym.episode_receipts(episode_id)
        log = receipts_to_ocel(receipts)
        operations = [r.operation for r in receipts]
        replay = replay_ledger(
            ledger,
            mode=ReplayMode.EVIDENCE_REPLAY,
            expected=ReplayExpectation(subject_ref=m.episode.environment_id),
        )
        return {"log": log, "operations": operations, "receipts": receipts, "replay": replay}

    return asyncio.run(_run())


@pytest.fixture(scope="module")
def real_episode(tmp_path_factory) -> dict:
    return _run_real_episode(tmp_path_factory.mktemp("crown_evidence_episode"))


def _with_goal_consequence_event(log: dict, *, episode_id: str, passed: bool) -> dict:
    """Return a copy of `log` with a real-shaped `verify_goal_consequence`
    event appended, exactly as `level4_crown.py`'s `_EXECUTE_SCRIPT`
    projects one from a real `gymact.models.VerificationResult` (see that
    module's comment at the projection site). Building this by hand here is
    legitimate: this module tests `crown_evidence.py`'s own parsing logic
    over the exact wire shape the bridge produces, not a re-derived
    approximation of the bridge itself -- every field mirrors a real
    `VerificationResult` field 1:1 (`verification_id`, `passed`,
    `state_digest`, digests of `expected`/`observed`), just without the
    subprocess round-trip.
    """
    import copy
    import hashlib
    import json
    import uuid

    def _digest(obj: object) -> str:
        return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()

    out = copy.deepcopy(log)
    out["events"].append(
        {
            "id": f"goal-verification:{uuid.uuid4().hex}",
            "type": GOAL_CONSEQUENCE_EVENT_TYPE,
            "time": "2026-08-08T00:00:00+00:00",
            "attributes": [
                {"name": "passed", "value": str(bool(passed))},
                {"name": "verification_id", "value": uuid.uuid4().hex},
                {"name": "state_digest", "value": _digest({"solved": passed})},
                {"name": "expected_digest", "value": _digest({"solved": True})},
                {"name": "observed_digest", "value": _digest({"solved": passed})},
            ],
            "relationships": [{"objectId": episode_id, "qualifier": "episode"}],
        }
    )
    if not any(et["name"] == GOAL_CONSEQUENCE_EVENT_TYPE for et in out["eventTypes"]):
        out["eventTypes"].append(
            {"name": GOAL_CONSEQUENCE_EVENT_TYPE, "attributes": [{"name": "passed", "type": "string"}]}
        )
    return out


# ---------------------------------------------------------------------------
# The positive case: every real check passes AND the goal consequence is
# independently observed as met -> Level4AliveEvidence, real fields.
# ---------------------------------------------------------------------------


def test_real_episode_is_genuinely_valid_conformant_and_replayable(real_episode: dict) -> None:
    """Ground the premise before relying on it below: the real chain this
    fixture produces really is clean, real evidence -- not hand-fabricated."""
    from gymact.ocel import validate_ocel_log

    validate_ocel_log(real_episode["log"])  # must not raise
    assert ConformanceChecker().check(real_episode["operations"]).conformant is True
    assert real_episode["replay"].valid is True
    assert len(real_episode["receipts"]) > 0


def test_standing_from_episode_returns_level4_alive_evidence_with_real_fields(
    real_episode: dict,
) -> None:
    episode_id = real_episode["receipts"][0].episode_id
    log_with_goal = _with_goal_consequence_event(real_episode["log"], episode_id=episode_id, passed=True)

    standing = standing_from_episode(
        log_with_goal,
        real_episode["operations"],
        real_episode["receipts"],
        replay=real_episode["replay"],
        postcondition_ref="urn:test:postcondition:switchboard-toggle",
    )

    assert isinstance(standing, Level4AliveEvidence)
    assert isinstance(standing.conformant, ConformantExecutionEvidence)
    assert standing.conformant.episode_digest  # real digest, non-empty
    assert standing.conformant.conformance.conformant is True
    assert standing.conformant.replay is real_episode["replay"]
    assert standing.conformant.replay.valid is True
    assert standing.conformant.receipt_id == str(real_episode["receipts"][0].receipt_id)
    assert standing.conformant.postcondition_ref == "urn:test:postcondition:switchboard-toggle"
    assert isinstance(standing.goal, GoalConsequenceEvidence)
    assert standing.goal.passed is True
    assert standing.goal.verification_id


# ---------------------------------------------------------------------------
# The pathological case named directly in the standing-refinement request:
# perfect process evidence (authority, commitment, OCEL, receipts, replay)
# but the goal consequence is absent or reports False -> a real, checked,
# NEGATIVE finding (`ConformantButGoalUnmetEvidence`), never a silently
# upgraded `Level4AliveEvidence` and never a collapse into `UnknownEvidence`.
# ---------------------------------------------------------------------------


def test_clean_process_with_no_goal_event_is_conformant_but_goal_unmet(real_episode: dict) -> None:
    """The real switchboard episode's own OCEL log (no goal-consequence
    event projected at all -- exactly what `gymact.ocel.receipts_to_ocel`
    produces on its own, before `level4_crown.py`'s bridge adds one)."""
    standing = standing_from_episode(
        real_episode["log"],
        real_episode["operations"],
        real_episode["receipts"],
        replay=real_episode["replay"],
        postcondition_ref="urn:test:postcondition:switchboard-toggle",
    )

    assert isinstance(standing, ConformantButGoalUnmetEvidence)
    assert not isinstance(standing, Level4AliveEvidence)
    assert isinstance(standing.conformant, ConformantExecutionEvidence)
    assert standing.conformant.conformance.conformant is True
    assert standing.conformant.replay.valid is True
    assert standing.goal is None
    assert standing.reason == "GOAL_CONSEQUENCE_ABSENT_FROM_OCEL_GRAPH"


def test_clean_process_with_failed_goal_event_is_conformant_but_goal_unmet(real_episode: dict) -> None:
    """Every process check is real and clean AND a real goal-consequence
    event is present -- it just independently reports `passed=False`. This
    must not be indistinguishable from "we never checked"."""
    episode_id = real_episode["receipts"][0].episode_id
    log_with_failed_goal = _with_goal_consequence_event(
        real_episode["log"], episode_id=episode_id, passed=False
    )

    standing = standing_from_episode(
        log_with_failed_goal,
        real_episode["operations"],
        real_episode["receipts"],
        replay=real_episode["replay"],
        postcondition_ref="urn:test:postcondition:switchboard-toggle",
    )

    assert isinstance(standing, ConformantButGoalUnmetEvidence)
    assert not isinstance(standing, Level4AliveEvidence)
    assert standing.conformant.conformance.conformant is True
    assert standing.conformant.replay.valid is True
    assert standing.goal is not None
    assert standing.goal.passed is False
    assert standing.reason.startswith("GOAL_CONSEQUENCE_REPORTED_FALSE:")


# ---------------------------------------------------------------------------
# Negative fixtures: each real process-level failure mode produces
# UnknownEvidence, never a silently-defaulted Level4AliveEvidence -- these
# never even reach the point of having a ConformantExecutionEvidence to
# evaluate a goal against.
# ---------------------------------------------------------------------------


def test_schema_invalid_log_returns_unknown_not_alive(real_episode: dict) -> None:
    broken_log = {"objects": []}  # genuinely missing required OCEL 2.0 sections

    standing = standing_from_episode(
        broken_log,
        real_episode["operations"],
        real_episode["receipts"],
        replay=real_episode["replay"],
        postcondition_ref="urn:test:postcondition",
    )

    assert isinstance(standing, UnknownEvidence)
    assert standing.missing.startswith("OCEL_SCHEMA_INVALID:")
    assert standing.episode_digest is None


def test_nonconformant_operations_returns_unknown_not_alive(real_episode: dict) -> None:
    # A real, out-of-lifecycle-order operation sequence: ACT before
    # MATERIALIZE is never a legal successor.
    bad_operations = [Operation.ACT, Operation.MATERIALIZE, Operation.TEARDOWN]

    standing = standing_from_episode(
        real_episode["log"],
        bad_operations,
        real_episode["receipts"],
        replay=real_episode["replay"],
        postcondition_ref="urn:test:postcondition",
    )

    assert isinstance(standing, UnknownEvidence)
    assert standing.missing.startswith("CONFORMANCE_DEVIATIONS:")
    assert standing.episode_digest  # schema check already passed, so this is real


def test_invalid_replay_returns_unknown_not_alive(real_episode: dict) -> None:
    real_but_invalid_replay = real_episode["replay"].model_copy(
        update={"valid": False, "mismatches": ("REAL_MISMATCH:head_digest_disagreement",)}
    )

    standing = standing_from_episode(
        real_episode["log"],
        real_episode["operations"],
        real_episode["receipts"],
        replay=real_but_invalid_replay,
        postcondition_ref="urn:test:postcondition",
    )

    assert isinstance(standing, UnknownEvidence)
    assert "REAL_MISMATCH:head_digest_disagreement" in standing.missing


def test_missing_postcondition_ref_returns_unknown_not_alive(real_episode: dict) -> None:
    standing = standing_from_episode(
        real_episode["log"],
        real_episode["operations"],
        real_episode["receipts"],
        replay=real_episode["replay"],
        postcondition_ref=None,
    )

    assert isinstance(standing, UnknownEvidence)
    assert standing.missing == "POSTCONDITION_REF_ABSENT"


def test_empty_receipts_returns_unknown_not_alive(real_episode: dict) -> None:
    standing = standing_from_episode(
        real_episode["log"],
        real_episode["operations"],
        [],
        replay=real_episode["replay"],
        postcondition_ref="urn:test:postcondition",
    )

    assert isinstance(standing, UnknownEvidence)
    assert standing.missing == "RECEIPTS_EMPTY"


def test_standing_from_episode_never_takes_a_boolean_success_shortcut(real_episode: dict) -> None:
    """`standing_from_episode` has no `success: bool` parameter at all --
    the only way for a caller to force `Level4AliveEvidence` is to supply
    real passing process AND goal-consequence evidence."""
    import inspect

    sig = inspect.signature(standing_from_episode)
    assert "success" not in sig.parameters
    for name, param in sig.parameters.items():
        assert param.annotation is not bool, f"{name} must not be a bare bool shortcut"


# ---------------------------------------------------------------------------
# No __bool__ on any Standing variant: `if standing:` must not compile to a
# plausible-looking verdict, mirroring CrownFactor's own discipline.
# ---------------------------------------------------------------------------


_SAMPLE_CONFORMANT = ConformantExecutionEvidence(
    episode_digest="d", conformance=object(), replay=object(),
    receipt_id="r", postcondition_ref="p",
)
_SAMPLE_GOAL_MET = GoalConsequenceEvidence(
    verification_id="v", passed=True, expected_digest="e", observed_digest="o", state_digest="s",
)
_SAMPLE_GOAL_UNMET = GoalConsequenceEvidence(
    verification_id="v2", passed=False, expected_digest="e", observed_digest="o", state_digest="s",
)


@pytest.mark.parametrize(
    "instance",
    [
        _SAMPLE_CONFORMANT,
        Level4AliveEvidence(conformant=_SAMPLE_CONFORMANT, goal=_SAMPLE_GOAL_MET),
        ConformantButGoalUnmetEvidence(
            conformant=_SAMPLE_CONFORMANT, goal=_SAMPLE_GOAL_UNMET, reason="GOAL_CONSEQUENCE_REPORTED_FALSE:x"
        ),
        UnknownEvidence(missing="X"),
        RefusedEvidence(reason="LIVE_AUTHORITY_REQUIRED", subject="cube_counter"),
        BlockedEvidence(reason="NO_VENV"),
        UnsupportedEvidence(reason="EXTRA_ABSENT"),
    ],
)
def test_no_standing_variant_defines_dunder_bool(instance: Standing) -> None:
    """Mirrors `test_crown_factor_typed_acceptance.py`'s
    `test_factor_has_no_truthy_shortcut`: a dataclass with no `__bool__`
    is truthy by default, so `bool(instance)` is `True` regardless of
    which variant it is -- the dangerous idiom this test makes explicit by
    naming it, rather than a `TypeError` that would (falsely) suggest the
    type already refuses `if standing:`."""
    assert "__bool__" not in type(instance).__dict__, (
        f"{type(instance).__name__} must not define __bool__: a custom truthiness "
        f"would make `if standing:` a plausible-looking verdict, which is the whole "
        f"defect this discriminated union exists to prevent"
    )
    assert bool(instance) is True  # the default-truthiness trap, named explicitly
