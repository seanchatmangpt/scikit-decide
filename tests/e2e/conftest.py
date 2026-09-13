# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Shared fixtures/markers for tests/e2e.

Every test in this package is Chicago-school: it exercises real, registered
domains and solvers through skdecide.utils.load_registered_domain /
load_registered_solver / rollout, with no mocks or stubs anywhere. See
tests/test_self_play_chicago.py for the precedent this suite follows, and
docs/jtbd/end-to-end-testing.md for why this suite exists.
"""

import importlib.util

import pytest

requires_discrete_optimization = pytest.mark.skipif(
    importlib.util.find_spec("discrete_optimization") is None,
    reason="discrete-optimization (scikit-decide[solvers]/[all] extra) not installed",
)

requires_flight_planning_deps = pytest.mark.skipif(
    any(
        importlib.util.find_spec(mod) is None
        for mod in ("openap", "cartopy", "pygeodesy")
    ),
    reason="flight planning optional deps (scikit-decide[domains] extra) not installed",
)


def assert_real_rollout_produced_output(episodes):
    """Real, minimal shared assertion: a rollout call actually produced episodes.

    Domain-family-specific assertions (reward shape, makespan bounds, valid
    moves, ...) stay in each test file, per Chicago-school precedent -- this
    only guards against the generic "rollout silently returned nothing".
    """
    assert episodes is not None
    assert len(episodes) > 0
    for _observations, actions, values in episodes:
        assert len(actions) > 0
        assert len(values) > 0
