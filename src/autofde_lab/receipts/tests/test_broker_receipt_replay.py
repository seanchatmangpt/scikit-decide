"""Checkpoint B/C verification (pure-Python ERRC prototype).

Positive: admit -> open -> actuate (wired to Checkpoint A's run_engine) -> close ->
persist -> replay, end to end.

Negative: token reuse, tampered digest, actuator failure (must still receipt, not
silently drop), admission refusal on a malformed observation.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import jsonschema
import pytest

from autofde_lab.planning.config import EngineConfig, OutputMode
from autofde_lab.planning.runner import run_engine
from autofde_lab.receipts.admission import admit
from autofde_lab.receipts.broker import (
    Broker,
    ColludingRoles,
    ConcurrentOpenUnsupported,
    TokenAlreadyConsumed,
)
from autofde_lab.receipts.receipt_store import ReceiptChainError, ReceiptLedger
from autofde_lab.receipts.replay import GallStatus, ReplayError, verify as replay_verify
from autofde_lab.standing import Blocked, Unsupported

RECEIPT_SCHEMA = json.loads(
    (Path(__file__).parents[1] / "receipt.schema.json").read_text()
)

FIXTURES = Path(__file__).parents[2] / "planning" / "tests" / "fixtures"
DOMAIN = FIXTURES / "blocks-domain.pddl"
PROBLEM = FIXTURES / "blocks-problem.pddl"
FAKE_ENGINE = FIXTURES / "fake_engine.py"


class RunEngineActuator:
    """Wires broker.Actuator directly around Checkpoint A's run_engine — the first
    end-to-end slice named in the plan."""

    def __init__(self, mode: str, plan_path: Path):
        self.mode = mode
        self.plan_path = plan_path

    def actuate(self, action: dict) -> dict:
        cfg = EngineConfig(
            role="classical",
            program=sys.executable,
            args=(str(FAKE_ENGINE), "--mode", self.mode, "--plan-file", "{plan}", "{domain}", "{problem}"),
            output_mode=OutputMode.FILE,
        )
        receipt = run_engine(cfg, domain=DOMAIN, problem=PROBLEM, plan=self.plan_path)
        if not receipt.is_success():
            raise RuntimeError(f"engine did not succeed: {receipt.outcome}")
        return {"plan_hash": receipt.plan_hash, "exit_code": receipt.exit_code}

    def adapter_digest(self) -> str:
        return "run_engine-adapter-v1"


class AlwaysTrueVerifier:
    def verify(self, action: dict, evidence: dict | None) -> bool:
        return evidence is not None and evidence.get("plan_hash") is not None

    def verifier_digest(self) -> str:
        return "always-true-verifier-v1"


# ---------------------------------------------------------------------------
# Positive: admit -> open -> actuate -> close -> persist -> replay
# ---------------------------------------------------------------------------


def test_full_cycle_admits_actuates_receipts_and_replays(tmp_path: Path) -> None:
    observation = {"action": {"name": "solve-blocks"}, "id": "run-1"}
    result = admit(observation, shape={"action": dict, "id": str})
    assert result.admitted

    plan_path = tmp_path / "plan.txt"
    broker = Broker(
        actuator=RunEngineActuator(mode="success", plan_path=plan_path),
        verifier=AlwaysTrueVerifier(),
    )

    opened = broker.open(observation["action"])
    closed = broker.actuate(opened.token)
    assert closed.outcome.value == "succeeded"
    assert closed.postcondition_satisfied

    ledger_path = tmp_path / "receipts.jsonl"
    ledger = ReceiptLedger.empty()
    ledger.append(opened.receipt.to_record(), path=ledger_path)
    ledger.append(closed.receipt.to_record(), path=ledger_path)
    assert ledger.verify_chain()

    reloaded = ReceiptLedger.load(ledger_path)
    assert reloaded.verify_chain()

    report = replay_verify(reloaded.records)
    assert report.closed_actions == 1
    assert report.all_effects_succeeded
    assert report.all_postconditions_satisfied
    assert report.gall_status == GallStatus.ALIVE


# ---------------------------------------------------------------------------
# Negative fixtures
# ---------------------------------------------------------------------------


def test_admission_refuses_missing_key_with_named_reason() -> None:
    with pytest.raises(Blocked, match="missing required key 'id'"):
        admit({"action": {}}, shape={"action": dict, "id": str})


def test_admission_refuses_empty_shape_as_unsupported() -> None:
    with pytest.raises(Unsupported):
        admit({"action": {}}, shape={})


def test_admission_refuses_wrong_typed_value_with_named_reason() -> None:
    with pytest.raises(Blocked, match=r"observation\['id'\] has type int, expected str"):
        admit({"action": {}, "id": 123}, shape={"action": dict, "id": str})


def test_token_reuse_is_rejected(tmp_path: Path) -> None:
    plan_path = tmp_path / "plan.txt"
    broker = Broker(
        actuator=RunEngineActuator(mode="success", plan_path=plan_path),
        verifier=AlwaysTrueVerifier(),
    )
    opened = broker.open({"name": "solve-blocks"})
    broker.actuate(opened.token)
    with pytest.raises(TokenAlreadyConsumed):
        broker.actuate(opened.token)


def test_concurrent_open_is_rejected(tmp_path: Path) -> None:
    broker = Broker(
        actuator=RunEngineActuator(mode="success", plan_path=tmp_path / "p.txt"),
        verifier=AlwaysTrueVerifier(),
    )
    broker.open({"name": "a"})
    with pytest.raises(ConcurrentOpenUnsupported):
        broker.open({"name": "b"})


def test_actuator_failure_still_produces_a_close_receipt(tmp_path: Path) -> None:
    plan_path = tmp_path / "plan.txt"
    broker = Broker(
        actuator=RunEngineActuator(mode="tool_failed", plan_path=plan_path),
        verifier=AlwaysTrueVerifier(),
    )
    opened = broker.open({"name": "solve-blocks"})
    closed = broker.actuate(opened.token)
    # Failure must still be receipted, not raised past the broker.
    assert closed.outcome.value == "failed"
    assert not closed.postcondition_satisfied
    assert closed.receipt.body["evidence"]["error"]


def test_verify_chain_rejects_a_tampered_digest(tmp_path: Path) -> None:
    plan_path = tmp_path / "plan.txt"
    broker = Broker(
        actuator=RunEngineActuator(mode="success", plan_path=plan_path),
        verifier=AlwaysTrueVerifier(),
    )
    opened = broker.open({"name": "solve-blocks"})
    closed = broker.actuate(opened.token)

    ledger = ReceiptLedger.empty()
    ledger.append(opened.receipt.to_record())
    ledger.append(closed.receipt.to_record())
    # Tamper with the second record's stored digest.
    ledger.records[1]["digest"] = "0" * 64
    with pytest.raises(ReceiptChainError):
        ledger.verify_chain()


def test_replay_rejects_odd_number_of_records(tmp_path: Path) -> None:
    plan_path = tmp_path / "plan.txt"
    broker = Broker(
        actuator=RunEngineActuator(mode="success", plan_path=plan_path),
        verifier=AlwaysTrueVerifier(),
    )
    opened = broker.open({"name": "solve-blocks"})
    with pytest.raises(ReplayError):
        replay_verify([opened.receipt.to_record()])


def test_replay_reports_partial_alive_when_postcondition_fails(tmp_path: Path) -> None:
    class AlwaysFalseVerifier:
        def verify(self, action, evidence):
            return False

        def verifier_digest(self):
            return "always-false-v1"

    plan_path = tmp_path / "plan.txt"
    broker = Broker(
        actuator=RunEngineActuator(mode="success", plan_path=plan_path),
        verifier=AlwaysFalseVerifier(),
    )
    opened = broker.open({"name": "solve-blocks"})
    closed = broker.actuate(opened.token)
    report = replay_verify([opened.receipt.to_record(), closed.receipt.to_record()])
    assert report.gall_status == GallStatus.PARTIAL_ALIVE
    assert not report.all_postconditions_satisfied


def test_receipts_validate_against_the_published_schema(tmp_path: Path) -> None:
    """The portable contract (receipt.schema.json) must actually describe what
    real receipts look like, not just what the docstring claims."""
    plan_path = tmp_path / "plan.txt"
    broker = Broker(
        actuator=RunEngineActuator(mode="success", plan_path=plan_path),
        verifier=AlwaysTrueVerifier(),
    )
    opened = broker.open({"name": "solve-blocks"})
    closed = broker.actuate(opened.token)

    for record in (opened.receipt.to_record(), closed.receipt.to_record()):
        jsonschema.validate(record, RECEIPT_SCHEMA)


# ---------------------------------------------------------------------------
# Adversarial: actuator/verifier collusion (prompt #24)
# ---------------------------------------------------------------------------


def test_colluding_actuator_and_verifier_is_refused() -> None:
    """A single real object implementing BOTH Actuator and PostconditionVerifier,
    wired into both broker slots, must be refused at construction -- otherwise it
    can actuate an action and then rubber-stamp its own effect with nothing in
    Broker.actuate or replay.verify able to catch the collusion."""

    class Colluder:
        def actuate(self, action: dict) -> dict:
            return {"result": "did nothing real"}

        def adapter_digest(self) -> str:
            return "colluder-actuator-v1"

        def verify(self, action: dict, evidence: dict | None) -> bool:
            return True  # lies unconditionally

        def verifier_digest(self) -> str:
            return "colluder-verifier-v1"

    colluder = Colluder()
    with pytest.raises(ColludingRoles):
        Broker(actuator=colluder, verifier=colluder)


def test_distinct_lying_verifier_is_not_detectable_by_replay(tmp_path: Path) -> None:
    """Documents a real, confirmed residual limit (not a claimed fix): a verifier
    that is a *distinct* object from the actuator, but always returns True
    regardless of the actual evidence, is NOT caught by Broker.actuate (which has
    no ground truth to compare against) and is NOT caught after the fact by
    replay.verify (which only re-checks digest-chain integrity, not the semantic
    honesty of a bool baked into a receipt that was honestly digested). The
    identity check added in Broker.__post_init__ closes the same-object case only;
    it does not and cannot close this one without an independent oracle."""

    class LyingVerifier:
        def verify(self, action: dict, evidence: dict | None) -> bool:
            return True  # ignores action/evidence entirely

        def verifier_digest(self) -> str:
            return "lying-verifier-v1"

    plan_path = tmp_path / "plan.txt"
    broker = Broker(
        actuator=RunEngineActuator(mode="tool_failed", plan_path=plan_path),
        verifier=LyingVerifier(),
    )
    opened = broker.open({"name": "solve-blocks"})
    closed = broker.actuate(opened.token)
    # The actuator failed, so the broker itself correctly skips verification and
    # marks postcondition_satisfied False -- the lying verifier only gets a real
    # chance to lie when the actuator claims success. Confirm that path too:
    assert closed.outcome.value == "failed"
    assert not closed.postcondition_satisfied

    plan_path2 = tmp_path / "plan2.txt"
    broker2 = Broker(
        actuator=RunEngineActuator(mode="success", plan_path=plan_path2),
        verifier=LyingVerifier(),
    )
    opened2 = broker2.open({"name": "solve-blocks"})
    closed2 = broker2.actuate(opened2.token)
    assert closed2.outcome.value == "succeeded"
    assert closed2.postcondition_satisfied  # the lie is accepted by the broker

    report = replay_verify([opened2.receipt.to_record(), closed2.receipt.to_record()])
    # replay cannot tell the lie from a true verification: digests are internally
    # consistent because the lie was baked in honestly at receipt-issuance time.
    assert report.gall_status == GallStatus.ALIVE
    assert report.all_postconditions_satisfied


def test_reloaded_ledger_detects_on_disk_tampering(tmp_path: Path) -> None:
    """Full loop: persist to a real file, tamper the file on disk (not just the
    in-memory object), reload via ReceiptLedger.load(), and confirm the *reloaded*
    ledger — a fresh real object, not the one that wrote the file — rejects it."""
    plan_path = tmp_path / "plan.txt"
    ledger_path = tmp_path / "receipts.jsonl"
    broker = Broker(
        actuator=RunEngineActuator(mode="success", plan_path=plan_path),
        verifier=AlwaysTrueVerifier(),
    )
    opened = broker.open({"name": "solve-blocks"})
    closed = broker.actuate(opened.token)

    ledger = ReceiptLedger.empty()
    ledger.append(opened.receipt.to_record(), path=ledger_path)
    ledger.append(closed.receipt.to_record(), path=ledger_path)

    # Tamper the file on disk directly (not the in-memory `ledger` object).
    lines = ledger_path.read_text().splitlines()
    second = json.loads(lines[1])
    second["body"]["postcondition_satisfied"] = not second["body"]["postcondition_satisfied"]
    lines[1] = json.dumps(second)
    ledger_path.write_text("\n".join(lines) + "\n")

    reloaded = ReceiptLedger.load(ledger_path)
    with pytest.raises(ReceiptChainError):
        reloaded.verify_chain()
