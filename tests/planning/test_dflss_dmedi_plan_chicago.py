# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style test: a real, registered solver (`Astar`) solves the real
`docs/planning/dflss-dmedi-curriculum/{domain,problem}.pddl` pair -- the
DFLSS (Design for Lean Six Sigma) DMEDI curriculum (Define, Measure,
Explore, Develop, Implement), 48 real named curriculum-module actions plus
4 real DFSS tollgate-review actions synthesizing each phase's composite
"-phase-complete" predicate (see `domain.pddl`'s own header comment for why
`:derived-predicates` was never an option in this repo -- `fabric/pddl_engine.py`'s
C++ backend parses it and implements none of it, silently).

This is itself bounded by `CLAUDE.md`'s law: **"It computes candidate plans.
It does not actuate."** This test only proves the plan is real and correctly
ordered -- it never claims any of the named curriculum modules have actually
been delivered/completed by any real learner.

Mirrors `tests/planning/test_fortune5_k8s_state_space_plan_chicago.py`'s own
pattern exactly (itself mirroring
`tests/domains/python/test_pddl_domain.py::TestPDDLDomain::test_astar_solve_blocks`) --
the "nearest working example" this repo already has for classical PDDL
planning, per `.claude/rules/architecture.md`. Replaces the throwaway
scratchpad-only validation this domain/problem pair was first checked with
(a real `PDDLDomain` + real `Astar` run, output observed, but never
committed as a durable test) with a permanent, committed Chicago test, per
`tests/CLAUDE.md`'s own law: "A domain/solver claim is `ALIVE` only with a
test constructing a real domain and running `solve()`, executed this
session."

