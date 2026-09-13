# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Signed attestations and an append-only provenance ledger."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from .locking import InterProcessFileLock

__all__ = [
    "AttestationKeyring",
    "AttestationSigner",
    "CacheAttestation",
    "LedgerVerification",
    "ProvenanceError",
    "ProvenanceLedger",
    "SignedAttestation",
]


class ProvenanceError(RuntimeError):
    """Raised when signed or chained provenance cannot be verified."""


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


@dataclass(frozen=True)
class CacheAttestation:
    """Portable evidence binding a result to code, model, data, and policy."""

    subject_id: str
    namespace: str
    method: str
    key_digest: str
    value_digest: str | None
    disposition: str
    policy_digest: str
    release_id: str
    model_fingerprint: str
    data_fingerprint: str
    rollout_reason: str
    rollout_cohort: float | None
    observed_at: float
    owner: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SignedAttestation:
    attestation: CacheAttestation
    key_id: str
    algorithm: str
    signature: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "attestation": self.attestation.to_dict(),
            "key_id": self.key_id,
            "algorithm": self.algorithm,
            "signature": self.signature,
        }


class AttestationSigner:
    """HMAC-SHA256 signer with explicit key identity."""

    algorithm = "hmac-sha256"

    def __init__(self, key: bytes, *, key_id: str) -> None:
        if len(key) < 32:
            raise ValueError("attestation key must contain at least 32 bytes")
        if not key_id:
            raise ValueError("key_id must be non-empty")
        self._key = bytes(key)
        self.key_id = key_id

    def sign(self, attestation: CacheAttestation) -> SignedAttestation:
        payload = _canonical_json(attestation.to_dict())
        signature = hmac.new(self._key, payload, hashlib.sha256).hexdigest()
        return SignedAttestation(
            attestation=attestation,
            key_id=self.key_id,
            algorithm=self.algorithm,
            signature=signature,
        )

    def verify(self, signed: SignedAttestation) -> bool:
        if signed.key_id != self.key_id or signed.algorithm != self.algorithm:
            return False
        expected = self.sign(signed.attestation).signature
        return hmac.compare_digest(expected, signed.signature)


class AttestationKeyring:
    """Verify current and historical attestations by explicit key identity."""

    def __init__(self, signers: Iterable[AttestationSigner]) -> None:
        mapping: dict[str, AttestationSigner] = {}
        for signer in signers:
            if signer.key_id in mapping:
                raise ValueError(f"duplicate attestation key id: {signer.key_id}")
            mapping[signer.key_id] = signer
        if not mapping:
            raise ValueError("attestation keyring must not be empty")
        self._signers = mapping

    def verify(self, signed: SignedAttestation) -> bool:
        signer = self._signers.get(signed.key_id)
        return signer is not None and signer.verify(signed)

    @property
    def key_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._signers))


@dataclass(frozen=True)
class LedgerVerification:
    valid: bool
    records: int
    tail_digest: str | None
    error: str | None = None


class ProvenanceLedger:
    """JSONL ledger with sequence, hash-chain, signature, flush, and fsync."""

    def __init__(
        self,
        path: Path | str,
        *,
        signer: AttestationSigner,
        keyring: AttestationKeyring | None = None,
        fsync: bool = True,
        lock_timeout_seconds: float = 5.0,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.signer = signer
        self.keyring = keyring or AttestationKeyring((signer,))
        if signer.key_id not in self.keyring.key_ids:
            raise ValueError("active signer must be present in the keyring")
        self.fsync = fsync
        self._lock = threading.RLock()
        self._file_lock = InterProcessFileLock(
            self.path.with_suffix(self.path.suffix + ".lock"),
            timeout_seconds=lock_timeout_seconds,
        )

    def _scan_tail(self) -> tuple[int, str | None]:
        if not self.path.exists():
            return 0, None
        sequence = 0
        tail: str | None = None
        with self.path.open("r", encoding="utf-8") as stream:
            for line in stream:
                if not line.strip():
                    continue
                record = json.loads(line)
                sequence = int(record["sequence"])
                tail = str(record["record_digest"])
        return sequence, tail

    def append(self, attestation: CacheAttestation) -> SignedAttestation:
        signed = self.signer.sign(attestation)
        with self._lock, self._file_lock:
            sequence, previous = self._scan_tail()
            body = {
                "sequence": sequence + 1,
                "previous_digest": previous,
                "signed_attestation": signed.to_dict(),
            }
            record_digest = hashlib.sha256(_canonical_json(body)).hexdigest()
            record = {**body, "record_digest": record_digest}
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, sort_keys=True, separators=(",", ":")))
                stream.write("\n")
                stream.flush()
                if self.fsync:
                    os.fsync(stream.fileno())
        return signed

    def verify(self) -> LedgerVerification:
        with self._lock, self._file_lock:
            return self._verify_locked()

    def _verify_locked(self) -> LedgerVerification:
        if not self.path.exists():
            return LedgerVerification(valid=True, records=0, tail_digest=None)
        previous: str | None = None
        expected_sequence = 1
        try:
            with self.path.open("r", encoding="utf-8") as stream:
                for line in stream:
                    if not line.strip():
                        continue
                    record = json.loads(line)
                    if record["sequence"] != expected_sequence:
                        raise ProvenanceError("ledger sequence is not contiguous")
                    if record["previous_digest"] != previous:
                        raise ProvenanceError("ledger hash chain is broken")
                    body = {
                        "sequence": record["sequence"],
                        "previous_digest": record["previous_digest"],
                        "signed_attestation": record["signed_attestation"],
                    }
                    digest = hashlib.sha256(_canonical_json(body)).hexdigest()
                    if not hmac.compare_digest(digest, record["record_digest"]):
                        raise ProvenanceError("ledger record digest mismatch")
                    signed_data = record["signed_attestation"]
                    attestation = CacheAttestation(**signed_data["attestation"])
                    signed = SignedAttestation(
                        attestation=attestation,
                        key_id=signed_data["key_id"],
                        algorithm=signed_data["algorithm"],
                        signature=signed_data["signature"],
                    )
                    if not self.keyring.verify(signed):
                        raise ProvenanceError("ledger attestation signature mismatch")
                    previous = record["record_digest"]
                    expected_sequence += 1
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            return LedgerVerification(
                valid=False,
                records=expected_sequence - 1,
                tail_digest=previous,
                error=f"{type(error).__name__}: {error}",
            )
        except ProvenanceError as error:
            return LedgerVerification(
                valid=False,
                records=expected_sequence - 1,
                tail_digest=previous,
                error=str(error),
            )
        return LedgerVerification(
            valid=True,
            records=expected_sequence - 1,
            tail_digest=previous,
        )
