# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Executable autonomic-life planning case study.

The case study composes the existing continuous-planning kernel over a bounded,
generic personal-operating-system world. It is SELECT/CONSTRUCT only: it admits
explicit observations, preserves a reversible candidate frontier, demonstrates
exact reuse, delta-local repair, irrelevant-delta continuation, and fresh-plan
routing, then emits deterministic planning evidence.

It never sends messages, changes calendars, submits applications, grants
authority, or manufactures an execution receipt.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Iterable

from autofde_lab.agent.continuous_planning import (
    ContinuousPlanner,
    PlanApplicability,
    PlanArtifact,
    PlanCache,
    PlanningContext,
)
from autofde_lab.fabric.canonical import sha256
from autofde_lab.powl.algebra import Atom, OrderEdge, PartialOrder

GOAL = "stabilize-week"
CONSTRAINT_DIGEST = "life-case-study-policy-v1"
SEMANTIC_REVISION = "life-case-study-v1"
PLANNING_CAPABILITY = "bounded-life-planning"


@dataclass(frozen=True, slots=True)
class LifeObservation:
    """One explicitly admitted or non-admitted fact observation."""

    fact: str
    source_ref: str
    admitted: bool


@dataclass(frozen=True, slots=True)
class LifeCaseStudyReceipt:
    """Deterministic planning evidence; explicitly not an execution receipt."""

    schema: str
    subject: str
    observation_digest: str
    frontier_keys: tuple[str, ...]
    exact_reuse_disposition: str
    repair_disposition: str
    repair_affected_paths: tuple[str, ...]
    continue_disposition: str
    fresh_goal_disposition: str
    authority: str
    do_authority: bool
    evidence_kind: str

    def payload(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "subject": self.subject,
            "observation_digest": self.observation_digest,
            "frontier_keys": list(self.frontier_keys),
            "exact_reuse_disposition": self.exact_reuse_disposition,
            "repair_disposition": self.repair_disposition,
            "repair_affected_paths": list(self.repair_affected_paths),
            "continue_disposition": self.continue_disposition,
            "fresh_goal_disposition": self.fresh_goal_disposition,
            "authority": self.authority,
            "do_authority": self.do_authority,
            "evidence_kind": self.evidence_kind,
        }

    @property
    def receipt_sha256(self) -> str:
        return sha256(self.payload())

    def as_dict(self) -> dict[str, object]:
        return {**self.payload(), "receipt_sha256": self.receipt_sha256}


def _observation_payload(
    observations: Iterable[LifeObservation],
) -> list[dict[str, object]]:
    return [
        {
            "fact": item.fact,
            "source_ref": item.source_ref,
            "admitted": item.admitted,
        }
        for item in observations
    ]


def admit_life_observations(
    observations: Iterable[LifeObservation],
    *,
    goal: str = GOAL,
) -> PlanningContext:
    """Project only explicitly admitted positive facts into the planning view."""

    observations = tuple(observations)
    facts = frozenset(item.fact for item in observations if item.admitted)
    return PlanningContext(
        goal=goal,
        facts=facts,
        capabilities=frozenset({PLANNING_CAPABILITY}),
        constraint_digest=CONSTRAINT_DIGEST,
        semantic_revision=SEMANTIC_REVISION,
    )


def _model(ordering: str) -> PartialOrder:
    activities = (
        Atom("preserve-income-option"),
        Atom("prepare-career-window"),
        Atom("advance-education-option"),
        Atom("publish-household-brief"),
    )
    if ordering == "balanced":
        edges = frozenset(
            {
                OrderEdge(0, 3),
                OrderEdge(1, 3),
                OrderEdge(2, 3),
            }
        )
    elif ordering == "income-protect":
        edges = frozenset(
            {
                OrderEdge(0, 1),
                OrderEdge(0, 2),
                OrderEdge(1, 3),
                OrderEdge(2, 3),
            }
        )
    elif ordering == "career-window":
        edges = frozenset(
            {
                OrderEdge(1, 0),
                OrderEdge(1, 2),
                OrderEdge(0, 3),
                OrderEdge(2, 3),
            }
        )
    else:
        raise ValueError(f"unknown case-study ordering: {ordering}")
    return PartialOrder(activities, edges)


