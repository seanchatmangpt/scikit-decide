# Architecture ontology projection

The 50 Mermaid diagrams under `docs/c4/` and `docs/diagrams/` are the admitted source observations.

`ontology/architecture.ttl` defines one shared semantic basis. `catalog/*.ttl` are **generated** ontology modules grouped into ten bundles of five diagrams: five C4 scopes plus sequence, state, flow, class, and ER families. Every source diagram becomes an individually addressable `arch:Diagram` with exact source path, SHA-256 digest, diagram kind, element count, relationship count, and parse standing.

The same generator can materialize the detailed element/relationship RDF without making that larger derivative graph another hand-maintained source of truth:

```bash
python scripts/ontology/mermaid_architecture.py
python scripts/ontology/mermaid_architecture.py --check
python scripts/ontology/mermaid_architecture.py --detail-dir /tmp/autofde-architecture-rdf
```

Validation basis:

- RDF vocabulary: `ontology/architecture.ttl`
- SHACL: `ontology/shapes/architecture.shacl.ttl`
- Generated catalog: `ontology/architecture/catalog/*.ttl`
- Source identity: `arch:sourcePath` + `arch:sourceDigest`
- Public ontology reuse: DCTERMS, PROV-O, SKOS, OWL/RDFS/XSD
- Drift/parser tests: `tests/ontology/test_architecture_diagram_ontology_chicago.py`

C4, sequence, state, flow, class, and ER syntax therefore share one graph algebra. Mermaid stays the admitted visualization source; RDF is its mechanically derived semantic projection.
