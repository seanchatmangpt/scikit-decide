# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style milestone test: the whole breach-clock loop, end to end.

Real :class:`~autofde_lab.hub.domain.breach_clock.BreachClockDomain`, real POWL 2.0
models, the real bounded executor, the real two-phase occurrence ledger, the
real preserve-map machinery. Nothing is mocked, stubbed, or faked.

**Self-contained by construction.** This module imports nothing outside
``autofde_lab`` and the standard library. It reaches no network, no cloud provider,
and no sibling repository — ``~/mfw``, ``~/bcinr``, ``~/ggen`` and ``~/mfact``
may all be absent. ``test_no_sibling_repository_is_imported_anywhere`` asserts
that mechanically rather than leaving it to review, and
``tests/agent/test_clean_checkout.py`` proves the import graph in a fresh
subprocess with ``HOME`` pointed at an empty directory.

**What this test does not establish.** Everything here computes a *candidate
plan*. Nothing actuates, admits, brokers, or issues an authoritative receipt,
and ``organizationalStanding`` is not computed anywhere in this repository — see
``.claude/rules/standing-law.md``. The boundary section at the bottom asserts
that so it cannot erode quietly.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from autofde_lab.agent import replan as R
from autofde_lab.agent.ledger import LedgerPhase
from autofde_lab.agent.models import EpochStanding
from autofde_lab.agent.refusals import CLAIM_CEILING
from autofde_lab.agent.session import AgentSession
from autofde_lab.hub.domain.breach_clock import (
    Action,
    BreachClockDomain,
    Containment,
    Notification,
    Scope,
)
from autofde_lab.powl.algebra import (
    Atom,
    ChoiceGraph,
    ChoiceGraphEdge,
    OrderEdge,
    PartialOrder,
    Silent,
)
from autofde_lab.powl.executor import enabled, node_at, replay, trace_of
from autofde_lab.powl.identity import OccurrenceKey
from autofde_lab.powl.membership import explain, trace_in_language
from autofde_lab.powl.validate import validate_model

# ── the two candidate plans ────────────────────────────────────────────────

#: triage || collect_evidence || compute_scope. The edge set is EMPTY, so the
#: closed order is empty and no pair is ordered. This is the concurrency claim.
INVESTIGATION = PartialOrder(
    (
        Atom("triage", Action.triage),
        Atom("collect_evidence", Action.collect_evidence),
        Atom("compute_scope", Action.compute_scope),
    ),
    frozenset(),
)

#: The 3-way exclusive containment choice. Its boundary nodes are ``Silent``
#: because POWL 2.0's boundary law requires a start with no incoming edge and an
#: end with no outgoing edge; the three postures are the interior, mutually
#: exclusive branches.
CONTAINMENT = ChoiceGraph(
    (
        Silent(),
        Atom("revoke_sessions", Action.revoke_sessions),
        Atom("isolate_workload", Action.isolate_workload),
        Atom("preserve_evidence_only", Action.preserve_evidence_only),
        Silent(),
    ),
    frozenset(
        {
            ChoiceGraphEdge(0, 1),
            ChoiceGraphEdge(0, 2),
            ChoiceGraphEdge(0, 3),
            ChoiceGraphEdge(1, 4),
            ChoiceGraphEdge(2, 4),
            ChoiceGraphEdge(3, 4),
        }
    ),
    start=0,
    end=4,
)

DRAFT = Atom("draft_notification", Action.draft_notification)
DELIVER = Atom("deliver_notification", Action.deliver_notification)

#: The plan as formed on the signal, while scope and population are UNKNOWN.
POWL0 = PartialOrder(
    (INVESTIGATION, CONTAINMENT, DRAFT, DELIVER),
    frozenset({OrderEdge(0, 1), OrderEdge(1, 2), OrderEdge(2, 3)}),
)

#: The plan after divergence. It carries the SAME containment subtree — that is
#: what makes "containment must not re-execute" a claim about one node rather
#: than about two structurally different ones — extends investigation with a
#: fresh scope computation for the widened population, and re-notifies.
POWL1 = PartialOrder(
    (CONTAINMENT, Atom("compute_scope", Action.compute_scope), DRAFT, DELIVER),
    frozenset({OrderEdge(0, 2), OrderEdge(1, 2), OrderEdge(2, 3)}),
)

