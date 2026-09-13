from __future__ import annotations

from dataclasses import dataclass, replace
from itertools import combinations, product
from math import prod
from typing import Iterable, Iterator, Mapping, Sequence

from .models import BasisChoice, BudgetPolicy, DecisionBasis


@dataclass(frozen=True, slots=True)
class CompatibilityRule:
    """Declarative compatibility law over DecisionBasis dimension names.

    A rule is active only when every pair in ``when`` matches. Once active,
    every pair in ``require`` must match and no pair in ``forbid`` may match.
    This keeps architecture constraints serializable and inspectable instead
    of hiding them in arbitrary Python predicates.
    """

    when: tuple[tuple[str, str], ...] = ()
    require: tuple[tuple[str, str], ...] = ()
    forbid: tuple[tuple[str, str], ...] = ()
    reason: str = ""

    @classmethod
    def from_mappings(
        cls,
        *,
        when: Mapping[str, str] | None = None,
        require: Mapping[str, str] | None = None,
        forbid: Mapping[str, str] | None = None,
        reason: str = "",
    ) -> "CompatibilityRule":
        return cls(
            when=tuple(sorted((when or {}).items())),
            require=tuple(sorted((require or {}).items())),
            forbid=tuple(sorted((forbid or {}).items())),
            reason=reason,
        )

    def allows(self, basis: DecisionBasis) -> bool:
        dims = basis.dimension_values()
        active = all(dims.get(key) == value for key, value in self.when)
        if not active:
            return True
        if any(dims.get(key) != value for key, value in self.require):
            return False
        if any(dims.get(key) == value for key, value in self.forbid):
            return False
        return True


