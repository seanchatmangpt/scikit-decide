"""Evidence-bounded policy-space response oracle for the planner league.

PSRO here is a SELECT-only empirical mixture controller. It consumes only
receipt-admitted payoff edges from :class:`PayoffHypergraph`, never executes a
planner or gym, and never manufactures authority. Missing payoff closure is a
typed refusal rather than an invitation to interpolate or guess.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from math import fsum
from typing import Iterable

from .core import PayoffHypergraph


@dataclass(frozen=True, slots=True)
class PsroState:
    """Immutable empirical meta-strategy state."""

    population: tuple[str, ...]
    counts: tuple[tuple[str, int], ...]
    iteration: int = 0

    def __post_init__(self) -> None:
        if not self.population:
            raise ValueError("REFUSED:PSRO_EMPTY_POPULATION")
        if len(set(self.population)) != len(self.population):
            raise ValueError("REFUSED:PSRO_DUPLICATE_POPULATION")
        count_map = dict(self.counts)
        if set(count_map) != set(self.population):
            raise ValueError("REFUSED:PSRO_COUNT_DOMAIN_MISMATCH")
        if any(value < 1 for value in count_map.values()):
            raise ValueError("REFUSED:PSRO_NONPOSITIVE_COUNT")
        if self.iteration < 0:
            raise ValueError("REFUSED:PSRO_NEGATIVE_ITERATION")

    @classmethod
    def seed(cls, population: Iterable[str]) -> "PsroState":
        """Create a deterministic uniform empirical seed over unique planners."""
        ordered = tuple(dict.fromkeys(population))
        if not ordered:
            raise ValueError("REFUSED:PSRO_EMPTY_POPULATION")
        return cls(
            population=ordered,
            counts=tuple((planner_id, 1) for planner_id in ordered),
        )

    @property
    def mixture(self) -> dict[str, float]:
        """Return the normalized empirical meta-strategy."""
        count_map = dict(self.counts)
        total = fsum(count_map.values())
        return {
            planner_id: count_map[planner_id] / total for planner_id in self.population
        }


@dataclass(frozen=True, slots=True)
class PsroReceipt:
    """Deterministic SELECT receipt for one empirical PSRO step."""

    iteration: int
    prior_population: tuple[str, ...]
    prior_mixture: tuple[tuple[str, float], ...]
    selected_best_response: str
    next_population: tuple[str, ...]
    next_mixture: tuple[tuple[str, float], ...]
    claim_ceiling: str = "EMPIRICAL_META_SELECTION_ONLY"
    do_authority: bool = False

    @property
    def identity_sha256(self) -> str:
        """Bind the exact SELECT transition without implying execution standing."""
        payload = json.dumps(
            {
                "iteration": self.iteration,
                "prior_population": self.prior_population,
                "prior_mixture": self.prior_mixture,
                "selected_best_response": self.selected_best_response,
                "next_population": self.next_population,
                "next_mixture": self.next_mixture,
                "claim_ceiling": self.claim_ceiling,
                "do_authority": self.do_authority,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class PsroStep:
    """Result of attempting one evidence-bounded PSRO iteration."""

    state: PsroState
    receipt: PsroReceipt | None
    standing: str
    reason: str

    @property
    def advanced(self) -> bool:
        """Whether the empirical state advanced under complete observed payoffs."""
        return self.receipt is not None


class PolicySpaceResponseOracle:
    """Receipt-gated empirical PSRO controller with zero actuation authority."""

    def __init__(
        self,
        payoffs: PayoffHypergraph,
        *,
        role_id: str,
        opponent_role_id: str,
        world_id: str,
        observation_projection_id: str = "full_observation",
        budget_id: str = "balanced",
    ) -> None:
        self.payoffs = payoffs
        self.role_id = role_id
        self.opponent_role_id = opponent_role_id
        self.world_id = world_id
        self.observation_projection_id = observation_projection_id
        self.budget_id = budget_id

    def step(self, state: PsroState, *, candidates: Iterable[str]) -> PsroStep:
        """Advance once only when every positive-weight payoff edge is observed."""
        candidate_ids = tuple(dict.fromkeys(candidates))
        if not candidate_ids:
            return PsroStep(
                state=state,
                receipt=None,
                standing="REFUSED",
                reason="REFUSED:PSRO_EMPTY_CANDIDATES",
            )

        best_response = self.payoffs.empirical_best_response(
            candidates=candidate_ids,
            opponent_mixture=state.mixture,
            role_id=self.role_id,
            opponent_role_id=self.opponent_role_id,
            world_id=self.world_id,
            observation_projection_id=self.observation_projection_id,
            budget_id=self.budget_id,
        )
        if best_response is None:
            return PsroStep(
                state=state,
                receipt=None,
                standing="REFUSED",
                reason="REFUSED:PSRO_MISSING_PAYOFF_CLOSURE",
            )

        prior_mixture = tuple(state.mixture.items())
        next_population = state.population
        count_map = dict(state.counts)
        if best_response not in count_map:
            next_population = (*state.population, best_response)
            count_map[best_response] = 1
        else:
            count_map[best_response] += 1
        next_state = PsroState(
            population=next_population,
            counts=tuple(
                (planner_id, count_map[planner_id]) for planner_id in next_population
            ),
            iteration=state.iteration + 1,
        )
        receipt = PsroReceipt(
            iteration=next_state.iteration,
            prior_population=state.population,
            prior_mixture=prior_mixture,
            selected_best_response=best_response,
            next_population=next_state.population,
            next_mixture=tuple(next_state.mixture.items()),
        )
        return PsroStep(
            state=next_state,
            receipt=receipt,
            standing="ALIVE",
            reason="ALIVE:EMPIRICAL_PSRO_STEP",
        )