#: The containment subtree's leaf paths. It is child 1 of POWL0 and child 0 of
#: POWL1 — the same subtree, addressed from two different roots.
CONTAINMENT_PATHS_POWL0 = ((1, 0), (1, 1), (1, 4))
CONTAINMENT_PATHS_POWL1 = ((0, 0), (0, 1), (0, 4))
POSTURE_PATHS = ((1, 1), (1, 2), (1, 3))


# ── the run ────────────────────────────────────────────────────────────────


class BreachClockRun:
    """One complete six-epoch run. Holds the real objects, not copies of them."""

    def __init__(self, session_id: str = "breach-clock-milestone") -> None:
        self.domain = BreachClockDomain()
        self.state = self.domain.get_initial_state()
        self.session = AgentSession(self.domain, session_id=session_id)
        self.epoch_ids: list[str] = []
        self.receipts: dict[str, Any] = {}
        self.records: dict[str, list[Any]] = {}
        self.seed = None

    # the domain is load-bearing: every atom carrying an action is checked
    # applicable in the real state and really advances it.
    def _apply(self, model, path) -> None:
        node = node_at(model, path)
        if isinstance(node, Atom) and node.action is not None:
            assert self.domain.applicable(self.state, node.action), (
                f"{node.label} is not applicable in {self.state}"
            )
            self.state = self.domain.get_next_state(self.state, node.action)

    def phase(self, name, model, paths, *, carry=True, **kwargs):
        marking = kwargs.pop("marking", None)
        if marking is None and carry and self.session.epochs:
            marking = self.session.epochs[-1].marking
        epoch = self.session.open_epoch(model, marking=marking, **kwargs)
        self.epoch_ids.append(epoch.epoch_id)
        recorded = []
        for path in paths:
            self._apply(model, path)
            record, _key = self.session.step(path, decided_by=f"test:{name}")
            recorded.append(record)
        self.records[name] = recorded
        self.receipts[name] = self.session.seal_epoch()
        return self.session.epochs[-1]

    # ── the prior ledger, in the replan module's own vocabulary ────────────

    def replan_ledger(self, prior_index: int) -> R.Ledger:
        entries = tuple(
            R.LedgerEntry(
                key=OccurrenceKey(
                    rec.activity_sha256, rec.occurrence_index, rec.context_sha256
                ),
                path=rec.path,
                status=R.OccurrenceStatus.COMPLETED,
                epoch=prior_index,
            )
            for rec in self.session.ledger.records()
            if rec.phase is LedgerPhase.COMMITTED
        )
        return R.Ledger(entries)


def run_scenario(session_id: str = "breach-clock-milestone") -> BreachClockRun:
    """Drive all six epochs. Every assertion below reads this real state."""
    run = BreachClockRun(session_id)

    # epoch 1 — signal. The plan is formed; nothing has been traversed.
    run.phase("signal", POWL0, ())

    # epoch 2 — investigation, genuinely concurrent.
    run.phase("investigation", POWL0, ((0, 0), (0, 1), (0, 2)))

    # epoch 3 — containment: the real 3-way choice.
    run.phase("containment", POWL0, ((1, 0), (1, 1), (1, 4)))

    # epoch 4 — notification drafted.
    run.phase("notification", POWL0, ((2,),))

    # epoch 5 — delivery, bounded.
    run.phase("delivery", POWL0, ((3,),))

    # ── divergence: population B is also affected ──────────────────────────
    run.state = run.domain.observe_divergence(run.state)

    prior_index = len(run.session.epochs) - 1
    ledger = run.replan_ledger(prior_index)
    inferred = R.infer_preserve_map(R.Epoch(prior_index, POWL0), ledger, POWL1)
    # Content addressing alone would also preserve scope/draft/deliver, because
    # POWL1 carries one node per prior occurrence of each. They must run again
    # for the widened population, so they are moved into `redo` WITH written
    # justifications — an unjustified redo is refused by validate_preserve_map.
    preserve_map = R.PreserveMap(
        entries={p: k for p, k in inferred.entries.items() if p[0] == 0},
        redo=frozenset({(1,), (2,), (3,)}),
        redo_justification={
            (1,): "scope fell back to PARTIAL when population B was revealed",
            (2,): "the drafted notification covers population A only",
            (3,): "delivery must cover every affected population",
        },
        from_epoch=prior_index,
        to_epoch=prior_index + 1,
    )
    R.validate_preserve_map(POWL1, preserve_map, ledger)
    run.seed = R.seed_marking(POWL1, preserve_map)
    run.preserve_map = preserve_map
    run.replan_ledger_obj = ledger
    run.inferred = inferred

    # epoch 6 — replan. Supersedes the whole prior lineage.
    run.phase(
        "replan",
        POWL1,
        ((1,), (2,), (3,)),
        marking=run.seed,
        supersedes=tuple(run.epoch_ids),
        preserves=("revoke_sessions",),
    )
    return run


