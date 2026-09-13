# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Independent OCEL 2.0 conformance checks for :mod:`autofde_lab.ocel`.

Written by an agent that did not build the package, against the *specification*
rather than against the package's own docstrings. Two authorities are used, and
where they disagree the disagreement is asserted rather than papered over:

* the published JSON Schema, ``https://www.ocel-standard.org/2.0/ocel20-schema-json.json``
  (draft-07), vendored below as :data:`OCEL20_JSON_SCHEMA` so this suite has no
  network dependency;
* the specification PDF, ``https://www.ocel-standard.org/2.0/ocel20_specification.pdf``,
  section 8 "JSON Format", quoted inline where a test depends on its wording.

Both were retrieved 2026-08-06.

**Ownership.** This file owns the OCEL 2.0 *wire format*: emitted document shape,
schema validity, attribute-type declarations, timestamp parsing/formatting,
third-party fixtures, and the recorded deviations where the parser is more
permissive than the schema. ``test_ocel.py`` owns the in-memory model and the
``OcelRefusal`` catalogue and does not re-prove anything here.

**Collapse convention.** Where a parametrization drew one property N times
(five ISO-8601 spellings; three fixture files x three checks), the cases are
driven from a table inside one item and *every* case is executed; failures
accumulate and the assertion is that the list is empty, so one red item names
every offender.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from autofde_lab.ocel.log import SPEC_ATTRIBUTE_TYPES, STATIC_ATTRIBUTE_NS, OcelLog
from autofde_lab.ocel.model import (
    EventObjectLink,
    ObjectChange,
    ObjectObjectLink,
    OcelAttribute,
    OcelAttributeValue,
    OcelEvent,
    OcelObject,
    format_ns,
    parse_ns,
)
from autofde_lab.ocel.refusals import OcelError

FIXTURES = pathlib.Path(__file__).parent / "fixtures"

#: Verbatim from https://www.ocel-standard.org/2.0/ocel20-schema-json.json (2026-08-06).
OCEL20_JSON_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "properties": {
        "eventTypes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "attributes": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "type": {"type": "string"},
                            },
                            "required": ["name", "type"],
                        },
                    },
                },
                "required": ["name", "attributes"],
            },
        },
        "objectTypes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "attributes": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "type": {"type": "string"},
                            },
                            "required": ["name", "type"],
                        },
                    },
                },
                "required": ["name", "attributes"],
            },
        },
        "events": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "type": {"type": "string"},
                    "time": {"type": "string", "format": "date-time"},
                    "attributes": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "value": {"type": "string"},
                            },
                            "required": ["name", "value"],
                        },
                    },
                    "relationships": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "objectId": {"type": "string"},
                                "qualifier": {"type": "string"},
                            },
                            "required": ["objectId", "qualifier"],
                        },
                    },
                },
                "required": ["id", "type", "time"],
            },
        },
        "objects": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "type": {"type": "string"},
                    "relationships": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "objectId": {"type": "string"},
                                "qualifier": {"type": "string"},
                            },
                            "required": ["objectId", "qualifier"],
                        },
                    },
                    "attributes": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "value": {"type": "string"},
                                "time": {"type": "string", "format": "date-time"},
                            },
                            "required": ["name", "value", "time"],
                        },
                    },
                },
                "required": ["id", "type"],
            },
        },
    },
    "required": ["eventTypes", "objectTypes", "events", "objects"],
}


def _validator():
    jsonschema = pytest.importorskip(
        "jsonschema", reason="UNSUPPORTED: jsonschema not installed"
    )
    return jsonschema.Draft7Validator(OCEL20_JSON_SCHEMA)


def _sample_log() -> OcelLog:
    """A log exercising every shape the projection can emit."""
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

# ── check 1: document shape, schema validity, and type declarations ───────