@dataclass(frozen=True, slots=True)
class DecisionSpace:
    models: tuple[BasisChoice, ...]
    planners: tuple[BasisChoice, ...]
    tool_policies: tuple[BasisChoice, ...]
    repair_policies: tuple[BasisChoice, ...]
    replanning_policies: tuple[BasisChoice, ...]
    verification_policies: tuple[BasisChoice, ...]
    projection_policies: tuple[BasisChoice, ...]
    memory_policies: tuple[BasisChoice, ...]
    budgets: tuple[BudgetPolicy, ...]
    rules: tuple[CompatibilityRule, ...] = ()

    def __post_init__(self) -> None:
        for field_name in (
            "models",
            "planners",
            "tool_policies",
            "repair_policies",
            "replanning_policies",
            "verification_policies",
            "projection_policies",
            "memory_policies",
            "budgets",
        ):
            values = getattr(self, field_name)
            if not values:
                raise ValueError(
                    f"decision-space dimension {field_name} must be non-empty"
                )
            names = [value.name for value in values]
            if len(names) != len(set(names)):
                raise ValueError(
                    f"decision-space dimension {field_name} contains duplicate names"
                )
        self._validate_compatibility_rules()

    @property
    def upper_bound_size(self) -> int:
        return prod(len(values) for values in self.dimension_options().values())

    def dimension_options(
        self,
    ) -> dict[str, tuple[BasisChoice, ...] | tuple[BudgetPolicy, ...]]:
        return {
            "model": self.models,
            "planner": self.planners,
            "tool_policy": self.tool_policies,
            "repair_policy": self.repair_policies,
            "replanning_policy": self.replanning_policies,
            "verification_policy": self.verification_policies,
            "projection_policy": self.projection_policies,
            "memory_policy": self.memory_policies,
            "budget": self.budgets,
        }

    def _validate_compatibility_rules(self) -> None:
        options = self.dimension_options()
        for rule_index, rule in enumerate(self.rules):
            for clause_name in ("when", "require", "forbid"):
                pairs = getattr(rule, clause_name)
                seen: set[str] = set()
                for dimension, option_name in pairs:
                    if dimension not in options:
                        raise ValueError(
                            "REFUSED:UNKNOWN_COMPATIBILITY_DIMENSION:"
                            f"rule={rule_index}:{clause_name}:{dimension}"
                        )
                    if dimension in seen:
                        raise ValueError(
                            "REFUSED:DUPLICATE_COMPATIBILITY_DIMENSION:"
                            f"rule={rule_index}:{clause_name}:{dimension}"
                        )
                    seen.add(dimension)
                    admitted_names = {item.name for item in options[dimension]}
                    if option_name not in admitted_names:
                        raise ValueError(
                            "REFUSED:UNKNOWN_COMPATIBILITY_OPTION:"
                            f"rule={rule_index}:{clause_name}:{dimension}={option_name}"
                        )
            contradictions = set(rule.require) & set(rule.forbid)
            if contradictions:
                detail = ",".join(
                    f"{dimension}={option}"
                    for dimension, option in sorted(contradictions)
                )
                raise ValueError(
                    "REFUSED:CONTRADICTORY_COMPATIBILITY_RULE:"
                    f"rule={rule_index}:{detail}"
                )

    def is_lawful(self, basis: DecisionBasis) -> bool:
        options = self.dimension_options()
        for dimension in DecisionBasis.DIMENSIONS:
            value = getattr(basis, dimension)
            # Full value equality is intentional. Name-only admission would allow
            # a caller to smuggle different model parameters or budget limits
            # under the identity of an admitted option.
            if value not in options[dimension]:
                return False
        return all(rule.allows(basis) for rule in self.rules)

    def iter_decisions(self, *, limit: int | None = None) -> Iterator[DecisionBasis]:
        emitted = 0
        for values in product(
            self.models,
            self.planners,
            self.tool_policies,
            self.repair_policies,
            self.replanning_policies,
            self.verification_policies,
            self.projection_policies,
            self.memory_policies,
            self.budgets,
        ):
            basis = DecisionBasis(
                model=values[0],
                planner=values[1],
                tool_policy=values[2],
                repair_policy=values[3],
                replanning_policy=values[4],
                verification_policy=values[5],
                projection_policy=values[6],
                memory_policy=values[7],
                budget=values[8],
            )
            if not all(rule.allows(basis) for rule in self.rules):
                continue
            yield basis
            emitted += 1
            if limit is not None and emitted >= limit:
                return

    def materialize(
        self, *, candidate_limit: int = 100_000
    ) -> tuple[DecisionBasis, ...]:
        if candidate_limit <= 0:
            raise ValueError("candidate_limit must be > 0")
        decisions = tuple(self.iter_decisions(limit=candidate_limit + 1))
        if len(decisions) > candidate_limit:
            raise ValueError(
                f"REFUSED:ARCHITECTURE_SPACE_TOO_LARGE:{len(decisions)}>{candidate_limit}; "
                "add constraints or use a larger explicit candidate_limit"
            )
        return decisions

    def combinatorial_pairwise_candidates(
        self,
        *,
        baseline: DecisionBasis | None = None,
        candidate_limit: int = 100_000,
    ) -> tuple[DecisionBasis, ...]:
        """Build a polynomial second-order design without Cartesian materialization.

        The candidate basis is the current behavior plus every lawful one-factor
        and two-factor substitution around it. Its description cost is bounded
        by O(sum(k_i) + sum(k_i*k_j)), rather than O(product(k_i)).

        ``candidate_limit`` applies to this second-order design, not to the full
        architecture-space upper bound. If even the pairwise design is too large,
        refusal is explicit rather than silently dropping interaction coverage.
        """

        if candidate_limit <= 0:
            raise ValueError("candidate_limit must be > 0")
        if baseline is None:
            baseline = next(self.iter_decisions(limit=1), None)
            if baseline is None:
                raise ValueError("REFUSED:NO_LAWFUL_DECISION_BASIS")
        if not self.is_lawful(baseline):
            raise ValueError("baseline does not exist in the lawful DecisionSpace")

        options = self.dimension_options()
        by_digest: dict[str, DecisionBasis] = {baseline.digest: baseline}

        def admit(candidate: DecisionBasis) -> None:
            if not self.is_lawful(candidate):
                return
            by_digest.setdefault(candidate.digest, candidate)
            if len(by_digest) > candidate_limit:
                raise ValueError(
                    "REFUSED:PAIRWISE_DESIGN_TOO_LARGE:"
                    f"{len(by_digest)}>{candidate_limit}; reduce basis cardinality, "
                    "add compatibility laws, or raise the explicit candidate_limit"
                )

        for dimension in DecisionBasis.DIMENSIONS:
            for option in options[dimension]:
                admit(replace(baseline, **{dimension: option}))

        for left, right in combinations(DecisionBasis.DIMENSIONS, 2):
            for left_option in options[left]:
                for right_option in options[right]:
                    admit(
                        replace(
                            baseline,
                            **{left: left_option, right: right_option},
                        )
                    )

        return tuple(by_digest[key] for key in sorted(by_digest))

    def combinatorial_pairwise_covering(
        self,
        *,
        baseline: DecisionBasis | None = None,
        candidate_limit: int = 100_000,
        max_architectures: int | None = None,
    ) -> tuple[DecisionBasis, ...]:
        """Select a bounded deterministic covering design from the pairwise basis.

        ``max_architectures`` is an acceptance ceiling, not permission to return
        an incomplete design under a covering label. If the ceiling cannot cover
        every represented lawful pair token, the operation refuses explicitly.
        """

        candidates = self.combinatorial_pairwise_candidates(
            baseline=baseline,
            candidate_limit=candidate_limit,
        )
        seed = baseline
        if seed is None:
            seed = candidates[0]
        return pairwise_covering(
            candidates,
            max_architectures=max_architectures,
            seed=(seed,),
        )