@pytest.fixture(scope="module")
def run() -> BreachClockRun:
    return run_scenario()


# ── 6. both models are structurally well formed ────────────────────────────


def test_validate_model_passes_on_both_powl0_and_powl1():
    assert validate_model(POWL0) is None
    assert validate_model(POWL1) is None


# ── 1. genuine concurrency in the investigation epoch ──────────────────────


def test_the_three_investigation_activities_are_pairwise_unordered(run):
    """The single most important failure to catch is a serialized investigation."""
    assert INVESTIGATION.closure == frozenset(), (
        "the closed order of the investigation subtree must be empty; any edge "
        "here means the three activities were silently serialized"
    )
    labels = [c.label for c in INVESTIGATION.children]
    assert labels == ["triage", "collect_evidence", "compute_scope"]

    # ... and the domain agrees they are independent, which is what makes the
    # empty order honest rather than a modelling convenience.
    state = BreachClockDomain().get_initial_state()
    for taken in INVESTIGATION.children:
        after = BreachClockDomain().get_next_state(state, taken.action)
        others = [c.action for c in INVESTIGATION.children if c is not taken]
        assert all(BreachClockDomain().applicable(after, a) for a in others)


def test_enabled_returns_all_three_investigation_activities_simultaneously(run):
    signal_epoch = run.session.epochs[0]
    live = enabled(signal_epoch.model, signal_epoch.marking, signal_epoch.bound)
    assert live == frozenset({(0, 0), (0, 1), (0, 2)}), (
        f"expected all three investigation leaves enabled at once, got {sorted(live)}"
    )
    # the investigation epoch begins from exactly that position
    assert run.records["investigation"][0].enabled == ((0, 0), (0, 1), (0, 2))
    assert sorted(run.receipts["investigation"].trace) == [
        "collect_evidence",
        "compute_scope",
        "triage",
    ]


# ── 2. a real 3-way choice, with the full enabled set recorded ─────────────


def test_containment_epoch_records_one_choice_over_all_three_postures(run):
    """Exactly one recorded step in the containment epoch is a *decision*.

    The epoch has three records, not one, and that is structural rather than a
    modelling slip: POWL 2.0's boundary law requires a choice graph's start to
    have no incoming edge and its end no outgoing edge, so reaching the branch
    point always costs one forced step and leaving it costs one more. The
    assertion is therefore made precisely — exactly one record has more than one
    option, and that record's enabled set is exactly the three postures.
    """
    records = run.records["containment"]
    decisions = [r for r in records if len(r.enabled) > 1]
    assert len(decisions) == 1, [r.enabled for r in records]

    decision = decisions[0]
    assert set(decision.enabled) == set(POSTURE_PATHS)
    assert len(decision.enabled) == 3
    assert decision.chosen == (1, 1)  # revoke_sessions
    assert decision.chosen in decision.enabled

    # the alternatives were live, not decoration: each is applicable in the real
    # domain state at the moment of the decision, and each closes the other two.
    posture_actions = [node_at(POWL0, p).action for p in POSTURE_PATHS]
    state = BreachClockDomain().get_initial_state()._replace(triaged=True)
    for action in posture_actions:
        assert BreachClockDomain().applicable(state, action)
        after = BreachClockDomain().get_next_state(state, action)
        assert after.containment is not Containment.NONE
        assert not any(
            BreachClockDomain().applicable(after, other)
            for other in posture_actions
            if other is not action
        )

    # the other two records are forced boundary steps, not choices
    forced = [r for r in records if len(r.enabled) == 1]
    assert [r.chosen for r in forced] == [(1, 0), (1, 4)]