def test_emitted_document_has_the_spec_shape_and_validates_against_the_schema():
    """Spec section 8: "top-level arrays events, eventTypes, objects, and objectTypes".

    Collapses two former items: the shape assertion and the schema validation
    are one law about one emitted document, and the schema check subsumes
    neither the key-set nor the list-ness assertion (a superset of keys still
    validates), so both are kept as named checks inside one item.
    """
    doc = _sample_log().to_ocel2_json()
    assert set(doc) == {"eventTypes", "objectTypes", "events", "objects"}
    assert all(isinstance(v, list) for v in doc.values())
    assert list(_validator().iter_errors(doc)) == []


def test_declared_attribute_types_stay_inside_the_spec_vocabulary():
    """Spec section 8: "Valid types are string, time, integer, float, and boolean".

    Collapses two former items: the vocabulary assertion over the sample log and
    the regression guard for the union-only kinds (``null`` / ``list`` / ``map``)
    that used to be emitted verbatim as out-of-spec ``"type"`` declarations.
    Both are the same law, checked on two documents; the second document is the
    one that used to fail, so it is kept explicitly rather than folded away.
    """
    assert SPEC_ATTRIBUTE_TYPES == {"string", "time", "integer", "float", "boolean"}

    union_only = OcelLog.new(
        objects=[
            OcelObject(
                "o1",
                "T",
                (
                    OcelAttribute("n", OcelAttributeValue.null()),
                    OcelAttribute(
                        "l", OcelAttributeValue.listing([OcelAttributeValue.integer(1)])
                    ),
                    OcelAttribute(
                        "m", OcelAttributeValue.mapping({"a": OcelAttributeValue.string("b")})
                    ),
                ),
            )
        ],
        events=[OcelEvent("e1", "A", 0, (OcelAttribute("x", OcelAttributeValue.null()),))],
        event_object_links=[EventObjectLink("e1", "o1", None)],
    )

    failures = []
    for label, log in (("sample", _sample_log()), ("union-only-kinds", union_only)):
        doc = log.to_ocel2_json()
        for section in ("eventTypes", "objectTypes"):
            for entry in doc[section]:
                if set(entry) != {"name", "attributes"}:
                    failures.append(f"{label}/{section}: entry keys {set(entry)}")
                for attr in entry["attributes"]:
                    if set(attr) != {"name", "type"}:
                        failures.append(f"{label}/{section}: attribute keys {set(attr)}")
                    if attr["type"] not in SPEC_ATTRIBUTE_TYPES:
                        failures.append(f"{label}/{section}: out-of-spec type {attr['type']!r}")
        if OcelLog.from_ocel2_json(doc) != log:
            failures.append(f"{label}: the type remap cost fidelity")
    assert not failures, f"declared types left the spec vocabulary: {failures}"


def test_time_values_round_trip_only_because_the_declaration_is_right():
    """The builder's stated dependency, checked rather than trusted."""
    when = 1_700_000_000_987_654_321
    log = OcelLog.new(
        objects=[OcelObject("o1", "T")],
        events=[
            OcelEvent("e1", "A", 0, (OcelAttribute("due", OcelAttributeValue.time_ns(when)),))
        ],
        event_object_links=[EventObjectLink("e1", "o1", None)],
    )
    doc = log.to_ocel2_json()
    assert doc["eventTypes"][0]["attributes"] == [{"name": "due", "type": "time"}]
    assert OcelLog.from_ocel2_json(doc) == log

    # strip the declaration and the time silently degrades to a string
    stripped = dict(doc, eventTypes=[{"name": "A", "attributes": []}])
    degraded = OcelLog.from_ocel2_json(stripped)
    assert degraded.events[0].attributes[0].value.kind == "string"


# ── check 2: event and object record shape ────────────────────────────────


