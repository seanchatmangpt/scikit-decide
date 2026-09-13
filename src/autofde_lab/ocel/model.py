# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Frozen dataclasses for both OCEL 2.0 models.

Shapes transcribed (not copied) from ``~/wasm4pm-compat/src/ocel.rs``, which
is dual-licensed MIT / Apache-2.0:

* the literal OCEL 2.0 JSON-schema model, lines 31-107 (``OCEL``,
  ``OCELType``, ``OCELTypeAttribute``, ``OCELEvent``, ``OCELObject``,
  ``OCELRelationship``, ``OCELEventAttribute``, ``OCELObjectAttribute``,
  ``OCELAttributeValue``);
* the normalized link-table model, lines 509-760 (``OcelAttributeValue``,
  ``OcelAttribute``, ``Object``, ``OcelEvent``, ``EventObjectLink``,
  ``ObjectObjectLink``, ``ObjectChange``).

Everything here is frozen and holds tuples, so values compare and hash by
content -- required for the round-trip equality guarantee in
:mod:`autofde_lab.ocel.log`.

Timestamps are ``int`` nanoseconds throughout the working model. Wall-clock
sources (``datetime.now``) are never read: these logs must be replay-stable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Any, Iterable, Mapping, Sequence

__all__ = [
    "OcelValueKind",
    "OcelAttributeValue",
    "OcelAttribute",
    "OcelObject",
    "OcelEvent",
    "EventObjectLink",
    "ObjectObjectLink",
    "ObjectChange",
    "OCELTypeAttribute",
    "OCELType",
    "OCELRelationship",
    "OCELEventAttribute",
    "OCELObjectAttribute",
    "OCELEvent",
    "OCELObject",
    "OCEL",
    "format_ns",
    "parse_ns",
]

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)

#: Sentinel time used for an object's *static* (non-versioned) attributes when
#: they are projected into the time-versioned OCEL 2.0 interchange form.
STATIC_ATTRIBUTE_NS = 0


