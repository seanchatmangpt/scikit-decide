# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Bounded dead-letter journal for cache infrastructure failures."""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

from .locking import InterProcessFileLock

__all__ = ["QuarantineEvent", "QuarantineJournal"]


@dataclass(frozen=True)
class QuarantineEvent:
    """Metadata-only failure evidence; cached values are never copied here."""

    event_id: str
    observed_at: float
    subject_id: str
    namespace: str
    method: str
    error_type: str
    error_message: str
    action: str
    key_digest: str | None = None
    attributes: Mapping[str, str] | None = None

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["attributes"] = dict(self.attributes or {})
        return value


class QuarantineJournal:
    """Append failures to size-bounded, rotated JSONL files."""

    def __init__(
        self,
        path: Path | str,
        *,
        max_bytes: int = 16 * 1024 * 1024,
        max_files: int = 5,
        fsync: bool = True,
        clock: Any = time.time,
        lock_timeout_seconds: float = 5.0,
    ) -> None:
        if max_bytes < 1024:
            raise ValueError("max_bytes must be at least 1024")
        if max_files < 1:
            raise ValueError("max_files must be at least 1")
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.max_bytes = max_bytes
        self.max_files = max_files
        self.fsync = fsync
        self._clock = clock
        self._lock = threading.RLock()
        self._file_lock = InterProcessFileLock(
            self.path.with_suffix(self.path.suffix + ".lock"),
            timeout_seconds=lock_timeout_seconds,
        )

    def _rotate(self, incoming_bytes: int) -> None:
        current = self.path.stat().st_size if self.path.exists() else 0
        if current + incoming_bytes <= self.max_bytes:
            return
        oldest = self.path.with_suffix(self.path.suffix + f".{self.max_files}")
        if oldest.exists():
            oldest.unlink()
        for index in range(self.max_files - 1, 0, -1):
            source = self.path.with_suffix(self.path.suffix + f".{index}")
            target = self.path.with_suffix(self.path.suffix + f".{index + 1}")
            if source.exists():
                source.replace(target)
        if self.path.exists():
            self.path.replace(self.path.with_suffix(self.path.suffix + ".1"))

    def record(
        self,
        *,
        subject_id: str,
        namespace: str,
        method: str,
        error: BaseException,
        action: str,
        key_digest: str | None = None,
        attributes: Mapping[str, str] | None = None,
    ) -> QuarantineEvent:
        observed_at = float(self._clock())
        identity = {
            "subject_id": subject_id,
            "namespace": namespace,
            "method": method,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "action": action,
            "key_digest": key_digest,
            "observed_at": observed_at,
        }
        event_id = hashlib.sha256(
            json.dumps(
                identity,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        event = QuarantineEvent(
            event_id=event_id,
            observed_at=observed_at,
            subject_id=subject_id,
            namespace=namespace,
            method=method,
            error_type=type(error).__name__,
            error_message=str(error),
            action=action,
            key_digest=key_digest,
            attributes=dict(attributes or {}),
        )
        line = (
            json.dumps(
                event.to_dict(),
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        )
        encoded = line.encode("utf-8")
        with self._lock, self._file_lock:
            self._rotate(len(encoded))
            with self.path.open("ab") as stream:
                stream.write(encoded)
                stream.flush()
                if self.fsync:
                    os.fsync(stream.fileno())
        return event

    def events(self, *, limit: int = 100) -> tuple[QuarantineEvent, ...]:
        if limit < 1:
            raise ValueError("limit must be at least 1")
        with self._lock, self._file_lock:
            if not self.path.exists():
                return ()
            lines = self.path.read_text(encoding="utf-8").splitlines()[-limit:]
        results = []
        for line in lines:
            data = json.loads(line)
            results.append(QuarantineEvent(**data))
        return tuple(results)
