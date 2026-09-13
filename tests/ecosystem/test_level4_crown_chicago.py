# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for the Level 4 crown chain.

Real collaborators throughout: real GymAct episodes driven through the real
``~/gymact/.venv`` subprocess bridge, real registered solvers loaded from the
real ``autofde_lab.solvers`` entry-point group and run via real ``solve()``,
real files on disk (probe logs, receipt ledger, OCEL json). Every assertion is
on final state -- returned values, parsed OCEL, on-disk artifacts. No mocks.

Tests that need the real provider skip -- with the named blocker from
``level4_gymact_bridge.skip_reason()`` -- only when ``~/gymact`` or its venv is
genuinely absent. That is a real environment gate, never a silent substitution.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from autofde_lab.hub.domain.gym_procedure.discovered_domain import (
    DiscoveredDomain,
    DiscoveredProblem,
    induce_discovered_domain,
    refine_from_probe,
)
from autofde_lab.hub.domain.gym_procedure.gym_procedure import Recipe, Step
from autofde_lab.hub.domain.gym_procedure.level4_crown import (
    AdvisoryAuthorityRefused,
    AdvisoryCritique,
    ValidatedPlan,
    _observation_from_facts,
    commit,
    commit_and_execute,
    validate_ocel_referential_integrity,
)
from autofde_lab.hub.domain.gym_procedure.level4_gymact_bridge import (
    RealBlindEnvironment,
    skip_reason,
)
from autofde_lab.hub.domain.gym_procedure.planner_federation import (
    PlannerAttempt,
    classify_registered_solvers,
    run_federation,
)
from autofde_lab.hub.domain.gym_procedure.state_typing import (
    DimensionKind,
    classify_observation,
    propositionalize,
)

_SKIP = skip_reason()
requires_gymact = pytest.mark.skipif(_SKIP is not None, reason=_SKIP or "")


# --------------------------------------------------------------------------
# Shared real fixtures
# --------------------------------------------------------------------------


def _counter_recipe(n: int = 2) -> Recipe:
    """A real Recipe over the counter provider's real fact vocabulary."""
    steps = tuple(
        Step(
            id=f"inc{i}",
            description=f"increment counter to {i + 1}",
            preconditions=frozenset({f"counter={i}"}),
            establishes=frozenset({f"counter={i + 1}"}),
            removes=frozenset({f"counter={i}"}),
        )
        for i in range(n)
    )
    return Recipe(
        gym="cube_counter",
        task="reach-target",
        source_ref="gymact/gyms/cube_counter.py",
        initial_facts=frozenset({"counter=0"}),
        goal_facts=frozenset({f"counter={n}"}),
        steps=steps,
    )


@pytest.fixture(scope="module")
def real_probe_record(tmp_path_factory) -> dict:
    """One real GymAct probe against the real cube_counter provider."""
    if _SKIP is not None:
        pytest.skip(_SKIP)
    evdir = tmp_path_factory.mktemp("probe")
    env = RealBlindEnvironment("cube_counter", {"target": 3}, evdir / "discovery")
    return env.try_action("increment")


@pytest.fixture(scope="module")
def real_execution_result(tmp_path_factory) -> dict:
    """One real, correct, verified actuation through the ONLY actuation path."""
    if _SKIP is not None:
        pytest.skip(_SKIP)
    evdir = tmp_path_factory.mktemp("exec")
    validated = ValidatedPlan(plan=("increment",) * 3, model_digest="module-fixture")
    commitment = commit(validated, "module-fixture-trial")
    return commit_and_execute(
        commitment,
        "cube_counter",
        {"target": 3},
        {"counter": 3, "solved": True},
        evdir / "actuation",
    )


# --------------------------------------------------------------------------
# 1. Typed state
# --------------------------------------------------------------------------


@requires_gymact
def test_typed_state_preserves_continuous_dimension_as_unrepresentable(real_probe_record):
    observation = _observation_from_facts(real_probe_record["observed_pre_facts"])
    # The REAL observation shape, not an invented one.
    assert set(observation) == {"counter", "target", "reward", "solved"}, observation

    dims = classify_observation([observation])
    assert dims["reward"].kind is DimensionKind.CONTINUOUS
    assert dims["solved"].kind is DimensionKind.BOOLEAN
    assert dims["counter"].kind is DimensionKind.INTEGER
    assert dims["target"].kind is DimensionKind.INTEGER

    facts, losses = propositionalize(observation, dims)
    assert "reward" in losses
    assert losses["reward"].startswith("UNREPRESENTABLE:")
    # The lossy dimension is excluded, not silently encoded as a pseudo-fact.
    assert not any(f.startswith("reward=") for f in facts), sorted(facts)
    assert f"solved={observation['solved']}" in facts
    assert f"counter={observation['counter']}" in facts


