# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for autofde_lab.ocel — real logs, real refusals.

**Ownership.** This file owns the *in-memory model*: construction via
``append_event``/``with_objects``, the whole ``OcelRefusal`` catalogue raised by
``validate()`` / ``validate_locality()``, and digest/canonical-JSON stability.

It does **not** own the OCEL 2.0 *wire format*. Document shape, the published
JSON Schema, timestamp parsing/formatting, third-party fixtures and the recorded
spec-vs-schema deviations all belong to ``test_ocel2_conformance.py``, which
checks them against the specification rather than against this package. Rules
proven there are not re-proven here.

**Collapse convention.** Where several adversarial constructions falsify one
law, they are driven from a table and *every* case is executed; failures
accumulate and the assertion is that the failure list is empty. A single red
item therefore names every offender, which is strictly more diagnostic than N
red items each naming one.
"""

from __future__ import annotations

import json
from typing import Callable

import pytest

from autofde_lab.ocel import (
    EventObjectLink,
    ObjectChange,
    ObjectObjectLink,
    OcelAttribute,
    OcelAttributeValue,
    OcelError,
    OcelEvent,
    OcelLog,
    OcelObject,
    OcelRefusal,
    OcelValueKind,
)


def lawful_log() -> OcelLog:
    """A minimal lawful log: one object, one event, one E2O link."""
    return (
        OcelLog()
        .with_objects(OcelObject("o1", "order"))
        .append_event("e1", "place", [("o1", "belongs_to")], timestamp_ns=1_700_000_000_000_000_000)
    )


def _expect_refusal(
    build: Callable[[], OcelLog],
    refusal: OcelRefusal,
    detail: str | None,
    validate_kwargs: dict | None = None,
) -> str | None:
    """Run one adversarial case; return a failure description or ``None``."""
    try:
        log = build()
    except Exception as exc:  # pragma: no cover - construction must not raise
        return f"construction raised {exc!r}"
    try:
        log.validate(**(validate_kwargs or {}))
    except OcelError as exc:
        if exc.refusal is not refusal:
            return f"refused as {exc.refusal!r}, expected {refusal!r}"
        if detail is not None and detail not in exc.detail:
            return f"detail {exc.detail!r} does not name {detail!r}"
        return None
    return f"ACCEPTED, expected refusal {refusal!r}"


def _collect(cases: dict[str, tuple]) -> None:
    failures = {
        name: problem
        for name, args in cases.items()
        if (problem := _expect_refusal(*args)) is not None
    }
    assert not failures, f"{len(failures)}/{len(cases)} adversarial cases lost their refusal: {failures}"


# ── the lawful baseline ───────────────────────────────────────────────────


def test_construction_is_pure_and_preserves_qualifiers():
    """``append_event`` never mutates its receiver, and accepts both link spellings.

    Collapses three former items (validates-and-returns-itself, is-pure,
    accepts-bare-ids-and-qualified-pairs) — one construction law, three facets.
    """
    log = lawful_log()
    assert log.validate() is log

    base = OcelLog().with_objects(OcelObject("o1", "order"), OcelObject("i1", "item"))
    once = base.append_event("e1", "place", ["o1", ("i1", "contains")])

    assert base.events == (), "append_event mutated its receiver"
    assert base.event_object_links == ()
    assert len(once.events) == 1
    assert once.event_object_links == (
        EventObjectLink("e1", "o1", None),
        EventObjectLink("e1", "i1", "contains"),
    )
    assert once.validate() is once


# ── the structural refusal catalogue ──────────────────────────────────────


def test_structural_refusals_all_fire_with_the_right_name_and_detail():
    """Every structural adversarial construction, each asserted by refusal name.

    Collapses eight former items. Each entry is a distinct falsifier and is
    still executed and named individually; the accumulation only changes how the
    failures are *reported*, never whether they are *checked*.
    """
    def _objectless_log():
        return OcelLog.new(objects=[OcelObject("o1", "order")])

    def _event_without_objects():
        return (
            OcelLog()
            .with_objects(OcelObject("o1", "order"))
            .append_event("e1", "place", ["o1"])
            .append_event("e2", "audit", [])  # touches nothing
        )

    def _dangling_e2o():
        return OcelLog().with_objects(OcelObject("o1", "order")).append_event(
            "e1", "place", ["missing"]
        )

    def _link_from_unknown_event():
        return OcelLog.new(
            objects=[OcelObject("o1", "order")],
            events=[OcelEvent("e1", "place")],
            event_object_links=[EventObjectLink("e1", "o1"), EventObjectLink("ghost", "o1")],
        )

    def _dangling_o2o():
        base = lawful_log()
        return OcelLog.new(
            base.objects, base.events, base.event_object_links, [ObjectObjectLink("o1", "nope")]
        )

    def _dangling_object_change():
        base = lawful_log()
        return OcelLog.new(
            base.objects,
            base.events,
            base.event_object_links,
            (),
            [ObjectChange("nope", "status", OcelAttributeValue.string("x"), 5)],
        )

    def _object_with_two_types():
        return (
            OcelLog()
            .with_objects(OcelObject("o1", "order"), OcelObject("o1", "invoice"))
            .append_event("e1", "place", ["o1"])
        )

    def _event_with_two_types():
        return (
            OcelLog()
            .with_objects(OcelObject("o1", "order"))
            .append_event("e1", "place", ["o1"])
            .append_event("e1", "cancel", ["o1"])
        )

    D = OcelRefusal.DANGLING_EVENT_OBJECT_LINK
    E = OcelRefusal.EMPTY_EVENT_OBJECT_LINKS
    _collect(
        {
            # object-centricity law: no event may touch nothing
            "log-with-no-links-at-all": (_objectless_log, E, None),
            "one-event-touches-nothing": (_event_without_objects, E, "e2"),
            # referential integrity, all four link tables
            "e2o-names-unknown-object": (_dangling_e2o, D, None),
            "e2o-names-unknown-event": (_link_from_unknown_event, D, "ghost"),
            "o2o-names-unknown-target": (_dangling_o2o, D, "target"),
            "change-names-unknown-object": (_dangling_object_change, D, None),
            # Definition 2, pp. 5-6: exactly one type per entity
            "object-id-given-two-types": (
                _object_with_two_types,
                OcelRefusal.DUPLICATE_ENTITY_ID,
                "invoice",
            ),
            "event-id-given-two-types": (
                _event_with_two_types,
                OcelRefusal.DUPLICATE_ENTITY_ID,
                "cancel",
            ),
        }
    )


# ── OCPQ Definition 2 (Küsters & van der Aalst 2025, pp. 5-6) ─────────────


def test_time_stable_attributes_may_not_change_but_others_may():
    """Definition 2, p. 6: for a in {objects, type}, oaval^t_o(a) = oaval^t'_o(a).

    Collapses four former items: the ``type`` and ``objects`` parametrizations
    (two draws of one law), the JSON-document variant of the same law, and the
    positive control that a *non*-stable attribute may still change. The
    positive control is what keeps the refusal from being vacuous.
    """
    base = lawful_log()

    def _change(attribute):
        return lambda: OcelLog.new(
            base.objects,
            base.events,
            base.event_object_links,
            (),
            [ObjectChange("o1", attribute, OcelAttributeValue.string("invoice"), 5)],
        )

    def _from_hostile_document():
        """A hostile *document*, not just a hostile in-memory log."""
        return OcelLog.from_ocel2_json(
            {
                "eventTypes": [],
                "objectTypes": [],
                "events": [
                    {
                        "id": "e1",
                        "type": "place",
                        "time": "2026-01-01T00:00:00Z",
                        "attributes": [],
                        "relationships": [{"objectId": "o1", "qualifier": "belongs_to"}],
                    }
                ],
                "objects": [
                    {
                        "id": "o1",
                        "type": "order",
                        "attributes": [
                            {"name": "type", "value": "invoice", "time": "2026-02-01T00:00:00Z"}
                        ],
                        "relationships": [],
                    }
                ],
            }
        )

    T = OcelRefusal.TIME_STABLE_ATTRIBUTE_CHANGED
    _collect(
        {
            "change-to-type": (_change("type"), T, "type"),
            "change-to-objects": (_change("objects"), T, "objects"),
            "change-to-type-arriving-as-json": (_from_hostile_document, T, None),
        }
    )

    # counterpart: ``city`` in the paper's own Fig. 3(a) example does change
    mutable = OcelLog.new(
        base.objects,
        base.events,
        base.event_object_links,
        (),
        [
            ObjectChange("o1", "city", OcelAttributeValue.string("Bonn"), 5),
            ObjectChange("o1", "city", OcelAttributeValue.string("Aachen"), 9),
        ],
    )
    assert mutable.validate() is mutable, "a non-time-stable attribute was wrongly refused"


def test_strict_qualifiers_is_opt_in_and_bites_both_link_tables():
    """Definition 2, p. 6: eaval_e(objects), oaval_o(objects) subset U_qual x O.

    Collapses four former items. Off by default — "" is a member of ``U_Sigma``
    and the OCEL 2.0 schema permits it, so a qualifier-less reference is
    formally admissible; the lenient assertions below are what prove the flag is
    genuinely opt-in rather than always-on.
    """
    unqualified_e2o = OcelLog().with_objects(OcelObject("o1", "order")).append_event(
        "e1", "place", ["o1"]
    )
    base = lawful_log().with_objects(OcelObject("i1", "item"))
    unqualified_o2o = OcelLog.new(
        base.objects, base.events, base.event_object_links, [ObjectObjectLink("o1", "i1", None)]
    )
    qualified_o2o = OcelLog.new(
        base.objects, base.events, base.event_object_links, [ObjectObjectLink("o1", "i1", "contains")]
    )

    # lenient by default
    assert unqualified_e2o.validate() is unqualified_e2o
    assert unqualified_o2o.validate() is unqualified_o2o
    # and a fully qualified log survives the strict pass
    assert qualified_o2o.validate(strict_qualifiers=True) is qualified_o2o

    U = OcelRefusal.UNQUALIFIED_OBJECT_REFERENCE
    strict = {"strict_qualifiers": True}
    _collect(
        {
            "unqualified-event-to-object": (lambda: unqualified_e2o, U, None, strict),
            "unqualified-object-to-object": (lambda: unqualified_o2o, U, "i1", strict),
        }
    )


# ── Gianola 2026 locality ─────────────────────────────────────────────────


def test_locality_refusals_fire_and_a_lawful_hierarchy_passes():
    """Collapses four former items — three named refusals plus the positive control."""
    def _no_team():
        return (
            OcelLog()
            .with_objects(OcelObject("p1", "employee"))
            .append_event("e1", "assign", ["p1"])
        )

    def _two_teams():
        return (
            OcelLog()
            .with_objects(OcelObject("t1", "team"), OcelObject("t2", "team"))
            .append_event("e1", "merge_teams", ["t1", "t2"])
        )

    def _steals_a_member():
        """Gianola (2026) Example 4, transcribed from the Rust doctest at ocel.rs:852.

        ``p2`` is a member of ``t1``; a later event creates ``t2`` including
        ``p2``, which implicitly deletes the ``(t1, p2)`` relationship — a
        modification of an object other than the event's reference object.
        """
        return (
            OcelLog()
            .with_objects(
                OcelObject("t1", "team"), OcelObject("t2", "team"), OcelObject("p2", "employee")
            )
            .append_event("evt1", "create_team", ["t1", "p2"])
            .append_event("evt2", "create_team", ["t2", "p2"])
        )

    cases = {
        "no-reference-object": (_no_team, OcelRefusal.MISSING_REFERENCE_OBJECT),
        "two-reference-objects": (_two_teams, OcelRefusal.MULTIPLE_REFERENCE_OBJECTS),
        "child-moved-between-parents": (_steals_a_member, OcelRefusal.VIOLATES_LOCALITY_PRINCIPLE),
    }
    failures = {}
    for name, (build, expected) in cases.items():
        log = build()
        log.validate()  # structurally fine; the defect is a locality defect
        try:
            log.validate_locality("team", "employee")
        except OcelError as exc:
            if exc.refusal is not expected:
                failures[name] = f"refused as {exc.refusal!r}, expected {expected!r}"
        else:
            failures[name] = f"ACCEPTED, expected refusal {expected!r}"
    assert not failures, f"locality falsifiers lost: {failures}"

    lawful = (
        OcelLog()
        .with_objects(
            OcelObject("t1", "team"),
            OcelObject("t2", "team"),
            OcelObject("p2", "employee"),
            OcelObject("p3", "employee"),
        )
        .append_event("evt1", "create_team", ["t1", "p2"])
        .append_event("evt2", "create_team", ["t2", "p3"])
        .append_event("evt3", "touch_team", ["t1", "p2"])
    )
    assert lawful.validate_locality("team", "employee") is lawful


def test_every_refusal_variant_is_exercised():
    """Guards against a refusal being added without an adversarial test.

    Load-bearing for the collapses above: if a new variant appears, this fails
    until a case naming it is added to one of the tables.
    """
    covered = {
        OcelRefusal.DANGLING_EVENT_OBJECT_LINK,
        OcelRefusal.EMPTY_EVENT_OBJECT_LINKS,
        OcelRefusal.MISSING_REFERENCE_OBJECT,
        OcelRefusal.MULTIPLE_REFERENCE_OBJECTS,
        OcelRefusal.VIOLATES_LOCALITY_PRINCIPLE,
        OcelRefusal.TIME_STABLE_ATTRIBUTE_CHANGED,
        OcelRefusal.DUPLICATE_ENTITY_ID,
        OcelRefusal.UNQUALIFIED_OBJECT_REFERENCE,
    }
    assert covered == set(OcelRefusal)


# ── round trip and digest stability ───────────────────────────────────────


def rich_log() -> OcelLog:
    """A log covering every value kind, both link kinds, and a change."""
    return OcelLog.new(
        objects=[
            OcelObject(
                "o1",
                "order",
                (
                    OcelAttribute("priority", OcelAttributeValue.integer(3)),
                    OcelAttribute("weight", OcelAttributeValue.floating(1.5)),
                    OcelAttribute("rush", OcelAttributeValue.boolean(True)),
                    OcelAttribute("label", OcelAttributeValue.string("gold")),
                    OcelAttribute("opened", OcelAttributeValue.time_ns(1_000_000_007)),
                    OcelAttribute("note", OcelAttributeValue.null()),
                ),
            ),
            OcelObject("i1", "item"),
        ],
        events=[
            OcelEvent(
                "e1",
                "place",
                1_700_000_000_000_000_000,
                (
                    OcelAttribute("channel", OcelAttributeValue.string("web")),
                    OcelAttribute("units", OcelAttributeValue.integer(2)),
                    OcelAttribute("at", OcelAttributeValue.time_ns(42_000_000_000)),
                ),
            ),
            OcelEvent("e2", "ship", 1_700_000_060_000_000_000),
        ],
        event_object_links=[
            EventObjectLink("e1", "o1", "belongs_to"),
            EventObjectLink("e1", "i1", None),
            EventObjectLink("e2", "o1", "belongs_to"),
        ],
        object_object_links=[ObjectObjectLink("o1", "i1", "contains")],
        object_changes=[
            ObjectChange("o1", "status", OcelAttributeValue.string("shipped"), 1_700_000_060_000_000_000)
        ],
    )


def test_round_trip_preserves_the_whole_model_not_merely_its_shape():
    """Collapses four former items — one law (round-trip fidelity), five facets.

    Value-equality alone is a weak witness: it can pass while a *kind* is
    silently coerced. The per-facet assertions below are the ones that catch
    that, so they are kept as separate named checks inside one item.
    """
    log = rich_log().validate()
    restored = OcelLog.from_ocel2_json(log.to_ocel2_json())

    attrs = {a.key: a.value for a in restored.objects[0].attributes}
    failures = []
    if restored != log:
        failures.append("round trip is not value-equal")
    if restored is log:
        failures.append("round trip returned the same object, so it proved nothing")
    if attrs["opened"].kind is not OcelValueKind.TIME or attrs["opened"].value != 1_000_000_007:
        failures.append(f"typed time value degraded to {attrs['opened']!r}")
    if attrs["note"].kind is not OcelValueKind.NULL:
        failures.append(f"null value degraded to {attrs['note']!r}")
    if EventObjectLink("e1", "i1", None) not in restored.event_object_links:
        failures.append("qualifier-less E2O link was not preserved")
    if restored.object_changes != rich_log().object_changes:
        failures.append("object changes were not preserved")
    if len(restored.objects[0].attributes) != 6:
        failures.append(
            f"static attributes and changes were conflated: {len(restored.objects[0].attributes)} != 6"
        )
    assert not failures, f"round trip lost fidelity: {failures}"


def test_digest_is_stable_across_equal_logs_and_sensitive_to_any_change():
    """Collapses three former items. Stability without sensitivity is a constant
    function, so both directions plus the canonical-JSON shape live together."""
    failures = []
    if rich_log().digest() != rich_log().digest():
        failures.append("digest is not stable across two equal logs")
    if OcelLog.from_ocel2_json(rich_log().to_ocel2_json()).digest() != rich_log().digest():
        failures.append("digest is not stable across a round trip")
    if rich_log().append_event("e3", "cancel", ["o1"]).digest() == rich_log().digest():
        failures.append("digest did not change when the log changed")

    text = rich_log().canonical_json()
    if " " in text.split('"')[0]:
        failures.append(f"canonical json is not compact: {text[:40]!r}")
    if json.loads(text)["events"][0]["id"] != "e1":
        failures.append("canonical json is not deterministically ordered")
    assert not failures, f"digest/canonicalisation law broken: {failures}"
