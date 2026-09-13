"""Pure, offline, deterministic replay verification over a list of Open/Close
certificate records produced by ``broker.Broker``.

Signature and check order deliberately mirror ``mfw_pcp_replay::verify()``
(``/Users/sac/mfw/crates/pcp/mfw-pcp-replay/src/lib.rs``) field-for-field, per the ERRC
grid's "Create" row — this function is meant to translate mechanically into Rust later,
not be redesigned there.

"Replay" here means what it means in mfw: re-verifying the causal/digest chain and
re-deriving a standing verdict from already-issued receipts — it does not re-run the
original actuation.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .core import Digest


class ReplayError(ValueError):
    pass


class StandingState(str, Enum):
    REPLAYED = "replayed"


class GallStatus(str, Enum):
    ALIVE = "ALIVE"
    PARTIAL_ALIVE = "PARTIAL_ALIVE"


@dataclass(frozen=True)
class ReplayReport:
    closed_actions: int
    all_effects_succeeded: bool
    all_postconditions_satisfied: bool
    final_state_digest: str
    chain_digest: str
    standing: StandingState
    gall_status: GallStatus


def _recompute_digest(record: dict) -> str:
    # Must match Certificate.certificate_digest() exactly: hashes only {kind, body},
    # not the full record (issued_at_ms/digest are metadata, not digest input).
    return str(Digest.of_json({"kind": record["kind"], "body": record["body"]}))


def verify(records: list[dict]) -> ReplayReport:
    if len(records) % 2 != 0:
        raise ReplayError("odd number of records: open/close must alternate in pairs")

    seen_digests: set[str] = set()
    previous_close_digest = str(Digest.genesis())
    closed_actions = 0
    all_effects_succeeded = True
    all_postconditions_satisfied = True
    last_digest = previous_close_digest

    for i in range(0, len(records), 2):
        open_record, close_record = records[i], records[i + 1]

        if open_record.get("kind") != "open":
            raise ReplayError(f"record {i}: expected kind=open, got {open_record.get('kind')!r}")
        if close_record.get("kind") != "close":
            raise ReplayError(f"record {i + 1}: expected kind=close, got {close_record.get('kind')!r}")

        open_digest = _recompute_digest(open_record)
        close_digest = _recompute_digest(close_record)
        for d in (open_digest, close_digest):
            if d in seen_digests:
                raise ReplayError(f"duplicate receipt digest: {d}")
            seen_digests.add(d)

        open_body = open_record["body"]
        close_body = close_record["body"]

        if open_body.get("previous_receipt_digest") != previous_close_digest:
            raise ReplayError(
                f"pair {i // 2}: open.previous_receipt_digest mismatch "
                f"(expected {previous_close_digest}, got {open_body.get('previous_receipt_digest')})"
            )
        if close_body.get("open_receipt_digest") != open_digest:
            raise ReplayError(
                f"pair {i // 2}: close.open_receipt_digest does not match open's digest"
            )
        if close_body.get("previous_receipt_digest") != open_digest:
            raise ReplayError(
                f"pair {i // 2}: close.previous_receipt_digest does not match open's digest"
            )
        if open_body.get("action") != close_body.get("action"):
            raise ReplayError(f"pair {i // 2}: action mismatch between open and close")

        closed_actions += 1
        if close_body.get("outcome") != "succeeded":
            all_effects_succeeded = False
        if not close_body.get("postcondition_satisfied"):
            all_postconditions_satisfied = False

        previous_close_digest = close_digest
        last_digest = close_digest

    gall_status = (
        GallStatus.ALIVE
        if all_effects_succeeded and all_postconditions_satisfied
        else GallStatus.PARTIAL_ALIVE
    )
    return ReplayReport(
        closed_actions=closed_actions,
        all_effects_succeeded=all_effects_succeeded,
        all_postconditions_satisfied=all_postconditions_satisfied,
        final_state_digest=last_digest,
        chain_digest=last_digest,
        standing=StandingState.REPLAYED,
        gall_status=gall_status,
    )
