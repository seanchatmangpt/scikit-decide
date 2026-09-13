# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style paired falsifier for `_dimensions_with_arithmetic_evidence`.

Every collaborator here is real: real `RealBlindEnvironment`/
`_discover_by_probing` driving the real `cube_counter`/`lock_and_key`
GymAct providers through the real subprocess bridge into `~/gymact`'s own
venv, and the real `induce_typed_domain` typed-effect induction. No mocks.

The defect this pins, found and root-caused this session on a real
`cube_counter` trial: `state_typing._is_categorical_id()` reclassifies an
`INTEGER` dimension to `CATEGORICAL_ID` (stripping arithmetic semantics)
whenever it observes a small distinct integer set including a negative
value -- a rule written for `lock_and_key`'s `held_key=-1` "no key held"
sentinel. Its own docstring states the premise it relies on: "counter/raw/
output/locks_open... never negative." `cube_counter`'s real `decrement`
action falsifies that premise directly, so `counter` was misclassified,
`induce_typed_domain` never claimed a delta for it, and `search_plan_typed`
had no rule to compose `increment` three times to reach an unobserved
`counter=3` -- an honest `NO_TYPED_VALID_PLAN` for a representational
reason, not a real one.

`_dimensions_with_arithmetic_evidence` supplies the missing behavioral
discriminator: real transition evidence (a consistent delta across >= 2
DISTINCT pre-state values, for some single action) outweighs the negative-
value coincidence. The bar is set precisely so it does not reopen the bug
`_is_categorical_id` exists to fix -- this is the paired falsifier that
proves that: `cube_counter`'s `counter` MUST regain arithmetic standing;
`lock_and_key`'s `held_key` MUST NOT.
"""

from __future__ import annotations

import pytest

from autofde_lab.hub.domain.gym_procedure.level4_crown import (
    _discover_by_probing,
    model_goal_predicate,
    run_real_trial,
)
from autofde_lab.hub.domain.gym_procedure.level4_gymact_bridge import (
    RealBlindEnvironment,
    skip_reason,
)
from autofde_lab.hub.domain.gym_procedure.state_typing import DimensionKind
from autofde_lab.hub.domain.gym_procedure.typed_induction import (
    induce_typed_domain,
    search_plan_typed,
)

pytestmark = pytest.mark.skipif(skip_reason() is not None, reason=str(skip_reason()))


def _typed_records(provider_key: str, config: dict, tmp_path, probe_budget: int = 40):
    env = RealBlindEnvironment(provider_key, config, tmp_path / "discovery")
    raw_records, _n = _discover_by_probing(env, probe_budget)
    return [r for r in raw_records if "observed_pre" in r and "observed_post" in r]


# ── cube_counter: a genuinely negative-going arithmetic quantity ─────────


def test_cube_counter_counter_regains_arithmetic_standing(tmp_path) -> None:
    typed_records = _typed_records("cube_counter", {"target": 3}, tmp_path)
    domain = induce_typed_domain(typed_records)

    assert domain.dimensions["counter"].kind is DimensionKind.INTEGER
    assert domain.dimensions["counter"].is_metric()

    increment_effect = domain.actions["increment"].effects["counter"]
    assert increment_effect.delta == 1.0
    assert not increment_effect.context_dependent


def test_cube_counter_typed_search_derives_unobserved_goal_state(tmp_path) -> None:
    """The actual payoff: a 3-step plan to `counter=3`, though `counter=3`
    itself was never observed during a bounded probe budget -- proof the
    fix restores real generalization, not just a reclassified label."""
    typed_records = _typed_records("cube_counter", {"target": 3}, tmp_path)
    observed_counters = {
        v
        for r in typed_records
        for v in (r["observed_pre"].get("counter"), r["observed_post"].get("counter"))
        if v is not None
    }
    assert 3 not in observed_counters, (
        "fixture premise gone: counter=3 was directly observed, so this test "
        "would no longer distinguish generalization from memorization"
    )

    domain = induce_typed_domain(typed_records)
    typed_initial = dict(typed_records[0]["observed_pre"])
    goal_predicate, _ = model_goal_predicate("cube_counter", typed_initial, {"target": 3})
    plan = search_plan_typed(domain, typed_initial, goal_predicate, max_len=12)

    assert plan == ("increment", "increment", "increment")


def test_cube_counter_real_trial_reaches_executed(tmp_path) -> None:
    """End-to-end regression: the fix closes the loop `run_real_trial`
    reported broken (`NO_TYPED_VALID_PLAN`) before this session's fix."""
    report = run_real_trial(3979297810, "cube_counter", {"target": 3}, tmp_path)
    assert report.outcome == "EXECUTED", report.outcome
    assert report.committed_plan == ("increment", "increment", "increment")


# ── lock_and_key: a genuine identity sentinel -- regression guard ────────


def test_lock_and_key_held_key_stays_non_arithmetic(tmp_path) -> None:
    """The other half of the paired falsifier: this is the exact bug
    `_is_categorical_id` was invented to fix (`held_key=-1` "no key held"),
    and the new behavioral override must not reopen it."""
    typed_records = _typed_records("lock_and_key", {"depth": 2}, tmp_path)
    domain = induce_typed_domain(typed_records)

    assert domain.dimensions["held_key"].kind is DimensionKind.CATEGORICAL_ID
    assert not domain.dimensions["held_key"].is_metric()

    # No action may claim a *delta* on held_key -- only absolute assignment
    # (an identity being set, not a quantity being changed) is sound here.
    for action_id, action in domain.actions.items():
        effect = action.effects.get("held_key")
        if effect is None:
            continue
        assert effect.delta is None, (
            f"{action_id} claimed a delta on held_key; the identity-sentinel "
            "regression guard has been reopened"
        )
