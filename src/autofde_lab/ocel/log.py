# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""The OCEL log: append-friendly working form plus interchange projection.

Shapes transcribed (not copied) from ``~/wasm4pm-compat/src/ocel.rs``
(dual MIT / Apache-2.0), lines 749-900: ``OcelLog``, ``OcelLog::validate``
(:799) and ``OcelLog::validate_gianola_2026_locality`` (:852).

Two models, one value
---------------------

:class:`OcelLog` is the normalized link-table form -- five flat tables that
an executor appends to, one event plus its links per fired activity. It
projects losslessly to and from the literal OCEL 2.0 JSON document
(:class:`~autofde_lab.ocel.model.OCEL`) via :meth:`OcelLog.to_ocel2_json` and
:meth:`OcelLog.from_ocel2_json`.

Projection rules, and where the two source models disagree
----------------------------------------------------------

The Rust file carries two parallel OCEL models that do not line up
one-to-one. Each mismatch is resolved here by an explicit rule:

* **Object attributes are time-versioned in the schema model, static in the
  link-table model.** Rule: an object's static ``attributes`` are emitted at
  ``time`` = epoch (``STATIC_ATTRIBUTE_NS`` = 0); every
  :class:`~autofde_lab.ocel.model.ObjectChange` is emitted at its own time. On
  parse, ``time`` == 0 means static, anything else means a change. A change
  whose ``timestamp_ns`` is ``None`` (the Rust ``Option`` allows it) is
  emitted at 0 and therefore reads back as a *static attribute* -- the one
  known lossy edge, kept rather than silently forbidden.
* **Qualifiers are required ``String`` in the schema model, ``Option`` in the
  link-table model.** Rule: ``None`` is emitted as ``""`` and ``""`` parses
  back to ``None``.
* **Attribute value enums differ**: the schema model has ``Time`` and no
  collections; the link-table model has ``TimestampNs``, ``List`` and
  ``Map``. Rule: the union is carried, and the declared type in
  ``eventTypes`` / ``objectTypes`` is what makes a ``time`` recoverable from
  its untagged JSON string.
* **``ObjectChange.value`` is a bare ``String`` in the Rust link-table
  model.** Rule: typed here as an ``OcelAttributeValue``, so a change does
  not lose its type crossing the projection.
* **``validate`` checks only E2O objects in the source.** Rule: the same
  named refusal (``DANGLING_EVENT_OBJECT_LINK``) is extended to unknown
  event ids, O2O endpoints, and object-change targets -- structurally the
  same defect, distinguished by ``OcelError.detail``.

Determinism
-----------

Timestamps are ``int`` nanoseconds and nothing here reads a wall clock.
:meth:`OcelLog.digest` hashes
:func:`autofde_lab.fabric.canonical.canonical_json` of the interchange
projection, so two runs of the same plan produce the same digest.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, replace
from typing import Any, Iterable, Mapping, Sequence

from autofde_lab.fabric.canonical import canonical_json
from autofde_lab.ocel.model import (
    OCEL,
    OcelValueKind,
    EventObjectLink,
    OCELEvent,
    OCELEventAttribute,
    OCELObject,
    OCELObjectAttribute,
    OCELRelationship,
    OCELType,
    OCELTypeAttribute,
    ObjectChange,
    ObjectObjectLink,
    OcelAttribute,
    OcelAttributeValue,
    OcelEvent,
    OcelObject,
    format_ns,
    parse_ns,
)
from autofde_lab.ocel.refusals import OcelError, OcelRefusal

__all__ = ["OcelLog", "STATIC_ATTRIBUTE_NS", "TIME_STABLE_OBJECT_ATTRIBUTES"]

#: Sentinel ``time`` marking an object's static (non-versioned) attributes.
STATIC_ATTRIBUTE_NS = 0

_AttrSpec = Mapping[str, OcelAttributeValue] | Sequence[OcelAttribute]
_LinkSpec = str | tuple[str, str | None]

