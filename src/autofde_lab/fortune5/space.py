"""Combinatorial state-space kernel for Fortune-5-scale enterprise exploration.

This module is SELECT/CONSTRUCT only. It has no actuation surface and produces
candidate scenario identities, never authority receipts.
"""

from __future__ import annotations

import hashlib
import heapq
import json
from dataclasses import dataclass, field
from itertools import combinations
from math import prod
from typing import Iterable, Iterator, Mapping, Sequence


def _canonical_digest(value: object) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode()
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True, slots=True)
class Option:
    name: str
    attrs: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("REFUSED:EMPTY_OPTION_NAME")
        if tuple(sorted(self.attrs)) != self.attrs:
            raise ValueError("REFUSED:OPTION_ATTRS_NOT_CANONICAL")
        keys = [key for key, _ in self.attrs]
        if len(keys) != len(set(keys)):
            raise ValueError("REFUSED:DUPLICATE_OPTION_ATTR")

    @classmethod
    def from_mapping(
        cls, name: str, attrs: Mapping[str, str] | None = None
    ) -> "Option":
        return cls(name=name, attrs=tuple(sorted((attrs or {}).items())))

    @property
    def identity(self) -> tuple[str, tuple[tuple[str, str], ...]]:
        return (self.name, self.attrs)


@dataclass(frozen=True, slots=True)
class Axis:
    name: str
    options: tuple[Option, ...]

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("REFUSED:EMPTY_AXIS_NAME")
        if not self.options:
            raise ValueError(f"REFUSED:EMPTY_AXIS:{self.name}")
        names = [option.name for option in self.options]
        if len(names) != len(set(names)):
            raise ValueError(f"REFUSED:DUPLICATE_OPTION_NAME:{self.name}")

    def resolve(self, option_name: str) -> Option:
        matches = [option for option in self.options if option.name == option_name]
        if len(matches) != 1:
            raise ValueError(f"REFUSED:UNKNOWN_OPTION:{self.name}:{option_name}")
        return matches[0]


@dataclass(frozen=True, slots=True)
class CompatibilityLaw:
    """Declarative, inspectable compatibility law; never arbitrary executable policy."""

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
    ) -> "CompatibilityLaw":
        return cls(
            when=tuple(sorted((when or {}).items())),
            require=tuple(sorted((require or {}).items())),
            forbid=tuple(sorted((forbid or {}).items())),
            reason=reason,
        )

    def allows(self, choices: Mapping[str, Option]) -> bool:
        if not all(choices[axis].name == option for axis, option in self.when):
            return True
        if any(choices[axis].name != option for axis, option in self.require):
            return False
        if any(choices[axis].name == option for axis, option in self.forbid):
            return False
        return True


@dataclass(frozen=True, slots=True)
class Scenario:
    space_digest: str
    choices: tuple[tuple[str, Option], ...]
    _digest: str = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if len(self.space_digest) != 64:
            raise ValueError("REFUSED:INVALID_STATE_SPACE_DIGEST")
        payload = {
            "space_digest": self.space_digest,
            "choices": [
                [axis, option.name, [[key, value] for key, value in option.attrs]]
                for axis, option in self.choices
            ],
        }
        object.__setattr__(self, "_digest", _canonical_digest(payload))

    @property
    def digest(self) -> str:
        return self._digest

    @property
    def scenario_id(self) -> str:
        return f"f5:{self.digest[:24]}"

    @property
    def authority(self) -> str:
        return "NONE"

    @property
    def standing(self) -> str:
        return "CANDIDATE"

    def by_axis(self) -> dict[str, Option]:
        return dict(self.choices)

    def names(self) -> dict[str, str]:
        return {axis: option.name for axis, option in self.choices}