# --------------------------------------------------------------------------
# 2. Causal refinement
# --------------------------------------------------------------------------


def test_causal_refinement_recovers_minimal_precondition():
    # Confounded log: A, B, C always co-occur in every successful pre-state,
    # so naive intersection cannot tell which one is load-bearing.
    probe_log = [
        {
            "action": "unlock",
            "applicable": True,
            "observed_pre_facts": ["A", "B", "C"],
            "delta_added": ["open"],
            "delta_removed": [],
        }
        for _ in range(3)
    ]
    domain = induce_discovered_domain(probe_log)
    naive = domain.actions["unlock"].preconditions
    assert naive == frozenset({"A", "B", "C"})
    assert domain.actions["unlock"].unresolved_semantics is True

    # Probe 1: hold {B, C}, drop A -> still succeeds => A is not causal.
    domain = refine_from_probe(domain, "unlock", frozenset({"B", "C"}), "A", succeeded=True)
    assert domain.actions["unlock"].preconditions == frozenset({"B", "C"})

    # Probe 2: hold {B}, drop C -> still succeeds => C is not causal.
    domain = refine_from_probe(domain, "unlock", frozenset({"B"}), "C", succeeded=True)
    assert domain.actions["unlock"].preconditions == frozenset({"B"})
    assert domain.actions["unlock"].unresolved_semantics is False


# --------------------------------------------------------------------------
# 3. Real probes, real deltas
# --------------------------------------------------------------------------


@requires_gymact
def test_real_gymact_probes_produce_real_state_deltas(tmp_path: Path):
    env = RealBlindEnvironment("cube_counter", {"target": 3}, tmp_path / "discovery")
    assert "increment" in env.available_actions()

    record = env.try_action("increment")
    assert record["applicable"] is True
    assert record["standing"] == "ALIVE"
    assert "counter=0" in record["observed_pre_facts"]
    assert "counter=1" in record["delta_added"]
    assert "counter=0" in record["delta_removed"]

    # A real episode was minted by GymAct itself, and the probe hit disk.
    assert env.episode_id()
    log_lines = (tmp_path / "discovery" / "probes.jsonl").read_text().splitlines()
    assert json.loads(log_lines[-1])["action"] == "increment"


# --------------------------------------------------------------------------
# 4. Real planner inventory
# --------------------------------------------------------------------------


def test_planner_federation_classifies_real_registered_solvers():
    classified = classify_registered_solvers(_counter_recipe())
    assert classified, "no solvers found in the autofde_lab.solvers entry-point group"
    supported = [c.name for c in classified if c.status == "SUPPORTED"]
    assert len(supported) >= 40, (len(supported), sorted(supported))
    assert "Astar" in supported
    # Every classification is a real verdict from a real check_domain call.
    astar = next(c for c in classified if c.name == "Astar")
    assert astar.entry_point


# --------------------------------------------------------------------------
# 5. Independent agreement across real planners
# --------------------------------------------------------------------------


def test_multiple_planners_independently_agree():
    recipe = _counter_recipe()
    supported = {c.name for c in classify_registered_solvers(recipe) if c.status == "SUPPORTED"}
    names = [n for n in ("Astar", "AOstar", "LRTAstar", "ILAOstar", "IDAstar") if n in supported]
    assert "Astar" in names and len(names) >= 3, sorted(supported)

    attempts = run_federation(recipe, names, timeout_s=20.0)
    candidates = [a for a in attempts if a.outcome == "PLAN_CANDIDATE"]
    assert len(candidates) >= 3, [(a.planner_identity, a.outcome, a.detail) for a in attempts]

    plans: dict[tuple[str, ...], int] = {}
    for a in candidates:
        plans[a.candidate_plan] = plans.get(a.candidate_plan, 0) + 1
    assert max(plans.values()) >= 2, plans
    # The agreed plan is a real, goal-reaching plan over the real recipe.
    agreed = max(plans, key=lambda p: plans[p])
    assert agreed == ("inc0", "inc1"), plans


