# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests closing the gap left open by the adversarial refute
pass on V2030.1.1 capability 9 (PR#111, `lab_standing.py`): that pass gave
`laboratory.falsify_candidate`'s `LabResultStanding` a typed boundary
against production claims (`production_technical_claim`), but
`exploration_payoff_bridge.admit_exploration_candidate_payoff`'s
`ExplorationPayoffOutcome` is a *second*, independent real producer of
lab-scoped evidence and had no such boundary. `ExplorationPayoffOutcome`
uses this repo's generic cross-module success token `'ALIVE'` for an
ordinary successful admission (the same token 30+ other tests across
reasoning/, planner_league/, and psro assert for ordinary successes) --
that token is correct and untouched here. The gap this file closes is
narrower: nothing stopped a caller from forwarding that outcome's evidence
into `derive_enterprise_standing(technical_standing=...)` as if it were
observed production evidence. `exploration_payoff_production_claim` closes
that gap the same way `production_technical_claim` already closes it for
`LabResultStanding`.

Real collaborators throughout: a real `Maze` domain, a real `PlannerLeague`
resolving real `Astar`/`MCTS`/`CIDual` solver entry points, real
`generate_triz_candidates` output, a real `ExperimentReceipt` +
`falsify_candidate` result, a real `PayoffHypergraph`, and the real
`derive_enterprise_standing` over the real committed
`tests/ecosystem/fixtures/fde/customer-authority.ttl` `AuthorityModel` --
the same fixture `test_lab_standing_boundary_chicago.py` and
`tests/ecosystem/test_enterprise_standing_chicago.py` already use. No
`unittest.mock` / `Mock` / `MagicMock` / `patch` / `monkeypatch` anywhere in
this file.
"""

from __future__ import annotations

from pathlib import Path

from autofde_lab.fabric.enterprise_standing import derive_enterprise_standing
from autofde_lab.fabric.fde import parse_authority_turtle
from autofde_lab.hub.domain.maze import Maze
from autofde_lab.planner_league import PayoffHypergraph, PlannerLeague
from autofde_lab.reasoning.exploration_payoff_bridge import (
    admit_exploration_candidate_payoff,
)
from autofde_lab.reasoning.lab_standing import (
    PRODUCTION_CLAIM_REFUSAL,
    exploration_payoff_production_claim,
)
from autofde_lab.reasoning.laboratory import (
    ExperimentReceipt,
    TRIZContradiction,
    TRIZParameter,
    falsify_candidate,
    generate_triz_candidates,
)

FIXTURES = Path(__file__).resolve().parents[1] / "ecosystem" / "fixtures" / "fde"
BASE = FIXTURES / "customer-authority.ttl"


def _hypothesis():
    from autofde_lab.reasoning.laboratory import DesiredStateHypothesis

    return DesiredStateHypothesis(
        hypothesis_id="rule-based-v1",
        targets=({"kind": "latency_reduction"},),
        evidence_used_refs=("obs-1",),
    )


def test_real_admitted_alive_payoff_outcome_still_refuses_production_claim() -> None:
    """A real, successfully-admitted `ExplorationPayoffOutcome`
    (`standing == 'ALIVE'`, a real `PayoffObservation` attached) still
    refuses via the new boundary function with the exact same
    `'UNKNOWN:LAB_RESULT_NOT_PRODUCTION_EVIDENCE'` string
    `production_technical_claim` uses for `LabResultStanding`."""
    contradiction = TRIZContradiction(
        improving_parameter=TRIZParameter.COST,
        worsening_parameter=TRIZParameter.AUTHORITY_NEEDS,
    )
    candidate = generate_triz_candidates((_hypothesis(),), contradiction)[0]

    receipt = ExperimentReceipt(
        intent_id="intent-triz-1",
        observed_outcome_refs=("outcome-1",),
        standing="ALIVE",
        postconditions_observed=("latency_reduced",),
    )
    falsification = falsify_candidate(candidate, receipts=(receipt,))

    outcome = admit_exploration_candidate_payoff(
        candidate,
        falsification,
        league=PlannerLeague(),
        domain=Maze(),
        hypergraph=PayoffHypergraph(),
        world_id="generic_enterprise",
        constructor_planner_id="Astar",
        falsifier_planner_id="MCTS",
    )

    assert outcome.standing == "ALIVE"
    assert outcome.admitted
    assert outcome.observation is not None

    claim = exploration_payoff_production_claim(outcome)
    assert claim == PRODUCTION_CLAIM_REFUSAL
    assert claim == "UNKNOWN:LAB_RESULT_NOT_PRODUCTION_EVIDENCE"
    assert claim != "ALIVE"


def test_forwarding_the_admitted_payoff_refusal_into_enterprise_standing_fails_closed() -> (
    None
):
    """Feeding the refusal string derived from a real, successfully-admitted
    payoff outcome into the real `derive_enterprise_standing` (over the real
    customer-authority.ttl `AuthorityModel`) yields enterprise standing
    `'UNKNOWN'`, fail-closed, with no exception raised."""
    contradiction = TRIZContradiction(
        improving_parameter=TRIZParameter.COST,
        worsening_parameter=TRIZParameter.AUTHORITY_NEEDS,
    )
    candidate = generate_triz_candidates((_hypothesis(),), contradiction)[0]
    receipt = ExperimentReceipt(
        intent_id="intent-triz-1",
        observed_outcome_refs=("outcome-1",),
        standing="ALIVE",
        postconditions_observed=("latency_reduced",),
    )
    falsification = falsify_candidate(candidate, receipts=(receipt,))
    outcome = admit_exploration_candidate_payoff(
        candidate,
        falsification,
        league=PlannerLeague(),
        domain=Maze(),
        hypergraph=PayoffHypergraph(),
        world_id="generic_enterprise",
        constructor_planner_id="Astar",
        falsifier_planner_id="MCTS",
    )
    assert outcome.standing == "ALIVE"

    claim = exploration_payoff_production_claim(outcome)
    model = parse_authority_turtle(BASE.read_text(encoding="utf-8"))

    standing = derive_enterprise_standing(model, technical_standing=claim)

    assert standing.technical_standing == claim
    assert standing.enterprise_standing == "UNKNOWN"
    assert standing.organizational_standing == "UNKNOWN"


def test_real_refused_payoff_outcome_refuses_the_exact_same_way() -> None:
    """A real refused/unadmitted `ExplorationPayoffOutcome`
    (`standing != 'ALIVE'`, `observation is None`) refuses identically --
    the boundary does not depend on which internal standing the outcome
    carries, and does not branch on whether a payoff was actually admitted."""
    contradiction = TRIZContradiction(
        improving_parameter=TRIZParameter.COST,
        worsening_parameter=TRIZParameter.AUTHORITY_NEEDS,
    )
    candidate = generate_triz_candidates((_hypothesis(),), contradiction)[0]
    # Real falsify_candidate contract: zero receipts -> real UNKNOWN standing,
    # which admit_exploration_candidate_payoff refuses to score (no real
    # PayoffObservation ever constructed).
    falsification = falsify_candidate(candidate, receipts=())

    outcome = admit_exploration_candidate_payoff(
        candidate,
        falsification,
        league=PlannerLeague(),
        domain=Maze(),
        hypergraph=PayoffHypergraph(),
        world_id="generic_enterprise",
        constructor_planner_id="Astar",
        falsifier_planner_id="MCTS",
    )

    assert outcome.standing == "UNKNOWN"
    assert not outcome.admitted
    assert outcome.observation is None

    claim = exploration_payoff_production_claim(outcome)
    assert claim == PRODUCTION_CLAIM_REFUSAL


def test_exploration_payoff_claim_requires_a_real_outcome() -> None:
    """The boundary is constructible only against a real
    `ExplorationPayoffOutcome` -- no way to mint the refusal from a bare
    string or an unrelated object, so it always traces back to a real
    `admit_exploration_candidate_payoff` call."""
    import pytest

    with pytest.raises(
        TypeError, match="EXPLORATION_PAYOFF_CLAIM_REQUIRES_REAL_OUTCOME"
    ):
        exploration_payoff_production_claim("ALIVE")  # type: ignore[arg-type]
