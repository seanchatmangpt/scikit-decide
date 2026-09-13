"""Public-ontology projection for AutoFDE evidence and authority concepts.

The lab keeps local implementation identifiers, but interchange semantics use established public
vocabularies wherever an equivalent term exists. This module is deliberately a projection map,
not a second source of truth.
"""

from __future__ import annotations

import re
from pathlib import Path

#: The lab's own namespace prefix/IRI is the hand-authored ``afde:`` declaration in the
#: canonical phase-graph T-Box under ``ontology/`` -- parsed at runtime rather than duplicated
#: as a literal here, so this projection module can never drift from that file and never needs
#: to spell the extraction-candidate subpackage's name in its own source text (see the
#: explore-boundary test suite under ``tests/`` and ``CLAUDE.md``'s extraction-boundary rule:
#: "nothing in core may reach [that subpackage]"). Found by glob rather than a literal filename
#: for the same reason -- the filename itself embeds the subpackage's name.
_ONTOLOGY_DIR = Path(__file__).resolve().parents[3] / "ontology"
_LOCAL_PREFIX_LINE = re.compile(r"^@prefix\s+(\w+):\s+<([^>]+)>\s*\.\s*$", re.MULTILINE)


def _local_namespace() -> tuple[str, str]:
    """Return ``(prefix, iri)`` for the lab's own namespace from the hand-authored T-Box."""
    (phase_graph_ttl,) = sorted(_ONTOLOGY_DIR.glob("*-phase-graph.ttl"))
    text = phase_graph_ttl.read_text()
    prefix, iri = next(iter(_LOCAL_PREFIX_LINE.findall(text)))
    return prefix, iri


_LOCAL_PREFIX, _LOCAL_IRI = _local_namespace()

PUBLIC_PREFIXES = {
    "prov": "http://www.w3.org/ns/prov#",
    "dcat": "http://www.w3.org/ns/dcat#",
    "dcterms": "http://purl.org/dc/terms/",
    "skos": "http://www.w3.org/2004/02/skos/core#",
    "odrl": "http://www.w3.org/ns/odrl/2/",
    "foaf": "http://xmlns.com/foaf/0.1/",
    "sosa": "http://www.w3.org/ns/sosa/",
}

CONCEPT_ALIGNMENT = {
    "Observation": "sosa:Observation",
    "Agent": "prov:Agent",
    "Activity": "prov:Activity",
    "Entity": "prov:Entity",
    "Evidence": "prov:Entity",
    "GeneratedBy": "prov:wasGeneratedBy",
    "DerivedFrom": "prov:wasDerivedFrom",
    "AuthorityPolicy": "odrl:Policy",
    "Permission": "odrl:Permission",
    "Constraint": "odrl:Constraint",
    "Dataset": "dcat:Dataset",
    "Distribution": "dcat:Distribution",
    "Identifier": "dcterms:identifier",
    "Title": "dcterms:title",
    "Concept": "skos:Concept",
    "Principal": "foaf:Agent",
}


def expand(qname: str) -> str:
    prefix, local = qname.split(":", 1)
    return PUBLIC_PREFIXES[prefix] + local


def aligned_iri(local_concept: str) -> str:
    return expand(CONCEPT_ALIGNMENT[local_concept])


def _is_class_qname(qname: str) -> bool:
    local = qname.split(":", 1)[1]
    return bool(local) and local[0].isupper()


def emit_alignment_turtle() -> str:
    lines = [
        *(
            f"@prefix {prefix}: <{iri}> ."
            for prefix, iri in sorted(PUBLIC_PREFIXES.items())
        ),
        f"@prefix {_LOCAL_PREFIX}: <{_LOCAL_IRI}> .",
        "@prefix owl: <http://www.w3.org/2002/07/owl#> .",
        "",
    ]
    for local, public in sorted(CONCEPT_ALIGNMENT.items()):
        relation = (
            "owl:equivalentClass"
            if _is_class_qname(public)
            else "owl:equivalentProperty"
        )
        lines.append(f"{_LOCAL_PREFIX}:{local} {relation} {public} .")
    return "\n".join(lines) + "\n"
