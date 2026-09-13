# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Career Graph -> post-LLM résumé projection.

This module is a real, deterministic, dependency-free implementation of the
methodology described in `books/post-llm-career`:

- Appendix A (Career Graph Worksheet) defines the source graph: outcomes,
  capabilities, and evidence.
- Appendix G (Post-LLM Résumé and Role-Brief Templates) defines the
  six-section résumé structure that graph is projected into.
- Chapter 16 ("The Post-LLM Résumé") states the evidence discipline this
  module enforces as an actual invariant, not just prose: "Do not include a
  metric unless you can defend its subject and method." Concretely, an
  `Outcome`'s bullet only cites its linked `Evidence` when that evidence's
  `proof_level` is at least 1 (an artifact exists) -- a bare assertion
  (`proof_level == 0`) is never surfaced as if it were proof.

No LLM, network, or randomness is involved: `generate_resume` is a pure
function of its `CareerGraph` argument, so it is fully testable without
mocks.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = [
    "CareerGraph",
    "Capability",
    "Evidence",
    "Outcome",
    "Resume",
    "generate_resume",
]

# Appendix G's Section 3 ("Capability system") default function groups.
_DEFAULT_CAPABILITY_ORDER = (
    "Agent architecture",
    "Decision systems",
    "Reliability",
    "Product engineering",
    "Enterprise delivery",
)


@dataclass(frozen=True)
class Evidence:
    """A single Appendix A5 evidence row.

    `proof_level` follows the book's 0-6 scale (0=assertion ... 6=outcome
    evidence). Only `proof_level >= 1` (an actual artifact or better) is
    ever surfaced in a generated résumé bullet.
    """

    label: str
    proof_level: int = 0

    def __post_init__(self) -> None:
        if not self.label:
            raise ValueError("Evidence.label must be a non-empty string")
        if not 0 <= self.proof_level <= 6:
            raise ValueError(
                f"Evidence.proof_level must be in 0..6 (got {self.proof_level})"
            )

    @property
    def is_defensible(self) -> bool:
        """True once this evidence is more than a bare assertion (level 0)."""
        return self.proof_level >= 1


@dataclass(frozen=True)
class Outcome:
    """A single Appendix A1 outcome row.

    `evidence` is optional: an outcome may be real and stated without yet
    having defensible proof attached, but `generate_resume` will only ever
    cite it in a bullet when `evidence.is_defensible` is True.
    """

    statement: str
    beneficiary: str
    system: str = ""
    evidence: Evidence | None = None

    def __post_init__(self) -> None:
        if not self.statement:
            raise ValueError("Outcome.statement must be a non-empty string")
        if not self.beneficiary:
            raise ValueError("Outcome.beneficiary must be a non-empty string")


@dataclass(frozen=True)
class Capability:
    """A single Appendix A4 capability row, grouped by function (Sec. 3)."""

    name: str
    category: str = "Agent architecture"

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Capability.name must be a non-empty string")
        if not self.category:
            raise ValueError("Capability.category must be a non-empty string")


@dataclass(frozen=True)
class CareerGraph:
    """The canonical source graph a résumé is projected from (Appendix A)."""

    target_role: str
    outcomes: list[Outcome] = field(default_factory=list)
    capabilities: list[Capability] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.target_role:
            raise ValueError("CareerGraph.target_role must be a non-empty string")


@dataclass(frozen=True)
class Resume:
    """Appendix G's six-section résumé structure (education is left to the
    caller -- it is biographical, not derivable from the career graph)."""

    headline: str
    summary: str
    capability_system: dict[str, list[str]]
    outcome_bullets: list[str]
    evidence_list: list[str]


def _capability_system(capabilities: list[Capability]) -> dict[str, list[str]]:
    """Group capabilities by function (Appendix G Sec. 3), preserving the
    book's default category order first, then any custom categories in
    first-seen order."""
    grouped: dict[str, list[str]] = {}
    for capability in capabilities:
        grouped.setdefault(capability.category, []).append(capability.name)

    ordered: dict[str, list[str]] = {}
    for category in _DEFAULT_CAPABILITY_ORDER:
        if category in grouped:
            ordered[category] = grouped.pop(category)
    # any remaining, non-default categories, in first-seen order
    ordered.update(grouped)
    return ordered


def _outcome_bullet(outcome: Outcome) -> str:
    """Build one bullet using the book's documented pattern: 'Action +
    system + outcome + evidence.' Evidence is only appended when it is
    defensible (proof_level >= 1) -- a bare assertion is never presented
    as proof."""
    parts = [outcome.statement]
    if outcome.system:
        parts.append(f"via {outcome.system}")
    parts.append(f"for {outcome.beneficiary}")
    if outcome.evidence is not None and outcome.evidence.is_defensible:
        parts.append(f"(evidence: {outcome.evidence.label})")
    return " ".join(parts) + "."


def generate_resume(graph: CareerGraph) -> Resume:
    """Project a `CareerGraph` into a `Resume` per Appendix G's structure.

    Raises `ValueError` if `graph.outcomes` is empty: a résumé requires at
    least one real, stated outcome to project from -- an empty graph should
    fail loudly rather than silently produce a hollow document.
    """
    if not graph.outcomes:
        raise ValueError(
            "CareerGraph.outcomes is empty: generate_resume() requires at "
            "least one real outcome to project a résumé from."
        )

    headline = f"{graph.target_role} | {graph.outcomes[0].beneficiary}"

    summary = (
        f"{graph.target_role} with {len(graph.outcomes)} documented outcome"
        f"{'s' if len(graph.outcomes) != 1 else ''} and "
        f"{len(graph.capabilities)} capabilit"
        f"{'ies' if len(graph.capabilities) != 1 else 'y'} in scope."
    )

    outcome_bullets = [_outcome_bullet(outcome) for outcome in graph.outcomes]

    evidence_list = [
        outcome.evidence.label
        for outcome in graph.outcomes
        if outcome.evidence is not None and outcome.evidence.is_defensible
    ]

    return Resume(
        headline=headline,
        summary=summary,
        capability_system=_capability_system(graph.capabilities),
        outcome_bullets=outcome_bullets,
        evidence_list=evidence_list,
    )