@dataclass(frozen=True, slots=True)
class StateSpace:
    axes: tuple[Axis, ...]
    laws: tuple[CompatibilityLaw, ...] = ()
    _digest: str = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.axes:
            raise ValueError("REFUSED:EMPTY_STATE_SPACE")
        axis_names = [axis.name for axis in self.axes]
        if len(axis_names) != len(set(axis_names)):
            raise ValueError("REFUSED:DUPLICATE_AXIS_NAME")
        self._validate_laws()
        payload = {
            "axes": [
                {
                    "name": axis.name,
                    "options": [
                        [option.name, [[key, value] for key, value in option.attrs]]
                        for option in axis.options
                    ],
                }
                for axis in self.axes
            ],
            "laws": [
                {
                    "when": list(law.when),
                    "require": list(law.require),
                    "forbid": list(law.forbid),
                    "reason": law.reason,
                }
                for law in self.laws
            ],
        }
        object.__setattr__(self, "_digest", _canonical_digest(payload))

    @property
    def digest(self) -> str:
        """Identity of the exact admitted axes, option identities, and laws."""
        return self._digest

    @property
    def raw_upper_bound(self) -> int:
        return prod(len(axis.options) for axis in self.axes)

    def _validate_laws(self) -> None:
        admitted = {
            axis.name: {option.name for option in axis.options} for axis in self.axes
        }
        for law_index, law in enumerate(self.laws):
            for clause_name in ("when", "require", "forbid"):
                clause = getattr(law, clause_name)
                seen: set[str] = set()
                for axis, option in clause:
                    if axis not in admitted:
                        raise ValueError(
                            "REFUSED:UNKNOWN_COMPATIBILITY_AXIS:"
                            f"{law_index}:{clause_name}:{axis}"
                        )
                    if option not in admitted[axis]:
                        raise ValueError(
                            "REFUSED:UNKNOWN_COMPATIBILITY_OPTION:"
                            f"{law_index}:{clause_name}:{axis}:{option}"
                        )
                    if axis in seen:
                        raise ValueError(
                            "REFUSED:DUPLICATE_COMPATIBILITY_AXIS:"
                            f"{law_index}:{clause_name}:{axis}"
                        )
                    seen.add(axis)
            if set(law.require) & set(law.forbid):
                raise ValueError(f"REFUSED:CONTRADICTORY_COMPATIBILITY_LAW:{law_index}")

    def scenario(self, choices: Mapping[str, Option | str]) -> Scenario:
        if set(choices) != {axis.name for axis in self.axes}:
            raise ValueError("REFUSED:SCENARIO_AXIS_SET_MISMATCH")
        resolved: list[tuple[str, Option]] = []
        for axis in self.axes:
            value = choices[axis.name]
            option = axis.resolve(value) if isinstance(value, str) else value
            if option not in axis.options:
                raise ValueError(
                    f"REFUSED:OPTION_IDENTITY_NOT_ADMITTED:{axis.name}:{option.name}"
                )
            resolved.append((axis.name, option))
        return Scenario(self.digest, tuple(resolved))

    def raw_coordinate_at(self, index: int) -> Scenario:
        if index < 0 or index >= self.raw_upper_bound:
            raise IndexError(f"REFUSED:COORDINATE_OUT_OF_RANGE:{index}")
        cursor = index
        selected: list[Option] = [self.axes[0].options[0]] * len(self.axes)
        for axis_index in range(len(self.axes) - 1, -1, -1):
            axis = self.axes[axis_index]
            cursor, option_index = divmod(cursor, len(axis.options))
            selected[axis_index] = axis.options[option_index]
        return Scenario(
            self.digest,
            tuple((axis.name, option) for axis, option in zip(self.axes, selected)),
        )

    def raw_index_of(self, scenario: Scenario) -> int:
        """Reverse a scenario to its exact mixed-radix raw coordinate."""
        if scenario.space_digest != self.digest:
            raise ValueError("REFUSED:SCENARIO_STATE_SPACE_MISMATCH")
        if tuple(axis for axis, _ in scenario.choices) != tuple(
            axis.name for axis in self.axes
        ):
            raise ValueError("REFUSED:SCENARIO_AXIS_SET_MISMATCH")
        index = 0
        for axis, (_, option) in zip(self.axes, scenario.choices):
            try:
                option_index = axis.options.index(option)
            except ValueError as exc:
                raise ValueError(
                    f"REFUSED:OPTION_IDENTITY_NOT_ADMITTED:{axis.name}:{option.name}"
                ) from exc
            index = index * len(axis.options) + option_index
        return index

    def is_lawful(self, scenario: Scenario) -> bool:
        try:
            self.raw_index_of(scenario)
        except ValueError:
            return False
        values = scenario.by_axis()
        return all(law.allows(values) for law in self.laws)

    def iter_raw(
        self, *, start: int = 0, stop: int | None = None
    ) -> Iterator[Scenario]:
        end = self.raw_upper_bound if stop is None else min(stop, self.raw_upper_bound)
        if start < 0 or start > end:
            raise ValueError("REFUSED:INVALID_ITERATION_RANGE")
        for index in range(start, end):
            yield self.raw_coordinate_at(index)

    def iter_lawful(self, *, limit: int, start: int = 0) -> Iterator[Scenario]:
        if limit <= 0:
            raise ValueError("REFUSED:NONPOSITIVE_LAWFUL_LIMIT")
        emitted = 0
        for scenario in self.iter_raw(start=start):
            if not self.is_lawful(scenario):
                continue
            yield scenario
            emitted += 1
            if emitted >= limit:
                return

    def baseline(self, *, scan_limit: int = 100_000) -> Scenario:
        if scan_limit <= 0:
            raise ValueError("REFUSED:NONPOSITIVE_BASELINE_SCAN_LIMIT")
        stop = min(scan_limit, self.raw_upper_bound)
        for scenario in self.iter_raw(stop=stop):
            if self.is_lawful(scenario):
                return scenario
        raise ValueError(f"REFUSED:NO_LAWFUL_BASELINE_WITHIN_LIMIT:{scan_limit}")

    def pairwise_candidates(
        self,
        *,
        baseline: Scenario | None = None,
        candidate_limit: int = 100_000,
    ) -> tuple[Scenario, ...]:
        if candidate_limit <= 0:
            raise ValueError("REFUSED:NONPOSITIVE_CANDIDATE_LIMIT")
        base = baseline or self.baseline()
        if not self.is_lawful(base):
            raise ValueError("REFUSED:BASELINE_NOT_LAWFUL")
        base_values = base.by_axis()
        by_digest: dict[str, Scenario] = {base.digest: base}

        def admit(overrides: Mapping[str, Option]) -> None:
            values = dict(base_values)
            values.update(overrides)
            candidate = self.scenario(values)
            if not self.is_lawful(candidate):
                return
            by_digest.setdefault(candidate.digest, candidate)
            if len(by_digest) > candidate_limit:
                raise ValueError(
                    "REFUSED:PAIRWISE_DESIGN_TOO_LARGE:"
                    f"{len(by_digest)}>{candidate_limit}"
                )

        for axis in self.axes:
            for option in axis.options:
                admit({axis.name: option})
        for left, right in combinations(self.axes, 2):
            for left_option in left.options:
                for right_option in right.options:
                    admit({left.name: left_option, right.name: right_option})
        return tuple(by_digest[key] for key in sorted(by_digest))

    def pairwise_covering(
        self,
        *,
        baseline: Scenario | None = None,
        candidate_limit: int = 100_000,
        max_scenarios: int | None = None,
    ) -> tuple[Scenario, ...]:
        candidates = self.pairwise_candidates(
            baseline=baseline,
            candidate_limit=candidate_limit,
        )
        base = baseline or self.baseline()
        return pairwise_covering(candidates, seed=(base,), max_scenarios=max_scenarios)


