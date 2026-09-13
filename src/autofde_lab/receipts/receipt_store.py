"""Reduced from ``runtime/mfw-rmcp/src/receipt.rs``'s schema-versioned Rust
``ReceiptLedger`` to an append-only JSON-lines file with the same three methods:
``append``, ``load``, ``verify_chain``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .core import Digest

SCHEMA_VERSION = "autofde-receipt-v1"


class ReceiptChainError(ValueError):
    pass


@dataclass
class ReceiptLedger:
    records: list[dict]

    @classmethod
    def empty(cls) -> "ReceiptLedger":
        return cls(records=[])

    @classmethod
    def load(cls, path: str | Path) -> "ReceiptLedger":
        path = Path(path)
        if not path.exists():
            return cls.empty()
        records = [
            json.loads(line)
            for line in path.read_text().splitlines()
            if line.strip()
        ]
        return cls(records=records)

    def append(self, record: dict, *, path: str | Path | None = None) -> None:
        record = {"schema_version": SCHEMA_VERSION, **record}
        self.records.append(record)
        if path is not None:
            with Path(path).open("a") as fh:
                fh.write(json.dumps(record, sort_keys=True) + "\n")

    def verify_chain(self) -> bool:
        """Re-derive each record's digest from its own body and check the
        previous-digest links form an unbroken chain, mirroring
        ``ReceiptLedger::verify_chain`` in mfw's ``runtime/mfw-rmcp/src/receipt.rs``."""
        previous = str(Digest.genesis())
        for record in self.records:
            if record.get("schema_version") != SCHEMA_VERSION:
                raise ReceiptChainError(
                    f"unexpected schema_version: {record.get('schema_version')!r}"
                )
            # Must match Certificate.certificate_digest() exactly: hashes only
            # {kind, body}, not the full record (schema_version/issued_at_ms/digest
            # are metadata, not digest input).
            recomputed = str(Digest.of_json({"kind": record["kind"], "body": record["body"]}))
            body = record.get("body", {})
            sequence = body.get("sequence")
            if record.get("digest") != recomputed:
                raise ReceiptChainError(
                    f"digest mismatch at sequence {sequence}: "
                    f"stored={record.get('digest')} recomputed={recomputed}"
                )
            if body.get("previous_receipt_digest") != previous:
                raise ReceiptChainError(
                    f"chain break at sequence {sequence}: "
                    f"expected previous={previous}, "
                    f"got={body.get('previous_receipt_digest')}"
                )
            previous = recomputed
        return True
