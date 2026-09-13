"""Chicago-style tests for DeadEdge retention in ``discover_procedure``.

Real module, real BFS, real hidden-precondition probe harness (the same one as
``tests/test_autonomous_procedure_discovery.py``). Synchronous: ``pytest_asyncio``
is absent from the venv, so the coroutine is driven with ``asyncio.run``.
"""

from __future__ import annotations

import asyncio

import pytest

from autofde_lab.hub.domain.gym_procedure.dead_edges import (
    DeadEdge,
    DeadEdgeLedger,
    ledger_digest,
)
from autofde_lab.hub.domain.gym_procedure.discovery import (
    DiscoveryChallenge,
    DiscoveryResult,
    ProbeEvidence,
    discover_procedure,
)

HIDDEN = {
    "opaque-a": (frozenset({"start"}), frozenset({"middle"})),
    "opaque-b": (frozenset({"middle"}), frozenset({"done"})),
}
DEAD_PAIR = (frozenset({"start"}), "opaque-b")


def _make_probe(calls: list[tuple[frozenset[str], str]]):
    async def probe(prefix: tuple[str, ...], action_id: str) -> ProbeEvidence:
        state = frozenset({"start"})
        for prior in prefix:
            required, effect = HIDDEN[prior]
            assert required <= state
            state |= effect
        calls.append((state, action_id))
        required, effect = HIDDEN[action_id]
        accepted = required <= state and not effect <= state
        after = state | effect if accepted else state
        return ProbeEvidence(
            action_id=action_id,
            prefix=prefix,
            accepted=accepted,
            before_facts=state,
            after_facts=after,
            standing="ALIVE" if accepted else "REFUSED",
            receipt_ids=(f"receipt:{len(prefix)}:{action_id}",),
            reason=None if accepted else "PRECONDITION_REFUSED",
        )

    return probe


def _run(
    hypothesis_digest: str, prior: tuple[DeadEdge, ...] = ()
) -> tuple[DiscoveryResult, list[tuple[frozenset[str], str]]]:
    calls: list[tuple[frozenset[str], str]] = []
    challenge = DiscoveryChallenge(
        subject="held-out/task",
        initial_facts=frozenset({"start"}),
        goal_facts=frozenset({"done"}),
        action_ids=("opaque-b", "opaque-a"),
        hypothesis_digest=hypothesis_digest,
        prior_dead_edges=prior,
    )
    return asyncio.run(discover_procedure(challenge, _make_probe(calls))), calls


def test_refused_probe_is_retained_as_typed_dead_edge() -> None:
    result, calls = _run("h1")
    assert result.plan == ("opaque-a", "opaque-b")
    assert result.suppressed_reprobes == 0
    assert DEAD_PAIR in calls
    assert (
        DeadEdge(
            frozenset({"start"}),
            "opaque-b",
            "PRECONDITION_REFUSED",
            ("receipt:0:opaque-b",),
            "h1",
        )
        in result.dead_edges
    )
    assert len(result.dead_edges) == result.rejected_probes


def test_same_hypothesis_suppresses_reprobe_without_spending_budget() -> None:
    run1, _ = _run("h1")
    run2, calls2 = _run("h1", prior=run1.dead_edges)
    assert run2.plan == run1.plan
    assert run2.probes < run1.probes
    assert run2.suppressed_reprobes == len(run1.dead_edges)
    assert DEAD_PAIR not in calls2
    assert run2.dead_edges == ()


def test_new_hypothesis_reopens_dead_edge() -> None:
    run1, _ = _run("h1")
    run3, calls3 = _run("h2", prior=run1.dead_edges)
    assert run3.suppressed_reprobes == 0
    assert DEAD_PAIR in calls3
    assert run3.probes == run1.probes


def test_ledger_digest_is_order_independent_and_content_sensitive() -> None:
    run1, _ = _run("h1")
    run2, _ = _run("h1", prior=run1.dead_edges)
    forward = DeadEdgeLedger(run1.dead_edges)
    reverse = DeadEdgeLedger(tuple(reversed(run1.dead_edges)))
    assert forward.digest() == reverse.digest()
    assert forward.digest() == ledger_digest(forward)
    assert DeadEdgeLedger(run2.dead_edges).digest() != forward.digest()
    assert forward.contains(*DEAD_PAIR, "h1")
    assert not forward.contains(*DEAD_PAIR, "h2")
    assert forward.under("h2").edges == ()
    assert forward.under("h1") == forward


def test_falsifiers_refuse_unreceipted_and_unhypothesized_edges() -> None:
    with pytest.raises(ValueError, match="UNRECEIPTED_DEAD_EDGE_REFUSED"):
        DeadEdge(frozenset({"start"}), "opaque-b", "REFUSED", (), "h1")
    with pytest.raises(ValueError, match="DEAD_EDGE_HYPOTHESIS_REQUIRED"):
        DeadEdge(frozenset({"start"}), "opaque-b", "REFUSED", ("r",), "")
    edge = DeadEdge(frozenset({"start"}), "opaque-b", "REFUSED", ("r",), "h1")
    with pytest.raises(ValueError, match="DISCOVERY_DEAD_EDGES_REQUIRE_HYPOTHESIS"):
        DiscoveryChallenge(
            subject="held-out/task",
            initial_facts=frozenset({"start"}),
            goal_facts=frozenset({"done"}),
            action_ids=("opaque-a",),
            prior_dead_edges=(edge,),
        )
