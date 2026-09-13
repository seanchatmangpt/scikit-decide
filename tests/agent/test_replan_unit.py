# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""UNIT checkpoint for single-hop preserve maps. Structure only -- nothing
here actuates, admits, brokers, or issues receipts.

**Collapse convention.** ``validate_preserve_map`` has six named refusals. They
were six items; they are now one table-driven item that executes every case and
accumulates failures, so a red run names every refusal that stopped firing
rather than only the first. Each case remains a distinct named falsifier with
its own constructed defect.
"""

import pytest

from autofde_lab.agent.replan import (
    Epoch,
    Ledger,
    LedgerEntry,
    OccurrenceStatus,
    PreserveMap,
    ReplanningMode,
    ReplanRefusal,
    ReplanError,
    activity_of,
    infer_preserve_map,
    redo_occurrence_key,
    seed_marking,
    validate_preserve_map,
)
from autofde_lab.powl.algebra import Atom, OrderEdge, PartialOrder
from autofde_lab.powl.executor import enabled, fire
from autofde_lab.powl.identity import OccurrenceKey


def _po(labels, edges=()):
    return PartialOrder(
        tuple(Atom(l) for l in labels),
        frozenset(OrderEdge(a, b) for a, b in edges),
    )


def _node_at(model, path):
    n = model
    for i in path:
        n = n.children[i]
    return n


def _ledger(model, paths, epoch=0, status=OccurrenceStatus.COMPLETED, resumable=False):
    counts = {}
    entries = []
    for p in paths:
        act = activity_of(_node_at(model, p))
        i = counts.get(act, 0)
        counts[act] = i + 1
        entries.append(
            LedgerEntry(OccurrenceKey(act, i, ""), p, status, epoch, resumable)
        )
    return Ledger(tuple(entries))


def test_modes_are_the_nine_named():
    assert {m.value for m in ReplanningMode} == {
        "Continue", "Repair", "Replan", "Reschedule", "UpdatePolicy",
        "LearnModel", "SpawnChild", "Terminate", "Refuse",
    }


def test_inference_maps_the_unambiguous_case_and_refuses_to_guess_the_ambiguous_one():
    """Collapses two former items — the positive and negative halves of one
    inference rule. Without the ambiguous half the positive half would not
    distinguish "matched correctly" from "matched anything that looked close"."""
    m0 = _po(["triage", "collect", "scope"])
    m1 = _po(["triage", "collect", "scope"])
    ledger = _ledger(m0, [(0,)])
    pm = infer_preserve_map(Epoch(0, m0), ledger, m1)
    assert set(pm.entries) == {(0,)}
    validate_preserve_map(m1, pm, ledger)
    mk = seed_marking(m1, pm)
    assert (0,) not in enabled(m1, mk), "a preserved occurrence was still enabled"
    assert enabled(m1, mk) == {(1,), (2,)}

    # POWL1 has TWO nodes carrying activity "a" for ONE prior occurrence
    ambiguous_before = _po(["a", "b"])
    ambiguous_after = _po(["a", "a", "b"])
    guessed = infer_preserve_map(
        Epoch(0, ambiguous_before), _ledger(ambiguous_before, [(0,)]), ambiguous_after
    )
    assert guessed.entries == {}, "an ambiguous match was guessed rather than left unmapped"


def test_every_named_preserve_map_refusal_fires_on_its_own_constructed_defect():
    """Collapses six former items — the whole ``ReplanRefusal`` surface reachable
    from ``validate_preserve_map``. Every case below is still constructed and
    executed by name; only the reporting is pooled."""
    ab = _po(["a", "b"])
    act_a = activity_of(ab.children[0])
    key_a = OccurrenceKey(act_a, 0, "")

    ordered = _po(["a", "b"], edges=[(0, 1)])
    act_b = activity_of(ordered.children[1])
    key_b = OccurrenceKey(act_b, 0, "")

    def _entry(key, path, status, **kw):
        return Ledger((LedgerEntry(key, path, status, 0, **kw),))

    cases = {
        # preserving "b" without its predecessor "a"
        "not-downward-closed": (
            ordered,
            PreserveMap(entries={(1,): key_b}),
            _entry(key_b, (1,), OccurrenceStatus.COMPLETED),
            ReplanRefusal.NOT_DOWNWARD_CLOSED,
        ),
        # an intention is not an observation
        "intended-only-is-not-an-observation": (
            ab,
            PreserveMap(entries={(0,): key_a}),
            _entry(key_a, (0,), OccurrenceStatus.INTENDED),
            ReplanRefusal.OCCURRENCE_NOT_IN_LEDGER,
        ),
        # ...and neither is a claim with nothing behind it at all
        "absent-from-ledger": (
            ab,
            PreserveMap(entries={(0,): key_a}),
            Ledger(()),
            ReplanRefusal.OCCURRENCE_NOT_IN_LEDGER,
        ),
        "unresumable-torn-fire": (
            ab,
            PreserveMap(entries={(0,): key_a}),
            _entry(key_a, (0,), OccurrenceStatus.TORN, resumable=False),
            ReplanRefusal.UNRESUMABLE_TORN_FIRE,
        ),
        "redo-without-justification": (
            ab,
            PreserveMap(redo=frozenset({(0,)})),
            Ledger(()),
            ReplanRefusal.REDO_WITHOUT_JUSTIFICATION,
        ),
        "non-adjacent-epoch": (
            ab,
            PreserveMap(from_epoch=0, to_epoch=2),
            Ledger(()),
            ReplanRefusal.NON_ADJACENT_EPOCH,
        ),
    }

    failures = {}
    for name, (model, pm, ledger, expected) in cases.items():
        try:
            validate_preserve_map(model, pm, ledger)
        except ReplanError as exc:
            if exc.refusal is not expected:
                failures[name] = f"refused as {exc.refusal!r}, expected {expected!r}"
        else:
            failures[name] = f"ACCEPTED, expected refusal {expected!r}"
    assert not failures, f"{len(failures)}/{len(cases)} preserve-map falsifiers lost: {failures}"

    # control for the torn case: a *resumable* torn fire is admissible, so the
    # refusal above is about resumability and not about TORN as such
    validate_preserve_map(
        ab,
        PreserveMap(entries={(0,): key_a}),
        _entry(key_a, (0,), OccurrenceStatus.TORN, resumable=True),
    )


def test_redo_is_legal_and_gets_a_fresh_rising_occurrence_index():
    m1 = _po(["revoke", "other"])
    act = activity_of(m1.children[0])
    prior = OccurrenceKey(act, 0, "")
    ledger = Ledger((LedgerEntry(prior, (0,), OccurrenceStatus.COMPLETED, 0),))
    pm = PreserveMap(
        entries={},
        redo=frozenset({(0,)}),
        redo_justification={(0,): "population B appeared after the revoke"},
    )
    validate_preserve_map(m1, pm, ledger)
    fresh = redo_occurrence_key(m1, ledger, (0,))
    assert fresh.occurrence_index == 1
    assert fresh != prior

    # and the executor, seeded with the prior key, derives the same index
    seeded = seed_marking(m1, PreserveMap(entries={(1,): OccurrenceKey(
        activity_of(m1.children[1]), 0, "")}))
    # seed_marking only carries what is preserved; add the prior key by hand
    from dataclasses import replace as _replace
    seeded = _replace(seeded, completed=seeded.completed | {prior})
    after = fire(m1, seeded, (0,))
    got = [k for k in after.completed if k.activity_sha256 == act]
    assert sorted(k.occurrence_index for k in got) == [0, 1]
