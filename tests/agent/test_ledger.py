# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for the two-phase occurrence ledger — **and its read view**.

Real objects throughout — no mocks, no patched internals.

``autofde_lab.agent.ledger.OccurrenceLedger`` is the write-ahead record;
``autofde_lab.agent.replan.Ledger`` is the read view a reuse claim is validated
against. They were reconciled into one read-view, and this file was merged from
``test_ledger.py`` + ``test_ledger_reconciliation.py`` to follow: the WAL and its
projection are one subject, and keeping them apart meant the central guarantee --
*an intention is not an observation* -- was asserted twice, once against a
hand-built view and once against the WAL, in two files that could drift.

Nothing here actuates, admits, brokers, or issues receipts.
"""

from __future__ import annotations

import pytest

from autofde_lab.agent.ledger import LedgerPhase, OccurrenceLedger
from autofde_lab.agent.refusals import AgentRefusal, AgentRefusalCode
from autofde_lab.agent.replan import (
    Ledger,
    OccurrenceStatus,
    PreserveMap,
    ReplanError,
    ReplanRefusal,
    activity_of,
    as_ledger,
    validate_preserve_map,
)
from autofde_lab.powl.algebra import Atom, PartialOrder


def _model():
    return PartialOrder((Atom("a"), Atom("b")), frozenset())


def _wal_with_one_committed():
    model = _model()
    wal = OccurrenceLedger()
    activity = activity_of(model.children[0])
    token = wal.intend((0,), "ctx", activity_sha256=activity, activity="a")
    key = wal.commit(token, activity_sha256=activity)
    return model, wal, key


def _wal_with_only_intended():
    model = _model()
    wal = OccurrenceLedger()
    activity = activity_of(model.children[0])
    wal.intend((0,), "ctx", activity_sha256=activity, activity="a")
    return model, wal, activity


# ── the write-ahead record ───────────────────────────────────────────────────


def test_intend_writes_before_commit_and_the_digest_moves_at_every_step():
    """Collapses three former items — write ordering, the per-activity occurrence
    index, and digest sensitivity are three facets of one append-only law, and
    the index/digest claims are only meaningful given the ordering claim."""
    ledger = OccurrenceLedger()
    empty = ledger.sha256()

    token = ledger.intend((0,), "ctx")
    intended = ledger.sha256()
    records = ledger.records()
    assert len(records) == 1
    assert records[0].phase is LedgerPhase.INTENDED
    assert ledger.occurrences() == (), "an intent was counted as an occurrence"

    key = ledger.commit(token, activity_sha256="a" * 64)
    committed = ledger.sha256()
    assert ledger.records()[1].phase is LedgerPhase.COMMITTED
    assert key.activity_sha256 == "a" * 64
    assert key.occurrence_index == 0
    assert ledger.occurrences() == (key,)

    assert len({empty, intended, committed}) == 3, "the digest did not move on append"

    # the occurrence index rises per activity across further round trips
    keys = [key]
    for step in (1, 2):
        keys.append(ledger.commit(ledger.intend((step,), "ctx"), activity_sha256="a" * 64))
    assert [k.occurrence_index for k in keys] == [0, 1, 2]


def test_an_outstanding_intent_makes_the_ledger_unresumable_everywhere():
    """The crash-consistency guarantee: after ``intend`` and before ``commit`` we
    cannot know whether the act happened, so resumption is refused.

    Collapses four former items — the predicate, the named refusal, the session
    that must honour it, and rehydration from records — because they are one
    guarantee observed at four call sites. Dropping any of them would let the
    guarantee hold in one place and silently not in another, so all four are
    still checked here.
    """
    from autofde_lab.hub.domain.maze import Maze

    from autofde_lab.agent.session import AgentSession

    ledger = OccurrenceLedger()
    ledger.intend((0,), "ctx")  # crash right here: acted? did not act? UNKNOWN

    assert ledger.is_resumable() is False
    with pytest.raises(AgentRefusal) as excinfo:
        ledger.assert_resumable()
    assert excinfo.value.code is AgentRefusalCode.LEDGER_UNRESUMABLE
    assert "SKD-AGENT-006" in str(excinfo.value)

    # a session may not open on top of it
    with pytest.raises(AgentRefusal) as excinfo:
        AgentSession(Maze(), ledger=ledger)
    assert excinfo.value.code is AgentRefusalCode.LEDGER_UNRESUMABLE

    # and the outstanding state survives rehydration from the records alone
    revived = OccurrenceLedger.from_records(ledger.records())
    assert [t.token_id for t in revived.outstanding()] == [
        t.token_id for t in ledger.outstanding()
    ]
    with pytest.raises(AgentRefusal):
        revived.assert_resumable()

    # control: resolving the intent lifts the refusal, so it is not unconditional
    resolved = OccurrenceLedger()
    resolved.commit(resolved.intend((0,), "ctx"), activity_sha256="b" * 64)
    resolved.assert_resumable()  # must not raise
    assert resolved.is_resumable() is True


def test_token_lifecycle_refusals_fire_by_name():
    """Collapses two former items — double-commit and second-outstanding-intent
    are the two ways to misuse a token, each still asserted by refusal code."""
    failures = []

    double = OccurrenceLedger()
    token = double.intend((0,), "ctx")
    double.commit(token, activity_sha256="c" * 64)
    try:
        double.commit(token, activity_sha256="c" * 64)
    except AgentRefusal as exc:
        if exc.code is not AgentRefusalCode.UNKNOWN_INTENT_TOKEN:
            failures.append(f"double-commit refused as {exc.code!r}")
    else:
        failures.append("double-commit was ACCEPTED")

    concurrent = OccurrenceLedger()
    concurrent.intend((0,), "ctx")
    try:
        concurrent.intend((1,), "ctx")
    except AgentRefusal as exc:
        if exc.code is not AgentRefusalCode.INTENT_ALREADY_OUTSTANDING:
            failures.append(f"second-intent refused as {exc.code!r}")
    else:
        failures.append("a second outstanding intent was ACCEPTED")

    assert not failures, f"token lifecycle refusals lost: {failures}"


# ── the projection onto the read view ────────────────────────────────────────


def test_the_wal_projects_onto_the_read_view_without_promoting_intent():
    """Collapses four former items covering one projection.

    The load-bearing asymmetry: a COMMITTED line becomes COMPLETED, an INTENDED
    line survives the projection *as INTENDED* (so a refusal can name it) but is
    not counted as prior completion, and the committed-only view drops it
    entirely. ``as_ledger`` accepting both types is what lets callers rely on
    exactly one of these views.
    """
    _model_, wal, key = _wal_with_one_committed()
    view = Ledger.from_occurrence_ledger(wal)
    assert [e.status for e in view.entries] == [OccurrenceStatus.COMPLETED]
    assert view.find(key, 0) is not None

    _m2, intended_wal, activity = _wal_with_only_intended()
    intended_view = Ledger.from_occurrence_ledger(intended_wal)
    assert [e.status for e in intended_view.entries] == [OccurrenceStatus.INTENDED]
    assert intended_view.entries[0].key.activity_sha256 == activity
    assert intended_view.completed_count(activity) == 0, "an intent was counted as completion"
    assert Ledger.from_occurrence_ledger(intended_wal, committed_only=True).entries == ()

    assert isinstance(as_ledger(wal), Ledger)
    already = Ledger(())
    assert as_ledger(already) is already
    with pytest.raises(TypeError):
        as_ledger(object())


# ── the guarantee that had no test: intent is never preservable ──────────────


def test_a_preserve_map_can_never_rest_on_an_INTENDED_occurrence():
    """Collapses two former items — the same rejection under both views.

    Against the committed-only view the occurrence is simply not there, so the
    reuse claim rests on nothing. Against the full view it *is* there and is
    rejected anyway, by name, with ``INTENDED`` in the detail. Both are kept
    because only the second proves the refusal is a decision about phase rather
    than an artifact of the occurrence being invisible.
    """
    model, wal, _activity = _wal_with_only_intended()
    view = Ledger.from_occurrence_ledger(wal)
    (entry,) = view.entries
    pm = PreserveMap(entries={(0,): entry.key}, from_epoch=0, to_epoch=1)

    committed_only = Ledger.from_occurrence_ledger(wal, committed_only=True)
    with pytest.raises(ReplanError) as excinfo:
        validate_preserve_map(model, pm, committed_only)
    assert excinfo.value.refusal is ReplanRefusal.OCCURRENCE_NOT_IN_LEDGER

    with pytest.raises(ReplanError) as excinfo:
        validate_preserve_map(model, pm, view)
    assert excinfo.value.refusal is ReplanRefusal.OCCURRENCE_NOT_IN_LEDGER
    assert "INTENDED" in excinfo.value.detail


def test_validate_consumes_the_WAL_directly_and_the_acceptance_is_load_bearing():
    """Collapses two former items. ``replan.py`` consumes the WAL, so no caller
    converts by hand; and stripping the COMMITTED line from that same WAL flips
    the result to a refusal, which is what stops the accepting case from being a
    vacuous pass."""
    model, wal, key = _wal_with_one_committed()
    pm = PreserveMap(entries={(0,): key}, from_epoch=0, to_epoch=1)
    validate_preserve_map(model, pm, wal)  # does not raise

    intended_only = OccurrenceLedger.from_records(
        [r for r in wal.records() if r.phase is LedgerPhase.INTENDED]
    )
    with pytest.raises(ReplanError) as excinfo:
        validate_preserve_map(model, pm, intended_only)
    assert excinfo.value.refusal is ReplanRefusal.OCCURRENCE_NOT_IN_LEDGER
