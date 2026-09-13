# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Value serialization, compression, and digest verification."""

from __future__ import annotations

import pickle
import zlib
from dataclasses import dataclass
from typing import Any, Protocol

from .keys import Digestor
from .types import CacheCorruptionError

__all__ = ["EncodedValue", "PickleCodec", "ValueCodec"]


@dataclass(frozen=True)
class EncodedValue:
    payload: bytes
    value_digest: str
    codec: str
    compressed: bool
    raw_size_bytes: int
    size_bytes: int


class ValueCodec(Protocol):
    name: str

    def encode(self, value: Any) -> EncodedValue: ...

    def decode(
        self,
        payload: bytes,
        *,
        value_digest: str,
        compressed: bool,
        copy_on_read: bool = True,
    ) -> Any: ...


class PickleCodec:
    """Protocol-5 pickle codec with optional zlib compression and checksums.

    Cache files are trusted-local artifacts. They must not be opened from an
    untrusted source because pickle is intentionally capable of reconstructing
    arbitrary Python objects.
    """

    name = "pickle-v5"

    def __init__(
        self,
        *,
        digestor: Digestor,
        compression_threshold_bytes: int = 4096,
        compression_level: int = 6,
    ) -> None:
        if compression_threshold_bytes < 0:
            raise ValueError("compression_threshold_bytes cannot be negative")
        if not 0 <= compression_level <= 9:
            raise ValueError("compression_level must be between 0 and 9")
        self._digestor = digestor
        self._threshold = compression_threshold_bytes
        self._level = compression_level

    def encode(self, value: Any) -> EncodedValue:
        raw = pickle.dumps(value, protocol=5)
        digest = self._digestor.digest(raw)
        compressed = len(raw) >= self._threshold and self._threshold > 0
        payload = zlib.compress(raw, self._level) if compressed else raw
        return EncodedValue(
            payload=payload,
            value_digest=digest,
            codec=self.name,
            compressed=compressed,
            raw_size_bytes=len(raw),
            size_bytes=len(payload),
        )

    def decode(
        self,
        payload: bytes,
        *,
        value_digest: str,
        compressed: bool,
        copy_on_read: bool = True,
    ) -> Any:
        try:
            raw = zlib.decompress(payload) if compressed else payload
        except zlib.error as error:
            raise CacheCorruptionError(
                "cached value compression stream is corrupt"
            ) from error
        observed = self._digestor.digest(raw)
        if observed != value_digest:
            raise CacheCorruptionError(
                "cached value digest mismatch: "
                f"expected {value_digest}, observed {observed}"
            )
        # Decoding itself manufactures an isolated object graph, so mutation by
        # a caller cannot corrupt a stored value. copy_on_read is retained as a
        # policy hook for future zero-copy codecs.
        try:
            return pickle.loads(raw)
        except (
            pickle.UnpicklingError,
            EOFError,
            AttributeError,
            ImportError,
            IndexError,
        ) as error:
            raise CacheCorruptionError(
                "cached value payload cannot be decoded"
            ) from error
