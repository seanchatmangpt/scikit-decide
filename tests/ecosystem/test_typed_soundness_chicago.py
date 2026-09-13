# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Regression suite for THE unified typed-model defect: absence of refusal
evidence was being modelled as proof of unconditional, repeatable
applicability.

One defect, three costumes, all three measured against real providers:

    lock_and_key   force_latch       learned repeatable locks_open +1
                                     | really ONE-SHOT, jams the rack forever
    switchboard    toggle_switch[i]  learned required_on +1
                                     | the second toggle turns the switch OFF
    resource_flow  burn_catalyst     learned output +2, no preconditions
                                     | the catalyst is spent; 2nd call REFUSED

The planner was never malfunctioning -- it optimally exploited a model that
promised a free repeatable gain. The repair inverts the default
(`repeatability_unknown`) and makes probing actively seek the refusal
evidence, by re-probing every never-refused action from the state its own
effect produced.

Chicago throughout: real GymAct episodes over the real `~/gymact/.venv`
subprocess bridge, the real `_discover_by_probing` loop, the real induction,
real files on disk, assertions on final state. No mocks. The gymact-backed
tests skip -- and only skip -- on the named blocker from `skip_reason()` when
the sibling checkout or its venv is genuinely absent.
"""

from __future__ import annotations

import pytest

from autofde_lab.hub.domain.gym_procedure.level4_crown import (
    _discover_by_probing,
    model_goal_predicate,
)
from autofde_lab.hub.domain.gym_procedure.level4_gymact_bridge import (
    RealBlindEnvironment,
    skip_reason,
)
from autofde_lab.hub.domain.gym_procedure.typed_induction import (
    induce_typed_domain,
    search_plan_typed,
)

_SKIP = skip_reason()
requires_gymact = pytest.mark.skipif(_SKIP is not None, reason=_SKIP or "")

PROBE_BUDGET = 40


def _discover(provider_key: str, config: dict, tmp_path):
    """Run the REAL probe loop against the REAL provider and induce the
    typed model from its real records. Returns (typed_domain, initial)."""
    env = RealBlindEnvironment(provider_key, config, tmp_path / "discovery")
    records, _n = _discover_by_probing(env, PROBE_BUDGET)
    typed = [r for r in records if "observed_pre" in r and "observed_post" in r]
    assert typed, "probing produced no typed records"
    return induce_typed_domain(typed), dict(typed[0]["observed_pre"])


def _counts(plan) -> dict[str, int]:
    out: dict[str, int] = {}
    for a in plan or ():
        out[a] = out.get(a, 0) + 1
    return out


# ==========================================================================
# COSTUME 1 -- lock_and_key / force_latch (one-shot, jams the rack)
# ==========================================================================


@requires_gymact
def test_force_latch_refusal_evidence_is_actively_sought_and_never_stacked(tmp_path):
    """Two properties in one real run, because the second only means
    anything given the first:

    1. Probing ACTIVELY discovers the jam. `force_latch` used to carry
       ``n_refusals == 0`` -- no evidence existed to bound it, so it got no
       precondition and no jam guard. Re-probing it from the state its own
       effect produced is the experiment that reveals the rack is jammed.
    2. It is therefore never stacked.
    """
    domain, initial = _discover("lock_and_key", {"depth": 3}, tmp_path)
    act = domain.actions["force_latch"]

    assert act.n_refusals >= 1, (
        "active experimentation found no refusal for force_latch; without it "
        "the action is modelled as unconditionally repeatable"
    )
    assert act.repeatability_unknown is True, [e.describe() for e in act.effects.values()]

    # The mechanism really fires on the REAL induced model: a second
    # force_latch is inapplicable, so no such plan can ever be validated.
    assert domain.simulate(initial, ("force_latch",)) is not None
    assert domain.simulate(initial, ("force_latch", "force_latch")) is None

    goal, _expr = model_goal_predicate("lock_and_key", initial, {"depth": 3})
    plan = search_plan_typed(domain, initial, goal, max_len=8)
    assert _counts(plan).get("force_latch", 0) <= 1, plan


# ==========================================================================
# COSTUME 2 -- switchboard / toggle_switch (self-inverse)
# ==========================================================================


@requires_gymact
def test_toggle_switch_is_never_planned_twice(tmp_path):
    config = {"seed": 4064909771, "n_switches": 4}
    domain, initial = _discover("switchboard", config, tmp_path)

    goal, _expr = model_goal_predicate("switchboard", initial, config)
    plan = search_plan_typed(domain, initial, goal, max_len=8)
    repeats = {a: c for a, c in _counts(plan).items() if c > 1}
    assert not repeats, f"plan repeats a self-inverse action: {plan}"

    # `required_on` is a COUNT DERIVED from self-inverse booleans. No
    # toggling action may carry it as a monotonic delta -- that inconsistency
    # (flip the switch AND gain +1 forever) is the gap the planner exploited.
    toggles = [a for a in domain.actions if a.startswith("toggle_switch")]
    assert toggles, sorted(domain.actions)
    for name in toggles:
        act = domain.actions[name]
        assert any(e.flip for e in act.effects.values()), name
        eff = act.effects.get("required_on")
        if eff is not None:
            assert eff.delta is None and eff.context_dependent, eff.describe()
        # And directly: applying the toggle twice returns its own switch.
        once = act.apply(initial)
        assert act.apply(once) == initial, name


# ==========================================================================
# COSTUME 3 -- resource_flow / burn_catalyst (consumable)
# ==========================================================================


@requires_gymact
def test_burn_catalyst_is_never_planned_twice(tmp_path):
    config = {"seed": 3979297810, "target": 3}
    domain, initial = _discover("resource_flow", config, tmp_path)
    act = domain.actions["burn_catalyst"]
    assert act.n_refusals >= 1, "no refusal evidence found for burn_catalyst"
    assert act.repeatability_unknown is True, [e.describe() for e in act.effects.values()]
    assert domain.simulate(initial, ("burn_catalyst", "burn_catalyst")) is None

    goal, _expr = model_goal_predicate("resource_flow", initial, config)
    plan = search_plan_typed(domain, initial, goal, max_len=10)
    # Non-vacuous: this provider really is still solvable under the model.
    assert plan is not None, "resource_flow became unplannable -- over-restriction"
    assert _counts(plan).get("burn_catalyst", 0) <= 1, plan


# ==========================================================================
# THE WORKING CASE MUST STILL WORK -- no over-restriction
# ==========================================================================


@requires_gymact
def test_cube_counter_still_finds_three_increments(tmp_path):
    """The inverted default must not make a genuinely repeatable action
    unusable. `increment` IS repeatable, and the new self-probe is what
    supplies the evidence: two successes from two different pre-states with
    the same +1 delta."""
    config = {"target": 3}
    domain, initial = _discover("cube_counter", config, tmp_path)
    inc = domain.actions["increment"]
    assert inc.n_distinct_success_states >= 2, inc
    assert inc.repeatability_unknown is False, [e.describe() for e in inc.effects.values()]

    goal, _expr = model_goal_predicate("cube_counter", initial, config)
    plan = search_plan_typed(domain, initial, goal, max_len=8)
    assert plan == ("increment",) * 3, plan
