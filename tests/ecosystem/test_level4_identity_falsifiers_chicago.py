# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Object-*identity* falsifiers for the Level 4 causal chain.

``test_level4_shacl_conformance_chicago.py`` establishes that a chain with a
*missing edge* is refused. This file raises the bar one level, to the standard
``.claude/rules/no-dual-bookkeeping.md`` actually demands: **identity, not
adjacency** -- "a correct activity order with broken object identity is
non-conformant". Every fixture here has a *sequence-correct* event log; the
only defect is which object an edge points at.

Every collaborator is real: real :class:`OcelLog` values, the real
``rdflib`` projection in ``autofde_lab.ocel.rdf_projection``, the real
committed shapes file read off disk, the real ``pyshacl`` engine. No mock,
stub, ``patch`` or ``monkeypatch``, and no assertion on "was something
called" -- every assertion is on the final state of the real validation
report.

Refusal must happen at GRAPH admission
--------------------------------------
No test in this file consults a Python boolean to decide whether a fixture is
bad. The decision is always ``check_graph_shacl(...).status``, and the named
shape / constraint component is asserted, not merely the count.

Honest coverage, not a green wall
---------------------------------
Seven of the twelve falsifiers (A, C, E, F, I, J, L) are refused by a committed
shape today. Five (B, D, G, H, K) are **NOT** -- there is no shape that could
refuse them, and each such test asserts the *real* current outcome
(``CONFORMS``) with a named account of the missing shape, rather than a
weakened assertion dressed up as coverage. Per
``.claude/rules/absence-is-not-evidence.md``, a graph that conforms only
because nothing checks it is ``UNKNOWN``, and the tests below say so in their
names (``..._is_NOT_refused_today``). Asserting the gap is what keeps the gap
from being silently closed by wishful thinking, and what will fail loudly the
day a shape is added.
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
from autofde_lab.ocel.rdf_projection import project_log_to_graph

SHAPES = pathlib.Path(__file__).parents[2] / "ontology" / "level4-chain.shacl.ttl"

DIGEST = "220f81bf978fe490"

TASK = "urn:level4:task:t1"
ENV = "urn:level4:environment:e1"
ENV2 = "urn:level4:environment:e2"
CAP = "urn:level4:capability:c1"
PROBE = "urn:level4:probe:p1"
CANDIDATE = "urn:level4:plancandidate:pc1"
COMMITMENT = "urn:level4:commitment:" + DIGEST
COMMITMENT2 = "urn:level4:commitment:deadbeefdeadbeef"
ENVELOPE = "urn:level4:authority:a1"
ACTUATION = "urn:level4:actuation:r1"
ACTUATION2 = "urn:level4:actuation:r2"
ACTUATION0 = "urn:level4:actuation:r0"
OBSERVATION = "urn:level4:postcondition:v1"
OBSERVATION0 = "urn:level4:postcondition:v0"
RECEIPT = "urn:level4:receipt:r1"
RECEIPT_PARENT = "urn:level4:receipt:r0"
REPLAY = "urn:level4:replay:" + DIGEST


def _s(value: str) -> OcelAttributeValue:
    return OcelAttributeValue.string(value)


# ── the sequence-correct baseline every falsifier perturbs ───────────────


def _objects() -> list[OcelObject]:
    return [
        OcelObject(TASK, "Task"),
        OcelObject(ENV, "Environment"),
        OcelObject(CAP, "Capability"),
        OcelObject(PROBE, "Probe"),
        OcelObject(CANDIDATE, "PlanCandidate", (OcelAttribute("plan_digest", _s(DIGEST)),)),
        OcelObject(
            COMMITMENT, "POWLCommitment", (OcelAttribute("plan_digest", _s(DIGEST)),)
        ),
        OcelObject(ENVELOPE, "AuthorityEnvelope"),
        OcelObject(ACTUATION, "Actuation"),
        OcelObject(OBSERVATION, "PostconditionObservation"),
        # The parent receipt is fully formed. It has to be: `Level4ReceiptShape`
        # requires *every* Receipt to be evidenced by both an Actuation and a
        # PostconditionObservation, so a bare causal ancestor cannot sit in the
        # same graph. See `test_L2_...` below, which pins that consequence.
        OcelObject(ACTUATION0, "Actuation"),
        OcelObject(OBSERVATION0, "PostconditionObservation"),
        OcelObject(
            RECEIPT_PARENT, "Receipt", (OcelAttribute("receipt_digest", _s("0000parent0000")),)
        ),
        OcelObject(RECEIPT, "Receipt", (OcelAttribute("receipt_digest", _s(DIGEST)),)),
        OcelObject(REPLAY, "Replay", (OcelAttribute("head_digest", _s(DIGEST)),)),
    ]