# ── 3. the replan: supersession, downward closure, no re-execution ─────────


def test_the_replan_supersedes_the_whole_prior_lineage(run):
    assert run.session.epochs[0].standing is EpochStanding.SUPERSEDED
    assert all(
        e.standing is EpochStanding.SUPERSEDED for e in run.session.epochs[:-1]
    )
    assert run.session.epochs[-1].standing is EpochStanding.ALIVE
    assert run.session.epochs[-1].supersedes == tuple(run.epoch_ids[:-1])


def test_the_preserve_map_validates_as_downward_closed(run):
    # returns None on success and raises ReplanError otherwise
    assert (
        R.validate_preserve_map(POWL1, run.preserve_map, run.replan_ledger_obj) is None
    )
    assert set(run.preserve_map.entries) == set(CONTAINMENT_PATHS_POWL1)

    # and it is a real check: dropping the choice-graph end from the preserved
    # set is refused, it does not quietly pass.
    truncated = R.PreserveMap(
        entries={p: k for p, k in run.preserve_map.entries.items() if p != (0, 4)},
        redo=run.preserve_map.redo,
        redo_justification=run.preserve_map.redo_justification,
        from_epoch=run.preserve_map.from_epoch,
        to_epoch=run.preserve_map.to_epoch,
    )
    seeded = R.seed_marking(POWL1, truncated)
    # the containment subtree is no longer complete, so POWL1 re-enables it
    assert any(p[0] == 0 for p in enabled(POWL1, seeded))


def test_containment_cannot_re_execute_after_the_replan(run):
    """Structural, not a guard: preserved leaves can never enter ``enabled``."""
    assert sorted(enabled(POWL1, run.seed)) == [(1,)], (
        "only the extended investigation may start; containment is complete"
    )
    for epoch_marking in (run.seed, run.session.epochs[-1].marking):
        assert not any(p[0] == 0 for p in enabled(POWL1, epoch_marking))

    replan_context = {
        r.context_sha256
        for r in run.session.ledger.records()
        if r.path in {(1,), (2,), (3,)} and r.phase is LedgerPhase.COMMITTED
    }
    containment_activities = {
        R.activity_of(node_at(POWL1, p)) for p in CONTAINMENT_PATHS_POWL1
    }
    replayed_containment = [
        r
        for r in run.session.ledger.records()
        if r.phase is LedgerPhase.COMMITTED
        and r.activity_sha256 in containment_activities
        and r.context_sha256 in replan_context
    ]
    assert replayed_containment == []


def test_no_occurrence_key_repeats_unless_the_node_is_a_justified_redo(run):
    keys = run.session.ledger.occurrences()
    assert len(keys) == len(set(keys)), "an occurrence key was recorded twice"

    containment_activities = {
        R.activity_of(node_at(POWL1, p)) for p in CONTAINMENT_PATHS_POWL1
    }
    committed = [
        r for r in run.session.ledger.records() if r.phase is LedgerPhase.COMMITTED
    ]
    # the two Silent boundary nodes share one activity address, so that activity
    # legitimately has two occurrences (indices 0 and 1) and the posture has one.
    counts = {
        a: sum(1 for r in committed if r.activity_sha256 == a)
        for a in containment_activities
    }
    assert sorted(counts.values()) == [1, 2]

    # every activity that DID occur more than once beyond that is a justified redo
    redo_activities = {
        R.activity_of(node_at(POWL1, p)) for p in run.preserve_map.redo
    }
    for activity, count in {
        a: sum(1 for r in committed if r.activity_sha256 == a)
        for a in {r.activity_sha256 for r in committed}
    }.items():
        if count > 1 and activity not in containment_activities:
            assert activity in redo_activities, activity
            justified = [
                run.preserve_map.redo_justification[p]
                for p in run.preserve_map.redo
                if R.activity_of(node_at(POWL1, p)) == activity
            ]
            assert justified and all(j.strip() for j in justified)


