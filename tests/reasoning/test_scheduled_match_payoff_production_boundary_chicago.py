# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests closing the sixth instance of the lab/production
standing boundary gap (`V2030.1.1-PRD-ARD.md` capability 9; falsifier "if
benchmark success grants production actuation") -- this time for
`cross_play_schedule_payoff.ScheduledMatchPayoffOutcome`, whose own module
docstring says it reuses `dflss_solve_payoff_bridge`'s established
`1.0 ALIVE / 0.0 otherwise` score contract, but which was never given a
`lab_standing.py` counterpart when it was introduced.

`ScheduledMatchPayoffOutcome.standing` legitimately carries this repo's
generic cross-module success token `'ALIVE'` (real fixtures in
`tests/reasoning/test_cross_play_schedule_payoff_chicago.py` construct an
outcome exactly this way: `AOstar` really solving `BreachClockDomain` to
its real goal in 6 actions). `cross_play_schedule_payoff.py` is untouched
by this change: the gap closed here is only that nothing stopped
`outcome.standing` from crossing the lab/production boundary if fed into
`fabric.enterprise_standing.derive_enterprise_standing` as though it were
observed production evidence.

Every collaborator is real: a real `ScheduledMatchPayoffOutcome` produced
by `admit_cross_play_schedule_payoffs` against a real `BreachClockDomain`
and a real scheduled `LeagueMatch` -- the exact same real setup
`test_cross_play_schedule_payoff_chicago.py` already uses -- the real
`scheduled_match_payoff_production_claim`, and the real
`derive_enterprise_standing` over the same committed Turtle fixture the
other boundary test files use. Assertions are on returned state only.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from autofde_lab.fabric.enterprise_standing import derive_enterprise_standing
from autofde_lab.fabric.fde import parse_authority_turtle
from autofde_lab.hub.domain.breach_clock import BreachClockDomain
from autofde_lab.planner_league import PayoffHypergraph, PlannerLeague
from autofde_lab.planner_league.cross_play_world_schedule import (
    schedule_cross_play_for_world,
)
from autofde_lab.reasoning.cross_play_schedule_payoff import (
    ScheduledMatchPayoffOutcome,
    admit_cross_play_schedule_payoffs,
)
from autofde_lab.reasoning.lab_standing import (
    PRODUCTION_CLAIM_REFUSAL,
    experiment_receipt_production_claim,
    scheduled_match_payoff_production_claim,
)
from autofde_lab.reasoning.laboratory import ExperimentReceipt

FIXTURES = Path(__file__).resolve().parents[1] / "ecosystem" / "fixtures" / "fde"
BASE = FIXTURES / "customer-authority.ttl"


def _alive_scheduled_outcome() -> ScheduledMatchPayoffOutcome:
    # The same real setup test_cross_play_schedule_payoff_chicago.py
    # confirms: AOstar vs AOstar both really solve BreachClockDomain.
    league = PlannerLeague()
    schedule = schedule_cross_play_for_world(
        league,
        "cyber_incident",
        left_role_id="plan_constructor",
        right_role_id="plan_falsifier",
    )
    domain = BreachClockDomain()
    hypergraph = PayoffHypergraph()
    outcomes = admit_cross_play_schedule_payoffs(
        schedule, domain, hypergraph=hypergraph, limit=1
    )
    outcome = outcomes[0]
    assert outcome.standing == "ALIVE", outcome.reason
    return outcome


def test_alive_standing_outcome_still_refuses_a_production_claim() -> None:
    """The most dangerous-looking case: a real scheduled-match outcome
    whose own `standing` is the literal success token `'ALIVE'` -- still
    refuses identically."""
    outcome = _alive_scheduled_outcome()

    claim = scheduled_match_payoff_production_claim(outcome)

    assert claim == "UNKNOWN:LAB_RESULT_NOT_PRODUCTION_EVIDENCE"
    assert claim == PRODUCTION_CLAIM_REFUSAL
    assert claim != "ALIVE"


def test_refusal_forwarded_into_enterprise_standing_fails_closed() -> None:
    model = parse_authority_turtle(BASE.read_text(encoding="utf-8"))
    outcome = _alive_scheduled_outcome()
    claim = scheduled_match_payoff_production_claim(outcome)

    standing = derive_enterprise_standing(model, technical_standing=claim)

    assert standing.technical_standing == claim
    assert standing.enterprise_standing == "UNKNOWN"
    assert standing.organizational_standing == "UNKNOWN"


def test_scheduled_match_claim_reuses_the_exact_same_refusal_object_as_the_other_boundaries() -> (
    None
):
    """Catches a second definition of the same refusal string: this must
    be the identical object the `ExperimentReceipt` boundary (and, via it,
    every other boundary in this module) already returns, not a
    look-alike."""
    outcome = _alive_scheduled_outcome()

    scheduled_claim = scheduled_match_payoff_production_claim(outcome)

    assert scheduled_claim is PRODUCTION_CLAIM_REFUSAL

    receipt = ExperimentReceipt(
        intent_id="intent-identity-scheduled-1",
        observed_outcome_refs=("outcome-identity-scheduled-1",),
        standing="ALIVE",
    )
    receipt_claim = experiment_receipt_production_claim(receipt)

    assert scheduled_claim == receipt_claim
    assert scheduled_claim is receipt_claim


def test_scheduled_match_claim_requires_a_real_scheduled_match_payoff_outcome() -> None:
    with pytest.raises(
        TypeError, match="SCHEDULED_MATCH_PAYOFF_CLAIM_REQUIRES_REAL_OUTCOME"
    ):
        scheduled_match_payoff_production_claim("ALIVE")  # type: ignore[arg-type]