def _pair_tokens(scenario: Scenario) -> frozenset[tuple[object, ...]]:
    values = scenario.choices
    return frozenset(
        (
            left_axis,
            left_option.identity,
            right_axis,
            right_option.identity,
        )
        for (left_axis, left_option), (right_axis, right_option) in combinations(
            values, 2
        )
    )


def pairwise_token_count(scenarios: Sequence[Scenario]) -> int:
    if not scenarios:
        return 0
    return len(set().union(*(_pair_tokens(scenario) for scenario in scenarios)))


def unique_by_digest(scenarios: Iterable[Scenario]) -> tuple[Scenario, ...]:
    by_digest = {scenario.digest: scenario for scenario in scenarios}
    return tuple(by_digest[key] for key in sorted(by_digest))


def pairwise_covering(
    scenarios: Sequence[Scenario],
    *,
    seed: Sequence[Scenario] = (),
    max_scenarios: int | None = None,
) -> tuple[Scenario, ...]:
    """Deterministic greedy set cover with incremental gain maintenance.

    The inverted token index prevents Fortune-5-scale candidate designs from
    rescanning every scenario's token set after every selection.
    """
    if not scenarios:
        return ()
    if max_scenarios is not None and max_scenarios <= 0:
        raise ValueError("REFUSED:NONPOSITIVE_MAX_SCENARIOS")

    by_digest = {scenario.digest: scenario for scenario in scenarios}
    token_map = {
        digest: _pair_tokens(scenario) for digest, scenario in by_digest.items()
    }
    uncovered = set().union(*token_map.values())
    owners: dict[tuple[object, ...], list[str]] = {}
    for digest, tokens in token_map.items():
        for token in tokens:
            owners.setdefault(token, []).append(digest)

    remaining = set(by_digest)
    gains = {digest: len(tokens) for digest, tokens in token_map.items()}
    heap = [(-gain, digest) for digest, gain in gains.items()]
    heapq.heapify(heap)
    selected: list[Scenario] = []

    def consume(digest: str) -> None:
        if digest not in remaining:
            return
        selected.append(by_digest[digest])
        remaining.remove(digest)
        newly_covered = token_map[digest] & uncovered
        uncovered.difference_update(newly_covered)
        impacted: set[str] = set()
        for token in newly_covered:
            for owner in owners[token]:
                if owner in remaining:
                    gains[owner] -= 1
                    impacted.add(owner)
        for owner in impacted:
            heapq.heappush(heap, (-gains[owner], owner))

    for scenario in unique_by_digest(seed):
        if scenario.digest not in by_digest:
            raise ValueError("REFUSED:SEED_NOT_IN_CANDIDATE_SET")
        if max_scenarios is not None and len(selected) >= max_scenarios:
            break
        consume(scenario.digest)

    while uncovered and remaining:
        if max_scenarios is not None and len(selected) >= max_scenarios:
            break
        while heap:
            neg_gain, digest = heapq.heappop(heap)
            if digest not in remaining:
                continue
            if -neg_gain != gains[digest]:
                continue
            if gains[digest] <= 0:
                heap.clear()
                break
            consume(digest)
            break
        else:
            break

    if uncovered:
        raise ValueError(
            "REFUSED:PAIRWISE_COVERAGE_INCOMPLETE:"
            f"uncovered={len(uncovered)}:selected={len(selected)}"
        )
    return tuple(selected)