def _o2o() -> list[ObjectObjectLink]:
    return [
        ObjectObjectLink(CANDIDATE, TASK, "candidate_for_task"),
        ObjectObjectLink(COMMITMENT, CANDIDATE, "commits_candidate"),
        ObjectObjectLink(ACTUATION, COMMITMENT, "actuates_commitment"),
        ObjectObjectLink(ACTUATION, ENVELOPE, "authorized_by"),
        ObjectObjectLink(ACTUATION, ENV, "acts_on_environment"),
        ObjectObjectLink(ACTUATION, CAP, "exercises_capability"),
        ObjectObjectLink(ACTUATION, RECEIPT, "evidenced_by_receipt"),
        ObjectObjectLink(OBSERVATION, RECEIPT, "evidenced_by_receipt"),
        ObjectObjectLink(OBSERVATION, ACTUATION, "observes_actuation"),
        ObjectObjectLink(OBSERVATION, ENV, "observes_subject"),
        ObjectObjectLink(RECEIPT, RECEIPT_PARENT, "caused_by"),
        ObjectObjectLink(REPLAY, RECEIPT, "replays_receipt"),
        # parent leg
        ObjectObjectLink(ACTUATION0, COMMITMENT, "actuates_commitment"),
        ObjectObjectLink(ACTUATION0, ENVELOPE, "authorized_by"),
        ObjectObjectLink(ACTUATION0, ENV, "acts_on_environment"),
        ObjectObjectLink(ACTUATION0, CAP, "exercises_capability"),
        ObjectObjectLink(ACTUATION0, RECEIPT_PARENT, "evidenced_by_receipt"),
        ObjectObjectLink(OBSERVATION0, RECEIPT_PARENT, "evidenced_by_receipt"),
        ObjectObjectLink(OBSERVATION0, ACTUATION0, "observes_actuation"),
        ObjectObjectLink(OBSERVATION0, ENV, "observes_subject"),
    ]


def _events() -> list[OcelEvent]:
    """Strictly ordered: probe < model < actuation < observation."""
    return [
        OcelEvent("ev:probe", "ProbeExecuted", 1_000_000_000),
        OcelEvent("ev:model", "ModelInferred", 2_000_000_000),
        OcelEvent("ev:open0", "ActuationOpened", 5_000_000_000),
        OcelEvent("ev:observed0", "PostconditionObserved", 6_000_000_000),
        OcelEvent("ev:open", "ActuationOpened", 10_000_000_000),
        OcelEvent("ev:observed", "PostconditionObserved", 11_000_000_000),
    ]


def _e2o() -> list[EventObjectLink]:
    return [
        EventObjectLink("ev:probe", TASK, "task"),
        EventObjectLink("ev:probe", PROBE, "probe"),
        EventObjectLink("ev:model", TASK, "task"),
        EventObjectLink("ev:open0", TASK, "task"),
        EventObjectLink("ev:open0", ACTUATION0, "actuation"),
        EventObjectLink("ev:observed0", TASK, "task"),
        EventObjectLink("ev:observed0", OBSERVATION0, "observation"),
        EventObjectLink("ev:open", TASK, "task"),
        EventObjectLink("ev:open", ACTUATION, "actuation"),
        EventObjectLink("ev:observed", TASK, "task"),
        EventObjectLink("ev:observed", OBSERVATION, "observation"),
    ]


