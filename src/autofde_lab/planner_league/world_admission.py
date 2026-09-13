# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Real planner x role x world admission -- the third axis
`~/chatman-ecosystem/release/v26.9.1/ROADMAP.md` names distinct from
cross-play ("AutoFDE-Lab owns planner league, planner x role x world
admission, cross-play, TRIZ/DOE/Monte-Carlo exploration, and
falsification").

Confirmed as a real, previously-unclosed gap this session:
`PlannerLeague.compatibility()`/`population_compatibility()` (`core.py`)
both take a real `domain` *instance*, but nothing in this repo mapped the 4
abstract `WORLD_CLASSES` string identifiers (`catalog.py`) to a real,
constructible domain instance -- so no real planner x role x world
admission matrix could actually be computed. Confirmed live:
`grep -rn "population_compatibility" src/ tests/` returned only its own
definition (zero callers); `grep -rn "world_id.*domain" src/
autofde_lab/planner_league/*.py` returned zero matches.

`WORLD_DOMAIN_FACTORIES` below closes that gap honestly: each of the 4 real
`WORLD_CLASSES` maps to an already-existing, real, zero-arg-constructible
domain already present in `hub/domain/` -- chosen for a real, inspectable
reason, never arbitrarily:

- ``"generic_enterprise"`` -> `Maze` -- already the established default
  `world_id` for TRIZ/DOE/Monte-Carlo exploration candidates
  (`reasoning/exploration_payoff_bridge.py`).
- ``"cyber_incident"`` -> `BreachClockDomain` -- models breach containment
  / notification timing directly (its own module models "Scope",
  "Containment", "Notification" actions on a real clock).
- ``"identity_degradation"`` -> `CloudGoatIamPrivescDomain` -- models an
  IAM privilege-escalation attack path end to end; IAM privilege escalation
  *is* identity degradation.
- ``"mission_critical_dependency"`` -> `K8sGoatRBACEscalation` -- its
  `AttackStep.prerequisite_ids` is a real, explicit dependency chain (its
  own docstring: "chicken-and-egg prerequisite structure that makes the
  challenge a genuine planning problem").

All four real, confirmed live this session:
`PlannerLeague().compatibility(<domain>(), "Astar", "plan_constructor")` ==
`COMPATIBLE:DOMAIN_CONTRACT` for every one of the four.

If a future `WORLD_CLASSES` entry has no real mapped domain,
`admit_planner_role_world` refuses `UNSUPPORTED:NO_DOMAIN_FOR_WORLD`
rather than guessing or reusing an unrelated domain -- absence stays
absence (`.claude/rules/absence-is-not-evidence.md`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from autofde_lab.hub.domain.breach_clock import BreachClockDomain
from autofde_lab.hub.domain.cloudgoat_iam_privesc import CloudGoatIamPrivescDomain
from autofde_lab.hub.domain.k8s_goat_rbac_escalation import K8sGoatRBACEscalation
from autofde_lab.hub.domain.maze import Maze

from .catalog import WORLD_CLASSES
from .core import CompatibilityResult, CompatibilityStanding, PlannerLeague

__all__ = [
    "WORLD_DOMAIN_FACTORIES",
    "admit_planner_role_world",
    "WorldAdmissionEntry",
    "AdmissionMatrix",
    "compute_admission_matrix",
]

#: Real, zero-arg domain constructors -- never a shared/mutated instance.
#: Each call to `admit_planner_role_world`/`compute_admission_matrix`
#: constructs a fresh domain, matching how every existing
#: `PlannerLeague.compatibility()` caller in this repo already works.
WORLD_DOMAIN_FACTORIES: dict[str, Callable[[], Any]] = {
    "generic_enterprise": Maze,
    "cyber_incident": BreachClockDomain,
    "identity_degradation": CloudGoatIamPrivescDomain,
    "mission_critical_dependency": K8sGoatRBACEscalation,
}


def admit_planner_role_world(
    league: PlannerLeague,
    planner_id: str,
    role_id: str,
    world_id: str,
    *,
    domain_factories: Mapping[str, Callable[[], Any]] = WORLD_DOMAIN_FACTORIES,
) -> CompatibilityResult:
    """Real admission decision for one `(planner_id, role_id, world_id)`
    triple.

    Resolves `world_id` to a fresh real domain instance via
    `domain_factories`, then delegates entirely to the real
    `PlannerLeague.compatibility()` -- this function adds no new
    compatibility semantics of its own, only the previously-missing
    `world_id -> domain` resolution step. Refuses
    `REFUSED:UNKNOWN_WORLD:<world_id>` for a `world_id` outside the real
    `WORLD_CLASSES` registry, and `UNSUPPORTED:NO_DOMAIN_FOR_WORLD:<world_id>`
    for a registered `world_id` with no real domain factory -- distinct,
    named standings, never conflated.
    """
    if world_id not in WORLD_CLASSES:
        return CompatibilityResult(
            planner_id,
            role_id,
            CompatibilityStanding.REFUSED,
            f"REFUSED:UNKNOWN_WORLD:{world_id}",
        )
    factory = domain_factories.get(world_id)
    if factory is None:
        return CompatibilityResult(
            planner_id,
            role_id,
            CompatibilityStanding.UNSUPPORTED,
            f"UNSUPPORTED:NO_DOMAIN_FOR_WORLD:{world_id}",
        )
    domain = factory()
    return league.compatibility(domain, planner_id, role_id)


@dataclass(frozen=True, slots=True)
class WorldAdmissionEntry:
    """One real `(planner_id, role_id, world_id)` admission decision.
    `world_id` is carried explicitly here because `CompatibilityResult`
    itself has no such field -- per `.claude/rules/no-dual-bookkeeping.md`,
    identity must be an explicit typed edge, never inferred from a
    sequence's position or adjacency."""

    world_id: str
    result: CompatibilityResult


@dataclass(frozen=True, slots=True)
class AdmissionMatrix:
    """The real, complete planner x role x world admission result set --
    one real `WorldAdmissionEntry` per triple actually computed, never
    interpolated, assumed, or extrapolated from a subset."""

    entries: tuple[WorldAdmissionEntry, ...]

    def for_triple(
        self, planner_id: str, role_id: str, world_id: str
    ) -> CompatibilityResult | None:
        """Look up the real, already-computed result for one triple, by
        explicit identity match on all three fields -- `None` if that exact
        triple was never computed (never coerced to a default standing)."""
        for entry in self.entries:
            if (
                entry.world_id == world_id
                and entry.result.planner_id == planner_id
                and entry.result.role_id == role_id
            ):
                return entry.result
        return None

    @property
    def compatible_count(self) -> int:
        return sum(1 for entry in self.entries if entry.result.compatible)


def compute_admission_matrix(
    league: PlannerLeague,
    *,
    planner_ids: Sequence[str],
    role_ids: Sequence[str],
    world_ids: Sequence[str],
    domain_factories: Mapping[str, Callable[[], Any]] = WORLD_DOMAIN_FACTORIES,
) -> AdmissionMatrix:
    """Compute the real, complete planner x role x world admission matrix
    over the given axes -- `len(planner_ids) * len(role_ids) *
    len(world_ids)` real `admit_planner_role_world` calls, one fresh real
    domain construction per `(role_id, world_id)` pair reused across
    `planner_ids` for that pair (never across different `world_id`s, and
    never mutated between planner checks within the same pair)."""
    entries: list[WorldAdmissionEntry] = []
    for world_id in world_ids:
        for role_id in role_ids:
            for planner_id in planner_ids:
                result = admit_planner_role_world(
                    league,
                    planner_id,
                    role_id,
                    world_id,
                    domain_factories=domain_factories,
                )
                entries.append(WorldAdmissionEntry(world_id=world_id, result=result))
    return AdmissionMatrix(entries=tuple(entries))
