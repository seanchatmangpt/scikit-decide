# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style: no plan source may bypass the common candidate contract.

Real registry (`classify_registered_solvers` over the real
`autofde_lab.solvers` entry points), real `GymProcedureDomain`, real recipe
from `recipes/`, real probe corpus collected by really stepping the domain,
real `TypedDomain` induced from those records, real `search_plan_typed`.
No test doubles anywhere in this module -- every assertion is on final state
(returned `PlannerAttempt` fields, the contents of the common candidate set,
the raised refusal), never on "was this called".

The defect under test, measured on an archived trial's `federation.json`:

    49 planners attempted
    13 produced PLAN_CANDIDATE
     0 matched the committed plan
    committed_plan_source = "typed_search"

`search_plan_typed` was called directly from `run_real_trial`, produced no
`PlannerAttempt`, appeared in no `federation.json`, was never ranked, and
still sourced the commitment. The federation was therefore observational.
These tests pin the repair: `typed_search` is a federated producer under the
same contract, and a plan that did not come through the common set cannot
source a commitment.
"""

from pathlib import Path

import pytest

from autofde_lab.hub.domain.gym_procedure.gym_procedure import (
    GymProcedureDomain,
    load_recipe,
)
from autofde_lab.hub.domain.gym_procedure.planner_federation import (
    TYPED_SEARCH_PLANNER_ID,
    CommonCandidateSet,
    GovernedCandidate,
    PlannerAttempt,
    UngovernedCandidateRefused,
    classify_registered_solvers,
    recipe_problem_digest,
    run_federation,
    run_typed_search_attempt,
    select_governed_candidate,
)
from autofde_lab.hub.domain.gym_procedure.typed_induction import (
    induce_typed_domain,
    validate_plan_typed,
)

REPO = Path(__file__).resolve().parents[2]
RECIPE_PATH = (
    REPO / "src/autofde_lab/hub/domain/gym_procedure/recipes/cube_standard_container_counter.json"
)

#: The typed outcome vocabulary EVERY producer's record must draw from.
TYPED_OUTCOMES = {
    "PLAN_CANDIDATE",
    "UNSUPPORTED",
    "UNSUPPORTED:REQUIRES_CONFIGURATION",
    "TIMEOUT",
    "FAILED",
    "REFUSED",
    "CRASHED",
}

#: A small, fast, real slice of the registry. Deliberately three genuinely
#: independent search families, not a mock of "some planners".
PEER_PLANNERS = ["Astar", "LRTDP", "EHC"]


@pytest.fixture(scope="module")
def recipe():
    return load_recipe(RECIPE_PATH)


@pytest.fixture(scope="module")
def probe_records(recipe):
    """A REAL probe corpus: really step a real domain and record what happened.

    Breadth-first over the reachable state space, trying every action in every
    reached state through the domain's own applicability check, and recording
    the real pre/post observations. This is the same shape of evidence
    `_discover_by_probing` collects in a live trial, produced here without a
    provider subprocess so the test is hermetic and fast.
    """
    from collections import deque

    domain = GymProcedureDomain(recipe)
    all_actions = sorted(a.id for a in recipe.steps)
    # Every record carries the FULL fact universe as real booleans, so an
    # unset fact is observed as False rather than silently missing -- the
    # same shape `_observation_from_facts` gives a live trial.
    universe = sorted(
        set(recipe.initial_facts)
        | set(recipe.goal_facts)
        | {f for s in recipe.steps for f in s.preconditions}
        | {f for s in recipe.steps for f in s.establishes}
        | {f for s in recipe.steps for f in s.removes}
    )
    records: list[dict] = []
    start = domain.reset()
    seen = {frozenset(start.facts)}
    queue = deque([start])
    while queue:
        obs = queue.popleft()
        legal = set(domain._get_applicable_actions_from(obs).get_elements())
        for action in all_actions:
            pre_facts = set(obs.facts)
            pre = {f: f in pre_facts for f in universe}
            if action not in legal:
                records.append({"action": action, "applicable": False, "observed_pre": pre})
                continue
            probe_domain = GymProcedureDomain(recipe)
            probe_domain.reset()
            probe_domain._state = obs  # real state object, real domain instance
            post_obs = probe_domain.step(action).observation
            post_facts = set(post_obs.facts)
            records.append(
                {
                    "action": action,
                    "applicable": True,
                    "observed_pre": pre,
                    "observed_post": {k: k in post_facts for k in universe},
                }
            )
            if frozenset(post_facts) not in seen:
                seen.add(frozenset(post_facts))
                queue.append(post_obs)
    return records


@pytest.fixture(scope="module")
def typed(recipe, probe_records):
    typed_domain = induce_typed_domain(probe_records)
    initial = dict(probe_records[0]["observed_pre"])
    goal_facts = sorted(recipe.goal_facts)

    def goal_predicate(state):
        return all(state.get(f, False) for f in goal_facts)

    return typed_domain, initial, goal_predicate


@pytest.fixture(scope="module")
def typed_search_attempt(recipe, typed):
    typed_domain, initial, goal_predicate = typed
    return run_typed_search_attempt(
        typed_domain, initial, goal_predicate, recipe_problem_digest(recipe), timeout_s=10.0
    )


# --------------------------------------------------------------------------
# 1. typed_search is a first-class candidate producer
# --------------------------------------------------------------------------


def test_typed_search_produces_a_real_planner_attempt(typed_search_attempt, recipe):
    """Same record type, same identity slot, same problem digest as any peer."""
    a = typed_search_attempt
    assert isinstance(a, PlannerAttempt)
    assert a.planner_identity == TYPED_SEARCH_PLANNER_ID == "typed_search"
    assert a.outcome in TYPED_OUTCOMES
    assert a.problem_digest == recipe_problem_digest(recipe)
    assert a.planning_duration_s >= 0.0
    # Provenance is REPORTED, not hidden: it searches the typed model, and
    # that is a real difference from a recipe-space planner.
    assert a.representation == "typed_model"


def test_typed_search_really_reaches_the_goal_on_this_recipe(typed, typed_search_attempt):
    """The capability that must NOT be regressed by the governance fix."""
    typed_domain, initial, goal_predicate = typed
    a = typed_search_attempt
    assert a.outcome == "PLAN_CANDIDATE", (a.outcome, a.detail)
    assert a.candidate_plan, "typed_search reached the goal with an empty plan"
    ok, _final, reason = validate_plan_typed(
        typed_domain, initial, a.candidate_plan, goal_predicate
    )
    assert ok, reason


def test_typed_search_appears_in_federation_output_beside_its_peers(recipe, typed_search_attempt):
    """REAL federation over REAL registered solvers; typed_search is in the list.

    This is the before/after fact: `federation.json` previously could not
    contain a `typed_search` row at all, because the producer emitted no
    attempt. It now serializes through the identical record projection.
    """
    peers = run_federation(recipe, PEER_PLANNERS, timeout_s=10.0)
    attempts = peers + [typed_search_attempt]
    rows = [
        {
            "planner": a.planner_identity,
            "representation": a.representation,
            "outcome": a.outcome,
            "plan": list(a.candidate_plan),
            "duration_s": a.planning_duration_s,
            "detail": a.detail,
        }
        for a in attempts
    ]
    identities = {r["planner"] for r in rows}
    assert set(PEER_PLANNERS) <= identities
    assert "typed_search" in identities
    # Every row -- including typed_search's -- carries the same keys and a
    # typed outcome. A producer that is "in the file" with a different shape
    # is not comparable, and comparability is the whole point.
    assert all(set(r) == set(rows[0]) for r in rows)
    assert {r["outcome"] for r in rows} <= TYPED_OUTCOMES


def test_typed_search_is_classified_like_any_other_registered_producer(recipe):
    """It is NOT smuggled into the entry-point registry to fake peer status."""
    names = {c.name for c in classify_registered_solvers(recipe)}
    assert "typed_search" not in names, (
        "typed_search is a federated producer, not a registered solver; it must "
        "join the candidate contract without faking registry membership"
    )


# --------------------------------------------------------------------------
# 2. It competes -- it does not get a privileged line to commitment
# --------------------------------------------------------------------------


def test_typed_search_candidate_enters_the_common_set_like_any_other(recipe, typed_search_attempt):
    peers = run_federation(recipe, PEER_PLANNERS, timeout_s=10.0)
    common = CommonCandidateSet(recipe_problem_digest(recipe))
    admitted = common.admit_all(peers + [typed_search_attempt])
    by_planner = {c.planner_identity for c in admitted}
    assert "typed_search" in by_planner
    # Peers that really produced candidates are in there too -- the common set
    # is common, not a rename of the typed_search path.
    peer_candidates = {a.planner_identity for a in peers if a.outcome == "PLAN_CANDIDATE"}
    assert peer_candidates <= by_planner
    assert peer_candidates, "expected at least one real peer candidate on this recipe"


def test_selection_runs_the_same_validation_over_every_governed_candidate(
    recipe, typed, typed_search_attempt
):
    typed_domain, initial, goal_predicate = typed
    peers = run_federation(recipe, PEER_PLANNERS, timeout_s=10.0)
    common = CommonCandidateSet(recipe_problem_digest(recipe))
    common.admit_all(peers + [typed_search_attempt])
    selected, verdicts = select_governed_candidate(
        common, typed_domain, initial, goal_predicate
    )
    # Every DISTINCT governed plan got a verdict -- no candidate is exempt and
    # none is skipped once one validates.
    assert len(verdicts) == len(common.distinct_plans())
    assert {v["planner"] for v in verdicts} <= {
        c.planner_identity for c in common.candidates()
    }
    assert selected is not None
    assert isinstance(selected, GovernedCandidate)
    # Whatever was selected, it was selected by validation, not by privilege.
    ok, _final, reason = validate_plan_typed(
        typed_domain, initial, selected.plan, goal_predicate
    )
    assert ok, reason
    assert common.is_governed(selected.plan)


def test_advisory_ranking_orders_but_cannot_admit(recipe, typed, typed_search_attempt):
    """A ranking that names a plan the common set never admitted is inert."""
    typed_domain, initial, goal_predicate = typed
    common = CommonCandidateSet(recipe_problem_digest(recipe))
    common.admit_all([typed_search_attempt])
    ranking = (("smuggler", ("action_that_never_existed",), 999.0),)
    selected, verdicts = select_governed_candidate(
        common, typed_domain, initial, goal_predicate, ranking
    )
    assert "smuggler" not in {v["planner"] for v in verdicts}
    assert selected is None or selected.planner_identity != "smuggler"


def test_non_candidate_outcomes_are_recorded_but_never_admitted(recipe):
    """Evidence is kept; authority is not granted."""
    digest = recipe_problem_digest(recipe)
    common = CommonCandidateSet(digest)
    for outcome in ("UNSUPPORTED", "TIMEOUT", "FAILED", "REFUSED", "CRASHED"):
        attempt = PlannerAttempt(
            "some_planner", "recipe", digest, outcome, ("a", "b"), 0.1, "detail"
        )
        assert common.admit(attempt) is None, outcome
    assert common.candidates() == ()
    with pytest.raises(UngovernedCandidateRefused):
        common.require_governed(("a", "b"))


# --------------------------------------------------------------------------
# 3. FALSIFIER -- a candidate outside the contract cannot source a commitment
# --------------------------------------------------------------------------


def test_plan_that_never_entered_the_common_set_cannot_source_a_commitment(
    recipe, typed_search_attempt
):
    common = CommonCandidateSet(recipe_problem_digest(recipe))
    common.admit(typed_search_attempt)
    with pytest.raises(UngovernedCandidateRefused) as exc:
        common.require_governed(("bypass_step",), "back_channel")
    assert "UNGOVERNED_CANDIDATE_SOURCED_COMMITMENT" in str(exc.value)


def test_forged_governed_candidate_is_refused(recipe, typed_search_attempt):
    """Constructing the token by hand is not a way in.

    Membership is checked against the issuing set's registry, so a forged
    `GovernedCandidate` -- even one carrying a real plan -- is refused by any
    set that did not itself admit it.
    """
    digest = recipe_problem_digest(recipe)
    issuing = CommonCandidateSet(digest)
    real = issuing.admit(typed_search_attempt)
    assert real is not None

    forged = GovernedCandidate(
        plan=("bypass_step",),
        planner_identity="back_channel",
        representation="typed_model",
        problem_digest=digest,
        admission_digest=real.admission_digest,  # stolen from a real admission
    )
    with pytest.raises(UngovernedCandidateRefused):
        issuing.require_governed(forged.plan, forged.planner_identity)

    # And a different set never admitted even the REAL candidate.
    other = CommonCandidateSet(digest)
    with pytest.raises(UngovernedCandidateRefused):
        other.require_governed(real.plan, real.planner_identity)


def test_admission_digests_are_not_predictable_across_sets(recipe, typed_search_attempt):
    a = CommonCandidateSet(recipe_problem_digest(recipe))
    b = CommonCandidateSet(recipe_problem_digest(recipe))
    ca = a.admit(typed_search_attempt)
    cb = b.admit(typed_search_attempt)
    assert ca is not None and cb is not None
    assert ca.plan == cb.plan
    assert ca.admission_digest != cb.admission_digest


# --------------------------------------------------------------------------
# 4. The bypass is gone from the trial loop itself (real source, real state)
# --------------------------------------------------------------------------


def test_crown_no_longer_calls_search_plan_typed_outside_the_contract():
    """`run_real_trial` must not reach `search_plan_typed` directly.

    A state assertion on the real file: the direct call was the bypass, and
    its absence -- together with `require_governed` sitting immediately
    before `commit(` -- is what makes the enforcement structural rather than
    a convention someone can re-break by adding one line.
    """
    src = (
        REPO / "src/autofde_lab/hub/domain/gym_procedure/level4_crown.py"
    ).read_text(encoding="utf-8")
    code = [
        line for line in src.splitlines() if not line.lstrip().startswith("#")
    ]
    assert not [ln for ln in code if "search_plan_typed(" in ln], (
        "level4_crown calls search_plan_typed directly again -- that is the "
        "bypass this module exists to prevent"
    )
    assert "run_typed_search_attempt(" in src
    assert "common.require_governed(" in src
    gate = next(i for i, ln in enumerate(code) if "common.require_governed(" in ln)
    commit_line = next(i for i, ln in enumerate(code) if ln.strip().startswith("commitment = commit("))
    assert gate < commit_line, "the governance gate must precede commitment"