def _log(
    *,
    objects: list[OcelObject] | None = None,
    o2o: list[ObjectObjectLink] | None = None,
    events: list[OcelEvent] | None = None,
    e2o: list[EventObjectLink] | None = None,
) -> OcelLog:
    return OcelLog.new(
        objects if objects is not None else _objects(),
        events if events is not None else _events(),
        e2o if e2o is not None else _e2o(),
        o2o if o2o is not None else _o2o(),
    )


def _drop_object(objects: list[OcelObject], object_id: str) -> list[OcelObject]:
    return [o for o in objects if o.id != object_id]


def _repoint(
    o2o: list[ObjectObjectLink], qualifier: str, *, source: str | None = None, target: str
) -> list[ObjectObjectLink]:
    """Redirect an existing edge at a different object -- identity broken,
    adjacency (the edge, its qualifier, its cardinality) untouched."""
    out = []
    for link in o2o:
        if link.qualifier == qualifier and (source is None or link.source_id == source):
            out.append(ObjectObjectLink(link.source_id, target, qualifier))
        else:
            out.append(link)
    return out


def _drop_edge(
    o2o: list[ObjectObjectLink], qualifier: str, *, source: str | None = None
) -> list[ObjectObjectLink]:
    return [
        link
        for link in o2o
        if not (link.qualifier == qualifier and (source is None or link.source_id == source))
    ]


def _validate(log: OcelLog):
    result = check_graph_shacl(project_log_to_graph(log).graph, SHAPES)
    if result.conforms is None:  # pragma: no cover - only without the extra
        pytest.skip(f"{result.status}: {result.unknown_reason}")
    return result


def _components(result) -> set[str]:
    return {v.source_constraint_component.rsplit("#", 1)[-1] for v in result.violations}


def _shapes(result) -> set[str]:
    return {
        (v.source_shape or "").rsplit("/", 1)[-1]
        for v in result.violations
        if v.source_shape and not v.source_shape.startswith("N")
    }


def _messages(result) -> str:
    return "\n".join(v.message for v in result.violations)


# ── the baseline is genuinely sequence- AND identity-correct ─────────────


def test_baseline_chain_conforms() -> None:
    result = _validate(_log())
    assert result.status == "CONFORMS", result.report_text
    assert result.violations == ()


# ═════════════════════════════════════════════════════════════════════════
# ENFORCED BY A COMMITTED SHAPE TODAY
# ═════════════════════════════════════════════════════════════════════════


def test_A_commitment_object_absent_is_refused() -> None:
    """A: the Actuation's `actuates_commitment` edge survives, its target does
    not. An unminted node carries no `rdf:type`, so `sh:class` refuses it."""
    result = _validate(_log(objects=_drop_object(_objects(), COMMITMENT)))
    assert result.status == "VIOLATED", result.report_text
    assert "ClassConstraintComponent" in _components(result)
    assert "exactly one POWLCommitment" in _messages(result)
    # Both actuations cite the vanished commitment, so both refuse.
    assert {v.focus_node for v in result.violations} == {ACTUATION, ACTUATION0}
    assert any(v.value_node == COMMITMENT for v in result.violations)
    assert any(
        v.result_path == "urn:autofde:ocel:o2o/actuates_commitment" for v in result.violations
    )


def test_C_authority_object_absent_is_refused() -> None:
    """C: same mechanism on the authority leg -- the envelope object is gone
    while the `authorized_by` edge still points at its id."""
    result = _validate(_log(objects=_drop_object(_objects(), ENVELOPE)))
    assert result.status == "VIOLATED", result.report_text
    assert "ClassConstraintComponent" in _components(result)
    assert "exactly one AuthorityEnvelope" in _messages(result)
    assert {v.focus_node for v in result.violations} == {ACTUATION, ACTUATION0}
    assert any(v.value_node == ENVELOPE for v in result.violations)


