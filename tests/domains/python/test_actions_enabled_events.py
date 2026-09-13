# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style (real collaborators, state-based assertions) coverage for
Actions._get_enabled_events_from(), exercised through the real, already-existing
`restricted_action_maze` domain (no mocks) rather than a hand-rolled minimal stub.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "solvers" / "python" / "openevolve"))

from restricted_action_maze import Maze  # noqa: E402


def test_get_enabled_events_matches_applicable_actions_on_real_maze_domain():
    domain = Maze()
    memory = domain.get_initial_state()

    enabled_events = domain.get_enabled_events(memory)
    applicable_actions = domain.get_applicable_actions(memory)

    # get_enabled_events() must delegate to the real applicable-actions logic for a
    # domain that only handles Actions (controllable events) -- not silently return
    # an EmptySpace().
    assert set(enabled_events.get_elements()) == set(applicable_actions.get_elements())
    assert len(enabled_events.get_elements()) > 0


def test_is_enabled_event_agrees_with_is_applicable_action_on_real_maze_domain():
    domain = Maze()
    memory = domain.get_initial_state()

    for action in domain.get_action_space().get_elements():
        assert domain.is_enabled_event(action, memory) == domain.is_applicable_action(
            action, memory
        )
