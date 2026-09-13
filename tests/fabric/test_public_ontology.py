from autofde_lab.fabric.public_ontology import (
    CONCEPT_ALIGNMENT,
    PUBLIC_PREFIXES,
    aligned_iri,
    emit_alignment_turtle,
)


def test_core_semantics_are_aligned_to_public_vocabularies():
    assert aligned_iri("Observation") == "http://www.w3.org/ns/sosa/Observation"
    assert aligned_iri("AuthorityPolicy") == "http://www.w3.org/ns/odrl/2/Policy"
    assert aligned_iri("GeneratedBy") == "http://www.w3.org/ns/prov#wasGeneratedBy"
    assert {qname.split(":", 1)[0] for qname in CONCEPT_ALIGNMENT.values()} <= set(
        PUBLIC_PREFIXES
    )


def test_alignment_projection_is_deterministic_and_uses_equivalence_not_duplicate_truth():
    first = emit_alignment_turtle()
    second = emit_alignment_turtle()
    assert first == second
    assert "afde:Observation owl:equivalentClass sosa:Observation ." in first
    assert "afde:GeneratedBy owl:equivalentProperty prov:wasGeneratedBy ." in first
    assert "prov:" in first and "odrl:" in first and "sosa:" in first
