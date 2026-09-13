# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests closing the fourth instance of the lab/production
standing boundary gap (`V2030.1.1-PRD-ARD.md` capability 9; falsifier "if
benchmark success grants production actuation") -- this time for
`planner_league.disturbance_episode.DisturbanceEpisodeResult`, the real
adversarial-episode outcome introduced by capability 6's `red_disturbance`
episodes (PR#112) and never wired into this boundary when it later
generalized past `LabResultStanding` (PR#123, PR#124).

`DisturbanceEpisodeResult.standing` is a `DisturbanceStanding` (`SURVIVES` /
`FALSIFIED` / `UNKNOWN`) -- the same shape `FalsificationStanding` already
carries -- and `disturbance_result_to_payoff()` projects a `SURVIVES`
standing into a `PayoffObservation` tagged
`f"ALIVE:DISTURBANCE_PAYOFF:{result.standing.value}"`. `disturbance_episode.py`
is untouched by this change: that projection is real, legitimate evidence
*within* the lab domain. The gap closed here is only that nothing stopped a
`DisturbanceEpisodeResult` from crossing the lab/production boundary if fed
into `fabric.enterprise_standing.derive_enterprise_standing` as though it
were observed production evidence.

Every collaborator is real: a real `DisturbanceEpisodeResult` produced by
`run_disturbance_episode` against the real `generic_enterprise` maze world
and the real installed `Astar` solver -- the exact same real setup
`tests/planner_league/test_disturbance_episode_chicago.py` already uses --
the real `disturbance_episode_production_claim`, and the real
`derive_enterprise_standing` over the same committed Turtle fixture the
other two boundary test files use. Assertions are on returned state only.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from autofde_lab.fabric.enterprise_standing import derive_enterprise_standing
from autofde_lab.fabric.fde import parse_authority_turtle
from autofde_lab.hub.domain.maze.maze import State
from autofde_lab.planner_league.disturbance_episode import (
    Disturbance,
    DisturbanceEpisodeResult,
    DisturbanceStanding,
    run_disturbance_episode,
)
from autofde_lab.reasoning.lab_standing import (
    PRODUCTION_CLAIM_REFUSAL,
    disturbance_episode_production_claim,
    experiment_receipt_production_claim,
)
from autofde_lab.reasoning.laboratory import ExperimentReceipt

FIXTURES = Path(__file__).resolve().parents[1] / "ecosystem" / "fixtures" / "fde"
BASE = FIXTURES / "customer-authority.ttl"

WORLD_ID = "generic_enterprise"
CONSTRUCTOR = "Astar"


def _survives_result() -> DisturbanceEpisodeResult:
    # A no-op disturbance at step 0 always survives -- the same real setup
    # test_disturbance_episode_chicago.py's own `_plan_length()` probe uses.
    result = run_disturbance_episode(
        WORLD_ID, CONSTRUCTOR, Disturbance("noop-probe", 0, lambda s: s)
    )
    assert result.standing is DisturbanceStanding.SURVIVES, result.reason
    return result


def test_survives_standing_result_still_refuses_a_production_claim() -> None:
    """The most dangerous-looking case: a real disturbance episode that
    SURVIVES -- the repo's own red-team apparatus failed to falsify the
    plan -- still refuses identically."""
    result = _survives_result()

    claim = disturbance_episode_production_claim(result)

    assert claim == "UNKNOWN:LAB_RESULT_NOT_PRODUCTION_EVIDENCE"
    assert claim == PRODUCTION_CLAIM_REFUSAL
    assert claim != "ALIVE"


def test_refusal_forwarded_into_enterprise_standing_fails_closed() -> None:
    model = parse_authority_turtle(BASE.read_text(encoding="utf-8"))
    result = _survives_result()
    claim = disturbance_episode_production_claim(result)

    standing = derive_enterprise_standing(model, technical_standing=claim)

    assert standing.technical_standing == claim
    assert standing.enterprise_standing == "UNKNOWN"
    assert standing.organizational_standing == "UNKNOWN"


def test_falsified_and_unknown_standing_results_refuse_identically() -> None:
    """The boundary does not depend on the episode's own internal standing
    at all: a real FALSIFIED result (disturbance placed behind a wall the
    replayed plan cannot cross, per `test_disturbance_episode_chicago.py`'s
    own maze geometry: `(1, 19)` is open, its southern neighbour `(1, 20)`
    is a wall) and a real UNKNOWN result (disturbance beyond the plan's
    length) both refuse the exact same way SURVIVES did."""
    plan_length = _survives_result().plan_length
    behind_wall = State(1, 20)
    falsified = run_disturbance_episode(
        WORLD_ID,
        CONSTRUCTOR,
        Disturbance("relocate-behind-wall", plan_length - 1, lambda _s: behind_wall),
    )
    assert falsified.standing is DisturbanceStanding.FALSIFIED, falsified.reason
    beyond_plan = run_disturbance_episode(
        WORLD_ID, CONSTRUCTOR, Disturbance("beyond-plan", 10_000, lambda s: s)
    )
    assert beyond_plan.standing is DisturbanceStanding.UNKNOWN, beyond_plan.reason

    assert disturbance_episode_production_claim(falsified) == PRODUCTION_CLAIM_REFUSAL
    assert disturbance_episode_production_claim(beyond_plan) == PRODUCTION_CLAIM_REFUSAL


def test_disturbance_claim_reuses_the_exact_same_refusal_object_as_the_other_boundaries() -> (
    None
):
    """Catches a second definition of the same refusal string: this must
    be the identical object the `ExperimentReceipt` boundary (and, via it,
    `LabResultStanding`/`ExplorationPayoffOutcome`) already returns, not a
    look-alike."""
    result = _survives_result()

    disturbance_claim = disturbance_episode_production_claim(result)

    assert disturbance_claim is PRODUCTION_CLAIM_REFUSAL

    receipt = ExperimentReceipt(
        intent_id="intent-identity-disturbance-1",
        observed_outcome_refs=("outcome-identity-disturbance-1",),
        standing="ALIVE",
    )
    receipt_claim = experiment_receipt_production_claim(receipt)

    assert disturbance_claim == receipt_claim
    assert disturbance_claim is receipt_claim


def test_disturbance_claim_requires_a_real_disturbance_episode_result() -> None:
    with pytest.raises(
        TypeError, match="DISTURBANCE_EPISODE_CLAIM_REQUIRES_REAL_RESULT"
    ):
        disturbance_episode_production_claim("ALIVE")  # type: ignore[arg-type]