def test_event_records_use_camelcase_objectid_and_carry_untimed_attributes():
    """Collapses two former items — event shape and "event attributes carry no
    time" are two assertions about the same emitted event record. Only *object*
    attributes are time-versioned (spec section 8)."""
    doc = _sample_log().to_ocel2_json()
    event = doc["events"][0]
    assert set(event) == {"id", "type", "time", "attributes", "relationships"}
    assert event["attributes"] == [{"name": "clerk", "value": "ada"}]
    for attr in event["attributes"]:
        assert "time" not in attr
    for rel in event["relationships"]:
        assert set(rel) == {"objectId", "qualifier"}  # camelCase, per schema
        assert "object_id" not in rel and "objectID" not in rel
    assert [r["objectId"] for r in event["relationships"]] == ["order-1", "item-1"]
    # qualifier is required by the schema; None becomes ""
    assert event["relationships"][1]["qualifier"] == ""


def test_object_records_are_time_versioned_from_the_specs_epoch_sentinel():
    """Collapses two former items: the object record shape and the epoch
    sentinel it depends on (spec section 7 uses 1970-01-01 00:00 UTC for the
    initial value assignment) are one law about one emitted object record."""
    assert STATIC_ATTRIBUTE_NS == 0
    assert format_ns(STATIC_ATTRIBUTE_NS).startswith("1970-01-01T00:00:00")

    doc = _sample_log().to_ocel2_json()
    obj = next(o for o in doc["objects"] if o["id"] == "order-1")
    assert set(obj) == {"id", "type", "attributes", "relationships"}
    for attr in obj["attributes"]:
        assert set(attr) == {"name", "value", "time"}
    assert obj["attributes"] == [
        {"name": "label", "value": "first", "time": "1970-01-01T00:00:00.000000000Z"},
        {"name": "label", "value": "second", "time": "2020-09-13T12:26:40.000000000Z"},
    ]
    assert obj["relationships"] == [{"objectId": "item-1", "qualifier": "contains"}]


# ── check 3: timestamps ───────────────────────────────────────────────────


def test_timestamps_parse_every_iso8601_variant_and_survive_nanosecond_exact():
    """Collapses eight former items (five parametrized ISO-8601 variants plus
    the format-checker, the nanosecond round trip, and the offset-equivalence
    check that used to live in ``test_ocel.py``). One law — nanosecond-exact,
    RFC-3339-tolerant time handling — previously drawn eight times.

    ``parse_ns`` is this repo's only clock boundary, so every accepted spelling
    is still exercised by name; the failures accumulate rather than short-circuit
    so one red item names every spelling that broke.
    """
    variants = [
        "1970-01-01T00:00:00Z",  # the spec's own example
        "2022-02-03T07:30:00Z",
        "2026-06-19T18:13:43.490Z",  # 3 fractional digits, as third-party logs emit
        "2017-07-14T02:40:00.123456789Z",  # 9, as we emit
        "2022-02-03T07:30:00+01:00",  # RFC 3339 numeric offset
    ]
    failures = []
    for text in variants:
        try:
            assert isinstance(parse_ns(text), int)
        except Exception as exc:
            failures.append(f"parse_ns({text!r}) -> {exc!r}")

    # fractional widths recover the exact sub-second component
    for text, expected in (("2026-06-19T06:22:27.725Z", 725_000_000), ("2026-06-19T06:22:27Z", 0)):
        got = parse_ns(text) % 1_000_000_000
        if got != expected:
            failures.append(f"parse_ns({text!r}) sub-second {got} != {expected}")

    # a numeric offset denotes the same instant as its UTC spelling
    if parse_ns("2026-06-19T08:22:27+02:00") != parse_ns("2026-06-19T06:22:27Z"):
        failures.append("a +02:00 offset was not normalised to UTC")

    # our own output is nanosecond-exact and passes a date-time format checker
    jsonschema = pytest.importorskip("jsonschema", reason="UNSUPPORTED: jsonschema not installed")
    fmt = jsonschema.FormatChecker()
    for ns in (0, 1, 999_999_999, 1_500_000_000_123_456_789, 1_700_000_000_123_456_789):
        if parse_ns(format_ns(ns)) != ns:
            failures.append(f"format_ns/parse_ns round trip lost {ns}")
        if not fmt.conforms(format_ns(ns), "date-time"):
            failures.append(f"format_ns({ns}) = {format_ns(ns)!r} is not a valid date-time")
    assert not failures, f"timestamp handling broken: {failures}"


