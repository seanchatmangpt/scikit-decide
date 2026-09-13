"""Content addressing and shared vocabulary.

Reduced from mfw-pcp-core's ``Digest``/``GallStatus``/``StandingState`` (blake3-backed
Rust) to sha256 + a plain string genesis marker. The ERRC grid calls this out
explicitly: sha256 is stdlib, blake3 is not, and byte-for-byte hash algorithm choice is
not part of what a prototype needs to get right — only the *shape* (content-addressed,
chainable, a distinguished genesis value) needs to survive into the Rust rewrite.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

GENESIS = "genesis:0" * 4  # distinguished, obviously-not-a-real-hash sentinel


@dataclass(frozen=True)
class Digest:
    """A content hash. ``of_json``/``of_bytes`` mirror mfw-pcp-core's ``Digest`` API
    names exactly so a future Rust port renames nothing but the hash function."""

    value: str

    @staticmethod
    def of_bytes(data: bytes) -> "Digest":
        return Digest(hashlib.sha256(data).hexdigest())

    @staticmethod
    def of_json(obj) -> "Digest":
        canonical = json.dumps(obj, sort_keys=True, separators=(",", ":"))
        return Digest.of_bytes(canonical.encode("utf-8"))

    @staticmethod
    def genesis() -> "Digest":
        return Digest(GENESIS)

    def __str__(self) -> str:
        return self.value