# --------------------------------------------------------------------------
# 6. FALSIFIER -- advisory output cannot actuate
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "advisory",
    [
        ("increment", "increment", "increment"),
        PlannerAttempt(
            planner_identity="Astar",
            representation="recipe",
            problem_digest="deadbeef",
            outcome="PLAN_CANDIDATE",
            candidate_plan=("increment",),
        ),
        AdvisoryCritique(
            ranked_candidates=(("Astar", ("increment",), 10.0),),
            disagreement_detected=False,
            information_deficit=None,
            rationale="advisory only",
            source="deterministic",
        ),
    ],
    ids=["raw_plan_tuple", "planner_attempt", "advisory_critique"],
)
def test_advisory_output_cannot_actuate(advisory, tmp_path: Path):
    with pytest.raises(AdvisoryAuthorityRefused) as excinfo:
        commit_and_execute(
            advisory, "cube_counter", {"target": 3}, {"counter": 3}, tmp_path / "actuation"
        )
    assert "ADVISORY_AUTHORITY_USED_AS_BEARER" in str(excinfo.value)
    # Refusal happened before any actuation artifact was created.
    assert not (tmp_path / "actuation" / "receipts.sqlite3").exists()


# --------------------------------------------------------------------------
# 7. FALSIFIER -- dangling OCEL object reference
# --------------------------------------------------------------------------


def test_dangling_ocel_object_reference_is_detected():
    log = {
        "objectTypes": [{"name": "episode"}],
        "eventTypes": [{"name": "actuation"}],
        "objects": [{"id": "ep-1", "type": "episode"}],
        "events": [
            {
                "id": "ev-1",
                "type": "actuation",
                "relationships": [{"objectId": "ep-MISSING", "qualifier": "subject"}],
            }
        ],
    }
    violations = validate_ocel_referential_integrity(log)
    assert any(v.startswith("DANGLING_OBJECT_REFERENCE:") for v in violations), violations
    assert "ep-MISSING" in " ".join(violations)


@requires_gymact
def test_real_ocel_log_has_zero_referential_violations(real_execution_result):
    assert real_execution_result["ocel_valid"] is True, real_execution_result.get("ocel_error")
    violations = validate_ocel_referential_integrity(real_execution_result["ocel"])
    assert violations == [], violations
    assert real_execution_result["n_receipts"] > 0
    assert real_execution_result["independently_verified"] is True


# --------------------------------------------------------------------------
# 8. FALSIFIER -- wrong postcondition must refuse
# --------------------------------------------------------------------------


@requires_gymact
def test_postcondition_failure_refuses(tmp_path: Path):
    validated = ValidatedPlan(plan=("increment",), model_digest="wrong-postcondition")
    commitment = commit(validated, "refusal-trial")
    result = commit_and_execute(
        commitment,
        "cube_counter",
        {"target": 3},
        {"counter": 999},  # deliberately wrong
        tmp_path / "actuation",
    )
    standings = [t["standing"] for t in result["transitions"]]
    assert standings == ["REFUSED"], result["transitions"]
    assert result["independently_verified"] is False
    assert all(t["verified"] is False for t in result["transitions"])


# --------------------------------------------------------------------------
# 9. Zero-step plans
# --------------------------------------------------------------------------


def test_zero_step_plan_requires_goal_already_satisfied():
    with pytest.raises(ValueError) as excinfo:
        Recipe(
            gym="cube_counter",
            task="empty-unmet",
            source_ref="test",
            initial_facts=frozenset({"counter=0"}),
            goal_facts=frozenset({"counter=3"}),
            steps=(),
        )
    assert "no steps" in str(excinfo.value)

    accepted = Recipe(
        gym="cube_counter",
        task="empty-satisfied",
        source_ref="test",
        initial_facts=frozenset({"counter=0", "solved=True"}),
        goal_facts=frozenset({"solved=True"}),
        steps=(),
    )
    assert accepted.steps == ()
    assert accepted.goal_facts <= accepted.initial_facts

    # And the zero-step plan is independently valid against a discovered model
    # only because the goal already holds -- no action is fabricated.
    domain = DiscoveredDomain(state_variables=frozenset({"solved=True"}))
    problem = DiscoveredProblem(
        initial_state=frozenset({"solved=True"}), goal=frozenset({"solved=True"})
    )
    from autofde_lab.hub.domain.gym_procedure.level4_crown import independently_validate

    assert independently_validate((), domain, problem) is not None
    unmet = DiscoveredProblem(
        initial_state=frozenset({"counter=0"}), goal=frozenset({"solved=True"})
    )
    assert independently_validate((), domain, unmet) is None
