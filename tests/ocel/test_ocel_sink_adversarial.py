# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Adversarial checkpoint for the ledger -> OCEL projection.

Every case here is *constructed* and then shown to be *rejected*. A test that
merely observes a malformed log is absent proves nothing: the log is absent in
the passing case too. So each test builds the defect explicitly and asserts the
named refusal.

Nothing here actuates, admits, brokers, or issues receipts. An OCEL log is a
document about a traversal, not evidence that one happened.
"""

import pytest

from autofde_lab.agent.ledger import LedgerPhase, OccurrenceLedger
from autofde_lab.agent.ocel_sink import (
    LifecyclePhase,
    OcelSink,
    OcelSinkError,
    SinkRefusal,
)
from autofde_lab.ocel.log import OcelLog
from autofde_lab.ocel.model import (
    EventObjectLink,
    ObjectChange,
    ObjectObjectLink,
    OcelAttributeValue,
    OcelEvent,
    OcelObject,
)
from autofde_lab.ocel.refusals import OcelError, OcelRefusal

TYPES = {"case-1": "WorkflowCase", "res-1": "Resource"}


def _ledger_with(objects=(("case-1", "belongs_to"),), *, commit=True, activity="Draft"):
    ledger = OccurrenceLedger()
    token = ledger.intend(
        (0,),
        "ctx-a",
        activity_sha256="act-a",
        activity=activity,
        objects=objects,
    )
    if commit:
        ledger.commit(token, activity_sha256="act-a")
    return ledger


def _sink():
    return OcelSink(object_types=TYPES, decision_epoch=3, commitment_digest="dig-0")


# ── the happy path, so the refusals below are not vacuous ────────────────────


def test_a_committed_record_becomes_one_qualified_event():
    ledger = _ledger_with()
    (committed,) = ledger.committed()
    log = _sink().absorb(ledger).validated()
    assert [e.id for e in log.events]
    (event,) = log.events
    # the event id IS the token id -- the projection invents no identity
    assert event.id == committed.token_id
    assert event.activity == "Draft"
    links = [l for l in log.event_object_links if l.event_id == event.id]
    assert links == [EventObjectLink(event.id, "case-1", "belongs_to")]
    carried = {a.key: a.value.value for a in event.attributes}
    assert carried["decisionEpoch"] == 3
    assert carried["commitmentDigest"] == "dig-0"
    assert carried["contextDigest"] == "ctx-a"
    assert carried["occurrenceIndex"] == 0
    assert carried["phase"] == LifecyclePhase.COMMITTED.value


def test_every_lifecycle_phase_is_recordable():
    sink = _sink().absorb(_ledger_with())
    for index, phase in enumerate(LifecyclePhase):
        if phase is LifecyclePhase.COMMITTED:
            continue
        sink = sink.note(
            phase, f"ev-{index}", phase.value, [("case-1", "concerns")],
            timestamp_ns=1000 + index,
        )
    log = sink.validated()
    phases = {
        a.value.value
        for e in log.events
        for a in e.attributes
        if a.key == "phase"
    }
    assert phases == {p.value for p in LifecyclePhase}


# ── 1. an event with no object links ─────────────────────────────────────────


def test_committed_record_with_zero_objects_is_REFUSED_not_repaired():
    sink = _sink()
    with pytest.raises(OcelSinkError) as excinfo:
        sink.absorb(_ledger_with(objects=()))
    assert excinfo.value.refusal is SinkRefusal.COMMITTED_RECORD_HAS_NO_OBJECTS
    # and it did not invent a placeholder object to get past validate()
    assert sink.log.objects == ()
    assert sink.log.events == ()


def test_a_hand_built_objectless_event_is_refused_by_the_validator_too():
    """The law the sink is protecting actually exists and actually bites."""
    log = OcelLog.new(
        objects=(OcelObject("case-1", "WorkflowCase"),),
        events=(OcelEvent("e1", "Draft", 1),),
    )
    with pytest.raises(OcelError) as excinfo:
        log.validate()
    assert excinfo.value.refusal is OcelRefusal.EMPTY_EVENT_OBJECT_LINKS


def test_phase_event_with_no_objects_is_refused():
    with pytest.raises(OcelSinkError) as excinfo:
        _sink().note(LifecyclePhase.REFUSED, "ev-x", "refused", [])
    assert excinfo.value.refusal is SinkRefusal.PHASE_EVENT_HAS_NO_OBJECTS


# ── 2. dangling E2O link ─────────────────────────────────────────────────────


def test_dangling_event_to_object_link_is_refused():
    log = OcelLog.new(
        events=(OcelEvent("e1", "Draft", 1),),
        event_object_links=(EventObjectLink("e1", "ghost", "belongs_to"),),
    )
    with pytest.raises(OcelError) as excinfo:
        log.validate()
    assert excinfo.value.refusal is OcelRefusal.DANGLING_EVENT_OBJECT_LINK


def test_an_undeclared_object_type_is_refused_rather_than_guessed():
    """The sink's own way of never producing a dangling link."""
    with pytest.raises(OcelSinkError) as excinfo:
        _sink().absorb(_ledger_with(objects=(("unknown-9", "belongs_to"),)))
    assert excinfo.value.refusal is SinkRefusal.UNDECLARED_OBJECT_TYPE


