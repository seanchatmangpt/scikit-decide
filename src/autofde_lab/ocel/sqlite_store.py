# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""SQLite persistence for :class:`~autofde_lab.ocel.log.OcelLog`.

Schema mirrors ``OcelLog``'s own five tuple-fields directly -- not the lossy
pm4py wide-table convention, which has no analogue for time-versioned
``object_changes`` at all:

.. code-block:: sql

    CREATE TABLE objects(id TEXT PRIMARY KEY, object_type TEXT NOT NULL);
    CREATE TABLE events(id TEXT PRIMARY KEY, activity TEXT NOT NULL, timestamp_ns INTEGER NOT NULL);
    CREATE TABLE event_object_links(event_id TEXT, object_id TEXT, qualifier TEXT);
    CREATE TABLE object_object_links(source_id TEXT, target_id TEXT, qualifier TEXT);
    CREATE TABLE object_changes(object_id TEXT, attribute TEXT, value_kind TEXT, value_json TEXT, timestamp_ns INTEGER);
    CREATE TABLE attributes(owner_table TEXT, owner_id TEXT, key TEXT, value_kind TEXT, value_json TEXT);

``value_kind``/``value_json`` is used instead of a typed column because
:meth:`~autofde_lab.ocel.model.OcelAttributeValue.to_json` is untagged: a
``time`` value and a ``string`` value both serialize to a JSON string, and
only ``value_kind`` disambiguates them on read. ``value_json`` reuses
:func:`autofde_lab.fabric.canonical.canonical_json` for the payload exactly
as :meth:`OcelLog.canonical_json` already does, so a scalar, a list, and a
map all round-trip through the same column.

The ``attributes`` table carries both object *static* attributes
(``owner_table='object'``) and event attributes (``owner_table='event'``);
``object_changes`` is its own table because it additionally carries
``timestamp_ns``, including the ``NULL`` case documented on
:class:`~autofde_lab.ocel.model.ObjectChange` and inherited here unchanged:
a change with ``timestamp_ns=None`` is written with a ``NULL`` timestamp and
read back as a static attribute in ``attributes``, not as an
:class:`~autofde_lab.ocel.model.ObjectChange` -- the exact lossy edge
``OcelLog.from_ocel2_json`` already documents for the JSON projection.

Style mirrors ``autofde_lab.fabric.cache.SQLiteERRCCache``: stdlib
``sqlite3``, ``sqlite3.connect(path, check_same_thread=False)``,
``row_factory = sqlite3.Row``, idempotent ``CREATE TABLE IF NOT EXISTS``, a
``_transaction()`` contextmanager, and a ``:memory:``-first design.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from autofde_lab.fabric.canonical import canonical_json
from autofde_lab.ocel.log import OcelLog
from autofde_lab.ocel.model import (
    EventObjectLink,
    ObjectChange,
    ObjectObjectLink,
    OcelAttribute,
    OcelAttributeValue,
    OcelEvent,
    OcelObject,
    OcelValueKind,
    parse_ns,
)

__all__ = ["to_sqlite", "from_sqlite"]


def _encode_value(value: OcelAttributeValue) -> tuple[str, str]:
    """Return ``(value_kind, value_json)`` for one attribute value.

    Scalars are encoded via ``json.dumps`` of the untagged ``to_json()``
    payload; ``list``/``map`` kinds go through ``canonical_json`` for a
    stable blob, matching ``OcelLog.canonical_json``'s own use of it.
    """
    if value.kind in (OcelValueKind.LIST, OcelValueKind.MAP):
        return value.kind.value, canonical_json(value.to_json())
    return value.kind.value, json.dumps(value.to_json())


def _decode_value(value_kind: str, value_json: str) -> OcelAttributeValue:
    kind = OcelValueKind(value_kind)
    raw = json.loads(value_json)
    if kind is OcelValueKind.TIME:
        return OcelAttributeValue.time_ns(parse_ns(raw))
    if kind is OcelValueKind.LIST:
        return OcelAttributeValue(
            OcelValueKind.LIST, tuple(OcelAttributeValue.from_json(item) for item in raw)
        )
    if kind is OcelValueKind.MAP:
        return OcelAttributeValue(
            OcelValueKind.MAP,
            tuple((str(k), OcelAttributeValue.from_json(v)) for k, v in raw.items()),
        )
    return OcelAttributeValue(kind, raw)