def _plan(ordering: str, objective: str) -> PlanArtifact:
    return PlanArtifact(
        model=_model(ordering),
        applicability=PlanApplicability(
            goal=GOAL,
            required_capabilities=frozenset({PLANNING_CAPABILITY}),
            constraint_digest=CONSTRAINT_DIGEST,
            semantic_revision=SEMANTIC_REVISION,
        ),
        planner="life-autonomic-case-study",
        planner_parameters={
            "ordering": ordering,
            "objective": objective,
            "selection_authority": "NONE",
        },
        dependency_keys={
            (0,): frozenset({"fact:income-option-open"}),
            (1,): frozenset({"fact:career-window-open"}),
            (2,): frozenset({"fact:education-option-open"}),
            (3,): frozenset({"fact:household-brief-due"}),
        },
        downstream={
            (0,): frozenset({(3,)}),
            (1,): frozenset({(3,)}),
            (2,): frozenset({(3,)}),
        },
        family_id="life-autonomic-week",
        required_authority_classes=(),
    )


def build_candidate_frontier() -> tuple[PlanArtifact, ...]:
    """Preserve three reversible lawful plans instead of claiming one winner."""

    return (
        _plan("balanced", "preserve-parallel-optionality"),
        _plan("income-protect", "protect-income-continuity"),
        _plan("career-window", "protect-time-bounded-career-window"),
    )


def _path_text(path: tuple[int, ...]) -> str:
    return "/".join(str(part) for part in path)


def run_case_study() -> LifeCaseStudyReceipt:
    """Execute the bounded planning experiment and return replayable evidence."""

    observations = (
        LifeObservation("income-option-open", "case:income-observation", True),
        LifeObservation("career-window-open", "case:career-observation", True),
        LifeObservation("education-option-open", "case:education-observation", True),
        LifeObservation("household-brief-due", "case:household-observation", True),
        LifeObservation("unverified-side-project", "case:unknown-observation", False),
    )
    context = admit_life_observations(observations)
    frontier = build_candidate_frontier()

    cache = PlanCache()
    frontier_keys = tuple(cache.remember(plan) for plan in frontier)
    active_plan = frontier[0]
    planner = ContinuousPlanner(cache)

    exact = planner.decide(context, exact_key=frontier_keys[0])

    career_window_closed = PlanningContext(
        goal=context.goal,
        facts=context.facts - {"career-window-open"},
        capabilities=context.capabilities,
        constraint_digest=context.constraint_digest,
        semantic_revision=context.semantic_revision,
    )
    repair = planner.decide(
        career_window_closed,
        active_plan=active_plan,
        previous_context=context,
    )

    unrelated_delta = PlanningContext(
        goal=context.goal,
        facts=context.facts | {"weather-noted"},
        capabilities=context.capabilities,
        constraint_digest=context.constraint_digest,
        semantic_revision=context.semantic_revision,
    )
    continuation = planner.decide(
        unrelated_delta,
        active_plan=active_plan,
        previous_context=context,
    )

    new_goal = PlanningContext(
        goal="different-weekly-goal",
        facts=context.facts,
        capabilities=context.capabilities,
        constraint_digest=context.constraint_digest,
        semantic_revision=context.semantic_revision,
    )
    fresh = planner.decide(new_goal)

    return LifeCaseStudyReceipt(
        schema="urn:autofde-lab:life-autonomic-case-study-receipt:1",
        subject=GOAL,
        observation_digest=sha256(_observation_payload(observations)),
        frontier_keys=frontier_keys,
        exact_reuse_disposition=exact.disposition.value,
        repair_disposition=repair.disposition.value,
        repair_affected_paths=tuple(
            sorted(_path_text(path) for path in repair.affected)
        ),
        continue_disposition=continuation.disposition.value,
        fresh_goal_disposition=fresh.disposition.value,
        authority="NONE",
        do_authority=False,
        evidence_kind="PLANNING_EVIDENCE_ONLY",
    )


def main() -> None:
    print(json.dumps(run_case_study().as_dict(), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
