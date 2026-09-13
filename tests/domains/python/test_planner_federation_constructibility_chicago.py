# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style: real recipe, real GymProcedureDomain, real registered solvers.

No test doubles anywhere in this module -- every solver class is the real one
loaded from the `autofde_lab.solvers` entry-point group, the domain is a real
`GymProcedureDomain`, and `run_federation` really runs `solve()`.

What is pinned here is the distinction between two facts that
`classify_registered_solvers` used to conflate into one:

- `status` -- ontology applicability, from `cls.check_domain(domain)`.
- `constructibility` -- whether the class can actually be instantiated with
  the arguments the federation supplies.

A solver may be SUPPORTED and still not runnable with defaults
(`src/autofde_lab/CLAUDE.md` invariant 2). IW/RIW/BFWS are the case where the
harness supplies a genuine `state_features` vector, so they are runnable;
MAHD/RayRLlib/StableBaseline/UPSolver are the case where it cannot, so they
get a typed `UNSUPPORTED:REQUIRES_CONFIGURATION` outcome instead of a generic
FAILED carrying a raw TypeError.
"""

from pathlib import Path

import pytest

from autofde_lab.hub.domain.gym_procedure.gym_procedure import load_recipe
from autofde_lab.hub.domain.gym_procedure.planner_federation import (
    classify_registered_solvers,
    run_federation,
)

RECIPE = (
    Path(__file__).resolve().parents[3]
    / "src/autofde_lab/hub/domain/gym_procedure/recipes/agentbench_kg_relation_path.json"
)

#: Measured against this repo's registry, and consistent with
#: `src/autofde_lab/CLAUDE.md` invariant 2's count of 7 solvers that are
#: ontology-applicable yet not runnable with defaults.
NEEDS_STATE_FEATURES = ("IW", "RIW", "BFWS")
NEEDS_CONFIG_UNSUPPLIABLE = ("MAHD", "RayRLlib", "StableBaseline", "UPSolver")


@pytest.fixture(scope="module")
def recipe():
    return load_recipe(RECIPE)


@pytest.fixture(scope="module")
def classified(recipe):
    return {c.name: c for c in classify_registered_solvers(recipe)}


def test_classification_and_constructibility_are_separate_facts(classified):
    """Both facts are reported; neither is derived from or suppressed by the other."""
    for name in NEEDS_STATE_FEATURES + NEEDS_CONFIG_UNSUPPLIABLE:
        assert name in classified, sorted(classified)
        # Not silently dropped from SUPPORTED to make the numbers look clean.
        assert classified[name].status == "SUPPORTED", classified[name]

    for name in NEEDS_STATE_FEATURES:
        c = classified[name].constructibility
        assert c.startswith("CONSTRUCTIBLE:VIA_SOLVER_KWARGS("), (name, c)
        assert "state_features" in c, (name, c)

    for name in NEEDS_CONFIG_UNSUPPLIABLE:
        c = classified[name].constructibility
        assert c.startswith("NOT_CONSTRUCTIBLE:REQUIRES_CONFIGURATION("), (name, c)


def test_plain_solver_is_constructible_with_defaults(classified):
    assert classified["Astar"].status == "SUPPORTED"
    assert classified["Astar"].constructibility == "CONSTRUCTIBLE"


def test_state_features_solvers_really_produce_plans(recipe):
    """Determination (a): `state_features` is genuinely derivable, so IW/BFWS run."""
    attempts = {
        a.planner_identity: a
        for a in run_federation(recipe, ["Astar", "IW", "BFWS"], timeout_s=30)
    }
    for name in ("Astar", "IW", "BFWS"):
        a = attempts[name]
        assert a.outcome == "PLAN_CANDIDATE", (name, a.outcome, a.detail)
        assert a.candidate_plan, (name, a)


def test_unconfigurable_solver_gets_typed_outcome_not_raw_typeerror(recipe):
    """Determination (b) for the residue: typed cause, not a generic FAILED."""
    attempts = {
        a.planner_identity: a
        for a in run_federation(recipe, list(NEEDS_CONFIG_UNSUPPLIABLE), timeout_s=30)
    }
    for name in NEEDS_CONFIG_UNSUPPLIABLE:
        a = attempts[name]
        assert a.outcome == "UNSUPPORTED:REQUIRES_CONFIGURATION", (
            name,
            a.outcome,
            a.detail,
        )
        assert "constructor requires argument" in a.detail, (name, a.detail)
        # The old behaviour leaked the raw constructor error text.
        assert "TypeError" not in a.detail, (name, a.detail)
        assert a.candidate_plan == ()