def _initialize(connection: sqlite3.Connection) -> None:
    connection.execute(
        "CREATE TABLE IF NOT EXISTS objects("
        "id TEXT PRIMARY KEY, object_type TEXT NOT NULL)"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS events("
        "id TEXT PRIMARY KEY, activity TEXT NOT NULL, timestamp_ns INTEGER NOT NULL)"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS event_object_links("
        "event_id TEXT, object_id TEXT, qualifier TEXT)"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS object_object_links("
        "source_id TEXT, target_id TEXT, qualifier TEXT)"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS object_changes("
        "object_id TEXT, attribute TEXT, value_kind TEXT, value_json TEXT, "
        "timestamp_ns INTEGER)"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS attributes("
        "owner_table TEXT, owner_id TEXT, key TEXT, value_kind TEXT, value_json TEXT)"
    )


@contextmanager
def _transaction(connection: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def to_sqlite(log: OcelLog, path: str | Path) -> None:
    """Write ``log`` to a fresh SQLite database at ``path``.

    ``path`` may be ``":memory:"``. Existing rows in a pre-existing database
    at ``path`` are cleared first, so this is an overwrite, not an append.
    """
    connection = sqlite3.connect(str(path), check_same_thread=False)
    try:
        connection.row_factory = sqlite3.Row
        _initialize(connection)
        with _transaction(connection) as conn:
            for table in (
                "objects",
                "events",
                "event_object_links",
                "object_object_links",
                "object_changes",
                "attributes",
            ):
                conn.execute(f"DELETE FROM {table}")

            for obj in log.objects:
                conn.execute(
                    "INSERT INTO objects(id, object_type) VALUES (?, ?)",
                    (obj.id, obj.object_type),
                )
                for attr in obj.attributes:
                    value_kind, value_json = _encode_value(attr.value)
                    conn.execute(
                        "INSERT INTO attributes(owner_table, owner_id, key, value_kind, "
                        "value_json) VALUES (?, ?, ?, ?, ?)",
                        ("object", obj.id, attr.key, value_kind, value_json),
                    )

            for event in log.events:
                conn.execute(
                    "INSERT INTO events(id, activity, timestamp_ns) VALUES (?, ?, ?)",
                    (event.id, event.activity, event.timestamp_ns),
                )
                for attr in event.attributes:
                    value_kind, value_json = _encode_value(attr.value)
                    conn.execute(
                        "INSERT INTO attributes(owner_table, owner_id, key, value_kind, "
                        "value_json) VALUES (?, ?, ?, ?, ?)",
                        ("event", event.id, attr.key, value_kind, value_json),
                    )

            for link in log.event_object_links:
                conn.execute(
                    "INSERT INTO event_object_links(event_id, object_id, qualifier) "
                    "VALUES (?, ?, ?)",
                    (link.event_id, link.object_id, link.qualifier),
                )

            for o2o in log.object_object_links:
                conn.execute(
                    "INSERT INTO object_object_links(source_id, target_id, qualifier) "
                    "VALUES (?, ?, ?)",
                    (o2o.source_id, o2o.target_id, o2o.qualifier),
                )

            for change in log.object_changes:
                value_kind, value_json = _encode_value(change.value)
                if change.timestamp_ns is None:
                    # Same lossy edge OcelLog.from_ocel2_json documents: an
                    # untimed change is indistinguishable from a static
                    # attribute once projected, so it is written here as one
                    # rather than round-tripped through object_changes.
                    conn.execute(
                        "INSERT INTO attributes(owner_table, owner_id, key, "
                        "value_kind, value_json) VALUES (?, ?, ?, ?, ?)",
                        ("object", change.object_id, change.attribute, value_kind, value_json),
                    )
                    continue
                conn.execute(
                    "INSERT INTO object_changes(object_id, attribute, value_kind, "
                    "value_json, timestamp_ns) VALUES (?, ?, ?, ?, ?)",
                    (
                        change.object_id,
                        change.attribute,
                        value_kind,
                        value_json,
                        change.timestamp_ns,
                    ),
                )
    finally:
        connection.close()


def from_sqlite(path: str | Path) -> OcelLog:
    """Reconstruct an :class:`OcelLog` from a database written by :func:`to_sqlite`.

    ``ObjectChange(timestamp_ns=None)`` is stored with a ``NULL``
    ``timestamp_ns`` and read back here as a static ``attributes`` row, not
    as an :class:`~autofde_lab.ocel.model.ObjectChange` -- the same lossy
    edge :meth:`OcelLog.from_ocel2_json` documents for the JSON projection,
    inherited by this path unchanged.
    """
    connection = sqlite3.connect(str(path), check_same_thread=False)
    try:
        connection.row_factory = sqlite3.Row
        _initialize(connection)

        object_attrs: dict[str, list[OcelAttribute]] = {}
        event_attrs: dict[str, list[OcelAttribute]] = {}
        for row in connection.execute(
            "SELECT owner_table, owner_id, key, value_kind, value_json FROM attributes"
        ):
            attr = OcelAttribute(
                row["key"], _decode_value(row["value_kind"], row["value_json"])
            )
            if row["owner_table"] == "object":
                object_attrs.setdefault(row["owner_id"], []).append(attr)
            elif row["owner_table"] == "event":
                event_attrs.setdefault(row["owner_id"], []).append(attr)

        objects = tuple(
            OcelObject(
                row["id"], row["object_type"], tuple(object_attrs.get(row["id"], ()))
            )
            for row in connection.execute("SELECT id, object_type FROM objects")
        )

        events = tuple(
            OcelEvent(
                row["id"],
                row["activity"],
                int(row["timestamp_ns"]),
                tuple(event_attrs.get(row["id"], ())),
            )
            for row in connection.execute(
                "SELECT id, activity, timestamp_ns FROM events"
            )
        )

        event_object_links = tuple(
            EventObjectLink(row["event_id"], row["object_id"], row["qualifier"])
            for row in connection.execute(
                "SELECT event_id, object_id, qualifier FROM event_object_links"
            )
        )

        object_object_links = tuple(
            ObjectObjectLink(row["source_id"], row["target_id"], row["qualifier"])
            for row in connection.execute(
                "SELECT source_id, target_id, qualifier FROM object_object_links"
            )
        )

        object_changes = tuple(
            ObjectChange(
                row["object_id"],
                row["attribute"],
                _decode_value(row["value_kind"], row["value_json"]),
                None if row["timestamp_ns"] is None else int(row["timestamp_ns"]),
            )
            for row in connection.execute(
                "SELECT object_id, attribute, value_kind, value_json, timestamp_ns "
                "FROM object_changes"
            )
        )

        return OcelLog.new(
            objects, events, event_object_links, object_object_links, object_changes
        )
    finally:
        connection.close()
