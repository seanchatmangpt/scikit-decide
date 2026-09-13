# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Deterministic canonicalization and content-addressed cache identities."""

from __future__ import annotations

import dataclasses
import datetime as dt
import enum
import hashlib
import math
import struct
import uuid
from collections.abc import Mapping
from decimal import Decimal
from fractions import Fraction
from pathlib import PurePath
from typing import Any

from .types import CacheKey, UnhashableCacheKeyError

__all__ = ["CanonicalKeyEncoder", "Digestor", "make_cache_key"]


def _length_prefix(payload: bytes) -> bytes:
    return len(payload).to_bytes(8, "big") + payload


def _type_name(value: Any) -> bytes:
    cls = value if isinstance(value, type) else type(value)
    return f"{cls.__module__}.{cls.__qualname__}".encode("utf-8")


class Digestor:
    """Small digest abstraction with an optional BLAKE3 fast path."""

    def __init__(self, algorithm: str = "blake2b") -> None:
        if algorithm not in {"blake2b", "sha256", "blake3"}:
            raise ValueError(f"unsupported digest algorithm: {algorithm}")
        self.algorithm = algorithm
        self._blake3 = None
        if algorithm == "blake3":
            try:
                import blake3  # type: ignore
            except ImportError as error:
                raise RuntimeError(
                    "digest_algorithm='blake3' requires the optional blake3 package"
                ) from error
            self._blake3 = blake3

    def digest(self, payload: bytes) -> str:
        if self.algorithm == "blake2b":
            return hashlib.blake2b(payload, digest_size=32).hexdigest()
        if self.algorithm == "sha256":
            return hashlib.sha256(payload).hexdigest()
        assert self._blake3 is not None
        return self._blake3.blake3(payload).hexdigest()