#: The complete attribute-type vocabulary OCEL 2.0 permits in an
#: ``eventTypes`` / ``objectTypes`` declaration. Specification section 8, "JSON
#: Format": *"Valid types are string, time, integer, float, and boolean."*
SPEC_ATTRIBUTE_TYPES = frozenset({"string", "time", "integer", "float", "boolean"})

#: The *time-stable* object attributes of OCPQ Definition 2 (Küsters & van der
#: Aalst 2025, arXiv:2506.11541, p. 6): *"For the time-stable attributes
#: a in {objects, type} subset U_attr, the assigned value must not change over
#: time. In particular, it should hold that for all o in O, t in T, t' in T:
#: oaval^t_o(a) = oaval^t'_o(a)."*
TIME_STABLE_OBJECT_ATTRIBUTES = frozenset({"objects", "type"})


def _declared_type(kind: OcelValueKind) -> str:
    """Map an internal value kind to a *declarable* OCEL 2.0 type string.

    :class:`~autofde_lab.ocel.model.OcelValueKind` is the union of the two source
    models and so carries ``null``, ``list`` and ``map``, none of which are in
    the specification's five-valued vocabulary above. Emitting them into a
    declaration would put an out-of-spec token in front of a conformant reader,
    so they are declared as ``string`` -- the value payload is unchanged, and
    ``OcelAttributeValue.from_json`` recovers all three from the untagged JSON
    without consulting the declaration.
    """
    name = kind.value
    return name if name in SPEC_ATTRIBUTE_TYPES else "string"


def _as_attributes(spec: _AttrSpec | None) -> tuple[OcelAttribute, ...]:
    if not spec:
        return ()
    if isinstance(spec, Mapping):
        return tuple(OcelAttribute(k, v) for k, v in spec.items())
    return tuple(spec)


def _as_link(event_id: str, spec: _LinkSpec) -> EventObjectLink:
    if isinstance(spec, str):
        return EventObjectLink(event_id, spec, None)
    object_id, qualifier = spec
    return EventObjectLink(event_id, object_id, qualifier)