# ── check 4: the builder's known lossy edge ───────────────────────────────


def test_only_an_untimed_object_change_degrades_and_it_degrades_at_most_once():
    """Documented lossy edge, reproduced, together with its control.

    Collapses two former items — the lossy (``timestamp_ns=None``) and the
    non-lossy (timed) case are the two halves of one statement about *where* the
    loss is. Without the timed control the lossy assertion would not distinguish
    "this edge is lossy" from "round-tripping object changes is lossy".

    The loss is an *internal-model* artifact, not a spec violation: the emitted
    document is schema-valid and the spec has no representation for an untimed
    value assignment (section 7 explicitly maps a missing timestamp onto the
    epoch). What is lost is the ability to distinguish "static" from "changed at
    time 0" after a round trip.
    """
    def _log(ts):
        return OcelLog.new(
            objects=[OcelObject("o1", "T")],
            events=[OcelEvent("e1", "A", 0)],
            event_object_links=[EventObjectLink("e1", "o1", None)],
            object_changes=[ObjectChange("o1", "st", OcelAttributeValue.string("done"), ts)],
        )

    # control: a timed change is not lossy at all
    timed = _log(5_000_000_000)
    assert OcelLog.from_ocel2_json(timed.to_ocel2_json()) == timed

    untimed = _log(None)
    doc = untimed.to_ocel2_json()
    assert doc["objects"][0]["attributes"] == [
        {"name": "st", "value": "done", "time": "1970-01-01T00:00:00.000000000Z"}
    ]
    assert list(_validator().iter_errors(doc)) == []  # still conformant on the wire

    back = OcelLog.from_ocel2_json(doc)
    assert back != untimed
    assert back.object_changes == ()
    assert back.objects[0].attributes == (
        OcelAttribute("st", OcelAttributeValue.string("done")),
    )
    # ...and it is stable from there: the degradation happens at most once
    assert OcelLog.from_ocel2_json(back.to_ocel2_json()) == back


# ── check 5: third-party fixtures ─────────────────────────────────────────

_FIXTURES = sorted(FIXTURES.glob("*.json"))