def test_E_authority_ref_null_on_an_act_receipt_is_refused() -> None:
    """E: `authority_ref` NULL on an act receipt.

    `level4_ocel.py` emits the `authorized_by` O2O edge only when
    `authority_of_receipt` resolves, so a NULL `authority_ref` reaches the
    graph as an *absent edge*, never as a null literal -- exactly what
    `.claude/rules/absence-is-not-evidence.md` requires of the projection.
    The refusal is therefore `sh:minCount`, and this test pins that mapping so
    a future projection that starts emitting a null literal (which would
    satisfy `minCount` and silently pass) fails here.
    """
    result = _validate(_log(o2o=_drop_edge(_o2o(), "authorized_by", source=ACTUATION)))
    assert result.status == "VIOLATED", result.report_text
    assert "MinCountConstraintComponent" in _components(result)
    assert "exactly one AuthorityEnvelope" in _messages(result)
    assert {v.focus_node for v in result.violations} == {ACTUATION}
    assert {v.result_path for v in result.violations} == {
        "urn:autofde:ocel:o2o/authorized_by"
    }


def test_F_postcondition_observation_absent_is_refused() -> None:
    """F: the Receipt keeps its Actuation but loses its independent
    observation. `Level4ReceiptShape`'s qualified inverse path refuses it."""
    objects = _drop_object(_objects(), OBSERVATION)
    o2o = [link for link in _o2o() if link.source_id != OBSERVATION]
    e2o = [link for link in _e2o() if link.object_id != OBSERVATION]
    result = _validate(_log(objects=objects, o2o=o2o, e2o=e2o))
    assert result.status == "VIOLATED", result.report_text
    assert "QualifiedMinCountConstraintComponent" in _components(result)
    assert "at least one PostconditionObservation" in _messages(result)
    assert RECEIPT in {v.focus_node for v in result.violations}


def test_I_replay_of_a_nonexistent_source_receipt_is_refused() -> None:
    """I: the replay's edge and its `head_digest` are both present and
    well-formed; only the *identity* of the receipt it names is wrong."""
    ghost = "urn:level4:receipt:never-minted"
    result = _validate(_log(o2o=_repoint(_o2o(), "replays_receipt", target=ghost)))
    assert result.status == "VIOLATED", result.report_text
    assert "ClassConstraintComponent" in _components(result)
    assert "exactly one existing Receipt" in _messages(result)
    assert {v.focus_node for v in result.violations} == {REPLAY}
    assert any(v.value_node == ghost for v in result.violations)
    # The digest-equality SPARQL join is silent, correctly: a node that was
    # never minted carries no `receipt_digest`, so the join binds nothing.
    # Absence of a mismatch is not evidence of a match.
    assert "SPARQLConstraintComponent" not in _components(result)


def test_J_correct_activity_order_with_wrong_object_identity_is_refused() -> None:
    """J -- the load-bearing one.

    The event log is *byte-identical in ordering* to the conforming baseline:
    ProbeExecuted < ModelInferred < ActuationOpened < PostconditionObserved,
    same activities, same timestamps, same E2O qualifiers. A conformance
    checker that scores activity sequences would call this a perfect trace.

    The only defect is object identity: the observation observes an Actuation
    that acted on `ENV`, but names `ENV2` as the subject it observed. That is
    `no-dual-bookkeeping.md`'s "correct activity order with broken object
    identity is non-conformant", and the same-subject `sh:sparql` join refuses
    it -- with no Python boolean anywhere in the decision.
    """
    objects = _objects() + [OcelObject(ENV2, "Environment")]
    o2o = _repoint(_o2o(), "observes_subject", source=OBSERVATION, target=ENV2)
    log = _log(objects=objects, o2o=o2o)

    # Sequence really is unperturbed.
    assert [e.activity for e in log.events] == [
        "ProbeExecuted",
        "ModelInferred",
        "ActuationOpened",
        "PostconditionObserved",
        "ActuationOpened",
        "PostconditionObserved",
    ]
    assert [e.timestamp_ns for e in log.events] == sorted(e.timestamp_ns for e in log.events)

    result = _validate(log)
    assert result.status == "VIOLATED", result.report_text
    assert "SPARQLConstraintComponent" in _components(result)
    assert "same subject (Environment)" in _messages(result)
    assert {v.focus_node for v in result.violations} == {OBSERVATION}
    assert any(v.value_node == ENV2 for v in result.violations)
    # And it is *only* the identity join that fires -- nothing structural,
    # nothing temporal. The refusal is attributable to identity alone.
    assert _components(result) == {"SPARQLConstraintComponent"}