def hamming_distance(left: DecisionBasis, right: DecisionBasis) -> int:
    lvals = left.dimension_values()
    rvals = right.dimension_values()
    return sum(lvals[key] != rvals[key] for key in DecisionBasis.DIMENSIONS)


def one_factor_at_a_time(
    decisions: Sequence[DecisionBasis], baseline: DecisionBasis
) -> tuple[DecisionBasis, ...]:
    chosen = [decision for decision in decisions if decision.digest == baseline.digest]
    chosen.extend(
        decision
        for decision in decisions
        if decision.digest != baseline.digest
        and hamming_distance(decision, baseline) == 1
    )
    if not chosen:
        raise ValueError("baseline does not exist in the lawful DecisionSpace")
    return (chosen[0], *sorted(chosen[1:], key=lambda item: item.digest))


def _pair_tokens(basis: DecisionBasis) -> frozenset[tuple[str, str, str, str]]:
    values = sorted(basis.dimension_values().items())
    return frozenset((a, av, b, bv) for (a, av), (b, bv) in combinations(values, 2))


def pairwise_covering(
    decisions: Sequence[DecisionBasis],
    *,
    max_architectures: int | None = None,
    seed: Sequence[DecisionBasis] = (),
) -> tuple[DecisionBasis, ...]:
    """Greedy deterministic pairwise covering selection.

    This is intentionally a bounded experimental-design primitive, not a claim
    of optimal minimum covering-array size. It preserves every pairwise
    interaction represented by the supplied lawful candidate set. A bound that
    is too small is a typed refusal, never silent loss of claimed coverage.
    """

    if not decisions:
        return ()
    if max_architectures is not None and max_architectures <= 0:
        raise ValueError("max_architectures must be > 0")

    by_digest = {decision.digest: decision for decision in decisions}
    token_map = {
        digest: _pair_tokens(decision) for digest, decision in by_digest.items()
    }
    uncovered = set().union(*(tokens for tokens in token_map.values()))
    remaining = dict(by_digest)
    selected: list[DecisionBasis] = []

    for item in unique_by_digest(seed):
        if item.digest not in remaining:
            raise ValueError("seed decision does not exist in candidate set")
        if max_architectures is not None and len(selected) >= max_architectures:
            break
        selected.append(remaining.pop(item.digest))
        uncovered.difference_update(token_map[item.digest])

    while uncovered and remaining:
        if max_architectures is not None and len(selected) >= max_architectures:
            break
        ranked = sorted(
            remaining.values(),
            key=lambda decision: (
                -len(token_map[decision.digest] & uncovered),
                decision.digest,
            ),
        )
        winner = ranked[0]
        selected.append(winner)
        uncovered.difference_update(token_map[winner.digest])
        remaining.pop(winner.digest)

    if uncovered:
        ceiling = "unbounded" if max_architectures is None else str(max_architectures)
        raise ValueError(
            "REFUSED:PAIRWISE_COVERAGE_INCOMPLETE:"
            f"uncovered={len(uncovered)}:max_architectures={ceiling}"
        )
    return tuple(selected)


def unique_by_digest(decisions: Iterable[DecisionBasis]) -> tuple[DecisionBasis, ...]:
    by_digest = {decision.digest: decision for decision in decisions}
    return tuple(by_digest[key] for key in sorted(by_digest))