@pytest.mark.skipif(not _FIXTURES, reason="BLOCKED:POWLV2LSP_ABSENT")
def test_every_third_party_fixture_is_ocel2_validates_and_round_trips_faithfully():
    """Collapses nine former items (three checks x three fixture files) plus the
    two fixture items that used to be re-drawn in ``test_ocel.py``.

    The parametrization was three draws of one property per check, and the three
    checks form one pipeline over one document. Every fixture is still visited
    and named: failures accumulate per ``(fixture, check)`` pair, so one red item
    reports exactly which file failed which stage — the parametrized form
    reported the same information across nine items.
    """
    validator = _validator()
    failures = []

    def _ev(d):
        return {
            e["id"]: (
                e["type"],
                parse_ns(e["time"]),
                {a["name"]: a["value"] for a in e.get("attributes") or ()},
                sorted(
                    (r["objectId"], r.get("qualifier") or "")
                    for r in e.get("relationships") or ()
                ),
            )
            for e in d["events"]
        }

    def _ob(d):
        return {
            o["id"]: (
                o["type"],
                sorted(
                    (a["name"], json.dumps(a["value"]), parse_ns(a["time"]) if a.get("time") else 0)
                    for a in o.get("attributes") or ()
                ),
                sorted(
                    (r["objectId"], r.get("qualifier") or "")
                    for r in o.get("relationships") or ()
                ),
            )
            for o in d["objects"]
        }

    for path in _FIXTURES:
        name = path.name
        doc = json.loads(path.read_text())

        # (a) OCEL 2.0 shaped, with an OCEL 1.0 negative control
        if not set(doc) >= {"eventTypes", "objectTypes", "events", "objects"}:
            failures.append(f"{name}: missing top-level OCEL 2.0 arrays")
        if any(k.startswith("ocel:") for k in doc):
            failures.append(f"{name}: carries OCEL 1.0 vocabulary")

        log = OcelLog.from_ocel2_json(doc)

        # (b) parses into a non-empty, *lawful* log (this stage is the one
        #     ``test_ocel.py`` used to own; ``validate()`` is the load-bearing call)
        if not log.events or not log.objects:
            failures.append(f"{name}: parsed to an empty log")
        try:
            log.validate()
        except Exception as exc:
            failures.append(f"{name}: validate() -> {exc!r}")

        # (c) our emission is schema-valid even where the input was not, and
        #     re-parsing it is idempotent
        emitted = log.to_ocel2_json()
        errors = [e.message for e in validator.iter_errors(emitted)]
        if errors:
            failures.append(f"{name}: emitted document is not schema-valid: {errors[:3]}")
        if OcelLog.from_ocel2_json(emitted) != log:
            failures.append(f"{name}: re-parsing our own emission is not idempotent")

        # (d) every field a conformant reader needs survives
        if _ev(emitted) != _ev(doc):
            failures.append(f"{name}: event fields changed across the round trip")
        if _ob(emitted) != _ob(doc):
            failures.append(f"{name}: object fields changed across the round trip")

    assert not failures, f"{len(_FIXTURES)} fixtures, {len(failures)} defects: {failures}"


@pytest.mark.skipif(
    not pathlib.Path.home().joinpath("powlv2lsp/ocel_fig3b.json").exists(),
    reason="BLOCKED:POWLV2LSP_ABSENT",
)
def test_excluded_fixture_really_is_ocel_1_0():
    """Checks the PROVENANCE.md exclusion claim rather than trusting it."""
    doc = json.loads(pathlib.Path.home().joinpath("powlv2lsp/ocel_fig3b.json").read_text())
    assert any(k.startswith("ocel:") for k in doc)
    assert not {"eventTypes", "objectTypes", "events", "objects"} & set(doc)
    assert list(_validator().iter_errors(doc))  # fails the OCEL 2.0 schema


# ── check 6: what we accept that we should reject ─────────────────────────

_MINIMAL_EVENT = {
    "id": "e",
    "type": "A",
    "time": "1970-01-01T00:00:00Z",
    "relationships": [{"objectId": "ghost", "qualifier": "q"}],
}


def test_dangling_objectid_is_refused_by_validate():
    """The one conformance defect that *is* caught, and caught by name.

    Kept separate from the recorded deviations below because it is the positive
    control for them: it proves the parser/validator split can name a refusal at
    all, so "no refusal was raised" in the deviations is a real finding rather
    than an absent mechanism.
    """
    doc = {
        "eventTypes": [],
        "objectTypes": [],
        "objects": [{"id": "o1", "type": "T"}],
        "events": [_MINIMAL_EVENT],
    }
    log = OcelLog.from_ocel2_json(doc)  # the parser is permissive by design
    with pytest.raises(OcelError) as excinfo:
        log.validate()
    assert excinfo.value.refusal == "DanglingEventObjectLink"


