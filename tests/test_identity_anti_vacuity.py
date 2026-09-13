# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Anti-vacuity guards for the identity surfaces a rename can silently break.

`importlib.metadata.entry_points(group=...)` returns an empty collection for
an unknown group rather than raising. A stale entry-point group name after a
partial rename therefore degrades to "zero domains, zero solvers" with no
error anywhere in the stack -- a valid-looking, capability-less system. These
tests pin the live counts so that degradation fails loudly instead.

As of this commit Phase 4 has landed: the live package is `autofde_lab` and
the entry-point GROUP names are `autofde_lab.domains` /
`autofde_lab.solvers`. These assert against the PRIMARY group constants in
tests/project_identity.py; the counts did not change across the rename. A
third test pins the other half of the same invariant -- that the legacy
groups are genuinely gone from pyproject.toml rather than left behind as a
duplicate registry that would double every count.
"""

from __future__ import annotations

import importlib.metadata
import pathlib

from project_identity import (
    DOMAIN_ENTRYPOINT_GROUP,
    EXPECTED_DOMAIN_COUNT,
    EXPECTED_SOLVER_COUNT,
    LEGACY_DOMAIN_ENTRYPOINT_GROUP,
    LEGACY_SOLVER_ENTRYPOINT_GROUP,
    SOLVER_ENTRYPOINT_GROUP,
)

_PYPROJECT = pathlib.Path(__file__).resolve().parents[1] / "pyproject.toml"


def _entries(group: str):
    return list(importlib.metadata.entry_points(group=group))


def test_domain_registry_is_not_silently_empty():
    entries = _entries(DOMAIN_ENTRYPOINT_GROUP)
    assert entries, (
        f"entry-point group {DOMAIN_ENTRYPOINT_GROUP!r} returned zero "
        "entries -- either the group name is stale or pyproject.toml drifted"
    )
    assert len(entries) == EXPECTED_DOMAIN_COUNT, (
        f"expected {EXPECTED_DOMAIN_COUNT} domains, found {len(entries)}: "
        f"{sorted(e.name for e in entries)}"
    )


def test_solver_registry_is_not_silently_empty():
    entries = _entries(SOLVER_ENTRYPOINT_GROUP)
    assert entries, (
        f"entry-point group {SOLVER_ENTRYPOINT_GROUP!r} returned zero "
        "entries -- either the group name is stale or pyproject.toml drifted"
    )
    assert len(entries) == EXPECTED_SOLVER_COUNT, (
        f"expected {EXPECTED_SOLVER_COUNT} solvers, found {len(entries)}: "
        f"{sorted(e.name for e in entries)}"
    )


def test_get_registered_domains_matches_the_entrypoint_count():
    from autofde_lab.utils import get_registered_domains

    domains = get_registered_domains()
    assert domains, "get_registered_domains() returned nothing"
    assert len(domains) == EXPECTED_DOMAIN_COUNT


def test_get_registered_solvers_matches_the_entrypoint_count():
    from autofde_lab.utils import get_registered_solvers

    solvers = get_registered_solvers()
    assert solvers, "get_registered_solvers() returned nothing"
    assert len(solvers) == EXPECTED_SOLVER_COUNT


def test_legacy_entrypoint_groups_are_absent_from_pyproject():
    """The other half of the anti-vacuity invariant.

    Flipping the consumers to the new group names while leaving the old
    ``[project.entry-points."skdecide.*"]`` tables in pyproject.toml would
    pass every count assertion above and still ship a duplicate registry.
    Assert the legacy tables are gone, not merely unused.
    """
    text = _PYPROJECT.read_text()
    for legacy in (LEGACY_DOMAIN_ENTRYPOINT_GROUP, LEGACY_SOLVER_ENTRYPOINT_GROUP):
        header = f'[project.entry-points."{legacy}"]'
        assert header not in text, (
            f"pyproject.toml still declares the legacy entry-point table "
            f"{header} -- Phase 4 renamed the consumers but left the registry"
        )
    for primary in (DOMAIN_ENTRYPOINT_GROUP, SOLVER_ENTRYPOINT_GROUP):
        header = f'[project.entry-points."{primary}"]'
        assert header in text, f"pyproject.toml is missing {header}"
