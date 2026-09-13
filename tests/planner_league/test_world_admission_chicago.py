# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for `world_admission` -- the real planner x role x
world admission matrix `~/chatman-ecosystem/release/v26.9.1/ROADMAP.md`
names distinct from cross-play.

Real collaborators throughout: real `Maze`/`BreachClockDomain`/
`CloudGoatIamPrivescDomain`/`K8sGoatRBACEscalation` domain instances, a
real `PlannerLeague` calling the real, installed `Astar`/`CIDual` solver
entry points' real `check_domain()`. No `unittest.mock` / `Mock` /
`MagicMock` / `patch` / `monkeypatch` anywhere in this file.

`Astar` is confirmed live (this session, real
`PlannerLeague().compatibility(<domain>(), "Astar", "plan_constructor")`
calls against all four real `WORLD_DOMAIN_FACTORIES` domains) to be
`COMPATIBLE` with every one of them; `CIDual` is confirmed live to be
`REFUSED:DOMAIN_CONTRACT_MISMATCH` against every one of them -- used below
for the real incompatible-planner path.
"""

from __future__ import annotations

from autofde_lab.planner_league import PlannerLeague
from autofde_lab.planner_league.catalog import WORLD_CLASSES
from autofde_lab.planner_league.core import CompatibilityStanding
from autofde_lab.planner_league.world_admission import (
    WORLD_DOMAIN_FACTORIES,
    AdmissionMatrix,
    admit_planner_role_world,
    compute_admission_matrix,
)


def test_world_domain_factories_cover_every_real_world_class() -> None:
    # No silent gap: every WORLD_CLASSES entry has a real mapped factory.
    assert set(WORLD_DOMAIN_FACTORIES) == set(WORLD_CLASSES)


def test_admit_planner_role_world_is_compatible_for_every_real_world() -> None:
    league = PlannerLeague()
    for world_id in WORLD_CLASSES:
        result = admit_planner_role_world(league, "Astar", "plan_constructor", world_id)
        assert result.standing == CompatibilityStanding.COMPATIBLE, (world_id, result.reason)
        assert result.compatible
        assert result.planner_id == "Astar"
        assert result.role_id == "plan_constructor"


def test_admit_planner_role_world_refuses_incompatible_planner_for_every_real_world() -> None:
    league = PlannerLeague()
    for world_id in WORLD_CLASSES:
        result = admit_planner_role_world(league, "CIDual", "plan_falsifier", world_id)
        assert result.standing == CompatibilityStanding.REFUSED, (world_id, result.reason)
        assert result.reason == "REFUSED:DOMAIN_CONTRACT_MISMATCH"
        assert not result.compatible


def test_admit_planner_role_world_refuses_unknown_world() -> None:
    league = PlannerLeague()
    result = admit_planner_role_world(league, "Astar", "plan_constructor", "not_a_real_world")
    assert result.standing == CompatibilityStanding.REFUSED
    assert result.reason == "REFUSED:UNKNOWN_WORLD:not_a_real_world"


def test_admit_planner_role_world_reports_unsupported_for_a_registered_world_missing_a_factory() -> None:
    league = PlannerLeague()
    reduced_factories = {
        world_id: factory
        for world_id, factory in WORLD_DOMAIN_FACTORIES.items()
        if world_id != "cyber_incident"
    }
    result = admit_planner_role_world(
        league, "Astar", "plan_constructor", "cyber_incident", domain_factories=reduced_factories
    )
    assert result.standing == CompatibilityStanding.UNSUPPORTED
    assert result.reason == "UNSUPPORTED:NO_DOMAIN_FOR_WORLD:cyber_incident"


def test_compute_admission_matrix_is_real_and_complete_over_the_full_axes() -> None:
    league = PlannerLeague()
    matrix = compute_admission_matrix(
        league,
        planner_ids=["Astar", "CIDual"],
        role_ids=["plan_constructor", "plan_falsifier"],
        world_ids=WORLD_CLASSES,
    )
    assert isinstance(matrix, AdmissionMatrix)
    # 2 planners * 2 roles * 4 worlds -- every triple actually computed,
    # never a subset extrapolated.
    assert len(matrix.entries) == 2 * 2 * len(WORLD_CLASSES)

    # Astar compatible for every (role, world) triple -> 2 * 4 = 8 real wins.
    astar_compatible = [
        e for e in matrix.entries if e.result.planner_id == "Astar" and e.result.compatible
    ]
    assert len(astar_compatible) == 2 * len(WORLD_CLASSES)

    # CIDual refused for every triple -> zero compatible entries.
    cidual_compatible = [
        e for e in matrix.entries if e.result.planner_id == "CIDual" and e.result.compatible
    ]
    assert cidual_compatible == []

    assert matrix.compatible_count == 2 * len(WORLD_CLASSES)

    # for_triple retrieves the exact real entry by explicit identity, never
    # by position -- confirm both a real hit and a real, honest miss.
    hit = matrix.for_triple("Astar", "plan_constructor", "cyber_incident")
    assert hit is not None
    assert hit.compatible

    miss = matrix.for_triple("Astar", "plan_constructor", "world_never_computed")
    assert miss is None
