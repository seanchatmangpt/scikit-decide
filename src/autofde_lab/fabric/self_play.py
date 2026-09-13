"""Bounded ontology-style combinatorial self-play scenario manufacture.

The generator treats an admitted constraint graph as a finite product of dimensions and preserves
all lawful reversible combinations up to an explicit bound.  It does not execute scenarios; it
manufactures deterministic subjects for solvers, verifiers and refusal tests.
"""

from __future__ import annotations

import hashlib
import itertools
import json
from dataclasses import dataclass
from typing import Callable, Mapping, Sequence


@dataclass(frozen=True, slots=True)
class Scenario:
    scenario_id: str
    values: Mapping[str, object]
    adversarial: bool = False


def _id(values: Mapping[str, object], adversarial: bool) -> str:
    payload = json.dumps(
        {"values": dict(values), "adversarial": adversarial},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode()
    return "scenario:sha256:" + hashlib.sha256(payload).hexdigest()


def manufacture_scenarios(
    dimensions: Mapping[str, Sequence[object]],
    *,
    admits: Callable[[Mapping[str, object]], bool] = lambda _: True,
    max_scenarios: int = 10_000,
) -> tuple[Scenario, ...]:
    if max_scenarios <= 0:
        raise ValueError("max_scenarios must be positive")
    names = tuple(sorted(dimensions))
    if any(not dimensions[name] for name in names):
        return ()
    rows: list[Scenario] = []
    for product in itertools.product(*(dimensions[name] for name in names)):
        values = dict(zip(names, product))
        if admits(values):
            rows.append(Scenario(_id(values, False), values))
            if len(rows) >= max_scenarios:
                break
    return tuple(rows)


def manufacture_boundary_adversaries(
    scenarios: Sequence[Scenario],
    *,
    forbidden_mutations: Mapping[str, object],
    admits: Callable[[Mapping[str, object]], bool],
) -> tuple[Scenario, ...]:
    """Generate one-step boundary violations that the admission law must reject."""
    out: list[Scenario] = []
    seen: set[str] = set()
    for scenario in scenarios:
        for name, forbidden in sorted(forbidden_mutations.items()):
            values = dict(scenario.values)
            values[name] = forbidden
            if admits(values):
                continue
            scenario_id = _id(values, True)
            if scenario_id not in seen:
                seen.add(scenario_id)
                out.append(Scenario(scenario_id, values, adversarial=True))
    return tuple(out)
