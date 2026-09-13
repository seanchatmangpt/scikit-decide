# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests closing the fifth instance of the lab/production
standing boundary gap (`V2030.1.1-PRD-ARD.md` capability 9; falsifier "if
benchmark success grants production actuation") -- this time for
`dflss_solve_payoff_bridge.DflssSolvePayoffOutcome`, whose own module
docstring says it "mirrors `ExplorationPayoffOutcome`'s own
`(observation/standing/reason)` shape", but which was never given a
`lab_standing.py` counterpart when it was introduced, and which now has a
real, externally-visible consumer: `fabric.cli`'s `dmedi-solve-payoff`
subcommand, which emits `result.standing` directly as CLI JSON output.

`DflssSolvePayoffOutcome.standing` legitimately carries this repo's generic
cross-module success token `'ALIVE'` (real fixtures in
`tests/reasoning/test_dflss_solve_payoff_bridge_chicago.py` construct an
outcome exactly this way, confirming both `Astar` and `LRTAstar` reach the
DMEDI-curriculum goal in 52 actions -- an honest tie). Neither
`dflss_solve_payoff_bridge.py` nor the CLI's own `standing` field is
touched by this change: the gap closed here is only that nothing stopped
`outcome.standing` from crossing the lab/production boundary if fed into
`fabric.enterprise_standing.derive_enterprise_standing` as though it were
observed production evidence.

Every collaborator is real: a real `DflssSolvePayoffOutcome` produced by
`admit_dflss_solve_payoff("Astar", "LRTAstar", ...)` -- the exact same real
setup `test_dflss_solve_payoff_bridge_chicago.py` already uses -- the real
`dflss_solve_payoff_production_claim`, and the real
`derive_enterprise_standing` over the same committed Turtle fixture the
other boundary test files use. Assertions are on returned state only.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from autofde_lab.fabric.enterprise_standing import derive_enterprise_standing
from autofde_lab.fabric.fde import parse_authority_turtle
from autofde_lab.planner_league import PayoffHypergraph
from autofde_lab.reasoning.dflss_solve_payoff_bridge import (
    DflssSolvePayoffOutcome,
    admit_dflss_solve_payoff,
)
from autofde_lab.reasoning.lab_standing import (
    PRODUCTION_CLAIM_REFUSAL,
    dflss_solve_payoff_production_claim,
    experiment_receipt_production_claim,
)
from autofde_lab.reasoning.laboratory import ExperimentReceipt

FIXTURES = Path(__file__).resolve().parents[1] / "ecosystem" / "fixtures" / "fde"
BASE = FIXTURES / "customer-authority.ttl"


def _alive_tie_outcome() -> DflssSolvePayoffOutcome:
    # The same real head-to-head tie test_dflss_solve_payoff_bridge_chicago.py
    # already confirms: Astar and LRTAstar both reach the goal in 52 actions.
    hypergraph = PayoffHypergraph()
    result = admit_dflss_solve_payoff("Astar", "LRTAstar", hypergraph=hypergraph)
    assert result.standing == "ALIVE", result.reason
    return result


def test_alive_standing_outcome_still_refuses_a_production_claim() -> None:
    """The most dangerous-looking case: a real head-to-head outcome whose
    own `standing` is the literal success token `'ALIVE'` -- still refuses
    identically."""
    outcome = _alive_tie_outcome()

    claim = dflss_solve_payoff_production_claim(outcome)

    assert claim == "UNKNOWN:LAB_RESULT_NOT_PRODUCTION_EVIDENCE"
    assert claim == PRODUCTION_CLAIM_REFUSAL
    assert claim != "ALIVE"


def test_refusal_forwarded_into_enterprise_standing_fails_closed() -> None:
    model = parse_authority_turtle(BASE.read_text(encoding="utf-8"))
    outcome = _alive_tie_outcome()
    claim = dflss_solve_payoff_production_claim(outcome)

    standing = derive_enterprise_standing(model, technical_standing=claim)

    assert standing.technical_standing == claim
    assert standing.enterprise_standing == "UNKNOWN"
    assert standing.organizational_standing == "UNKNOWN"


def test_refused_planner_outcome_refuses_identically() -> None:
    """The boundary does not depend on the outcome's own internal standing
    at all: a real domain-incompatible-planner outcome refuses the exact
    same way the `'ALIVE'` tie above did."""
    hypergraph = PayoffHypergraph()
    result = admit_dflss_solve_payoff("Astar", "CIDual", hypergraph=hypergraph)

    assert dflss_solve_payoff_production_claim(result) == PRODUCTION_CLAIM_REFUSAL


def test_dflss_claim_reuses_the_exact_same_refusal_object_as_the_other_boundaries() -> (
    None
):
    """Catches a second definition of the same refusal string: this must
    be the identical object the `ExperimentReceipt` boundary (and, via it,
    every other boundary in this module) already returns, not a
    look-alike."""
    outcome = _alive_tie_outcome()

    dflss_claim = dflss_solve_payoff_production_claim(outcome)

    assert dflss_claim is PRODUCTION_CLAIM_REFUSAL

    receipt = ExperimentReceipt(
        intent_id="intent-identity-dflss-1",
        observed_outcome_refs=("outcome-identity-dflss-1",),
        standing="ALIVE",
    )
    receipt_claim = experiment_receipt_production_claim(receipt)

    assert dflss_claim == receipt_claim
    assert dflss_claim is receipt_claim


def test_dflss_claim_requires_a_real_dflss_solve_payoff_outcome() -> None:
    with pytest.raises(
        TypeError, match="DFLSS_SOLVE_PAYOFF_CLAIM_REQUIRES_REAL_OUTCOME"
    ):
        dflss_solve_payoff_production_claim("ALIVE")  # type: ignore[arg-type]
