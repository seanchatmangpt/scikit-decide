"""Evidence-bounded role-conditioned planner league.

This module constructs candidate experiment portfolios. It does not actuate a
gym and it does not confer authority on a planner. Executed outcomes only enter
the payoff hypergraph when an external GymAct execution receipt is supplied.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from math import fsum
from typing import Any, Iterable, Mapping, Sequence

from .catalog import (
    BUDGETS,
    NOVELTY_ORACLES,
    OBSERVATION_PROJECTIONS,
    PRIMARY_PLANNERS,
    ROLE_SPECS,
    WORLD_CLASSES,
)


class CompatibilityStanding(str, Enum):
    COMPATIBLE = "COMPATIBLE"
    REFUSED = "REFUSED"
    UNSUPPORTED = "UNSUPPORTED"


@dataclass(frozen=True, slots=True)
class CompatibilityResult:
    planner_id: str
    role_id: str
    standing: CompatibilityStanding
    reason: str

    @property
    def compatible(self) -> bool:
        return self.standing is CompatibilityStanding.COMPATIBLE


@dataclass(frozen=True, slots=True)
class PolicySpec:
    planner_id: str
    parameters: tuple[tuple[str, Any], ...] = ()
    objective_id: str = ""
    observation_projection_id: str = "full_observation"
    action_projection_id: str = "candidate_plan"
    budget_id: str = "balanced"

    @classmethod
    def for_role(
        cls,
        planner_id: str,
        role_id: str,
        *,
        parameters: Mapping[str, Any] | None = None,
        observation_projection_id: str = "full_observation",
        budget_id: str = "balanced",
    ) -> "PolicySpec":
        try:
            role = ROLE_SPECS[role_id]
        except KeyError as exc:
            raise ValueError(f"REFUSED:UNKNOWN_ROLE:{role_id}") from exc
        if observation_projection_id not in OBSERVATION_PROJECTIONS:
            raise ValueError(
                f"REFUSED:UNKNOWN_OBSERVATION_PROJECTION:{observation_projection_id}"
            )
        if budget_id not in BUDGETS:
            raise ValueError(f"REFUSED:UNKNOWN_BUDGET:{budget_id}")
        return cls(
            planner_id=planner_id,
            parameters=tuple(sorted((parameters or {}).items())),
            objective_id=role["objective"],
            observation_projection_id=observation_projection_id,
            action_projection_id=role["action_projection"],
            budget_id=budget_id,
        )


@dataclass(frozen=True, slots=True)
class LeagueMatch:
    world_id: str
    left_role_id: str
    left_policy: PolicySpec
    right_role_id: str
    right_policy: PolicySpec
    information_partition_id: str = "shared"
    authority_context_ref: str | None = None

    def __post_init__(self) -> None:
        if self.world_id not in WORLD_CLASSES:
            raise ValueError(f"REFUSED:UNKNOWN_WORLD:{self.world_id}")
        for role_id in (self.left_role_id, self.right_role_id):
            if role_id not in ROLE_SPECS:
                raise ValueError(f"REFUSED:UNKNOWN_ROLE:{role_id}")

    @property
    def identity_sha256(self) -> str:
        """Stable experiment identity, explicitly not an execution receipt."""
        return hashlib.sha256(self._canonical_json().encode("utf-8")).hexdigest()

    def _canonical_json(self) -> str:
        return json.dumps(
            {
                "world_id": self.world_id,
                "left_role_id": self.left_role_id,
                "left_policy": {
                    "planner_id": self.left_policy.planner_id,
                    "parameters": self.left_policy.parameters,
                    "objective_id": self.left_policy.objective_id,
                    "observation_projection_id": self.left_policy.observation_projection_id,
                    "action_projection_id": self.left_policy.action_projection_id,
                    "budget_id": self.left_policy.budget_id,
                },
                "right_role_id": self.right_role_id,
                "right_policy": {
                    "planner_id": self.right_policy.planner_id,
                    "parameters": self.right_policy.parameters,
                    "objective_id": self.right_policy.objective_id,
                    "observation_projection_id": self.right_policy.observation_projection_id,
                    "action_projection_id": self.right_policy.action_projection_id,
                    "budget_id": self.right_policy.budget_id,
                },
                "information_partition_id": self.information_partition_id,
                "authority_context_ref": self.authority_context_ref,
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    def as_gymact_candidate(self) -> dict[str, Any]:
        """Construct a transport-neutral candidate; does not execute it."""
        return {
            "schema_version": 1,
            "experiment_kind": "role_conditioned_planner_cross_play",
            "experiment_identity_sha256": self.identity_sha256,
            "world_id": self.world_id,
            "information_partition_id": self.information_partition_id,
            "authority_context_ref": self.authority_context_ref,
            "players": [
                {
                    "side": "left",
                    "role_id": self.left_role_id,
                    "planner_id": self.left_policy.planner_id,
                    "objective_id": self.left_policy.objective_id,
                    "observation_projection_id": self.left_policy.observation_projection_id,
                    "action_projection_id": self.left_policy.action_projection_id,
                    "budget_id": self.left_policy.budget_id,
                    "parameters": dict(self.left_policy.parameters),
                },
                {
                    "side": "right",
                    "role_id": self.right_role_id,
                    "planner_id": self.right_policy.planner_id,
                    "objective_id": self.right_policy.objective_id,
                    "observation_projection_id": self.right_policy.observation_projection_id,
                    "action_projection_id": self.right_policy.action_projection_id,
                    "budget_id": self.right_policy.budget_id,
                    "parameters": dict(self.right_policy.parameters),
                },
            ],
        }


@dataclass(frozen=True, slots=True)
class NoveltyRequest:
    role_id: str
    checked_planners: tuple[str, ...]
    refusal_reasons: tuple[str, ...]
    allowed_oracles: tuple[str, ...] = NOVELTY_ORACLES


class PlannerLeague:
    """Primary population and compatibility/manufacture operations."""

    def __init__(self, planners: Iterable[str] | None = None) -> None:
        population = tuple(planners) if planners is not None else PRIMARY_PLANNERS
        if any(p in NOVELTY_ORACLES for p in population):
            raise ValueError("REFUSED:LLM_NOVELTY_BOUNDARY")
        self.planners = population

    def compatibility(
        self, domain: Any, planner_id: str, role_id: str
    ) -> CompatibilityResult:
        if planner_id in NOVELTY_ORACLES:
            return CompatibilityResult(
                planner_id,
                role_id,
                CompatibilityStanding.REFUSED,
                "REFUSED:LLM_NOVELTY_BOUNDARY",
            )
        if planner_id not in self.planners:
            return CompatibilityResult(
                planner_id,
                role_id,
                CompatibilityStanding.UNSUPPORTED,
                "UNSUPPORTED:UNKNOWN_PLANNER",
            )
        if role_id not in ROLE_SPECS:
            return CompatibilityResult(
                planner_id,
                role_id,
                CompatibilityStanding.REFUSED,
                "REFUSED:UNKNOWN_ROLE",
            )

        # Lazy import keeps league construction independent of optional solver extras.
        from autofde_lab.utils import load_registered_solver

        solver_type = load_registered_solver(planner_id)
        if solver_type is None:
            return CompatibilityResult(
                planner_id,
                role_id,
                CompatibilityStanding.UNSUPPORTED,
                "UNSUPPORTED:PLANNER_LOAD_FAILED",
            )
        try:
            compatible = bool(solver_type.check_domain(domain))
        except Exception as exc:
            return CompatibilityResult(
                planner_id,
                role_id,
                CompatibilityStanding.UNSUPPORTED,
                f"UNSUPPORTED:DOMAIN_CHECK_FAILED:{type(exc).__name__}",
            )
        if not compatible:
            return CompatibilityResult(
                planner_id,
                role_id,
                CompatibilityStanding.REFUSED,
                "REFUSED:DOMAIN_CONTRACT_MISMATCH",
            )
        return CompatibilityResult(
            planner_id,
            role_id,
            CompatibilityStanding.COMPATIBLE,
            "COMPATIBLE:DOMAIN_CONTRACT",
        )

    def population_compatibility(
        self, domain: Any, role_id: str
    ) -> tuple[CompatibilityResult, ...]:
        return tuple(self.compatibility(domain, p, role_id) for p in self.planners)

    @staticmethod
    def novelty_frontier(
        results: Sequence[CompatibilityResult],
    ) -> NoveltyRequest | None:
        """Open novelty only after a complete, known refusal frontier.

        UNSUPPORTED is evidence of an unavailable/unknown edge, not proof that the
        registered planner population cannot solve the admitted subject.
        """
        if not results:
            return None
        if any(r.standing is CompatibilityStanding.COMPATIBLE for r in results):
            return None
        if any(r.standing is CompatibilityStanding.UNSUPPORTED for r in results):
            return None
        return NoveltyRequest(
            role_id=results[0].role_id,
            checked_planners=tuple(r.planner_id for r in results),
            refusal_reasons=tuple(r.reason for r in results),
        )

    @staticmethod
    def cover_cross_play(
        left: Sequence[CompatibilityResult],
        right: Sequence[CompatibilityResult],
        *,
        world_id: str,
        left_role_id: str,
        right_role_id: str,
        rounds: int = 3,
        observation_projection_id: str = "full_observation",
        budget_id: str = "balanced",
    ) -> tuple[LeagueMatch, ...]:
        """Deterministic covering schedule over admitted edges, not an N² sweep."""
        if rounds < 1:
            raise ValueError("REFUSED:ROUNDS_MUST_BE_POSITIVE")
        left_ids = tuple(r.planner_id for r in left if r.compatible)
        right_ids = tuple(r.planner_id for r in right if r.compatible)
        if not left_ids or not right_ids:
            return ()

        matches: list[LeagueMatch] = []
        seen: set[tuple[str, str]] = set()
        max_rounds = min(rounds, len(right_ids))
        for i, left_id in enumerate(left_ids):
            for shift in range(max_rounds):
                right_id = right_ids[(i + shift) % len(right_ids)]
                edge = (left_id, right_id)
                if edge in seen:
                    continue
                seen.add(edge)
                matches.append(
                    LeagueMatch(
                        world_id=world_id,
                        left_role_id=left_role_id,
                        left_policy=PolicySpec.for_role(
                            left_id,
                            left_role_id,
                            observation_projection_id=observation_projection_id,
                            budget_id=budget_id,
                        ),
                        right_role_id=right_role_id,
                        right_policy=PolicySpec.for_role(
                            right_id,
                            right_role_id,
                            observation_projection_id=observation_projection_id,
                            budget_id=budget_id,
                        ),
                    )
                )
        return tuple(matches)


@dataclass(frozen=True, slots=True)
class PayoffObservation:
    match: LeagueMatch
    left_score: float
    right_score: float
    receipt_id: str
    execution_observed: bool = True

    def __post_init__(self) -> None:
        if not self.execution_observed or not self.receipt_id.strip():
            raise ValueError("REFUSED:UNRECEIPTED_PAYOFF")


@dataclass(slots=True)
class PayoffHypergraph:
    """Empirical planner competence edges; no global speculative leaderboard."""

    observations: list[PayoffObservation] = field(default_factory=list)

    def add(self, observation: PayoffObservation) -> None:
        # `PayoffObservation.__post_init__` is the receipted-execution gate;
        # this isinstance check is what actually makes it the *only* door.
        # Found by the V2030.1.1 cap 1 adversarial refute pass (#114):
        # `add()` accepted a `LeagueSolveOutcome` (candidate-plan evidence,
        # deliberately never a `PayoffObservation`) silently, and only
        # failed later, downstream, in `_scores()` with an unrelated
        # `AttributeError: 'LeagueSolveOutcome' object has no attribute
        # 'match'` -- a second, unguarded door into this hypergraph.
        if not isinstance(observation, PayoffObservation):
            raise TypeError(
                f"REFUSED:PAYOFF_HYPERGRAPH_REQUIRES_PAYOFF_OBSERVATION:{type(observation).__name__}"
            )
        self.observations.append(observation)

    def _scores(
        self,
        *,
        planner_id: str,
        role_id: str,
        opponent_id: str,
        opponent_role_id: str,
        world_id: str,
        observation_projection_id: str,
        budget_id: str,
    ) -> list[float]:
        out: list[float] = []
        for obs in self.observations:
            m = obs.match
            if (
                m.left_policy.planner_id == planner_id
                and m.left_role_id == role_id
                and m.right_policy.planner_id == opponent_id
                and m.right_role_id == opponent_role_id
                and m.world_id == world_id
                and m.left_policy.observation_projection_id == observation_projection_id
                and m.left_policy.budget_id == budget_id
            ):
                out.append(obs.left_score)
        return out

    def empirical_best_response(
        self,
        *,
        candidates: Iterable[str],
        opponent_mixture: Mapping[str, float],
        role_id: str,
        opponent_role_id: str,
        world_id: str,
        observation_projection_id: str = "full_observation",
        budget_id: str = "balanced",
    ) -> str | None:
        """Return best response only where every positive-weight edge is observed."""
        positive = {p: w for p, w in opponent_mixture.items() if w > 0.0}
        if not positive:
            return None

        best: tuple[float, str] | None = None
        for planner_id in candidates:
            weighted: list[float] = []
            missing = False
            for opponent_id, weight in positive.items():
                scores = self._scores(
                    planner_id=planner_id,
                    role_id=role_id,
                    opponent_id=opponent_id,
                    opponent_role_id=opponent_role_id,
                    world_id=world_id,
                    observation_projection_id=observation_projection_id,
                    budget_id=budget_id,
                )
                if not scores:
                    missing = True
                    break
                weighted.append(weight * (fsum(scores) / len(scores)))
            if missing:
                continue
            value = fsum(weighted) / fsum(positive.values())
            key = (value, planner_id)
            if best is None or key > best:
                best = key
        return None if best is None else best[1]


class MetaSelector:
    """Evidence-bounded per-step planner selector (mixture-of-experts boundary)."""

    def __init__(self, payoffs: PayoffHypergraph) -> None:
        self.payoffs = payoffs

    def select(
        self,
        *,
        candidates: Iterable[str],
        opponent_mixture: Mapping[str, float],
        role_id: str,
        opponent_role_id: str,
        world_id: str,
        observation_projection_id: str,
        budget_id: str,
    ) -> str | None:
        return self.payoffs.empirical_best_response(
            candidates=candidates,
            opponent_mixture=opponent_mixture,
            role_id=role_id,
            opponent_role_id=opponent_role_id,
            world_id=world_id,
            observation_projection_id=observation_projection_id,
            budget_id=budget_id,
        )