def test_recorded_deviations_from_the_published_schema_still_hold():
    """DEVIATIONS, recorded not fixed. Collapses four former items.

    Each is a distinct, separately named finding and each is still executed;
    they are collapsed because they share one shape — *this* is what the parser
    lets through that the schema forbids — and because a deviation ledger is
    more useful read as a list than as four scattered green items. Any entry
    that starts being *refused* will fail here and must be promoted out of this
    list into a named-refusal test.

    1. ``"required": ["eventTypes", "objectTypes", "events", "objects"]`` makes
       all four mandatory; :meth:`OcelLog.from_ocel2_json` treats each as
       optional. Permissive reading is defensible for a parser, but it means
       "it parsed" carries no conformance information about the input.
    2. Spec section 8 fixes the attribute-type vocabulary; a declaration of
       ``"type": "quaternion"`` is out of it, and the parser silently ignores
       the declaration and sniffs the untagged JSON instead.
    3. ``id``/``type``/``time`` are required on an event; a document missing
       ``id`` escapes as an unnamed ``KeyError`` rather than an
       :class:`OcelError`, so a caller branching on ``OcelError.refusal``
       cannot handle it.
    """
    failures = []

    # 1. missing required top-level keys are accepted silently
    for label, doc in (
        ("no-toplevel-keys", {}),
        ("missing-objects-and-types", {"events": [_MINIMAL_EVENT]}),
    ):
        try:
            if not isinstance(OcelLog.from_ocel2_json(doc), OcelLog):
                failures.append(f"{label}: did not return an OcelLog")
        except Exception as exc:
            failures.append(f"{label}: now raises {exc!r} -- promote this to a refusal test")

    # 2. an out-of-vocabulary attribute type declaration is accepted silently
    quaternion = {
        "eventTypes": [{"name": "A", "attributes": [{"name": "x", "type": "quaternion"}]}],
        "objectTypes": [],
        "objects": [{"id": "o1", "type": "T"}],
        "events": [
            {
                "id": "e",
                "type": "A",
                "time": "1970-01-01T00:00:00Z",
                "attributes": [{"name": "x", "value": "v"}],
                "relationships": [{"objectId": "o1", "qualifier": "q"}],
            }
        ],
    }
    try:
        log = OcelLog.from_ocel2_json(quaternion).validate()
        if log.events[0].attributes[0].value.kind != "string":
            failures.append(
                f"unknown-attribute-type: sniffed as {log.events[0].attributes[0].value.kind!r}"
            )
    except Exception as exc:
        failures.append(f"unknown-attribute-type: now raises {exc!r} -- promote to a refusal test")

    # 3. an event missing ``id`` escapes as a raw KeyError, not an OcelError
    missing_id = {
        "eventTypes": [],
        "objectTypes": [],
        "objects": [],
        "events": [{"type": "A", "time": "1970-01-01T00:00:00Z"}],
    }
    try:
        OcelLog.from_ocel2_json(missing_id)
    except KeyError:
        pass
    except OcelError as exc:
        failures.append(f"event-missing-id: now a named refusal {exc.refusal!r} -- promote it")
    except Exception as exc:
        failures.append(f"event-missing-id: raised {exc!r}, expected KeyError")
    else:
        failures.append("event-missing-id: accepted, expected KeyError")

    assert not failures, f"the recorded deviation ledger drifted: {failures}"


# ── spec-vs-schema divergence, asserted so it cannot drift unnoticed ──────


def test_native_typed_values_fail_the_published_schema_but_match_the_spec_text():
    """The two authorities disagree; this pins which side we are on.

    Published schema: an attribute ``value`` is ``{"type": "string"}``.
    Spec section 8: "Valid types are string, time, integer, float, and boolean."
    We follow the spec text (and pm4py's exporter) and emit native JSON numbers
    and booleans, which the literal schema rejects.
    """
    log = OcelLog.new(
        objects=[OcelObject("o1", "T")],
        events=[
            OcelEvent("e1", "A", 0, (OcelAttribute("n", OcelAttributeValue.integer(7)),))
        ],
        event_object_links=[EventObjectLink("e1", "o1", "q")],
    )
    doc = log.to_ocel2_json()
    assert doc["events"][0]["attributes"] == [{"name": "n", "value": 7}]
    assert doc["eventTypes"][0]["attributes"] == [{"name": "n", "type": "integer"}]
    messages = [e.message for e in _validator().iter_errors(doc)]
    assert messages == ["7 is not of type 'string'"]