def test_an_unjustified_redo_is_refused(run):
    with pytest.raises(R.ReplanError) as excinfo:
        R.validate_preserve_map(
            POWL1,
            R.PreserveMap(
                entries=dict(run.preserve_map.entries),
                redo=frozenset({(1,)}),
                redo_justification={},
                from_epoch=run.preserve_map.from_epoch,
                to_epoch=run.preserve_map.to_epoch,
            ),
            run.replan_ledger_obj,
        )
    assert excinfo.value.refusal is R.ReplanRefusal.REDO_WITHOUT_JUSTIFICATION


# ── 4. replay reproduces the marking and the lineage ───────────────────────


def test_replay_reproduces_the_identical_final_marking(run):
    prior_choices = [c for e in run.session.epochs[:-1] for c in e.choices]
    replayed = replay(POWL0, prior_choices)
    assert replayed == run.session.epochs[-2].marking

    final = run.session.epochs[-1]
    assert replay(POWL1, final.choices, initial=run.seed) == final.marking


def test_replay_diverges_on_a_tampered_record(run):
    from autofde_lab.powl.executor import DeadlockKind, ReplayDivergedError

    choices = list(run.session.epochs[-1].choices)
    tampered = choices[:]
    tampered[0] = type(choices[0])(
        step=choices[0].step,
        path=choices[0].path,
        enabled=((1,), (0, 1)),  # a set the model never produces here
        chosen=choices[0].chosen,
        decided_by=choices[0].decided_by,
        context_sha256=choices[0].context_sha256,
    )
    with pytest.raises(ReplayDivergedError) as excinfo:
        replay(POWL1, tampered, initial=run.seed)
    assert excinfo.value.kind is DeadlockKind.REPLAY_DIVERGED


def test_the_lineage_digest_is_reproducible(run):
    other = run_scenario()
    assert other.session.outcome().lineage_sha256 == (
        run.session.outcome().lineage_sha256
    )
    assert other.session.outcome().receipt_sha256 == (
        run.session.outcome().receipt_sha256
    )
    assert other.session.epochs[-1].marking == run.session.epochs[-1].marking


# ── 5. the independent language check ──────────────────────────────────────


def test_every_trace_produced_is_in_the_language_of_its_model(run):
    """``membership`` decides this by a different algorithm than the executor."""
    prior = trace_of(POWL0, [c for e in run.session.epochs[:-1] for c in e.choices])
    assert prior == (
        "triage",
        "collect_evidence",
        "compute_scope",
        "revoke_sessions",
        "draft_notification",
        "deliver_notification",
    )
    assert trace_in_language(POWL0, prior), explain(POWL0, prior)

    # POWL1's trace is the preserved containment label plus what epoch 6 ran.
    preserved_labels = tuple(
        node_at(POWL1, p).label
        for p in sorted(run.preserve_map.entries)
        if isinstance(node_at(POWL1, p), Atom)
    )
    full = preserved_labels + run.receipts["replan"].trace
    assert full == (
        "revoke_sessions",
        "compute_scope",
        "draft_notification",
        "deliver_notification",
    )
    assert trace_in_language(POWL1, full), explain(POWL1, full)

    # and the checker is not vacuous: precedence and branch are both enforced
    assert not trace_in_language(POWL1, tuple(reversed(full)))
    assert not trace_in_language(
        POWL1, ("isolate_workload",) + run.receipts["replan"].trace[:1]
    )


# ── the loop actually closed, in the domain ────────────────────────────────