# ── 3. dangling O2O link ─────────────────────────────────────────────────────


def test_dangling_object_to_object_link_is_refused():
    log = _sink().absorb(_ledger_with()).log
    torn = OcelLog.new(
        objects=log.objects,
        events=log.events,
        event_object_links=log.event_object_links,
        object_object_links=(ObjectObjectLink("case-1", "ghost", "parent"),),
    )
    with pytest.raises(OcelError) as excinfo:
        torn.validate()
    assert excinfo.value.refusal is OcelRefusal.DANGLING_EVENT_OBJECT_LINK


# ── 4. invalid change target ─────────────────────────────────────────────────


def test_object_change_naming_an_unknown_object_is_refused():
    log = _sink().absorb(_ledger_with()).log
    torn = OcelLog.new(
        objects=log.objects,
        events=log.events,
        event_object_links=log.event_object_links,
        object_changes=(
            ObjectChange("ghost", "status", OcelAttributeValue.string("x"), 5),
        ),
    )
    with pytest.raises(OcelError) as excinfo:
        torn.validate()
    assert excinfo.value.refusal is OcelRefusal.DANGLING_EVENT_OBJECT_LINK


def test_change_to_a_time_stable_attribute_is_refused():
    log = _sink().absorb(_ledger_with()).log
    torn = OcelLog.new(
        objects=log.objects,
        events=log.events,
        event_object_links=log.event_object_links,
        object_changes=(
            ObjectChange("case-1", "type", OcelAttributeValue.string("Other"), 5),
        ),
    )
    with pytest.raises(OcelError) as excinfo:
        torn.validate()
    assert excinfo.value.refusal is OcelRefusal.TIME_STABLE_ATTRIBUTE_CHANGED


# ── 5. executor history diverging from OCEL history ──────────────────────────


def test_ledger_history_and_ocel_history_agree_step_for_step():
    ledger = OccurrenceLedger()
    for index, (label, activity) in enumerate([("Draft", "a"), ("Review", "b")]):
        token = ledger.intend(
            (index,),
            "ctx-a",
            activity_sha256=activity,
            activity=label,
            objects=(("case-1", "belongs_to"),),
        )
        ledger.commit(token, activity_sha256=activity)
    sink = _sink().absorb(ledger)
    sink.validated()
    assert sink.activities() == tuple(r.activity for r in ledger.committed())
    assert [e.timestamp_ns for e in sink.log.events] == [
        r.timestamp_ns for r in ledger.committed()
    ]


def test_a_divergent_ocel_history_is_detectable_not_silent():
    """Guard against a vacuous pass: the agreement check must be able to fail."""
    ledger = _ledger_with()
    sink = _sink().absorb(ledger)
    forged = OcelLog.new(
        objects=sink.log.objects,
        events=(OcelEvent("e-forged", "NeverHappened", 1),),
        event_object_links=(EventObjectLink("e-forged", "case-1", "belongs_to"),),
    )
    forged.validate()  # structurally fine -- the defect is not structural
    assert tuple(e.activity for e in forged.events) != tuple(
        r.activity for r in ledger.committed()
    )


# ── 6. a superseded commitment emits a FRESH occurrence ──────────────────────


def test_a_redo_emits_a_fresh_occurrence_rather_than_overwriting():
    ledger = OccurrenceLedger()
    for _ in range(2):
        token = ledger.intend(
            (0,),
            "ctx-a",
            activity_sha256="act-a",
            activity="RevokeSessions",
            objects=(("case-1", "belongs_to"),),
        )
        ledger.commit(token, activity_sha256="act-a")

    sink = _sink().absorb(ledger)
    sink.validated()
    assert len(sink.log.events) == 2, "the second occurrence overwrote the first"
    indices = [
        a.value.value
        for e in sink.log.events
        for a in e.attributes
        if a.key == "occurrenceIndex"
    ]
    assert indices == [0, 1]
    assert len({e.id for e in sink.log.events}) == 2


def test_a_superseding_phase_event_does_not_erase_what_it_supersedes():
    ledger = _ledger_with()
    (committed,) = ledger.committed()
    sink = _sink().absorb(ledger).note(
        LifecyclePhase.SUPERSEDED,
        "ev-supersede",
        "supersede",
        [("case-1", "concerns")],
        timestamp_ns=10_000,
    )
    sink.validated()
    assert committed.token_id in {e.id for e in sink.log.events}
    assert len(sink.log.events) == 2