def test_L_missing_ocel_object_refuses_regardless_of_any_python_summary() -> None:
    """L: an OCEL object is absent while a Python summary claims success.

    The summary is constructed here as a real dict that says the trial
    succeeded -- and it is never consulted by the admission decision. The
    graph refuses on its own, which is the whole point: standing is a query
    over the evidence graph, never a field somebody set
    (`.claude/rules/no-dual-bookkeeping.md`).
    """
    python_summary = {"status": "SUCCESS", "receipts_written": 2, "replay_verified": True}

    objects = _drop_object(_objects(), RECEIPT)
    result = _validate(_log(objects=objects))

    assert python_summary["status"] == "SUCCESS"  # the claim really is present
    assert result.status == "VIOLATED", result.report_text
    # Both dependents of the vanished Receipt refuse independently.
    assert {v.focus_node for v in result.violations} == {REPLAY}
    assert "ClassConstraintComponent" in _components(result)
    assert "exactly one existing Receipt" in _messages(result)


def test_L2_a_non_actuating_receipt_is_refused_by_the_committed_shape() -> None:
    """L (second half) -- a product finding surfaced while building the
    baseline, reported rather than designed around.

    `Level4ReceiptShape` requires **every** `otype:Receipt` in the graph to be
    evidenced by an Actuation *and* a PostconditionObservation. But
    `level4_ocel.py` mints a `Receipt` object for every ledger record
    regardless of `operation`, and only records whose operation is in
    `{act, materialize}` get an Actuation, only records carrying a
    `verification_id` get an observation. A real trial containing a `plan`
    or `discover` receipt therefore produces a graph that this shape refuses,
    for a reason that is not a defect in the trial.

    This test pins the current behaviour so the discrepancy cannot be closed
    silently in either direction. It is a *shape-vs-projection* mismatch, not
    an identity falsifier, and it is scoped to whoever owns
    `ontology/level4-chain.shacl.ttl` -- the fix is a narrower target
    (e.g. `sh:targetClass` on an `ActuatingReceipt` subtype, or an
    `sh:targetSubjectsOf o2o:replays_receipt`), not a weakened constraint.
    """
    bare = "urn:level4:receipt:plan-only"
    objects = _objects() + [
        OcelObject(bare, "Receipt", (OcelAttribute("receipt_digest", _s("aaaaaaaaaaaaaaaa")),))
    ]
    result = _validate(_log(objects=objects))
    assert result.status == "VIOLATED", result.report_text
    assert {v.focus_node for v in result.violations} == {bare}
    assert _components(result) == {"QualifiedMinCountConstraintComponent"}
    assert "at least one Actuation" in _messages(result)
    assert "at least one PostconditionObservation" in _messages(result)


# ═════════════════════════════════════════════════════════════════════════
# NOT ENFORCED BY ANY COMMITTED SHAPE TODAY
#
# Each test asserts the real, current outcome and names the missing shape.
# None of these is a passing falsifier; they are recorded negatives.
# ═════════════════════════════════════════════════════════════════════════


