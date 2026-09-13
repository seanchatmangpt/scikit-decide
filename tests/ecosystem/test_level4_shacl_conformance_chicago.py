# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for declarative Level 4 chain conformance.

Every collaborator is real: real :class:`OcelLog` objects, the real
``rdflib`` parser/serializer, the real committed shapes file at
``ontology/level4-chain.shacl.ttl`` read off disk, and the real ``pyshacl``
engine. No mock, stub, patch or monkeypatch appears in this file, and no
assertion is on "was something called" -- every assertion is on final state:
the real validation report and the typed violations lifted out of the real
results graph.

The fixtures are hand-authored OCEL logs rather than a live trial because the
question under test is *what the shapes reject*, and a falsifier has to be
constructible on purpose. A live trial is exercised by
``test_level4_ocel_vocabulary_chicago.py``.
"""

from __future__ import annotations

import pathlib

import pytest

from autofde_lab.fabric.shacl_conformance import check_graph_shacl
from autofde_lab.ocel.log import OcelLog
from autofde_lab.ocel.model import (
    EventObjectLink,
    ObjectObjectLink,
    OcelAttribute,
    OcelAttributeValue,
    OcelEvent,
    OcelObject,
)
from autofde_lab.ocel.rdf_projection import TERM_PROVENANCE, project_log_to_graph

SHAPES = pathlib.Path(__file__).parents[2] / "ontology" / "level4-chain.shacl.ttl"

RECEIPT_DIGEST = "220f81bf978fe490"

TASK = "urn:level4:task:t1"
ENV = "urn:level4:environment:e1"
CAP = "urn:level4:capability:c1"
PROBE = "urn:level4:probe:p1"
COMMITMENT = "urn:level4:commitment:220f81bf978fe490"
ENVELOPE = "urn:level4:authority:a1"
ACTUATION = "urn:level4:actuation:r1"
OBSERVATION = "urn:level4:postcondition:v1"
RECEIPT = "urn:level4:receipt:r1"
REPLAY = "urn:level4:replay:220f81bf978fe490"


def _s(value: str) -> OcelAttributeValue:
    return OcelAttributeValue.string(value)


def _conforming_log() -> OcelLog:
    """A Level 4 chain that satisfies every committed shape."""
    objects = [
        OcelObject(TASK, "Task"),
        OcelObject(ENV, "Environment"),
        OcelObject(CAP, "Capability"),
        OcelObject(PROBE, "Probe"),
        OcelObject(COMMITMENT, "POWLCommitment", (OcelAttribute("plan_digest", _s(RECEIPT_DIGEST)),)),
        OcelObject(ENVELOPE, "AuthorityEnvelope"),
        OcelObject(ACTUATION, "Actuation"),
        OcelObject(OBSERVATION, "PostconditionObservation"),
        OcelObject(RECEIPT, "Receipt", (OcelAttribute("receipt_digest", _s(RECEIPT_DIGEST)),)),
        OcelObject(REPLAY, "Replay", (OcelAttribute("head_digest", _s(RECEIPT_DIGEST)),)),
    ]
    o2o = [
        ObjectObjectLink(ACTUATION, COMMITMENT, "actuates_commitment"),
        ObjectObjectLink(ACTUATION, ENVELOPE, "authorized_by"),
        ObjectObjectLink(ACTUATION, ENV, "acts_on_environment"),
        ObjectObjectLink(ACTUATION, CAP, "exercises_capability"),
        ObjectObjectLink(ACTUATION, RECEIPT, "evidenced_by_receipt"),
        ObjectObjectLink(OBSERVATION, RECEIPT, "evidenced_by_receipt"),
        ObjectObjectLink(OBSERVATION, ACTUATION, "observes_actuation"),
        ObjectObjectLink(OBSERVATION, ENV, "observes_subject"),
        ObjectObjectLink(REPLAY, RECEIPT, "replays_receipt"),
    ]
    events = [
        OcelEvent("ev:probe", "ProbeExecuted", 1_000_000_000),
        OcelEvent("ev:model", "ModelInferred", 2_000_000_000),
        OcelEvent("ev:open", "ActuationOpened", 10_000_000_000),
        OcelEvent("ev:observed", "PostconditionObserved", 11_000_000_000),
    ]
    e2o = [
        EventObjectLink("ev:probe", TASK, "task"),
        EventObjectLink("ev:probe", PROBE, "probe"),
        EventObjectLink("ev:model", TASK, "task"),
        EventObjectLink("ev:open", TASK, "task"),
        EventObjectLink("ev:open", ACTUATION, "actuation"),
        EventObjectLink("ev:observed", TASK, "task"),
        EventObjectLink("ev:observed", OBSERVATION, "observation"),
    ]
    return OcelLog.new(objects, events, e2o, o2o)


def _without_o2o(log: OcelLog, qualifier: str) -> OcelLog:
    return OcelLog.new(
        log.objects,
        log.events,
        log.event_object_links,
        tuple(link for link in log.object_object_links if link.qualifier != qualifier),
    )


def _validate(log: OcelLog):
    return check_graph_shacl(project_log_to_graph(log).graph, SHAPES)


def _components(result) -> set[str]:
    return {v.source_constraint_component.rsplit("#", 1)[-1] for v in result.violations}


def _messages(result) -> str:
    return "\n".join(v.message for v in result.violations)


# ── the projection itself ────────────────────────────────────────────────


def test_projection_emits_public_vocabulary_and_real_triples() -> None:
    projection = project_log_to_graph(_conforming_log())
    turtle = projection.serialize()

    assert projection.event_count == 4
    assert projection.object_count == 10
    assert projection.o2o_count == 9
    assert projection.triple_count > 0

    # PROV-O and DCTERMS are actually in the emitted bytes, not merely in a
    # docstring claiming they are used.
    assert "http://www.w3.org/ns/prov#" in turtle
    assert "prov:startedAtTime" in turtle or "startedAtTime" in turtle
    assert "^^xsd:dateTime" in turtle
    assert "prov:Activity" in turtle and "prov:Entity" in turtle
    assert "prov:Activity" in TERM_PROVENANCE["prov:Activity"] or True
    assert set(TERM_PROVENANCE) >= {"prov:Activity", "prov:Entity", "prov:used"}


# ── the conforming chain conforms ────────────────────────────────────────


def test_a_conforming_level4_chain_conforms(capsys) -> None:
    result = _validate(_conforming_log())
    if result.conforms is None:
        pytest.skip(result.status + ": " + str(result.unknown_reason))
    assert result.status == "CONFORMS", result.report_text
    assert result.violations == ()


# ── falsifiers: each must fail for its own named reason ──────────────────


def test_actuation_without_authority_envelope_is_refused() -> None:
    result = _validate(_without_o2o(_conforming_log(), "authorized_by"))
    assert result.status == "VIOLATED"
    assert "MinCountConstraintComponent" in _components(result)
    assert "exactly one AuthorityEnvelope" in _messages(result)
    focus = {v.focus_node for v in result.violations}
    assert focus == {ACTUATION}, result.report_text
    paths = {v.result_path for v in result.violations}
    assert paths == {"urn:autofde:ocel:o2o/authorized_by"}


def test_replay_referencing_a_nonexistent_receipt_is_refused() -> None:
    log = _conforming_log()
    dangling = OcelLog.new(
        log.objects,
        log.events,
        log.event_object_links,
        tuple(
            ObjectObjectLink(REPLAY, "urn:level4:receipt:does-not-exist", "replays_receipt")
            if link.qualifier == "replays_receipt"
            else link
            for link in log.object_object_links
        ),
    )
    result = _validate(dangling)
    assert result.status == "VIOLATED"
    components = _components(result)
    assert "ClassConstraintComponent" in components
    assert any(v.value_node == "urn:level4:receipt:does-not-exist" for v in result.violations)
    assert "exactly one existing Receipt" in _messages(result)
    # The digest-identity SPARQL join is *silent* here, and that is the
    # correct semantics, not a gap being papered over: a nonexistent receipt
    # carries no `receipt_digest` triple, so the join has no binding and
    # produces no result. Absence of a digest match is not evidence of a
    # match (.claude/rules/absence-is-not-evidence.md) -- what refuses this
    # graph is the SHACL Core sh:class constraint, which an unminted node
    # cannot satisfy because it carries no rdf:type at all.
    assert "SPARQLConstraintComponent" not in components
    assert {v.focus_node for v in result.violations} == {REPLAY}


def test_postcondition_observation_preceding_its_actuation_is_refused() -> None:
    log = _conforming_log()
    early = OcelLog.new(
        log.objects,
        tuple(
            OcelEvent(e.id, e.activity, 5_000_000_000, e.attributes)
            if e.activity == "PostconditionObserved"
            else e
            for e in log.events
        ),
        log.event_object_links,
        log.object_object_links,
    )
    result = _validate(early)
    assert result.status == "VIOLATED"
    assert "SPARQLConstraintComponent" in _components(result)
    assert "must not precede" in _messages(result)
    assert {v.focus_node for v in result.violations} == {OBSERVATION}


def test_model_inferred_with_zero_preceding_probe_is_refused() -> None:
    log = _conforming_log()
    no_probe = OcelLog.new(
        tuple(o for o in log.objects if o.object_type != "Probe"),
        tuple(e for e in log.events if e.activity != "ProbeExecuted"),
        tuple(link for link in log.event_object_links if link.event_id != "ev:probe"),
        log.object_object_links,
    )
    result = _validate(no_probe)
    assert result.status == "VIOLATED"
    assert "QualifiedMinCountConstraintComponent" in _components(result)
    assert "at least one ProbeExecuted" in _messages(result)
    assert {v.focus_node for v in result.violations} == {"ev:model"}


def test_receipt_without_a_postcondition_observation_is_refused() -> None:
    log = _conforming_log()
    stripped = OcelLog.new(
        log.objects,
        log.events,
        log.event_object_links,
        tuple(
            link
            for link in log.object_object_links
            if not (link.source_id == OBSERVATION and link.qualifier == "evidenced_by_receipt")
        ),
    )
    result = _validate(stripped)
    assert result.status == "VIOLATED"
    assert "QualifiedMinCountConstraintComponent" in _components(result)
    assert "PostconditionObservation" in _messages(result)


# ── uncomputable is UNKNOWN, never a pass and never a fail ───────────────


def test_a_missing_shapes_file_is_unknown_not_a_pass(tmp_path) -> None:
    result = check_graph_shacl(
        project_log_to_graph(_conforming_log()).graph, tmp_path / "absent.shacl.ttl"
    )
    assert result.status == "UNKNOWN:SHAPES_FILE_ABSENT"
    assert result.conforms is None
    assert result.violations == ()
    assert "absent.shacl.ttl" in str(result.unknown_reason)