# ── 7. INTENDED resumed without COMMITTED ────────────────────────────────────


def test_an_outstanding_intent_produces_no_committed_event():
    ledger = _ledger_with(commit=False)
    sink = _sink().absorb(ledger)
    assert sink.log.events == (), "an intention was projected as a commitment"


def test_an_outstanding_intent_is_projected_only_under_a_distinct_id():
    ledger = _ledger_with(commit=False)
    sink = _sink().absorb(ledger, include_intended=True)
    sink.validated()
    (event,) = sink.log.events
    assert event.id.endswith("#INTENDED")
    phase = next(a.value.value for a in event.attributes if a.key == "phase")
    assert phase == LifecyclePhase.INTENDED.value
    assert not ledger.is_resumable()


def test_the_ledger_itself_refuses_to_resume_across_an_outstanding_intent():
    from autofde_lab.agent.refusals import AgentRefusal

    with pytest.raises(AgentRefusal):
        _ledger_with(commit=False).assert_resumable()


# ── 8. a duplicate occurrence hidden by content hash ─────────────────────────


def test_two_legal_redos_are_distinguishable_from_a_dedup_bug():
    """Content-identical by construction; distinguished only by index.

    Both occurrences carry the same activity hash and the same context hash.
    If ``OccurrenceKey`` were a bare content hash they would collide, and a
    dedup bug that dropped one would be indistinguishable from a correct log.
    """
    ledger = OccurrenceLedger()
    keys = []
    for _ in range(2):
        token = ledger.intend(
            (0,), "ctx-a", activity_sha256="act-a", activity="Same",
            objects=(("case-1", "belongs_to"),),
        )
        keys.append(ledger.commit(token, activity_sha256="act-a"))

    first, second = keys
    assert first.activity_sha256 == second.activity_sha256
    assert first.context_sha256 == second.context_sha256
    assert first.occurrence_index != second.occurrence_index
    assert first != second


def test_replaying_the_same_ledger_twice_is_refused_as_a_duplicate_id():
    """A dedup bug's mirror image: the same occurrence projected twice."""
    ledger = _ledger_with()
    sink = _sink().absorb(ledger)
    with pytest.raises(OcelSinkError) as excinfo:
        sink.absorb(ledger)
    assert excinfo.value.refusal is SinkRefusal.DUPLICATE_EVENT_ID


def test_duplicate_event_ids_are_refused_by_the_validator_independently():
    log = OcelLog.new(
        objects=(OcelObject("case-1", "WorkflowCase"),),
        events=(OcelEvent("e1", "Draft", 1), OcelEvent("e1", "Draft", 2)),
        event_object_links=(
            EventObjectLink("e1", "case-1", "belongs_to"),
        ),
    )
    with pytest.raises(OcelError) as excinfo:
        log.validate()
    assert excinfo.value.refusal is OcelRefusal.DUPLICATE_ENTITY_ID


def test_a_note_cannot_reuse_an_existing_event_id():
    ledger = _ledger_with()
    (committed,) = ledger.committed()
    sink = _sink().absorb(ledger)
    with pytest.raises(OcelSinkError) as excinfo:
        sink.note(
            LifecyclePhase.REPLANNED,
            committed.token_id,
            "replan",
            [("case-1", "concerns")],
        )
    assert excinfo.value.refusal is SinkRefusal.DUPLICATE_EVENT_ID


# ── the projection is not the record ─────────────────────────────────────────


def test_the_sink_is_immutable_so_a_refused_absorb_leaves_no_partial_log():
    ledger = OccurrenceLedger()
    good = ledger.intend(
        (0,), "ctx-a", activity_sha256="act-a", activity="Draft",
        objects=(("case-1", "belongs_to"),),
    )
    ledger.commit(good, activity_sha256="act-a")
    bad = ledger.intend((1,), "ctx-a", activity_sha256="act-b", activity="Bad")
    ledger.commit(bad, activity_sha256="act-b")

    sink = _sink()
    with pytest.raises(OcelSinkError) as excinfo:
        sink.absorb(ledger)
    assert excinfo.value.refusal is SinkRefusal.COMMITTED_RECORD_HAS_NO_OBJECTS
    assert sink.log.events == (), "a refused projection left a partial log behind"


def test_ledger_phases_are_exactly_two_and_lifecycle_phases_are_eight():
    assert {p.value for p in LedgerPhase} == {"INTENDED", "COMMITTED"}
    assert {p.value for p in LifecyclePhase} == {
        "intended",
        "committed",
        "refused",
        "superseded",
        "replanned",
        "authority-requested",
        "authority-granted",
        "authority-refused",
    }