def test_B_actuation_referencing_a_different_commitment_is_NOT_refused_today() -> None:
    """B: RECORDED NEGATIVE.

    The Actuation is repointed at `COMMITMENT2` -- a legitimately minted
    `POWLCommitment` that commits nothing, is linked to no `PlanCandidate`,
    and whose `plan_digest` differs from the receipt digest the chain is
    built on. Cardinality (1..1) and `sh:class` are both satisfied, so
    `Level4ActuationShape` passes.

    Missing shape: nothing joins `Actuation -> actuates_commitment ->
    POWLCommitment.plan_digest` to the digest the rest of the chain carries.
    An `sh:sparql` constraint of the same form as the Replay head_digest join
    would refuse it; it has not been written.
    """
    objects = _objects() + [
        OcelObject(
            COMMITMENT2,
            "POWLCommitment",
            (OcelAttribute("plan_digest", _s("deadbeefdeadbeef")),),
        )
    ]
    o2o = _repoint(_o2o(), "actuates_commitment", source=ACTUATION, target=COMMITMENT2)
    result = _validate(_log(objects=objects, o2o=o2o))
    assert result.status == "CONFORMS", (
        "a shape now refuses B -- delete this recorded negative and write the "
        "positive falsifier:\n" + result.report_text
    )


def test_B_two_commitments_on_one_actuation_IS_refused() -> None:
    """B (the adjacency half, which *is* covered): if the wrong commitment is
    *added* rather than substituted, `sh:maxCount 1` refuses it. Only
    substitution -- pure identity error -- escapes."""
    objects = _objects() + [OcelObject(COMMITMENT2, "POWLCommitment")]
    o2o = _o2o() + [ObjectObjectLink(ACTUATION, COMMITMENT2, "actuates_commitment")]
    result = _validate(_log(objects=objects, o2o=o2o))
    assert result.status == "VIOLATED", result.report_text
    assert "MaxCountConstraintComponent" in _components(result)
    assert {v.focus_node for v in result.violations} == {ACTUATION}


def test_D_authority_bound_to_the_wrong_actuation_is_NOT_refused_today() -> None:
    """D: RECORDED NEGATIVE.

    A second Actuation (`ACTUATION2`) claims the *same* `AuthorityEnvelope`
    that was issued for the first, over a different Environment and a
    different commitment. Every `Level4ActuationShape` property is satisfied
    for both actuations.

    Missing shape: the `AuthorityEnvelope` carries no scope -- no
    `authorizes_capability`, no `authorizes_subject`, no inverse-cardinality
    constraint bounding how many Actuations may cite one envelope. Without a
    scope on the envelope there is nothing for a shape to compare against, so
    this is a *vocabulary* gap before it is a shape gap: `level4_ocel.py`
    would have to project the envelope's scope first.
    """
    objects = _objects() + [
        OcelObject(ACTUATION2, "Actuation"),
        OcelObject(ENV2, "Environment"),
        OcelObject(COMMITMENT2, "POWLCommitment"),
    ]
    o2o = _o2o() + [
        ObjectObjectLink(ACTUATION2, COMMITMENT2, "actuates_commitment"),
        ObjectObjectLink(ACTUATION2, ENVELOPE, "authorized_by"),
        ObjectObjectLink(ACTUATION2, ENV2, "acts_on_environment"),
        ObjectObjectLink(ACTUATION2, CAP, "exercises_capability"),
        ObjectObjectLink(ACTUATION2, RECEIPT, "evidenced_by_receipt"),
    ]
    result = _validate(_log(objects=objects, o2o=o2o))
    assert result.status == "CONFORMS", (
        "a shape now refuses D -- delete this recorded negative:\n" + result.report_text
    )


