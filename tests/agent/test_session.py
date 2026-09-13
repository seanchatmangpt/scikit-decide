# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for :class:`autofde_lab.agent.session.AgentSession`.

Real ``Maze`` domain, real ``rollout``, real POWL executor. Nothing mocked.

**Ownership.** Ledger properties belong to ``test_ledger.py``; this file asserts
them only where the *session* is the thing that must honour them (the occurrence
count and context split after a real two-epoch run, and the "no intent was
written" claim on a pre-intent refusal). It does not re-prove the two-phase
protocol itself.
"""

from __future__ import annotations

from typing import Any

import pytest

from autofde_lab.agent.models import EpochStanding
from autofde_lab.agent.refusals import (
    BLOCKED_ACTION_NODE_UNRESOLVED,
    AgentRefusal,
    AgentRefusalCode,
)
from autofde_lab.agent.epoch import DecisionEpoch
from autofde_lab.agent.session import AgentSession
from autofde_lab.hub.domain.maze import Maze
from autofde_lab.hub.domain.maze.maze import Action
from autofde_lab.powl.algebra import Atom, PartialOrder
from autofde_lab.powl.bounds import ExecutionBound

# ── fixtures: a scripted policy so the trace is deterministic ───────────────


class ScriptedPolicy:
    """Replays a fixed action list. Real object, not a mock."""

    def __init__(self, actions: list[Any]) -> None:
        self.actions = list(actions)
        self.index = 0

    def sample_action(self, observation: Any, domain: Any = None) -> Any:
        action = self.actions[min(self.index, len(self.actions) - 1)]
        self.index += 1
        return action

    def is_policy_defined_for(self, observation: Any) -> bool:
        return True


def _unordered(*labels: str) -> PartialOrder:
    """A partial order with no edges: every child is enabled at once."""
    return PartialOrder(tuple(Atom(label=label) for label in labels))


def _session(actions: list[Any], **kwargs: Any) -> AgentSession:
    return AgentSession(Maze(), ScriptedPolicy(actions), **kwargs)


# ── the session advances across epochs ─────────────────────────────────────


def test_session_advances_across_two_epochs():
    session = _session([Action.up, Action.right, Action.down, Action.left])

    session.open_epoch(_unordered("up", "right"))
    first = session.advance(max_steps=2)

    assert first.steps == 2
    assert sorted(first.trace) == ["right", "up"]
    assert first.standing is EpochStanding.ALIVE  # both atoms fired => final
    assert first.blocked_reason is None

    second_epoch = session.open_epoch(_unordered("down", "left"))
    second = session.advance(max_steps=2)

    assert second.epoch_id == second_epoch.epoch_id
    assert second.steps == 2
    assert sorted(second.trace) == ["down", "left"]
    assert second.standing is EpochStanding.ALIVE

    outcome = session.outcome()
    assert len(outcome.epochs) == 2
    assert outcome.standing is EpochStanding.ALIVE
    # Four committed occurrences across both epochs, none re-executed.
    assert len(session.ledger.occurrences()) == 4
    assert len({k.context_sha256 for k in session.ledger.occurrences()}) == 2


def test_a_partially_traversed_epoch_is_partial_alive_not_alive():
    session = _session([Action.up])
    session.open_epoch(_unordered("up", "right"))
    receipt = session.advance(max_steps=1)

    assert receipt.steps == 1
    assert receipt.standing is EpochStanding.PARTIAL_ALIVE
    assert session.outcome().standing is EpochStanding.PARTIAL_ALIVE


# ── the receipt digest ─────────────────────────────────────────────────────


def test_the_receipt_digest_is_reproducible_and_covers_the_bound():
    """Collapses two former items. Reproducibility without bound-sensitivity is
    a constant function and bound-sensitivity without reproducibility is noise,
    so the two halves are asserted against the same fixed ``session_id``."""
    def run(bound: ExecutionBound):
        session = _session(
            [Action.up, Action.right], bound=bound, session_id="fixed-session"
        )
        session.open_epoch(_unordered("up", "right"))
        session.advance(max_steps=2)
        return session.outcome()

    default, again = run(ExecutionBound()), run(ExecutionBound())
    tighter = run(ExecutionBound(max_activity_fires=4))

    assert default.receipt_sha256 == again.receipt_sha256, "the digest is not reproducible"
    assert default.epochs[0].trace == tighter.epochs[0].trace  # same observed run
    assert default.input_sha256 != tighter.input_sha256
    assert default.receipt_sha256 != tighter.receipt_sha256


# ── ACTION_NODE_UNRESOLVED ─────────────────────────────────────────────────


def test_action_node_is_never_guessed_when_resolution_is_not_injective():
    """Collapses three former items. The refusal has two triggers -- no enabled
    node matches, and two enabled nodes share a label -- plus the direct
    ``resolve_enabled_node`` call that shows the refusal names the ambiguous set
    rather than silently picking one. All three are still executed here; the
    third is what makes the first two more than "it declined to act".
    """
    from autofde_lab.agent.bridge import resolve_enabled_node

    # (a) the policy offers an action the model does not contain
    no_match = _session([Action.left])  # model offers only "up"/"right"
    no_match.open_epoch(_unordered("up", "right"))
    receipt = no_match.advance(max_steps=1)
    assert receipt.standing is EpochStanding.BLOCKED
    assert receipt.blocked_reason == BLOCKED_ACTION_NODE_UNRESOLVED
    assert receipt.steps == 0
    # The refusal fired *before* any intent was written, so nothing is dangling.
    assert no_match.ledger.is_resumable() is True
    assert no_match.outcome().standing is EpochStanding.BLOCKED

    # (b) two identically-labelled atoms: action -> node is not injective
    ambiguous = _session([Action.up])
    ambiguous.open_epoch(_unordered("up", "up"))
    receipt = ambiguous.advance(max_steps=1)
    assert receipt.standing is EpochStanding.BLOCKED
    assert receipt.blocked_reason == BLOCKED_ACTION_NODE_UNRESOLVED
    assert receipt.steps == 0

    # (c) and the underlying refusal names the set it could not disambiguate
    direct = _session([])
    epoch = direct.open_epoch(_unordered("up", "up"))
    with pytest.raises(AgentRefusal) as excinfo:
        resolve_enabled_node(epoch, Action.up)
    assert excinfo.value.code is AgentRefusalCode.ACTION_NODE_UNRESOLVED
    assert excinfo.value.details["matches"] == [[0], [1]]


# ── replan / supersede ─────────────────────────────────────────────────────


def test_replan_is_append_only_and_may_not_drop_a_preserved_activity():
    """Collapses two former items — the successful replan and the refused one
    are the two outcomes of one gate, and the success is only meaningful given
    that the gate can refuse."""
    session = _session([Action.up, Action.right, Action.down])
    first = session.open_epoch(_unordered("up", "right"))
    session.advance(max_steps=1)

    session.replan(_unordered("right", "down"), preserves=("right",))

    assert len(session.epochs) == 2  # append-only: nothing was popped
    assert session.epochs[0].epoch_id == first.epoch_id
    assert session.epochs[0].standing is EpochStanding.SUPERSEDED

    dropping = _session([Action.up])
    dropping.open_epoch(_unordered("up", "right"))
    with pytest.raises(AgentRefusal) as excinfo:
        dropping.replan(_unordered("down", "left"), preserves=("right",))
    assert excinfo.value.code is AgentRefusalCode.PRESERVATION_VIOLATED
    assert excinfo.value.details["missing"] == ["right"]


def test_the_session_refuses_calls_that_name_no_epoch_or_a_foreign_one():
    """Collapses two former items — both are the same law (a session may only
    act on epochs it opened), asserted at the two entry points that can break
    it."""
    no_epoch = _session([Action.up])
    with pytest.raises(AgentRefusal) as excinfo:
        no_epoch.advance(max_steps=1)
    assert excinfo.value.code is AgentRefusalCode.NO_OPEN_EPOCH

    foreign = _session([])
    with pytest.raises(AgentRefusal) as excinfo:
        foreign.open_epoch(_unordered("up", "right"), supersedes=("not-an-epoch",))
    assert excinfo.value.code is AgentRefusalCode.UNKNOWN_SUPERSEDED_EPOCH


# ── envelope shape ─────────────────────────────────────────────────────────


def test_outcome_carries_the_claim_ceiling_is_json_shaped_and_is_seeded():
    """Collapses two former items — the envelope's contents and its determinism
    source. The seeding claim is part of what makes the envelope reproducible,
    so it is asserted alongside rather than in isolation."""
    from autofde_lab.agent.refusals import CLAIM_CEILING
    from autofde_lab.fabric.canonical import canonical_json

    session = _session([Action.up, Action.right])
    session.open_epoch(_unordered("up", "right"))
    session.advance(max_steps=2)
    outcome = session.outcome()

    assert outcome.claim_ceiling == CLAIM_CEILING
    assert "does not actuate" in outcome.claim_ceiling
    canonical_json(outcome.as_dict())  # must not raise
    assert outcome.epochs[0].evidence is not None
    assert len(outcome.epochs[0].evidence.steps) == 2

    a = _session([], session_id="seed-a")
    b = _session([], session_id="seed-a")
    c = _session([], session_id="seed-b")
    assert a.random.random() == b.random.random()
    assert a.random.random() != c.random.random()


def test_a_superseded_epoch_enables_nothing_and_that_is_a_gate_not_a_mutation():
    """Containment must be structural, not a property of one call site.

    Every ``AgentSession`` mutator addresses ``_epochs[-1]``, so today no session
    API can fire from a superseded epoch. That is one call site holding the line.
    A caller holding a direct reference to the old epoch — the plan's own
    falsifier list names "superseded POWL0 still enabling activities" — must not
    be handed a live step set for a plan that has been replaced.

    Collapses two former items: restoring the standing revives the same enabled
    set from the same object, which pins that the containment is a standing gate
    and not a destructive mutation of the marking. Asserting the containment
    without that second half would not distinguish the two.
    """
    session = _session([Action.up, Action.right, Action.down])
    old = session.open_epoch(_unordered("up", "right"))
    assert sorted(old.enabled()) == [(0,), (1,)], "live before the replan"

    session.replan(_unordered("right", "down"), preserves=("right",))

    superseded = session.epochs[0]
    assert superseded.standing is EpochStanding.SUPERSEDED
    assert superseded.enabled() == frozenset()
    assert (
        EpochStanding.SUPERSEDED in DecisionEpoch.TERMINAL_STANDINGS
    ), "SUPERSEDED must be a terminal standing, not a label"
    # the new epoch is unaffected
    assert session.epochs[-1].enabled()

    # the model itself is untouched: restore the standing, get the same set back
    revived = superseded.with_standing(EpochStanding.UNKNOWN)
    assert sorted(revived.enabled()) == [(0,), (1,)]
    assert revived.marking == superseded.marking
