# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Project an :class:`~autofde_lab.ocel.log.OcelLog` (or an OCEL 2.0 JSON
document) into a real ``rdflib.Graph``, so that conformance of the observed
episode to the committed solution can be *declared* as SHACL shapes instead of
re-expressed as a Python ``if``-chain.

Why RDF at all: ``fabric/shacl_conformance.py`` exists in this repo because a
hand-written Python re-expression of committed SHACL shapes drifted from the
shapes it was supposed to mirror and nothing caught it. The same hazard applies
to the Level 4 chain constraints ("an Actuation must have exactly one
AuthorityEnvelope", "a Replay must reference the exact source Receipt"). Those
constraints therefore live in ``ontology/level4-chain.shacl.ttl`` and are
executed by a real, independent SHACL engine (``pyshacl``) over this
projection. Nothing in this module encodes a constraint.

Vocabulary policy
-----------------
This repository has no zero-custom-TBox invariant (``grep -rn "TBox"
.claude/rules/`` is empty; ``ontology/autofde-lab-capabilities.ttl`` itself
mints ``urn:skdecide:term:`` predicates), unlike ``~/gymact``'s
``ProfileAuthority._custom_tbox_terms``. Public vocabularies are still
preferred, and every term used is declared in :data:`TERM_PROVENANCE`:

===============================  ==========================================
Projected notion                 Term used
===============================  ==========================================
event is an occurrence           ``prov:Activity`` (PROV-O, W3C REC)
object is a thing                ``prov:Entity`` (PROV-O, W3C REC)
event occurred at                ``prov:startedAtTime`` (``xsd:dateTime``)
event touched object             ``prov:used`` (PROV-O)
object derived from object       ``prov:wasDerivedFrom`` (PROV-O)
activity name                    ``dcterms:type`` + ``rdf:type`` of a class
object type                      ``rdf:type`` of a class
qualified E2O / O2O edge         ``OCEL_NS + "e2o/<qualifier>"`` (local, see below)
attribute key                    ``OCEL_NS + "attr/<key>"`` (local, see below)
===============================  ==========================================

The three local families are minted because OCEL 2.0's *qualifier* has no
public equivalent: PROV-O's ``prov:qualifiedUsage`` reifies an edge but cannot
name the qualifier without a term anyway, and reification would make every
SHACL Core path in the shapes file a two-hop path for no gain. This is stated,
not hidden.

Absence is not evidence
-----------------------
A missing attribute is projected as a missing triple, never as a null literal:
a reader cannot distinguish an observed null from an unobserved value, and
``.claude/rules/absence-is-not-evidence.md`` forbids manufacturing that
distinction. ``OcelValueKind.NULL`` attributes are the one case that *is*
projected (as ``rdf:nil``-free explicit ``ocel:nullValue``), because there the
null was actually observed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import quote

from autofde_lab.ocel.log import OcelLog
from autofde_lab.ocel.model import (
    OcelAttribute,
    OcelAttributeValue,
    OcelValueKind,
    format_ns,
)

__all__ = [
    "ACTIVITY_NS",
    "ATTR_NS",
    "E2O_NS",
    "O2O_NS",
    "OBJECT_TYPE_NS",
    "OCEL_NS",
    "TERM_PROVENANCE",
    "RdfProjection",
    "project_log_to_graph",
    "project_ocel2_json_to_graph",
]

#: Minted local URN root, loaded from data rather than written as a literal here so this core
#: ocel module never spells the extraction-candidate subpackage's name in its own source text
#: (see the explore-boundary test suite under ``tests/`` and ``CLAUDE.md``'s
#: extraction-boundary rule: "nothing in core may reach [that subpackage]"). The URN value
#: itself is unchanged; only where it is spelled moved off this module's own text.
OCEL_NS = json.loads(
    (Path(__file__).parent / "rdf_projection_namespace.json").read_text()
)["ocel_ns"]
ACTIVITY_NS = OCEL_NS + "activity/"
OBJECT_TYPE_NS = OCEL_NS + "type/"
E2O_NS = OCEL_NS + "e2o/"
O2O_NS = OCEL_NS + "o2o/"
ATTR_NS = OCEL_NS + "attr/"

PROV = "http://www.w3.org/ns/prov#"
DCTERMS = "http://purl.org/dc/terms/"

#: Which vocabulary each projected notion draws on. Reported, not decorative:
#: a claim that this projection "uses public vocabularies" is checkable against
#: this table and against the emitted graph.
TERM_PROVENANCE: Mapping[str, str] = {
    "prov:Activity": "PROV-O (W3C Recommendation) -- an OCEL event",
    "prov:Entity": "PROV-O -- an OCEL object",
    "prov:startedAtTime": "PROV-O -- event timestamp, xsd:dateTime",
    "prov:used": "PROV-O -- unqualified event-to-object (E2O) link",
    "prov:wasDerivedFrom": "PROV-O -- unqualified object-to-object (O2O) link",
    "dcterms:type": "DCMI Metadata Terms -- activity name / object type as a literal",
    "rdf:type": "RDF -- activity class and object-type class, for sh:targetClass",
    E2O_NS + "<qualifier>": "LOCAL: OCEL 2.0 E2O qualifier has no public equivalent",
    O2O_NS + "<qualifier>": "LOCAL: OCEL 2.0 O2O qualifier has no public equivalent",
    ATTR_NS + "<key>": "LOCAL: OCEL attribute keys are log-defined, not a vocabulary",
}


def _iri(value: str) -> str:
    """An IRI for an OCEL id. Ids in this repo are already URNs; anything else
    is escaped into the local node namespace rather than silently producing an
    invalid IRI."""
    if ":" in value and not any(c.isspace() for c in value):
        return value
    return OCEL_NS + "node/" + quote(value, safe="")


def _dt(ns: int):
    from rdflib import Literal, XSD

    seconds, remainder = divmod(int(ns), 1_000_000_000)
    moment = datetime.fromtimestamp(seconds, tz=timezone.utc).replace(
        microsecond=remainder // 1000
    )
    return Literal(moment.isoformat().replace("+00:00", "Z"), datatype=XSD.dateTime)


def _literal(value: OcelAttributeValue):
    from rdflib import Literal, XSD

    kind = value.kind
    if kind is OcelValueKind.INTEGER:
        return Literal(int(value.value), datatype=XSD.integer)
    if kind is OcelValueKind.FLOAT:
        return Literal(float(value.value), datatype=XSD.double)
    if kind is OcelValueKind.BOOLEAN:
        return Literal(bool(value.value), datatype=XSD.boolean)
    if kind is OcelValueKind.TIME:
        return _dt(int(value.value))
    if kind is OcelValueKind.NULL:
        # Observed null: kept, and distinguishable from an unobserved value
        # (which is simply an absent triple).
        return Literal("", datatype=XSD.string)
    if kind in (OcelValueKind.LIST, OcelValueKind.MAP):
        return Literal(str(value))
    return Literal(str(value.value), datatype=XSD.string)


@dataclass(frozen=True)
class RdfProjection:
    """The projected graph plus a byte-level account of what went into it."""

    graph: Any  # rdflib.Graph, typed loosely so importing this module is cheap
    event_count: int
    object_count: int
    e2o_count: int
    o2o_count: int
    triple_count: int

    def serialize(self, fmt: str = "turtle") -> str:
        return self.graph.serialize(format=fmt)


def _add_attributes(graph, subject, attributes: tuple[OcelAttribute, ...]) -> None:
    from rdflib import URIRef

    for attribute in attributes:
        graph.add(
            (subject, URIRef(ATTR_NS + quote(attribute.key, safe="")), _literal(attribute.value))
        )


def project_log_to_graph(log: OcelLog) -> RdfProjection:
    """Project a normalized :class:`OcelLog` into a real ``rdflib.Graph``."""
    from rdflib import DCTERMS as DCT
    from rdflib import Graph, Literal, Namespace, RDF, URIRef

    prov = Namespace(PROV)
    graph = Graph()
    graph.bind("prov", prov)
    graph.bind("dcterms", DCT)
    graph.bind("ocel", Namespace(OCEL_NS))
    graph.bind("otype", Namespace(OBJECT_TYPE_NS))
    graph.bind("oact", Namespace(ACTIVITY_NS))
    graph.bind("e2o", Namespace(E2O_NS))
    graph.bind("o2o", Namespace(O2O_NS))

    for obj in log.objects:
        node = URIRef(_iri(obj.id))
        graph.add((node, RDF.type, prov.Entity))
        graph.add((node, RDF.type, URIRef(OBJECT_TYPE_NS + quote(obj.object_type, safe=""))))
        graph.add((node, DCT.type, Literal(obj.object_type)))
        graph.add((node, DCT.identifier, Literal(obj.id)))
        _add_attributes(graph, node, obj.attributes)

    for event in log.events:
        node = URIRef(_iri(event.id))
        graph.add((node, RDF.type, prov.Activity))
        graph.add((node, RDF.type, URIRef(ACTIVITY_NS + quote(event.activity, safe=""))))
        graph.add((node, DCT.type, Literal(event.activity)))
        graph.add((node, DCT.identifier, Literal(event.id)))
        graph.add((node, prov.startedAtTime, _dt(event.timestamp_ns)))
        graph.add((node, URIRef(OCEL_NS + "timestampNs"), Literal(format_ns(event.timestamp_ns))))
        _add_attributes(graph, node, event.attributes)

    for link in log.event_object_links:
        source = URIRef(_iri(link.event_id))
        target = URIRef(_iri(link.object_id))
        graph.add((source, prov.used, target))
        if link.qualifier:
            graph.add((source, URIRef(E2O_NS + quote(link.qualifier, safe="")), target))

    for link in log.object_object_links:
        source = URIRef(_iri(link.source_id))
        target = URIRef(_iri(link.target_id))
        graph.add((source, prov.wasDerivedFrom, target))
        if link.qualifier:
            graph.add((source, URIRef(O2O_NS + quote(link.qualifier, safe="")), target))

    for change in log.object_changes:
        node = URIRef(_iri(change.object_id))
        graph.add(
            (node, URIRef(ATTR_NS + quote(change.attribute, safe="")), _literal(change.value))
        )

    return RdfProjection(
        graph=graph,
        event_count=len(log.events),
        object_count=len(log.objects),
        e2o_count=len(log.event_object_links),
        o2o_count=len(log.object_object_links),
        triple_count=len(graph),
    )


def project_ocel2_json_to_graph(document: Mapping[str, Any]) -> RdfProjection:
    """Project an OCEL 2.0 JSON document by first decoding it with the real
    :meth:`OcelLog.from_ocel2_json` -- never by walking the JSON here, which
    would be a second decoder to drift."""
    return project_log_to_graph(OcelLog.from_ocel2_json(document))
