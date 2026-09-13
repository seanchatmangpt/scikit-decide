from pathlib import Path

from rdflib import Graph, Namespace, URIRef
from rdflib.namespace import DCTERMS, OWL, RDF, RDFS

ROOT = Path(__file__).resolve().parents[1]
AFL = Namespace("urn:autofde-lab:")
APS = Namespace("https://w3id.org/chatman/aps#")
SH = Namespace("http://www.w3.org/ns/shacl#")
EX = Namespace("urn:autofde-lab:test:aps:")
SOURCE_SHA = "b5916330905195b124409ca0e857f43b897ffc80"
SOURCE_TREE = URIRef(
    f"https://github.com/seanchatmangpt/agile-protocol-specification/tree/{SOURCE_SHA}"
)


def parse(*relative_paths: str) -> Graph:
    graph = Graph()
    for relative_path in relative_paths:
        graph.parse(ROOT / relative_path, format="turtle")
    return graph


def require(graph: Graph, subject, predicate, obj) -> None:
    assert (subject, predicate, obj) in graph, (
        f"missing triple: {subject} {predicate} {obj}"
    )


def test_profile_is_pinned_and_parseable() -> None:
    graph = parse("ontology/aps-autofde-profile.ttl")
    ontology = URIRef("urn:autofde-lab:ontology:aps-profile")
    require(graph, ontology, RDF.type, OWL.Ontology)
    require(graph, ontology, DCTERMS.source, SOURCE_TREE)
    assert str(graph.value(ontology, AFL.sourceRevision)) == SOURCE_SHA


def test_shared_standing_is_identity_mapped_without_collapsing_refusal() -> None:
    graph = parse("ontology/aps-autofde-profile.ttl", "ontology/standing.ttl")
    for name in (
        "UNKNOWN",
        "PARTIAL_ALIVE",
        "ALIVE",
        "BLOCKED",
        "BUILD_BROKEN",
        "UNSUPPORTED",
    ):
        require(graph, APS[name], OWL.sameAs, AFL[name])
        require(graph, AFL[name], RDF.type, AFL.StandingValue)

    assert (APS.REFUSED, OWL.sameAs, AFL.Refusal) not in graph
    require(graph, APS.REFUSED, DCTERMS.relation, AFL.Refusal)


def test_raw_candidate_has_no_private_path_to_do() -> None:
    graph = parse(
        "ontology/aps-autofde-profile.ttl",
        "ontology/planning.ttl",
        "ontology/process.ttl",
        "ontology/authority.ttl",
    )
    require(graph, AFL.commitsTo, RDFS.range, AFL.GovernedCandidate)
    require(graph, AFL.ProtocolActuationIntent, RDFS.subClassOf, APS.ActuationIntent)
    require(graph, AFL.intentCommitment, RDFS.range, AFL.POWLCommitment)
    require(graph, AFL.intentAuthority, RDFS.range, AFL.AuthorityEnvelope)
    assert (AFL.ProtocolActuationIntent, RDFS.subClassOf, AFL.Actuation) not in graph


def test_connected_reconstitution_fixture_reaches_derived_standing() -> None:
    graph = parse(
        "ontology/lab.ttl",
        "ontology/planning.ttl",
        "ontology/process.ttl",
        "ontology/authority.ttl",
        "ontology/evidence.ttl",
        "ontology/standing.ttl",
        "ontology/aps-autofde-profile.ttl",
        "tests/fixtures/aps/reconstitution-trial.ttl",
    )

    # SELECT / CONSTRUCT
    require(graph, EX.strategy, AFL.strategyForCandidateSet, EX["candidate-set"])
    require(graph, EX.governed, AFL.governsCandidate, EX.strategy)
    require(graph, EX.commitment, AFL.commitsTo, EX.governed)

    # DO is authorized through the existing target boundary, never by the protocol
    # intent itself.
    require(graph, EX.intent, AFL.intentCommitment, EX.commitment)
    require(graph, EX.intent, AFL.intentAuthority, EX.authority)
    require(graph, EX.actuation, AFL.authorizedBy, EX.authority)
    require(graph, EX.actuation, AFL.realizesCommitment, EX.commitment)

    # Receipt / replay / standing remain one trial-scoped causal chain.
    require(graph, EX.observation, AFL.observesActuation, EX.actuation)
    require(graph, EX.receipt, AFL.evidencesObservation, EX.observation)
    require(graph, EX["receipt-dag"], AFL.containsReceipt, EX.receipt)
    require(graph, EX.witness, AFL.receiptDag, EX["receipt-dag"])
    require(graph, EX.witness, AFL.replay, EX.replay)
    require(graph, EX.standing, AFL.derivedFromWitness, EX.witness)
    require(graph, EX.standing, AFL.standingValue, AFL.ALIVE)
    require(graph, EX.trial, AFL.reconstitutionStanding, EX.standing)


def test_shacl_profile_covers_each_new_protocol_subject() -> None:
    shapes = parse("ontology/shapes/aps-autofde-profile.shacl.ttl")
    for target in (
        AFL.AdmittedKnowledge,
        AFL.ProtocolContract,
        AFL.CandidateFalsifier,
        AFL.ProtocolActuationIntent,
        AFL.ReconstitutionTrial,
    ):
        assert any(shapes.triples((None, SH.targetClass, target))), (
            f"no SHACL target for {target}"
        )