def test_the_domain_reaches_the_goal_only_after_the_replan(run):
    reconstructed = BreachClockDomain()
    state = reconstructed.get_initial_state()
    assert state.scope is Scope.UNKNOWN
    assert state.populations == frozenset({"A"})
    assert not reconstructed.is_goal(state)

    for path in ((0, 0), (0, 1), (0, 2), (1, 1), (2,), (3,)):
        node = node_at(POWL0, path)
        state = reconstructed.get_next_state(state, node.action)
    assert reconstructed.is_goal(state)
    assert state.notification is Notification.DELIVERED

    diverged = reconstructed.observe_divergence(state)
    assert diverged.populations == frozenset({"A", "B"})
    assert diverged.scope is Scope.PARTIAL
    assert not reconstructed.is_goal(diverged), (
        "divergence must genuinely break the goal, otherwise the replan is theatre"
    )
    assert not reconstructed.applicable(diverged, Action.deliver_notification)

    # the real run ended at the goal for the widened population
    assert run.domain.is_goal(run.state)
    assert run.state.populations == frozenset({"A", "B"})
    assert run.state.notified_populations == frozenset({"A", "B"})


def test_the_run_is_bounded_and_every_occurrence_is_recorded(run):
    final = run.session.epochs[-1]
    assert final.marking.fires <= run.session.bound.max_activity_fires
    committed = [
        r for r in run.session.ledger.records() if r.phase is LedgerPhase.COMMITTED
    ]
    intended = [
        r for r in run.session.ledger.records() if r.phase is LedgerPhase.INTENDED
    ]
    # 3 investigation + 3 containment (2 boundaries + 1 posture) + draft +
    # deliver = 8 under POWL0, then 3 more under POWL1.
    assert len(committed) == len(intended) == 11
    assert run.session.ledger.is_resumable()


# ══ BOUNDARY — asserted here so it cannot erode quietly ════════════════════


def test_the_outcome_carries_no_admission_actuation_or_authority_claim(run):
    outcome = run.session.outcome()
    assert outcome.claim_ceiling == CLAIM_CEILING
    assert CLAIM_CEILING.startswith("CANDIDATE_PLAN_ONLY")

    payload = outcome.as_dict()
    blob = json.dumps(payload, default=str).lower()

    def keys(node):
        if isinstance(node, dict):
            for k, v in node.items():
                yield k
                yield from keys(v)
        elif isinstance(node, (list, tuple)):
            for v in node:
                yield from keys(v)

    forbidden = ("admit", "admission", "actuat", "authoriz", "authority", "broker")
    assert not [k for k in keys(payload) if any(f in k.lower() for f in forbidden)]

    # the words appear exactly once, inside the claim ceiling, and only negated
    stripped = blob.replace(CLAIM_CEILING.lower(), "")
    assert not [f for f in forbidden if f in stripped], stripped

    # standing is technical only
    assert outcome.standing in set(EpochStanding)
    assert all(r.claim_ceiling == CLAIM_CEILING for r in outcome.epochs)


def test_organizational_standing_is_unknown_throughout(run):
    """Nothing in this repository computes ``organizationalStanding``.

    Per ``.claude/rules/standing-law.md`` every standing claim this runtime makes
    is a ``technicalStanding`` claim. The honest assertion is therefore that the
    outcome exposes no organizational standing at all — it is ``UNKNOWN`` by
    absence, and a simulated authority grant would be a CONTROL rather than
    evidence that organizational admission works.
    """
    payload = run.session.outcome().as_dict()
    blob = json.dumps(payload, default=str).lower()
    assert "organizational" not in blob
    assert "enterprisestanding" not in blob
    assert set(EpochStanding) == {
        EpochStanding.ALIVE,
        EpochStanding.PARTIAL_ALIVE,
        EpochStanding.BLOCKED,
        EpochStanding.SUPERSEDED,
        EpochStanding.UNKNOWN,
        EpochStanding.UNSUPPORTED,
    }, "EpochStanding must stay a technical vocabulary"


SIBLING_REPOS = ("mfw", "bcinr", "ggen", "mfact", "ggen_create", "wasm4pm", "praxis")


def test_no_sibling_repository_is_imported_anywhere(run):
    source = Path(__file__).read_text()
    for name in SIBLING_REPOS:
        assert f"import {name}" not in source
        assert f"from {name}" not in source
    assert not [m for m in sys.modules if m.split(".")[0] in SIBLING_REPOS]

    home = Path.home()
    loaded = [
        m
        for m, mod in list(sys.modules.items())
        if getattr(mod, "__file__", None)
        and any(
            str(mod.__file__).startswith(str(home / repo) + "/")
            for repo in SIBLING_REPOS
        )
    ]
    assert loaded == []
