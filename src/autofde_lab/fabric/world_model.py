"""Canonical bounded world-model record for consequence experiments."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Mapping


@dataclass(frozen=True, slots=True)
class WorldModelRecord:
    subject_id: str
    observation_id: str
    state: Mapping[str, object]
    capability_id: str
    authority_id: str
    intended_effect: Mapping[str, object]
    evidence_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        required = (
            self.subject_id,
            self.observation_id,
            self.capability_id,
            self.authority_id,
        )
        if any(not value.strip() for value in required):
            raise ValueError("world-model identities must be non-empty")
        if not self.evidence_ids:
            raise ValueError("world-model record requires evidence lineage")

    @property
    def digest(self) -> str:
        payload = json.dumps(
            asdict(self), sort_keys=True, separators=(",", ":"), default=str
        ).encode()
        return "sha256:" + hashlib.sha256(payload).hexdigest()