@dataclass(frozen=True, slots=True)
class OcelLog:
    """An object-centric event log in normalized link-table form.

    Frozen: every mutator returns a new log, so a partially built log can be
    shared and replayed without aliasing surprises.
    """

    objects: tuple[OcelObject, ...] = field(default_factory=tuple)
    events: tuple[OcelEvent, ...] = field(default_factory=tuple)
    event_object_links: tuple[EventObjectLink, ...] = field(default_factory=tuple)
    object_object_links: tuple[ObjectObjectLink, ...] = field(default_factory=tuple)
    object_changes: tuple[ObjectChange, ...] = field(default_factory=tuple)

    # ── construction ──────────────────────────────────────────────────────

    @classmethod
    def new(
        cls,
        objects: Iterable[OcelObject] = (),
        events: Iterable[OcelEvent] = (),
        event_object_links: Iterable[EventObjectLink] = (),
        object_object_links: Iterable[ObjectObjectLink] = (),
        object_changes: Iterable[ObjectChange] = (),
    ) -> "OcelLog":
        """Build a log from the five tables (``OcelLog::new``, ocel.rs:757)."""
        return cls(
            tuple(objects),
            tuple(events),
            tuple(event_object_links),
            tuple(object_object_links),
            tuple(object_changes),
        )

    def with_objects(self, *objects: OcelObject) -> "OcelLog":
        """Return a copy with additional objects declared."""
        return replace(self, objects=self.objects + tuple(objects))

    def append_event(
        self,
        event_id: str,
        activity: str,
        objects: Sequence[_LinkSpec],
        *,
        timestamp_ns: int = 0,
        attributes: _AttrSpec | None = None,
        object_object_links: Iterable[ObjectObjectLink] = (),
        object_changes: Iterable[ObjectChange] = (),
    ) -> "OcelLog":
        """Append one occurrence and everything it touched.

        This is the executor-facing entry point: one fired activity, one
        call. ``objects`` is the event's E2O links, each either a bare object
        id or an ``(object_id, qualifier)`` pair; it is the caller's
        responsibility that the objects already exist (:meth:`with_objects`),
        which :meth:`validate` then checks.
        """
        event = OcelEvent(event_id, activity, int(timestamp_ns), _as_attributes(attributes))
        links = tuple(_as_link(event_id, spec) for spec in objects)
        return replace(
            self,
            events=self.events + (event,),
            event_object_links=self.event_object_links + links,
            object_object_links=self.object_object_links + tuple(object_object_links),
            object_changes=self.object_changes + tuple(object_changes),
        )

    # ── validation ────────────────────────────────────────────────────────

    def validate(self, *, strict_qualifiers: bool = False) -> "OcelLog":
        """Enforce the structural laws, or raise :class:`OcelError`.

        The laws are the mandatory properties of *Object-Centric Event Data*
        as given in Küsters & van der Aalst (2025), "OCPQ: Object-Centric
        Process Querying & Constraints" (arXiv:2506.11541), **Definition 2**,
        pp. 5-6, where ``L = (E, O, eaval, oaval)``.

        Returns ``self`` on success so it can be used as an admission gate in
        an expression. Laws, in check order:

        1. ``EMPTY_EVENT_OBJECT_LINKS`` -- the log has no E2O links at all, or
           some event has none. This is Definition 2's
           ``forall e in E: eaval_e(objects) != {}`` ("each event has at least
           one qualified reference to an object", p. 6). The quantifier is
           ``forall e in E``, so the **per-event** reading is the paper's own;
           the whole-log check is the degenerate case of it. This is no longer
           a judgment call.
        2. ``DANGLING_EVENT_OBJECT_LINK`` -- any link or change naming an id
           the log does not declare. Definition 2 requires
           ``eaval_e(objects) subset U_qual x O`` and
           ``oaval_o(objects) subset U_qual x O`` (pp. 5-6): the right-hand
           component must be a member of ``O``, this log's own object set.
        3. ``DUPLICATE_ENTITY_ID`` -- Definition 2 has
           ``forall e in E: eaval_e(activity) in U_etype`` ("each event has
           exactly one event type", p. 5) and
           ``forall o in O: oaval_o(type) in U_otype`` ("every object has
           exactly one object type", p. 6). A single ``activity`` /
           ``object_type`` field gives *at most* one; **exactly** one fails
           only when the same id is declared twice, which would make ``E`` or
           ``O`` a multiset with a two-valued type function.
        4. ``TIME_STABLE_ATTRIBUTE_CHANGED`` -- Definition 2, p. 6: for
           ``a in {objects, type}`` the value must not change over time. An
           :class:`~autofde_lab.ocel.model.ObjectChange` naming one of these is
           exactly the forbidden ``oaval^t_o(a) != oaval^t'_o(a)``.
        5. ``UNQUALIFIED_OBJECT_REFERENCE`` -- **opt-in only**, via
           ``strict_qualifiers=True``. Definition 2 types both reference sets
           as subsets of ``U_qual x O``, i.e. every reference carries a
           qualifier. This is off by default because the paper's ``U_qual``
           is only constrained as ``U_qual subset U_Sigma`` (Definition 1,
           p. 5), the universe of *strings*, which contains the empty string;
           and the OCEL 2.0 JSON schema requires the ``qualifier`` key to be
           present but permits ``""``. So an unqualified reference is
           formally admissible under both documents while being almost
           certainly a modelling defect -- hence a named, opt-in refusal
           rather than a default one. Turning it on by default would also
           weaken nothing but would reject conformant third-party logs.

        Args:
            strict_qualifiers: also enforce law 5 above.
        """
        object_ids = {o.id for o in self.objects}
        event_ids = {e.id for e in self.events}

        # law 3 -- Definition 2, pp. 5-6: exactly one type per entity.
        seen: dict[str, str] = {}
        for obj in self.objects:
            if obj.id in seen:
                raise OcelError(
                    OcelRefusal.DUPLICATE_ENTITY_ID,
                    f"object {obj.id!r} declared more than once (types "
                    f"{seen[obj.id]!r} and {obj.object_type!r}); OCPQ Definition 2 "
                    f"requires exactly one object type",
                )
            seen[obj.id] = obj.object_type
        seen = {}
        for event in self.events:
            if event.id in seen:
                raise OcelError(
                    OcelRefusal.DUPLICATE_ENTITY_ID,
                    f"event {event.id!r} declared more than once (activities "
                    f"{seen[event.id]!r} and {event.activity!r}); OCPQ Definition 2 "
                    f"requires exactly one event type",
                )
            seen[event.id] = event.activity

        if self.events and not self.event_object_links:
            raise OcelError(
                OcelRefusal.EMPTY_EVENT_OBJECT_LINKS,
                "log declares events but no event-to-object links",
            )
        if not self.events and not self.event_object_links:
            raise OcelError(
                OcelRefusal.EMPTY_EVENT_OBJECT_LINKS, "log has no event-to-object links"
            )

        linked = {link.event_id for link in self.event_object_links}
        for event in self.events:
            if event.id not in linked:
                raise OcelError(
                    OcelRefusal.EMPTY_EVENT_OBJECT_LINKS,
                    f"event {event.id!r} has no object links",
                )

        for link in self.event_object_links:
            if link.object_id not in object_ids:
                raise OcelError(
                    OcelRefusal.DANGLING_EVENT_OBJECT_LINK,
                    f"event {link.event_id!r} links to undeclared object {link.object_id!r}",
                )
            if link.event_id not in event_ids:
                raise OcelError(
                    OcelRefusal.DANGLING_EVENT_OBJECT_LINK,
                    f"link names undeclared event {link.event_id!r}",
                )
        for o2o in self.object_object_links:
            for side, oid in (("source", o2o.source_id), ("target", o2o.target_id)):
                if oid not in object_ids:
                    raise OcelError(
                        OcelRefusal.DANGLING_EVENT_OBJECT_LINK,
                        f"object-to-object link {side} names undeclared object {oid!r}",
                    )
        for change in self.object_changes:
            if change.object_id not in object_ids:
                raise OcelError(
                    OcelRefusal.DANGLING_EVENT_OBJECT_LINK,
                    f"object change names undeclared object {change.object_id!r}",
                )
            if change.attribute in TIME_STABLE_OBJECT_ATTRIBUTES:
                raise OcelError(
                    OcelRefusal.TIME_STABLE_ATTRIBUTE_CHANGED,
                    f"object change on {change.object_id!r} assigns time-stable "
                    f"attribute {change.attribute!r}; OCPQ Definition 2 (p. 6) requires "
                    f"oaval^t_o(a) = oaval^t'_o(a) for a in "
                    f"{sorted(TIME_STABLE_OBJECT_ATTRIBUTES)}",
                )

        if strict_qualifiers:
            for link in self.event_object_links:
                if not link.qualifier:
                    raise OcelError(
                        OcelRefusal.UNQUALIFIED_OBJECT_REFERENCE,
                        f"event {link.event_id!r} references object "
                        f"{link.object_id!r} without a qualifier",
                    )
            for o2o in self.object_object_links:
                if not o2o.qualifier:
                    raise OcelError(
                        OcelRefusal.UNQUALIFIED_OBJECT_REFERENCE,
                        f"object {o2o.source_id!r} references object "
                        f"{o2o.target_id!r} without a qualifier",
                    )
        return self

    def validate_locality(self, reference_type: str, child_type: str) -> "OcelLog":
        """Enforce Gianola et al. (2026) Assumptions 3 and 5.

        Transcribed from ``validate_gianola_2026_locality`` (ocel.rs:852).

        Assumption 3: each event has exactly one object of ``reference_type``
        among its E2O links -- otherwise ``MISSING_REFERENCE_OBJECT`` or
        ``MULTIPLE_REFERENCE_OBJECTS``.

        Assumption 5 (Locality Principle): an event may only modify the
        relationships of its own reference object. Re-parenting a
        ``child_type`` object that a previous event already attached to a
        different reference object is an *implicit deletion* of that earlier
        relationship, and is refused with ``VIOLATES_LOCALITY_PRINCIPLE``.
        Events are examined in log order, so this is replay-order sensitive
        by construction.

        Returns ``self`` on success.
        """
        object_types = {o.id: o.object_type for o in self.objects}
        child_to_parent: dict[str, str] = {}

        for event in self.events:
            reference: str | None = None
            reference_count = 0
            children: list[str] = []
            for link in self.event_object_links:
                if link.event_id != event.id:
                    continue
                otype = object_types.get(link.object_id, "")
                if otype == reference_type:
                    reference_count += 1
                    reference = link.object_id
                elif otype == child_type:
                    children.append(link.object_id)

            if reference_count == 0:
                raise OcelError(
                    OcelRefusal.MISSING_REFERENCE_OBJECT,
                    f"event {event.id!r} has no object of reference type {reference_type!r}",
                )
            if reference_count > 1:
                raise OcelError(
                    OcelRefusal.MULTIPLE_REFERENCE_OBJECTS,
                    f"event {event.id!r} has {reference_count} objects of reference "
                    f"type {reference_type!r}",
                )

            assert reference is not None
            for child in children:
                previous = child_to_parent.get(child)
                if previous is not None and previous != reference:
                    raise OcelError(
                        OcelRefusal.VIOLATES_LOCALITY_PRINCIPLE,
                        f"event {event.id!r} re-parents {child!r} from {previous!r} to "
                        f"{reference!r}, implicitly deleting a relationship of an object "
                        f"other than its reference object",
                    )
                child_to_parent[child] = reference
        return self

    # ── interchange projection ────────────────────────────────────────────

    def to_ocel2(self) -> OCEL:
        """Project to the literal OCEL 2.0 document model."""
        event_type_attrs: dict[str, dict[str, str]] = {}
        events: list[OCELEvent] = []
        for event in self.events:
            declared = event_type_attrs.setdefault(event.activity, {})
            for attr in event.attributes:
                declared[attr.key] = _declared_type(attr.value.kind)
            rels = tuple(
                OCELRelationship(link.object_id, link.qualifier or "")
                for link in self.event_object_links
                if link.event_id == event.id
            )
            events.append(
                OCELEvent(
                    id=event.id,
                    event_type=event.activity,
                    time_ns=event.timestamp_ns,
                    attributes=tuple(
                        OCELEventAttribute(a.key, a.value) for a in event.attributes
                    ),
                    relationships=rels,
                )
            )

        object_type_attrs: dict[str, dict[str, str]] = {}
        changes_by_object: dict[str, list[ObjectChange]] = {}
        for change in self.object_changes:
            changes_by_object.setdefault(change.object_id, []).append(change)

        objects: list[OCELObject] = []
        for obj in self.objects:
            declared = object_type_attrs.setdefault(obj.object_type, {})
            attrs: list[OCELObjectAttribute] = []
            for attr in obj.attributes:
                declared[attr.key] = _declared_type(attr.value.kind)
                attrs.append(
                    OCELObjectAttribute(attr.key, attr.value, STATIC_ATTRIBUTE_NS)
                )
            for change in changes_by_object.get(obj.id, ()):
                declared[change.attribute] = _declared_type(change.value.kind)
                attrs.append(
                    OCELObjectAttribute(
                        change.attribute,
                        change.value,
                        change.timestamp_ns
                        if change.timestamp_ns is not None
                        else STATIC_ATTRIBUTE_NS,
                    )
                )
            rels = tuple(
                OCELRelationship(link.target_id, link.qualifier or "")
                for link in self.object_object_links
                if link.source_id == obj.id
            )
            objects.append(
                OCELObject(
                    id=obj.id,
                    object_type=obj.object_type,
                    attributes=tuple(attrs),
                    relationships=rels,
                )
            )

        def _types(table: dict[str, dict[str, str]]) -> tuple[OCELType, ...]:
            return tuple(
                OCELType(
                    name,
                    tuple(
                        OCELTypeAttribute(k, v) for k, v in sorted(attrs.items())
                    ),
                )
                for name, attrs in table.items()
            )

        return OCEL(
            event_types=_types(event_type_attrs),
            object_types=_types(object_type_attrs),
            events=tuple(events),
            objects=tuple(objects),
        )

    def to_ocel2_json(self) -> dict[str, Any]:
        """Project to a plain OCEL 2.0 JSON-schema ``dict``."""
        doc = self.to_ocel2()

        def _type_json(t: OCELType) -> dict[str, Any]:
            return {
                "name": t.name,
                "attributes": [{"name": a.name, "type": a.value_type} for a in t.attributes],
            }

        return {
            "eventTypes": [_type_json(t) for t in doc.event_types],
            "objectTypes": [_type_json(t) for t in doc.object_types],
            "events": [
                {
                    "id": e.id,
                    "type": e.event_type,
                    "time": format_ns(e.time_ns),
                    "attributes": [
                        {"name": a.name, "value": a.value.to_json()} for a in e.attributes
                    ],
                    "relationships": [
                        {"objectId": r.object_id, "qualifier": r.qualifier}
                        for r in e.relationships
                    ],
                }
                for e in doc.events
            ],
            "objects": [
                {
                    "id": o.id,
                    "type": o.object_type,
                    "attributes": [
                        {
                            "name": a.name,
                            "value": a.value.to_json(),
                            "time": format_ns(a.time_ns),
                        }
                        for a in o.attributes
                    ],
                    "relationships": [
                        {"objectId": r.object_id, "qualifier": r.qualifier}
                        for r in o.relationships
                    ],
                }
                for o in doc.objects
            ],
        }

    @classmethod
    def from_ocel2_json(cls, document: Mapping[str, Any]) -> "OcelLog":
        """Parse an OCEL 2.0 JSON-schema ``dict`` back into the working form.

        Tolerates real-world variance seen in independently produced logs: a
        missing ``attributes`` / ``relationships`` array, a missing
        ``objectTypes`` / ``eventTypes`` declaration, and a stray ``time`` on
        an *event* attribute (which the schema does not carry -- it is
        ignored).
        """
        declared: dict[tuple[str, str], str] = {}
        for section in ("eventTypes", "objectTypes"):
            for entry in document.get(section) or ():
                for attr in entry.get("attributes") or ():
                    declared[(entry["name"], attr["name"])] = attr.get("type", "")

        events: list[OcelEvent] = []
        e2o: list[EventObjectLink] = []
        for raw in document.get("events") or ():
            etype = raw["type"]
            events.append(
                OcelEvent(
                    id=raw["id"],
                    activity=etype,
                    timestamp_ns=parse_ns(raw["time"]) if raw.get("time") else 0,
                    attributes=tuple(
                        OcelAttribute(
                            a["name"],
                            OcelAttributeValue.from_json(
                                a.get("value"), declared.get((etype, a["name"]))
                            ),
                        )
                        for a in raw.get("attributes") or ()
                    ),
                )
            )
            for rel in raw.get("relationships") or ():
                e2o.append(
                    EventObjectLink(raw["id"], rel["objectId"], rel.get("qualifier") or None)
                )

        objects: list[OcelObject] = []
        o2o: list[ObjectObjectLink] = []
        changes: list[ObjectChange] = []
        for raw in document.get("objects") or ():
            otype = raw["type"]
            static: list[OcelAttribute] = []
            for a in raw.get("attributes") or ():
                value = OcelAttributeValue.from_json(
                    a.get("value"), declared.get((otype, a["name"]))
                )
                when = parse_ns(a["time"]) if a.get("time") else STATIC_ATTRIBUTE_NS
                if when == STATIC_ATTRIBUTE_NS:
                    static.append(OcelAttribute(a["name"], value))
                else:
                    changes.append(ObjectChange(raw["id"], a["name"], value, when))
            objects.append(OcelObject(raw["id"], otype, tuple(static)))
            for rel in raw.get("relationships") or ():
                o2o.append(
                    ObjectObjectLink(raw["id"], rel["objectId"], rel.get("qualifier") or None)
                )

        return cls.new(objects, events, e2o, o2o, changes)

    # ── determinism ───────────────────────────────────────────────────────

    def canonical_json(self) -> str:
        """Stable, compact JSON of the interchange projection."""
        return canonical_json(self.to_ocel2_json())

    def digest(self) -> str:
        """SHA-256 over :meth:`canonical_json` -- replay-stable by construction."""
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()