def test_G_observer_identity_equal_to_actuator_identity_is_NOT_refused_today() -> None:
    """G: RECORDED NEGATIVE, and the gap is at the vocabulary level.

    Independence of the verifier from the actuator is the property this
    falsifier targets. It cannot be expressed at all: there is no agent object
    type in `LEVEL4_OBJECT_TYPES` and no `performed_by` / `observed_by`
    qualifier anywhere in `level4_ocel.py` (`grep -n
    "observer\\|actor\\|performed_by\\|observed_by" ...` returns nothing).

    The fixture below therefore states the *intended* edges using terms that
    do not exist in the projection's vocabulary, with the same agent on both
    ends. Nothing refuses it, because nothing looks at it -- a factor that
    cannot fail is a factor that is not being checked
    (`.claude/rules/absence-is-not-evidence.md`). Writing a shape over these
    invented terms would be faking coverage: the real trial never emits them.
    """
    agent = "urn:level4:agent:same-process"
    objects = _objects() + [OcelObject(agent, "Agent")]
    o2o = _o2o() + [
        ObjectObjectLink(ACTUATION, agent, "performed_by"),
        ObjectObjectLink(OBSERVATION, agent, "observed_by"),
    ]
    result = _validate(_log(objects=objects, o2o=o2o))
    assert result.status == "CONFORMS", (
        "a shape now refuses G -- delete this recorded negative:\n" + result.report_text
    )


def test_H_receipt_missing_parent_receipt_ids_is_NOT_refused_today() -> None:
    """H: RECORDED NEGATIVE.

    `level4_ocel.py` projects `parent_receipt_ids` as `caused_by` O2O edges --
    "the causal DAG gymact's exporter drops at the OCEL boundary". The
    baseline carries one. Dropping it leaves a Receipt with no causal parent
    and no violation.

    Missing shape: `Level4ReceiptShape` constrains only the inverse
    `evidenced_by_receipt` path. There is no `caused_by` constraint, and a
    naive `sh:minCount 1` would be wrong anyway -- the *first* receipt in a
    ledger legitimately has no parent, so the shape needs a genuine chain-head
    predicate (e.g. "a Receipt has a `caused_by` parent unless its
    `previous_digest` is absent"), which is a real design decision, not an
    oversight to be papered over with a one-line minCount.
    """
    result = _validate(_log(o2o=_drop_edge(_o2o(), "caused_by")))
    assert result.status == "CONFORMS", (
        "a shape now refuses H -- delete this recorded negative:\n" + result.report_text
    )


def test_K_wrong_plancandidate_to_commitment_relation_is_NOT_refused_today() -> None:
    """K: RECORDED NEGATIVE.

    The sequence is correct and the commitment is the right one; only the
    `commits_candidate` edge is repointed at a second `PlanCandidate` that was
    never the one planned for this Task.

    Missing shape: there is no `sh:targetClass otype:PlanCandidate` and no
    `sh:targetClass otype:POWLCommitment` shape in
    `ontology/level4-chain.shacl.ttl` at all -- the shapes file starts at the
    Actuation. The whole plan-side half of the chain
    (PlannerAttempt -> PlanCandidate -> POWLCommitment) is unconstrained.
    """
    other = "urn:level4:plancandidate:pc2"
    objects = _objects() + [
        OcelObject(other, "PlanCandidate", (OcelAttribute("plan_digest", _s("ffffffffffffffff")),))
    ]
    o2o = _repoint(_o2o(), "commits_candidate", target=other)
    result = _validate(_log(objects=objects, o2o=o2o))
    assert result.status == "CONFORMS", (
        "a shape now refuses K -- delete this recorded negative:\n" + result.report_text
    )


# ── verbatim report evidence, printed for the record ─────────────────────


@pytest.mark.parametrize(
    "name,builder",
    [
        (
            "J: order correct, subject identity wrong",
            lambda: _log(
                objects=_objects() + [OcelObject(ENV2, "Environment")],
                o2o=_repoint(_o2o(), "observes_subject", source=OBSERVATION, target=ENV2),
            ),
        ),
        (
            "A: commitment object absent",
            lambda: _log(objects=_drop_object(_objects(), COMMITMENT)),
        ),
    ],
)
def test_real_pyshacl_report_text_is_emitted(name, builder, capsys) -> None:
    """The report text is pyshacl's own, unparaphrased. Run with `-s` to read
    it; the assertions below pin the parts a status claim may quote."""
    result = _validate(builder())
    with capsys.disabled():
        print(f"\n=== {name} ===\n{result.report_text}")
    assert "Validation Report" in result.report_text
    assert "Conforms: False" in result.report_text
    assert "Constraint Violation" in result.report_text
