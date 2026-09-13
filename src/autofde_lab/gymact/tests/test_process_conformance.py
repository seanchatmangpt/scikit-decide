"""Chicago-style: a real GymActKernel episode, replayed against the real
declared lifecycle by a real ConformanceChecker.

No mocked event source -- the event log is the kernel's own real `EventLog`,
populated by real kernel-method calls in this test.
"""

from __future__ import annotations

from autofde_lab.gymact.kernel import GymActKernel
from autofde_lab.gymact.process import ConformanceChecker


def test_a_full_real_episode_replays_conformant() -> None:
    kernel = GymActKernel()
    episode_id = "episode-conformant-1"

    kernel.discover(subject="cloudgoat", episode_id=episode_id)
    kernel.materialize(subject="cloudgoat", episode_id=episode_id)
    kernel.configure(subject="cloudgoat", episode_id=episode_id)
    kernel.reset(subject="cloudgoat", episode_id=episode_id)
    kernel.start(subject="cloudgoat", episode_id=episode_id)
    kernel.observe(subject="cloudgoat", episode_id=episode_id)
    kernel.act(subject="cloudgoat", episode_id=episode_id, payload={})
    kernel.observe(subject="cloudgoat", episode_id=episode_id)
    kernel.verify(subject="cloudgoat", episode_id=episode_id)
    kernel.score(subject="cloudgoat", episode_id=episode_id)
    kernel.teardown(subject="cloudgoat", episode_id=episode_id)

    events = kernel.event_log.events_for_episode(episode_id)
    result = ConformanceChecker().check(events)

    assert result.conformant is True
    assert result.deviations == []


def test_calling_act_before_start_is_named_as_an_illegal_transition() -> None:
    kernel = GymActKernel()
    episode_id = "episode-illegal-1"

    kernel.discover(subject="cloudgoat", episode_id=episode_id)
    kernel.act(subject="cloudgoat", episode_id=episode_id, payload={})

    events = kernel.event_log.events_for_episode(episode_id)
    result = ConformanceChecker().check(events)

    assert result.conformant is False
    assert len(result.deviations) == 1
    deviation = result.deviations[0]
    assert deviation.from_activity == "discover"
    assert deviation.to_activity == "act"
    assert "not a legal successor" in deviation.reason
