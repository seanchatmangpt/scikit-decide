# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style identity-mutation falsifiers for `autofde_lab.evidence` --
the System C (PR #37, `afl:`/`urn:autofde-lab:`) bridge from a real Level 4
trial's durable artifacts to `ontology/shapes/{level4,authority,planning}.
shacl.ttl`.

Every collaborator here is real: a real `run_real_trial` driving the real
gymact actuation subprocess, the real SQLite receipt ledger it writes, the
real `commitment.ttl`/`level4.ocel.json` it emits, the real `rdflib` graph
`level4_witness.project_trial_to_witness` builds from them, and the real
`pyshacl` engine `verify.verify_witness_graph` runs against the real
committed shapes files. No mock, stub, `patch`, or `monkeypatch` anywhere in
this file.

Mirrors `tests/ecosystem/test_level4_identity_falsifiers_chicago.py`'s proven
pattern exactly: start from a graph that genuinely conforms, mutate exactly
one identity-bearing edge, assert the real `pyshacl` report now reports
`Conforms: False` naming the specific shape/constraint that fired. Unlike
that file's hand-built `OcelLog` fixture, the baseline graph here is
projected from a real, once-per-module, end-to-end trial -- not synthesized.

Same honesty discipline as the reference file: if a mutation turns out not to
be caught by any committed shape, the test says so and asserts the real
current (`CONFORMS`) outcome with a named account of the missing shape,
rather than silently dropping the case or asserting something false.
"""

from __future__ import annotations

import pathlib

import pytest
import rdflib
from rdflib import RDF, Namespace

from autofde_lab.evidence.level4_witness import project_trial_to_witness
from autofde_lab.evidence.verify import verify_witness_graph
from autofde_lab.hub.domain.gym_procedure.level4_crown import run_real_trial
from autofde_lab.hub.domain.gym_procedure.level4_ocel import (
    build_level4_ocel,
    link_commitment_ttl,
)

AFL = Namespace("urn:autofde-lab:")
PROV = Namespace("http://www.w3.org/ns/prov#")


@pytest.fixture(scope="module")
def linked_trial(tmp_path_factory) -> pathlib.Path:
    """One real, executed, commitment-linked Level 4 trial -- the same
    fixture recipe as `test_level4_ocel_vocabulary_chicago.py::linked_trial`,
    reused rather than re-derived."""
    root = tmp_path_factory.mktemp("level4_witness_falsifiers")
    report = run_real_trial(
        3979297810, "resource_flow", {"target": 3, "capacity": 4, "mine_rate": 1}, root
    )
    if report.outcome != "EXECUTED":
        pytest.skip(f"UNSUPPORTED: trial did not reach actuation (outcome={report.outcome})")
    trial_dir = pathlib.Path(report.evidence_dir)

    built = build_level4_ocel(trial_dir)
    assert built.episode_id is not None and built.environment_id is not None
    link_commitment_ttl(
        trial_dir / "actuation" / "commitment.ttl",
        episode_id=built.episode_id,
        environment_id=built.environment_id,
    )
    rebuilt = build_level4_ocel(trial_dir)
    import json

    (trial_dir / "actuation" / "level4.ocel.json").write_text(
        json.dumps(rebuilt.log.to_ocel2_json(), sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    return trial_dir


@pytest.fixture(scope="module")
def baseline_graph(linked_trial: pathlib.Path) -> rdflib.Graph:
    """The real, unmutated witness graph -- projected once per module."""
    return project_trial_to_witness(linked_trial).graph


def _clone(graph: rdflib.Graph) -> rdflib.Graph:
    """A real, independent copy -- mutating the clone must never touch the
    module-scoped `baseline_graph` fixture other tests still depend on.

    Namespace bindings (`afl:`, `prov:`) must be copied too, not just
    triples: pyshacl's SPARQL-based (`sh:sparql`) constraints resolve
    prefixes off the *data* graph's namespace manager, not the shapes
    graph's, and a bare `rdflib.Graph()` starts with none of them bound.
    """
    out = rdflib.Graph()
    for prefix, namespace in graph.namespaces():
        out.bind(prefix, namespace)
    for triple in graph:
        out.add(triple)
    return out


def _sever(graph: rdflib.Graph, subject, predicate) -> None:
    """Remove exactly one edge; keep the object node's own type triple (if
    any) so a class-membership check still has a real node to compare
    against -- an identity falsifier repoints or unlinks, it doesn't also
    delete the target's type."""
    obj = graph.value(subject, predicate)
    assert obj is not None, f"fixture premise gone: {subject} has no {predicate} edge"
    graph.remove((subject, predicate, obj))


def _one(graph: rdflib.Graph, predicate, obj=None, subject=None):
    if obj is not None:
        return next(graph.subjects(predicate, obj))
    return next(graph.objects(subject, predicate))


def _messages(result) -> str:
    return "\n".join(result.violations)


# ── the baseline is genuinely conformant ──────────────────────────────────


def test_baseline_witness_conforms(baseline_graph: rdflib.Graph) -> None:
    result = verify_witness_graph(baseline_graph)
    assert result.conforms is not None, result.unknown_reason
    assert result.conforms is True, result.report_text
    assert result.violations == ()
    # Non-vacuous: a real, non-trivial graph actually got checked.
    assert len(baseline_graph) > 20
    assert len(list(baseline_graph.subjects(RDF.type, AFL.Level4Witness))) == 1


# ═══════════════════════════════════════════════════════════════════════════
# ENFORCED BY A COMMITTED SHAPE TODAY
# ═══════════════════════════════════════════════════════════════════════════


def test_severed_governs_candidate_is_refused(baseline_graph: rdflib.Graph) -> None:
    """planning.shacl.ttl's GovernedCandidate shape: `governsCandidate` is
    minCount 1 / maxCount 1 / sh:class PlanCandidate."""
    g = _clone(baseline_graph)
    governed = _one(g, AFL.governedCandidate, subject=_one(g, RDF.type, obj=AFL.Level4Witness))
    _sever(g, governed, AFL.governsCandidate)
    result = verify_witness_graph(g)
    assert result.conforms is False, result.report_text
    assert "exactly one PlanCandidate" in _messages(result)


def test_severed_admitted_from_candidate_set_is_refused(baseline_graph: rdflib.Graph) -> None:
    g = _clone(baseline_graph)
    governed = _one(g, AFL.governedCandidate, subject=_one(g, RDF.type, obj=AFL.Level4Witness))
    _sever(g, governed, AFL.admittedFromCandidateSet)
    result = verify_witness_graph(g)
    assert result.conforms is False, result.report_text
    assert "exactly one common CandidateSet" in _messages(result)


def test_severed_commits_to_is_refused(baseline_graph: rdflib.Graph) -> None:
    """planning.shacl.ttl's POWLCommitment shape: `commitsTo` requires a
    GovernedCandidate, not a raw PlanCandidate."""
    g = _clone(baseline_graph)
    commitment = _one(g, AFL.commitment, subject=_one(g, RDF.type, obj=AFL.Level4Witness))
    _sever(g, commitment, AFL.commitsTo)
    result = verify_witness_graph(g)
    assert result.conforms is False, result.report_text
    assert "a raw PlanCandidate is not sufficient" in _messages(result)


def test_severed_committed_process_is_refused(baseline_graph: rdflib.Graph) -> None:
    g = _clone(baseline_graph)
    commitment = _one(g, AFL.commitment, subject=_one(g, RDF.type, obj=AFL.Level4Witness))
    _sever(g, commitment, AFL.committedProcess)
    result = verify_witness_graph(g)
    assert result.conforms is False, result.report_text
    assert "exactly one POWL process" in _messages(result)


def test_severed_realizes_commitment_is_refused(baseline_graph: rdflib.Graph) -> None:
    """authority.shacl.ttl's ActuationAuthority shape."""
    g = _clone(baseline_graph)
    actuation = _one(g, AFL.actuation, subject=_one(g, RDF.type, obj=AFL.Level4Witness))
    _sever(g, actuation, AFL.realizesCommitment)
    result = verify_witness_graph(g)
    assert result.conforms is False, result.report_text
    assert "explicit POWL commitment" in _messages(result)


def test_severed_authorized_by_is_refused(baseline_graph: rdflib.Graph) -> None:
    g = _clone(baseline_graph)
    actuation = _one(g, AFL.actuation, subject=_one(g, RDF.type, obj=AFL.Level4Witness))
    _sever(g, actuation, AFL.authorizedBy)
    result = verify_witness_graph(g)
    assert result.conforms is False, result.report_text
    assert "explicit AuthorityEnvelope" in _messages(result)


def test_severed_actuation_belongs_to_trial_is_refused(baseline_graph: rdflib.Graph) -> None:
    g = _clone(baseline_graph)
    actuation = _one(g, AFL.actuation, subject=_one(g, RDF.type, obj=AFL.Level4Witness))
    _sever(g, actuation, AFL.belongsToTrial)
    result = verify_witness_graph(g)
    assert result.conforms is False, result.report_text
    assert "exactly one Trial identity" in _messages(result)


def test_severed_top_level_replay_is_refused(baseline_graph: rdflib.Graph) -> None:
    """level4.shacl.ttl's Level4Witness top-level sh:property (minCount 1)."""
    g = _clone(baseline_graph)
    witness = _one(g, RDF.type, obj=AFL.Level4Witness)
    _sever(g, witness, AFL.replay)
    result = verify_witness_graph(g)
    assert result.conforms is False, result.report_text


def test_severed_top_level_manifest_is_refused(baseline_graph: rdflib.Graph) -> None:
    g = _clone(baseline_graph)
    witness = _one(g, RDF.type, obj=AFL.Level4Witness)
    _sever(g, witness, AFL.manifest)
    result = verify_witness_graph(g)
    assert result.conforms is False, result.report_text


def test_manifest_missing_one_bound_entity_is_refused(baseline_graph: rdflib.Graph) -> None:
    """level4.shacl.ttl's SPARQL closure requires the manifest to bind
    *every* entity on the causal chain -- dropping exactly one (the
    AuthorityEnvelope) must still fail the joined-witness check even though
    every top-level property and every sub-shape individually still holds."""
    g = _clone(baseline_graph)
    witness = _one(g, RDF.type, obj=AFL.Level4Witness)
    manifest = _one(g, AFL.manifest, subject=witness)
    authority = _one(g, AFL.authority, subject=witness)
    g.remove((manifest, AFL.bindsEntity, authority))
    result = verify_witness_graph(g)
    assert result.conforms is False, result.report_text
    assert "one joined witness" in _messages(result)


def test_actuation_repointed_at_a_decoy_commitment_is_refused(baseline_graph: rdflib.Graph) -> None:
    """The load-bearing identity falsifier: adjacency is preserved (the
    `realizesCommitment` edge still points at *a* real, well-typed
    `POWLCommitment`), only the *identity* is wrong -- a decoy commitment
    minted for a different (never-actuated) trial. Cardinality and
    `sh:class` are both satisfied, so only the SPARQL closure -- which
    requires the actuation's commitment to be the SAME node the witness
    itself points at via `afl:commitment` -- can catch it."""
    g = _clone(baseline_graph)
    witness = _one(g, RDF.type, obj=AFL.Level4Witness)
    actuation = _one(g, AFL.actuation, subject=witness)
    real_commitment = _one(g, AFL.realizesCommitment, subject=actuation)

    decoy = AFL["commitment/decoy-never-witnessed"]
    g.add((decoy, RDF.type, AFL.POWLCommitment))
    g.remove((actuation, AFL.realizesCommitment, real_commitment))
    g.add((actuation, AFL.realizesCommitment, decoy))

    result = verify_witness_graph(g)
    assert result.conforms is False, result.report_text
    assert "one joined witness" in _messages(result)


def test_self_certified_observation_is_refused(baseline_graph: rdflib.Graph) -> None:
    """The self-attestation guard: level4.shacl.ttl's SPARQL closure binds
    `?actor` from `Actuation prov:wasAssociatedWith ?actor` and requires
    `FILTER (?observer != ?actor)` on the PostconditionObservation's
    `performedBy`. Making the observer the same identity as the actor is
    exactly `no-dual-bookkeeping.md`'s `SELF_CERTIFIED_POSTCONDITION` --
    the verifier attesting to its own actuation -- and must be refused."""
    g = _clone(baseline_graph)
    witness = _one(g, RDF.type, obj=AFL.Level4Witness)
    actuation = _one(g, AFL.actuation, subject=witness)
    observation = _one(g, AFL.postconditionObservation, subject=witness)
    actor = _one(g, PROV.wasAssociatedWith, subject=actuation)
    observer = _one(g, AFL.performedBy, subject=observation)
    assert actor != observer, "fixture premise gone: baseline already self-certifies"

    g.remove((observation, AFL.performedBy, observer))
    g.add((observation, AFL.performedBy, actor))

    result = verify_witness_graph(g)
    assert result.conforms is False, result.report_text
    assert "one joined witness" in _messages(result)


def test_standing_alive_without_a_witness_is_refused(baseline_graph: rdflib.Graph) -> None:
    """The `AliveStanding` shape: a `StandingAssertion` claiming
    `afl:ALIVE` must be `derivedFromWitness` an actual `Level4Witness`."""
    g = _clone(baseline_graph)
    naked = AFL["standingassertion/naked-claim"]
    g.add((naked, RDF.type, AFL.StandingAssertion))
    g.add((naked, AFL.standingValue, AFL.ALIVE))
    # deliberately no afl:derivedFromWitness edge
    result = verify_witness_graph(g)
    assert result.conforms is False, result.report_text
    assert "derived from a Level4Witness" in _messages(result)
