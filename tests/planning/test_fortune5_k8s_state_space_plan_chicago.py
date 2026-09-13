# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style test: a real, registered solver (`Astar`) solves the real
`docs/planning/fortune5-k8s-state-space/{domain,problem}.pddl` pair, producing
a real, ordered candidate plan for the cross-repo engineering work named in
the 2026-08-10 review of ~/ggen-marketplace and ~/wasm4pm.

This is itself bounded by `CLAUDE.md`'s law: **"It computes candidate plans.
It does not actuate."** This test only proves the plan is real and correctly
ordered -- it never claims any of the named engineering work (a typed k8s
schema, an indexed blackboard, a schema-to-ontology generator, a k8s state
encoder) has actually been done. See `ROADMAP.md` in the same directory as
the PDDL files for the honest, generated candidate-plan document.

Mirrors `tests/domains/python/test_pddl_domain.py::TestPDDLDomain::test_astar_solve_blocks`
exactly (same `PDDLDomain` + `Astar` + rollout pattern) -- the "nearest
working example" this repo already has for classical PDDL planning, per
`.claude/rules/architecture.md`.

No `unittest.mock` / `Mock` / `MagicMock` / `patch` / `monkeypatch` anywhere
in this file.
"""

from __future__ import annotations

import os

DOMAIN_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "docs", "planning", "fortune5-k8s-state-space"
)
DOMAIN_PATH = os.path.join(DOMAIN_DIR, "domain.pddl")
PROBLEM_PATH = os.path.join(DOMAIN_DIR, "problem.pddl")


def _build_domain():
    from autofde_lab.hub.domain.pddl import PDDLDomain

    return PDDLDomain(DOMAIN_PATH, PROBLEM_PATH)


def test_domain_constructs_and_has_expected_actions_from_empty_init() -> None:
    """From the real, empty :init, exactly the three zero-precondition
    actions are applicable -- the other five real actions have real
    dependencies and must not appear yet."""
    domain = _build_domain()
    s0 = domain._get_initial_state_()
    actions = {str(a) for a in domain._get_applicable_actions_from(s0).get_elements()}

    assert actions == {
        "(build-typed-k8s-object-schema)",
        "(build-schema-to-ontology-generator)",
        "(loosen-dspy-pack-nesting-gate)",
    }


def test_astar_solves_fortune5_k8s_state_space_plan() -> None:
    """End-to-end: a real, registered Astar solver reaches the real goal
    predicate `(has-fortune5-state-space-model)`, and the resulting real,
    ordered plan respects every action's real precondition/effect
    dependency -- proven here by re-checking the dependency invariants
    against the actual solved action sequence, not merely trusting the
    solver's own success signal."""
    from autofde_lab import utils

    domain = _build_domain()
    Astar = utils.load_registered_solver("Astar")

    with Astar(domain_factory=lambda: domain) as solver:
        solver.solve()
        obs = domain.reset()
        plan: list[str] = []
        for _ in range(20):
            if domain._is_terminal(obs):
                break
            action = solver.sample_action(obs)
            plan.append(str(action))
            outcome = domain.step(action)
            obs = outcome.observation

        assert domain._goal_checker.is_goal(obs.to_cpp()), f"Astar did not reach the goal. Plan: {plan}"

    assert len(plan) == 8, f"expected all 8 real actions in the plan, got: {plan}"

    # Real dependency-order assertions -- a plan reaching the goal by luck
    # (e.g. a bugged domain letting actions fire out of order) would still
    # pass the bare goal check above; these catch that class of defect.
    def index_of(action_name: str) -> int:
        return plan.index(f"({action_name})")

    assert index_of("build-schema-to-ontology-generator") < index_of("author-k8s-pack")
    assert index_of("loosen-dspy-pack-nesting-gate") < index_of("author-k8s-pack")
    assert index_of("build-typed-k8s-object-schema") < index_of("index-hearsay-blackboard")
    assert index_of("index-hearsay-blackboard") < index_of("rescale-firing-budget")
    assert index_of("rescale-firing-budget") < index_of("build-k8s-state-encoder")
    assert index_of("build-typed-k8s-object-schema") < index_of("build-k8s-state-encoder")
    assert index_of("build-k8s-state-encoder") < index_of("integrate-with-autofde-cognition")
    assert index_of("author-k8s-pack") < index_of("integrate-with-autofde-cognition")

    # The goal-producing action is always last -- a structural sanity check
    # on the rollout itself, not just the dependency graph.
    assert plan[-1] == "(integrate-with-autofde-cognition)"
