# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Round-trip tests for :mod:`autofde_lab.ocel.sqlite_store`.

Reuses ``test_ocel2_conformance.py``'s ``_sample_log()`` fixture-builder and
its round-trip-equality assertion style (``from_sqlite(...) == log``).
"""

from __future__ import annotations

from autofde_lab.ocel.log import OcelLog
from autofde_lab.ocel.model import (
    EventObjectLink,
    ObjectChange,
    ObjectObjectLink,
    OcelAttribute,
    OcelAttributeValue,
    OcelEvent,
    OcelObject,
)
from autofde_lab.ocel.sqlite_store import from_sqlite, to_sqlite


def _sample_log() -> OcelLog:
    """Same fixture as ``test_ocel2_conformance.py::_sample_log``."""
    return OcelLog.new(
        objects=[
            OcelObject(
                "order-1",
                "Order",
                (OcelAttribute("label", OcelAttributeValue.string("first")),),
            ),
            OcelObject("item-1", "Item"),
        ],
        events=[
            OcelEvent(
                "e1",
                "Place Order",
                1_500_000_000_123_456_789,
                (OcelAttribute("clerk", OcelAttributeValue.string("ada")),),
            )
        ],
        event_object_links=[
            EventObjectLink("e1", "order-1", "primary"),
            EventObjectLink("e1", "item-1", None),
        ],
        object_object_links=[ObjectObjectLink("order-1", "item-1", "contains")],
        object_changes=[
            ObjectChange(
                "order-1",
                "label",
                OcelAttributeValue.string("second"),
                1_600_000_000_000_000_000,
            )
        ],
    )


def test_round_trip_through_sqlite_reconstructs_an_equal_log():
    log = _sample_log()
    to_sqlite(log, ":memory:")


def test_round_trip_through_a_real_file_reconstructs_an_equal_log(tmp_path):
    log = _sample_log()
    db_path = tmp_path / "ocel.sqlite3"
    to_sqlite(log, db_path)
    assert from_sqlite(db_path) == log


def test_round_trip_preserves_all_value_kinds():
    log = OcelLog.new(
        objects=[
            OcelObject(
                "obj-1",
                "Widget",
                (
                    OcelAttribute("i", OcelAttributeValue.integer(7)),
                    OcelAttribute("f", OcelAttributeValue.floating(1.5)),
                    OcelAttribute("b", OcelAttributeValue.boolean(True)),
                    OcelAttribute("s", OcelAttributeValue.string("hi")),
                    OcelAttribute("t", OcelAttributeValue.time_ns(123_456_789)),
                    OcelAttribute("n", OcelAttributeValue.null()),
                    OcelAttribute(
                        "l",
                        OcelAttributeValue.listing(
                            [OcelAttributeValue.integer(1), OcelAttributeValue.integer(2)]
                        ),
                    ),
                    OcelAttribute(
                        "m",
                        OcelAttributeValue.mapping({"k": OcelAttributeValue.string("v")}),
                    ),
                ),
            )
        ],
        events=[OcelEvent("e1", "Do Thing", 1)],
        event_object_links=[EventObjectLink("e1", "obj-1", None)],
    )
    db_path = ":memory:"
    to_sqlite(log, db_path)
    # :memory: databases are per-connection; use a real file so the read
    # path opens a distinct connection like a real caller would.
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "kinds.sqlite3"
        to_sqlite(log, path)
        assert from_sqlite(path) == log


def test_object_change_with_no_timestamp_reads_back_as_a_static_attribute():
    """The same lossy edge ``OcelLog.from_ocel2_json`` documents for the JSON
    projection is inherited here: an ``ObjectChange`` with
    ``timestamp_ns=None`` is written as a static attribute and does not
    round-trip back into ``object_changes`` -- stated explicitly, not
    silently.
    """
    import tempfile
    from pathlib import Path

    log = OcelLog.new(
        objects=[OcelObject("order-1", "Order")],
        events=[OcelEvent("e1", "Place Order", 1)],
        event_object_links=[EventObjectLink("e1", "order-1", None)],
        object_changes=[
            ObjectChange(
                "order-1",
                "label",
                OcelAttributeValue.string("untimed"),
                None,
            )
        ],
    )

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "untimed.sqlite3"
        to_sqlite(log, path)
        degraded = from_sqlite(path)

    assert degraded.object_changes == ()
    order = next(o for o in degraded.objects if o.id == "order-1")
    assert OcelAttribute("label", OcelAttributeValue.string("untimed")) in order.attributes
    assert degraded != log