class CanonicalKeyEncoder:
    """Encode supported Python values without ``repr`` or object identity.

    Unsupported values are refused unless they implement ``__cache_key__``.
    This deliberately rejects ambient hashability because many Python objects
    inherit identity-based hashes that are not stable across processes.
    """

    def encode(self, value: Any) -> bytes:
        return self._encode(value, active=set())

    def _encode(self, value: Any, active: set[int]) -> bytes:
        if hasattr(value, "__cache_key__"):
            projected = value.__cache_key__()
            return (
                b"K"
                + _length_prefix(_type_name(value))
                + _length_prefix(self._encode(projected, active))
            )
        if value is None:
            return b"N"
        if value is True:
            return b"B1"
        if value is False:
            return b"B0"
        if isinstance(value, int) and not isinstance(value, bool):
            payload = str(value).encode("ascii")
            return b"I" + _length_prefix(payload)
        if isinstance(value, float):
            if math.isnan(value):
                payload = b"nan"
            else:
                payload = value.hex().encode("ascii")
            return b"F" + _length_prefix(payload)
        if isinstance(value, complex):
            return (
                b"X"
                + _length_prefix(self._encode(value.real, active))
                + _length_prefix(self._encode(value.imag, active))
            )
        if isinstance(value, str):
            return b"S" + _length_prefix(value.encode("utf-8"))
        if isinstance(value, bytes):
            return b"Y" + _length_prefix(value)
        if isinstance(value, (bytearray, memoryview)):
            return b"Y" + _length_prefix(bytes(value))
        if isinstance(value, Decimal):
            return b"D" + _length_prefix(str(value.normalize()).encode("ascii"))
        if isinstance(value, Fraction):
            return (
                b"R"
                + _length_prefix(self._encode(value.numerator, active))
                + _length_prefix(self._encode(value.denominator, active))
            )
        if isinstance(value, uuid.UUID):
            return b"U" + value.bytes
        if isinstance(value, PurePath):
            return (
                b"P"
                + _length_prefix(_type_name(value))
                + _length_prefix(value.as_posix().encode("utf-8"))
            )
        if isinstance(value, dt.datetime):
            if value.tzinfo is not None:
                value = value.astimezone(dt.timezone.utc)
            payload = value.isoformat(timespec="microseconds").encode("ascii")
            return b"Z" + _length_prefix(payload)
        if isinstance(value, dt.date):
            return b"A" + _length_prefix(value.isoformat().encode("ascii"))
        if isinstance(value, dt.time):
            payload = value.isoformat(timespec="microseconds").encode("ascii")
            return b"M" + _length_prefix(payload)
        if isinstance(value, enum.Enum):
            return (
                b"E"
                + _length_prefix(_type_name(value))
                + _length_prefix(value.name.encode("utf-8"))
            )
        if isinstance(value, range):
            return b"G" + b"".join(
                _length_prefix(self._encode(part, active))
                for part in (value.start, value.stop, value.step)
            )
        if isinstance(value, slice):
            return b"C" + b"".join(
                _length_prefix(self._encode(part, active))
                for part in (value.start, value.stop, value.step)
            )

        marker = id(value)
        recursive = dataclasses.is_dataclass(value) or isinstance(
            value, (Mapping, tuple, list, set, frozenset)
        )
        if recursive:
            if marker in active:
                raise UnhashableCacheKeyError(
                    "recursive values require an explicit __cache_key__ projection"
                )
            active.add(marker)
        try:
            if dataclasses.is_dataclass(value) and not isinstance(value, type):
                fields = []
                for item in dataclasses.fields(value):
                    encoded_name = self._encode(item.name, active)
                    encoded_value = self._encode(getattr(value, item.name), active)
                    fields.append(
                        _length_prefix(encoded_name) + _length_prefix(encoded_value)
                    )
                return b"@" + _length_prefix(_type_name(value)) + b"".join(fields)
            if isinstance(value, Mapping):
                items = []
                for key, item in value.items():
                    encoded_key = self._encode(key, active)
                    encoded_value = self._encode(item, active)
                    items.append(
                        _length_prefix(encoded_key) + _length_prefix(encoded_value)
                    )
                items.sort()
                return b"Q" + _length_prefix(_type_name(value)) + b"".join(items)
            if isinstance(value, tuple):
                return b"T" + b"".join(
                    _length_prefix(self._encode(item, active)) for item in value
                )
            if isinstance(value, list):
                return b"L" + b"".join(
                    _length_prefix(self._encode(item, active)) for item in value
                )
            if isinstance(value, (set, frozenset)):
                items = sorted(self._encode(item, active) for item in value)
                return (
                    b"O"
                    + _length_prefix(_type_name(value))
                    + b"".join(_length_prefix(item) for item in items)
                )

            numpy_payload = self._encode_numpy(value)
            if numpy_payload is not None:
                return numpy_payload
        finally:
            if recursive:
                active.remove(marker)

        raise UnhashableCacheKeyError(
            f"{type(value).__module__}.{type(value).__qualname__} has no "
            "stable cache key; implement __cache_key__ or provide "
            "MethodPolicy.key_fn"
        )

    def _encode_numpy(self, value: Any) -> bytes | None:
        module = type(value).__module__.split(".", 1)[0]
        if module != "numpy":
            return None
        try:
            import numpy as np
        except ImportError:
            return None
        if isinstance(value, np.generic):
            array = np.asarray(value)
        elif isinstance(value, np.ndarray):
            array = value
        else:
            return None
        contiguous = np.ascontiguousarray(array)
        shape = b"".join(
            struct.pack(">q", int(dimension)) for dimension in contiguous.shape
        )
        return (
            b"V"
            + _length_prefix(str(contiguous.dtype).encode("ascii"))
            + _length_prefix(shape)
            + _length_prefix(contiguous.tobytes(order="C"))
        )


def make_cache_key(
    *,
    namespace: str,
    method: str,
    version: str,
    args: tuple[Any, ...],
    kwargs: Mapping[str, Any],
    encoder: CanonicalKeyEncoder,
    digestor: Digestor,
    key_projection: Any | None = None,
) -> CacheKey:
    """Manufacture a stable key from admitted subject identity and call inputs."""

    projected = key_projection if key_projection is not None else (args, dict(kwargs))
    body = encoder.encode(
        {
            "schema": "autofde_lab-cache-key-v2",
            "namespace": namespace,
            "method": method,
            "version": version,
            "input": projected,
        }
    )
    return CacheKey(
        digest=digestor.digest(body),
        algorithm=digestor.algorithm,
        namespace=namespace,
        method=method,
        version=version,
        canonical_size=len(body),
    )