No `unittest.mock` / `Mock` / `MagicMock` / `patch` / `monkeypatch` anywhere
in this file.
"""

from __future__ import annotations

import os

DOMAIN_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "docs", "planning", "dflss-dmedi-curriculum"
)
DOMAIN_PATH = os.path.join(DOMAIN_DIR, "domain.pddl")
PROBLEM_PATH = os.path.join(DOMAIN_DIR, "problem.pddl")

# The real 6 zero-precondition Define modules -- every other real action in
# this domain requires at least one tollgate predicate, directly or
# transitively.
_ZERO_PRECONDITION_ACTIONS = {
    "(complete-introduction-to-dfss)",
    "(complete-overview-of-define-phase)",
    "(complete-charter)",
    "(complete-mgpp)",
    "(complete-risk-management)",
    "(complete-communication-plan)",
}


def _build_domain():
    from autofde_lab.hub.domain.pddl import PDDLDomain

    return PDDLDomain(DOMAIN_PATH, PROBLEM_PATH)


def test_domain_constructs_and_has_expected_actions_from_empty_init() -> None:
    """From the real, empty :init, exactly the 6 real zero-precondition
    Define-phase actions are applicable -- the other 46 real actions all
    have a real tollgate (or intra-phase module) dependency and must not
    appear yet."""
    domain = _build_domain()
    s0 = domain._get_initial_state_()
    actions = {str(a) for a in domain._get_applicable_actions_from(s0).get_elements()}

    assert actions == _ZERO_PRECONDITION_ACTIONS


def test_astar_solves_dflss_dmedi_curriculum_plan() -> None:
    """End-to-end: a real, registered Astar solver reaches the real goal
    predicate `(dmedi-capstone-complete)`, and the resulting real, ordered
    plan respects every real phase-gate and intra-phase dependency named in
    `domain.pddl` -- proven here by re-checking each dependency directly
    against the actual solved action sequence, not merely trusting the
    solver's own success signal (per `.claude/rules/absence-is-not-evidence.md`:
    a planner-valid plan is not the same claim as an environment-valid
    plan; here it is at least independently re-checked against the domain's
    own real precondition/effect structure, not merely trusted)."""
    from autofde_lab import utils

    domain = _build_domain()
    Astar = utils.load_registered_solver("Astar")

    with Astar(domain_factory=lambda: domain) as solver:
        solver.solve()
        obs = domain.reset()
        plan: list[str] = []
        for _ in range(60):
            if domain._is_terminal(obs):
                break
            action = solver.sample_action(obs)
            plan.append(str(action))
            outcome = domain.step(action)
            obs = outcome.observation

        assert domain._goal_checker.is_goal(obs.to_cpp()), f"Astar did not reach the goal. Plan: {plan}"

    assert len(plan) == 52, f"expected all 52 real actions in the plan, got {len(plan)}: {plan}"
    assert set(plan[:6]) == _ZERO_PRECONDITION_ACTIONS, (
        "the 6 real zero-precondition Define modules must be the first 6 actions taken "
        f"(nothing else is applicable from the empty :init); got: {plan[:6]}"
    )

    def index_of(action_name: str) -> int:
        return plan.index(f"({action_name})")

    # ---- Define tollgate gates every real Measure module ----
    for module in (
        "complete-voice-of-the-customer",
        "complete-quality-function-deployment",
        "complete-target-costing",
        "complete-scorecards",
        "complete-intro-to-minitab",
        "complete-basic-statistics",
        "complete-understanding-variation-and-control-charts",
        "complete-measurement-systems-analysis",
        "complete-process-capability",
    ):
        assert index_of("conduct-define-tollgate-review") < index_of(module)
        assert index_of(module) < index_of("conduct-measure-tollgate-review")

    # ---- Measure tollgate gates every real Explore module; Concept
    # Generation additionally gates both real TRIZ modules ----
    for module in (
        "complete-concept-generation",
        "complete-concept-selection-pugh",
        "complete-concept-selection-ahp",
        "complete-statistical-tolerance-design",
        "complete-monte-carlo-simulation",
        "complete-hypothesis-testing",
        "complete-confidence-intervals",
        "complete-testing-means-medians-variances",
        "complete-proportion-and-chi-square",
        "complete-simple-and-multiple-regression",
        "complete-multi-vari-analysis",
        "complete-design-fmea",
    ):
        assert index_of("conduct-measure-tollgate-review") < index_of(module)
        assert index_of(module) < index_of("conduct-explore-tollgate-review")

    assert index_of("complete-concept-generation") < index_of("complete-triz-for-new-product-design")
    assert index_of("complete-concept-generation") < index_of("complete-transactional-triz")
    assert index_of("complete-triz-for-new-product-design") < index_of("conduct-explore-tollgate-review")
    assert index_of("complete-transactional-triz") < index_of("conduct-explore-tollgate-review")

    # ---- Explore tollgate gates every real Develop module; the real DOE
    # progression additionally chains Intro -> Full-Factorial ->
    # {Curvature, Catapult} -> Robust ----
    for module in (
        "complete-detailed-design",
        "complete-two-way-anova",
        "complete-intro-to-doe",
        "complete-fractional-factorial-doe",
        "complete-lean-design",
        "complete-design-for-manufacture-and-assembly",
        "complete-intro-to-reliability",
        "complete-conjoint-analysis",
        "complete-mixture-designs",
        "complete-helicopter-rsm-simulation",
    ):
        assert index_of("conduct-explore-tollgate-review") < index_of(module)
        assert index_of(module) < index_of("conduct-develop-tollgate-review")

    assert index_of("complete-intro-to-doe") < index_of("complete-full-factorial-doe")
    assert index_of("complete-full-factorial-doe") < index_of("complete-doe-with-curvature")
    assert index_of("complete-full-factorial-doe") < index_of("complete-doe-catapult-simulation")
    assert index_of("complete-doe-with-curvature") < index_of("complete-robust-design")
    for module in (
        "complete-full-factorial-doe",
        "complete-doe-with-curvature",
        "complete-doe-catapult-simulation",
        "complete-robust-design",
    ):
        assert index_of(module) < index_of("conduct-develop-tollgate-review")

    # ---- Develop tollgate gates every real Implement module; the DMEDI
    # Capstone requires all four real phase-composite predicates plus the
    # four Implement modules that precede it ----
    for module in (
        "complete-overview-of-implement-phase",
        "complete-prototype-and-pilot",
        "complete-process-control",
        "complete-implementation-planning",
    ):
        assert index_of("conduct-develop-tollgate-review") < index_of(module)
        assert index_of(module) < index_of("complete-dmedi-capstone")

    for tollgate in (
        "conduct-define-tollgate-review",
        "conduct-measure-tollgate-review",
        "conduct-explore-tollgate-review",
        "conduct-develop-tollgate-review",
    ):
        assert index_of(tollgate) < index_of("complete-dmedi-capstone")

    # The goal-producing action is always last -- a structural sanity check
    # on the rollout itself, not just the dependency graph.
    assert plan[-1] == "(complete-dmedi-capstone)"
