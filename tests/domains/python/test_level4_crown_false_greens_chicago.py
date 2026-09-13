# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Falsifiers for three FALSE GREENS in the Level 4 crown's evidence.

Each of these passed as green while the underlying fact was false:

a. `step_standings` read ALIVE for a step the provider itself reported
   inapplicable, because gymact's kernel never reads the `applicable` flag a
   provider returns from `actuate()` and the model's expectation for that
   step had dropped the only dimension that would have revealed it.
b. `unsound_candidates_rejected` was structurally pinned at 0: the loop that
   incremented it `break`-ed on the first accepted candidate.
c. `critique_candidates` labelled its output `source="dspy"` whenever a
   global `dspy.settings.lm` existed, then ranked deterministically and made
   zero LM calls.

Every collaborator is real: real gymact subprocess, real providers, real
receipts. The one test that needs an LM uses the REAL local TurboFieldfare
server over real HTTP with a named skip when it is not up -- a stub LM is
forbidden by this repo's Chicago rule.
"""

from __future__ import annotations

import pytest

from autofde_lab.hub.domain.gym_procedure.level4_crown import (
    ValidatedPlan,
    commit,
    commit_and_execute,
    critique_candidates,
    predict_step_postconditions,
)
from autofde_lab.hub.domain.gym_procedure.level4_gymact_bridge import skip_reason
from autofde_lab.hub.domain.gym_procedure.planner_federation import PlannerAttempt


def _lm_server_up() -> bool:
    """Real health check against the real local server.

    `autofde_lab.receipts.llm_agent.is_server_available` is the repo's own
    helper and does exactly this, but importing it drags in the optional
    `pydantic_integration` package, which is absent from this venv -- so the
    same two-line urllib GET is inlined rather than turning a missing
    optional dependency into a fake pass.
    """
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen("http://127.0.0.1:8080/health", timeout=2.0) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError):
        return False


# --------------------------------------------------------------------------
# (a) a provider-refused step must never be recorded ALIVE
# --------------------------------------------------------------------------


@pytest.mark.skipif(skip_reason() is not None, reason=str(skip_reason()))
def test_second_burn_catalyst_is_recorded_refused_not_alive(tmp_path) -> None:
    """The exact shape that produced ["ALIVE","ALIVE"] in frozen attempt 3.

    `resource-flow` allows `burn_catalyst` exactly once; the second call is
    inapplicable ("catalyst already burned") and moves nothing. The model's
    own oracle drops `output` after the first burn, so verification of the
    second step cannot see the failure -- the provider's verdict is the only
    honest witness, and it must win.
    """
    plan = ("burn_catalyst", "burn_catalyst")
    config = {"seed": 7, "capacity": 8, "target": 3}
    initial = {"capacity": 8, "target": 3, "mine_rate": 1, "raw": 0, "refined": 0, "output": 0}
    expected = predict_step_postconditions(plan, "resource_flow", initial)
    commitment = commit(ValidatedPlan(plan=plan, model_digest="d"), "trial-doubleburn")

    result = commit_and_execute(
        commitment, "resource_flow", config, expected, tmp_path / "doubleburn"
    )

    standings = [t["standing"] for t in result["transitions"]]
    assert standings == ["ALIVE", "REFUSED"], standings
    assert result["transitions"][0]["provider_applicable"] is True
    assert result["transitions"][1]["provider_applicable"] is False
    assert result["transitions"][1]["reason"].startswith("PROVIDER_REPORTED_INAPPLICABLE")
    # The receipt gymact itself issued really did say ALIVE -- which is
    # precisely why the provider verdict had to be read separately.
    assert result["transitions"][1]["receipt_standing"] == "ALIVE"
    # And the world really did not move on that second step.
    assert result["final_state"]["catalyst"] is False


@pytest.mark.skipif(skip_reason() is not None, reason=str(skip_reason()))
def test_applicable_step_still_records_alive(tmp_path) -> None:
    """The override must only ever turn a green red, never invent a red."""
    import random

    # `mine_rate` is seeded state the provider draws first from
    # `random.Random(seed)`; the oracle needs the real value or the ALIVE
    # steps would fail verification for an unrelated reason.
    mine_rate = random.Random(7).randint(1, 3)
    plan = ("mine", "mine")
    config = {"seed": 7, "capacity": 8, "target": 3}
    initial = {
        "capacity": 8, "target": 3, "mine_rate": mine_rate,
        "raw": 0, "refined": 0, "output": 0,
    }
    expected = predict_step_postconditions(plan, "resource_flow", initial)
    commitment = commit(ValidatedPlan(plan=plan, model_digest="d"), "trial-mine")

    result = commit_and_execute(commitment, "resource_flow", config, expected, tmp_path / "mine")

    assert [t["provider_applicable"] for t in result["transitions"]] == [True, True]
    assert [t["standing"] for t in result["transitions"]] == ["ALIVE", "ALIVE"]


# --------------------------------------------------------------------------
# (c) source="dspy" only after a real call that really validated
# --------------------------------------------------------------------------


def _attempts() -> list[PlannerAttempt]:
    return [
        PlannerAttempt(
            planner_identity="alpha",
            representation="Recipe",
            problem_digest="d",
            outcome="PLAN_CANDIDATE",
            candidate_plan=("mine", "refine", "assemble"),
        ),
        PlannerAttempt(
            planner_identity="beta",
            representation="Recipe",
            problem_digest="d",
            outcome="PLAN_CANDIDATE",
            candidate_plan=("burn_catalyst",),
        ),
    ]


class _EmptyDomain:
    actions: dict = {}


def test_lm_none_is_deterministic_and_needs_no_server() -> None:
    """Always runs. The default path must never claim an LM contributed."""
    critique = critique_candidates(_attempts(), _EmptyDomain(), lm=None)

    assert critique.source == "deterministic"
    assert critique.disagreement_detected is True
    # Deterministic ranking is unchanged: shorter plan, same vote count.
    assert critique.ranked_candidates[0][1] == ("burn_catalyst",)


def test_default_argument_is_deterministic_even_with_a_global_dspy_lm() -> None:
    """The precise defect: a configured global LM used to flip the label with
    no call made. Configuring one here must change nothing."""
    dspy = pytest.importorskip("dspy")
    from autofde_lab.hub.solver.dspy_policy.dspy_policy import default_lm

    previous = getattr(dspy.settings, "lm", None)
    dspy.configure(lm=default_lm())
    try:
        critique = critique_candidates(_attempts(), _EmptyDomain())
    finally:
        dspy.configure(lm=previous)

    assert critique.source == "deterministic"


def test_real_local_lm_call_yields_source_dspy() -> None:
    """Real HTTP against the real local TurboFieldfare server, no stub."""
    pytest.importorskip("dspy")
    from autofde_lab.hub.solver.dspy_policy.dspy_policy import default_lm
    if not _lm_server_up():
        pytest.skip("no local LM server on 127.0.0.1:8080")

    attempts = _attempts()
    critique = critique_candidates(attempts, _EmptyDomain(), lm=default_lm())

    assert critique.source == "dspy"
    # Whatever it chose must be a REAL candidate, never a hallucination.
    real_plans = {tuple(a.candidate_plan) for a in attempts}
    assert critique.ranked_candidates[0][1] in real_plans


# --------------------------------------------------------------------------
# lock_and_key representation: CATEGORICAL_ID + relational-precondition refusal
# --------------------------------------------------------------------------


def test_held_key_is_categorical_id_not_a_metric_integer() -> None:
    from autofde_lab.hub.domain.gym_procedure.state_typing import (
        DimensionKind,
        classify_observation,
    )

    dims = classify_observation(
        [
            {"held_key": -1, "locks_open": 0, "depth": 3},
            {"held_key": 2, "locks_open": 1, "depth": 3},
            {"held_key": -1, "locks_open": 2, "depth": 3},
        ]
    )

    assert dims["held_key"].kind is DimensionKind.CATEGORICAL_ID
    assert dims["held_key"].is_metric() is False
    # The narrow discriminator must not steal ordinary counters.
    assert dims["locks_open"].kind is DimensionKind.INTEGER
    assert dims["locks_open"].is_metric() is True


def test_pick_key_learns_an_absolute_identity_not_a_delta() -> None:
    """The measured category error: -1 -> 2 induced `held_key: +3`, so the
    model believed a second `pick_key[key=2]` would leave key 5 in hand."""
    from autofde_lab.hub.domain.gym_procedure.typed_induction import induce_typed_domain

    records = [
        {
            "action": "pick_key[key=2]",
            "applicable": True,
            "observed_pre": {"held_key": -1, "locks_open": 0},
            "observed_post": {"held_key": 2, "locks_open": 0},
        },
        {
            "action": "drop_key",
            "applicable": True,
            "observed_pre": {"held_key": 2, "locks_open": 0},
            "observed_post": {"held_key": -1, "locks_open": 0},
        },
    ]
    domain = induce_typed_domain(records)
    eff = domain.actions["pick_key[key=2]"].effects["held_key"]

    assert eff.delta is None
    assert eff.absolute_value == 2
    state = domain.actions["pick_key[key=2]"].apply({"held_key": -1})
    assert state["held_key"] == 2


def test_relational_precondition_is_reported_unrepresentable_and_refused() -> None:
    """`open_lock` succeeds behind key 1 and is refused behind key 1 later
    (the permutation moved on). No flat `dimension -> constant` map can
    explain both, so the model must say UNREPRESENTABLE and the planner must
    refuse rather than commit."""
    from autofde_lab.hub.domain.gym_procedure.typed_induction import (
        induce_typed_domain,
        validate_plan_typed,
    )

    records = [
        {
            "action": "open_lock",
            "applicable": True,
            "observed_pre": {"held_key": 1, "locks_open": 0},
            "observed_post": {"held_key": -1, "locks_open": 1},
        },
        {
            "action": "open_lock",
            "applicable": False,
            "observed_pre": {"held_key": 1, "locks_open": 1},
            "observed_post": {"held_key": 1, "locks_open": 1},
        },
    ]
    domain = induce_typed_domain(records)

    assert domain.actions["open_lock"].unrepresentable == (
        "UNREPRESENTABLE:RELATIONAL_PRECONDITION"
    )
    ok, _final, reason = validate_plan_typed(
        domain, {"held_key": 1, "locks_open": 0}, ("open_lock",), lambda s: True
    )
    assert ok is False
    assert reason == "UNREPRESENTABLE:RELATIONAL_PRECONDITION"


def test_a_flat_precondition_that_really_explains_refusals_stays_representable() -> None:
    """The detector must only fire on a REAL falsification."""
    from autofde_lab.hub.domain.gym_procedure.typed_induction import induce_typed_domain

    records = [
        {
            "action": "engage_master",
            "applicable": True,
            "observed_pre": {"switch_0": True, "master": False},
            "observed_post": {"switch_0": True, "master": True},
        },
        {
            "action": "engage_master",
            "applicable": False,
            "observed_pre": {"switch_0": False, "master": False},
            "observed_post": {"switch_0": False, "master": False},
        },
    ]
    domain = induce_typed_domain(records)

    assert domain.actions["engage_master"].preconditions == {"switch_0": True}
    assert domain.actions["engage_master"].unrepresentable is None


# --------------------------------------------------------------------------
# (b) unsound_candidates_rejected must be able to be non-zero
# --------------------------------------------------------------------------


def test_every_unsound_candidate_is_counted_not_only_those_before_the_first_valid() -> None:
    """Real TypedDomain induced from real probe records, real PlannerAttempts,
    the real ranking function, and the same validation helper `run_real_trial`
    calls. The old loop broke on the first valid plan, so a candidate ranked
    AFTER it could never be counted -- here the valid plan ranks first and two
    unsound ones follow, which is exactly the shape that read 0."""
    from autofde_lab.hub.domain.gym_procedure.level4_crown import (
        validate_federation_candidates,
    )
    from autofde_lab.hub.domain.gym_procedure.typed_induction import induce_typed_domain

    # `increment` really moves counter by +1, observed twice from two
    # different pre-states, so it is a repeatable metric effect.
    records = [
        {
            "action": "increment",
            "applicable": True,
            "observed_pre": {"counter": 0, "target": 2},
            "observed_post": {"counter": 1, "target": 2},
        },
        {
            "action": "increment",
            "applicable": True,
            "observed_pre": {"counter": 1, "target": 2},
            "observed_post": {"counter": 2, "target": 2},
        },
    ]
    typed = induce_typed_domain(records)
    initial = {"counter": 0, "target": 2}
    goal = lambda s: s.get("counter") == s.get("target")  # noqa: E731

    attempts = [
        PlannerAttempt("good", "Recipe", "d", "PLAN_CANDIDATE", ("increment", "increment")),
        PlannerAttempt("short", "Recipe", "d", "PLAN_CANDIDATE", ("increment",)),
        PlannerAttempt("bogus", "Recipe", "d", "PLAN_CANDIDATE", ("no_such_action",)),
    ]
    ranked = critique_candidates(attempts, _EmptyDomain(), lm=None).ranked_candidates
    validated, source, verdicts = validate_federation_candidates(
        typed, initial, ranked, goal
    )
    rejected = sum(1 for v in verdicts if not v["valid"])

    assert validated is not None
    assert validated.plan == ("increment", "increment")
    assert source == "federation:good"
    assert len(verdicts) == 3
    assert rejected == 2, verdicts
    reasons = {v["reason"] for v in verdicts if not v["valid"]}
    assert reasons == {
        "GOAL_NOT_REACHED_UNDER_TYPED_MODEL",
        "PLAN_INAPPLICABLE_UNDER_TYPED_MODEL",
    }