def format_ns(ns: int) -> str:
    """Render integer nanoseconds as a nanosecond-precision RFC 3339 UTC stamp."""
    seconds, nanos = divmod(int(ns), 1_000_000_000)
    base = (_EPOCH + timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%S")
    return f"{base}.{nanos:09d}Z"


def parse_ns(text: str) -> int:
    """Parse an RFC 3339 stamp into integer nanoseconds (UTC).

    Accepts a trailing ``Z`` and any number of fractional digits, which
    ``datetime.fromisoformat`` does not do uniformly across versions -- hence
    the manual split rather than a library call.
    """
    raw = text.strip()
    if raw.endswith(("Z", "z")):
        raw, offset = raw[:-1], "+00:00"
    else:
        head = raw[10:]  # skip the date, so a date-level '-' is not mistaken
        idx = max(head.rfind("+"), head.rfind("-"))
        if idx >= 0:
            offset, raw = head[idx:], raw[: 10 + idx]
        else:
            offset = "+00:00"
    extra_ns = 0
    if "." in raw:
        raw, frac = raw.split(".", 1)
        frac = (frac + "0" * 9)[:9]
        extra_ns = int(frac)
    moment = datetime.fromisoformat(raw + offset)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return int((moment - _EPOCH).total_seconds()) * 1_000_000_000 + extra_ns


# ── attribute values ──────────────────────────────────────────────────────


class OcelValueKind(StrEnum):
    """Discriminator for :class:`OcelAttributeValue`.

    The Rust source carries two disjoint value enums: the schema one
    (``OCELAttributeValue``, line 98: Integer/Float/Boolean/Time/String/Null)
    and the link-table one (``OcelAttributeValue``, line 513, which drops
    ``Time`` in favour of ``TimestampNs`` and adds ``List``/``Map``). This is
    their union; see the module note in :mod:`autofde_lab.ocel.log` about how the
    extra kinds survive a JSON round trip.
    """

    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    STRING = "string"
    TIME = "time"
    NULL = "null"
    LIST = "list"
    MAP = "map"


@dataclass(frozen=True, slots=True)
class OcelAttributeValue:
    """A typed OCEL attribute value.

    ``kind`` is carried explicitly because the OCEL 2.0 JSON encoding is
    *untagged*: a ``time`` value and a ``string`` value are both JSON strings
    on the wire, and only the type declaration distinguishes them.
    """

    kind: OcelValueKind
    value: Any = None

    @classmethod
    def integer(cls, value: int) -> "OcelAttributeValue":
        return cls(OcelValueKind.INTEGER, int(value))

    @classmethod
    def floating(cls, value: float) -> "OcelAttributeValue":
        return cls(OcelValueKind.FLOAT, float(value))

    @classmethod
    def boolean(cls, value: bool) -> "OcelAttributeValue":
        return cls(OcelValueKind.BOOLEAN, bool(value))

    @classmethod
    def string(cls, value: str) -> "OcelAttributeValue":
        return cls(OcelValueKind.STRING, str(value))

    @classmethod
    def time_ns(cls, value: int) -> "OcelAttributeValue":
        return cls(OcelValueKind.TIME, int(value))

    @classmethod
    def null(cls) -> "OcelAttributeValue":
        return cls(OcelValueKind.NULL, None)

    @classmethod
    def listing(cls, values: Iterable["OcelAttributeValue"]) -> "OcelAttributeValue":
        return cls(OcelValueKind.LIST, tuple(values))

    @classmethod
    def mapping(
        cls, pairs: Mapping[str, "OcelAttributeValue"] | Sequence[tuple[str, "OcelAttributeValue"]]
    ) -> "OcelAttributeValue":
        items = pairs.items() if isinstance(pairs, Mapping) else pairs
        return cls(OcelValueKind.MAP, tuple((str(k), v) for k, v in items))

    def to_json(self) -> Any:
        """Project to the untagged JSON representation OCEL 2.0 uses."""
        if self.kind is OcelValueKind.TIME:
            return format_ns(self.value)
        if self.kind is OcelValueKind.NULL:
            return None
        if self.kind is OcelValueKind.LIST:
            return [item.to_json() for item in self.value]
        if self.kind is OcelValueKind.MAP:
            return {key: item.to_json() for key, item in self.value}
        return self.value

    @classmethod
    def from_json(cls, raw: Any, declared: str | None = None) -> "OcelAttributeValue":
        """Recover a typed value from untagged JSON plus its declared type.

        ``declared`` is the ``type`` string from the log's ``eventTypes`` /
        ``objectTypes`` declaration. Without it, a stored ``time`` is
        indistinguishable from a ``string`` and is read back as a string.
        """
        if declared is not None:
            try:
                kind = OcelValueKind(declared)
            except ValueError:
                kind = None
            if kind is OcelValueKind.TIME and isinstance(raw, str):
                return cls.time_ns(parse_ns(raw))
            if kind is OcelValueKind.FLOAT and isinstance(raw, (int, float)):
                return cls.floating(raw)
            if kind is OcelValueKind.INTEGER and isinstance(raw, bool) is False and isinstance(raw, int):
                return cls.integer(raw)
        if raw is None:
            return cls.null()
        if isinstance(raw, bool):
            return cls.boolean(raw)
        if isinstance(raw, int):
            return cls.integer(raw)
        if isinstance(raw, float):
            return cls.floating(raw)
        if isinstance(raw, list):
            return cls.listing(cls.from_json(item) for item in raw)
        if isinstance(raw, dict):
            return cls.mapping([(k, cls.from_json(v)) for k, v in raw.items()])
        return cls.string(raw)

    def __str__(self) -> str:
        if self.kind is OcelValueKind.NULL:
            return ""
        if self.kind is OcelValueKind.TIME:
            return format_ns(self.value)
        if self.kind is OcelValueKind.LIST:
            return f"list of {len(self.value)} items"
        if self.kind is OcelValueKind.MAP:
            return f"map of {len(self.value)} pairs"
        return str(self.value)


@dataclass(frozen=True, slots=True)
class OcelAttribute:
    """A key/value attribute pair (``OcelAttribute``, ocel.rs:539)."""

    key: str
    value: OcelAttributeValue


def _attrs(items: Iterable[OcelAttribute] | None) -> tuple[OcelAttribute, ...]:
    return tuple(items or ())


# ── (b) the normalized link-table model ───────────────────────────────────


@dataclass(frozen=True, slots=True)
class OcelObject:
    """An object with a typed identity (``Object``, ocel.rs:571).

    ``attributes`` here are *static*: the time-versioned history lives in
    :class:`ObjectChange`.
    """

    id: str
    object_type: str
    attributes: tuple[OcelAttribute, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class OcelEvent:
    """An occurrence: activity plus timestamp (``OcelEvent``, ocel.rs:600)."""

    id: str
    activity: str
    timestamp_ns: int = 0
    attributes: tuple[OcelAttribute, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class EventObjectLink:
    """E2O relation (``EventObjectLink``, ocel.rs:651)."""

    event_id: str
    object_id: str
    qualifier: str | None = None


@dataclass(frozen=True, slots=True)
class ObjectObjectLink:
    """O2O relation (``ObjectObjectLink``, ocel.rs:684)."""

    source_id: str
    target_id: str
    qualifier: str | None = None


@dataclass(frozen=True, slots=True)
class ObjectChange:
    """A time-stamped attribute change on an object (``ObjectChange``, ocel.rs:716).

    The Rust source types ``value`` as a bare ``String``; this uses a typed
    :class:`OcelAttributeValue` so that a change survives the interchange
    projection with its type intact. See the judgment-call note in
    :mod:`autofde_lab.ocel.log`.
    """

    object_id: str
    attribute: str
    value: OcelAttributeValue
    timestamp_ns: int | None = None


# ── (a) the literal OCEL 2.0 JSON-schema model ────────────────────────────


@dataclass(frozen=True, slots=True)
class OCELTypeAttribute:
    """Declared attribute of a type (``OCELTypeAttribute``, ocel.rs:49)."""

    name: str
    value_type: str


@dataclass(frozen=True, slots=True)
class OCELType:
    """A declared event or object type (``OCELType``, ocel.rs:42)."""

    name: str
    attributes: tuple[OCELTypeAttribute, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class OCELRelationship:
    """A qualified reference to an object (``OCELRelationship``, ocel.rs:73).

    E2O and O2O use this *same* shape; they are discriminated only by whether
    an :class:`OCELEvent` or an :class:`OCELObject` holds it.
    """

    object_id: str
    qualifier: str


@dataclass(frozen=True, slots=True)
class OCELEventAttribute:
    """Untimed event attribute (``OCELEventAttribute``, ocel.rs:56)."""

    name: str
    value: OcelAttributeValue


@dataclass(frozen=True, slots=True)
class OCELObjectAttribute:
    """Time-versioned object attribute (``OCELObjectAttribute``, ocel.rs:90)."""

    name: str
    value: OcelAttributeValue
    time_ns: int


@dataclass(frozen=True, slots=True)
class OCELEvent:
    """Interchange event (``OCELEvent``, ocel.rs:62)."""

    id: str
    event_type: str
    time_ns: int
    attributes: tuple[OCELEventAttribute, ...] = field(default_factory=tuple)
    relationships: tuple[OCELRelationship, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class OCELObject:
    """Interchange object (``OCELObject``, ocel.rs:80)."""

    id: str
    object_type: str
    attributes: tuple[OCELObjectAttribute, ...] = field(default_factory=tuple)
    relationships: tuple[OCELRelationship, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class OCEL:
    """The literal OCEL 2.0 document (``OCEL``, ocel.rs:31)."""

    event_types: tuple[OCELType, ...] = field(default_factory=tuple)
    object_types: tuple[OCELType, ...] = field(default_factory=tuple)
    events: tuple[OCELEvent, ...] = field(default_factory=tuple)
    objects: tuple[OCELObject, ...] = field(default_factory=tuple)
