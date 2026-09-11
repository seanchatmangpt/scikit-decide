"""Chicago-style tests closing the third instance of the lab/production
standing boundary gap (`V2030.1.1-PRD-ARD.md` capability 9; falsifier "if
benchmark success grants production actuation") -- this time for
`laboratory.ExperimentReceipt`, the real observed-consequence evidence
object the cap-9 refute pass (PR#111) and its own follow-up (PR#123) both
named as a pre-existing, still-unfixed instance of the same class of gap.

`ExperimentReceipt.standing` is a bare `str` that can legitimately hold the
literal production success token `'ALIVE'` (real fixtures in
`tests/reasoning/test_laboratory_chicago.py` construct receipts exactly this
way). `laboratory.py` is untouched by this change: that field is real,
legitimate evidence *within* the lab domain. The gap closed here is only
that nothing stopped `receipt.standing`/`receipt.authority_standing` from
crossing the lab/production boundary if fed into
`fabric.enterprise_standing.derive_enterprise_standing` as though it were
observed production evidence.

Every collaborator is real: a real `ExperimentReceipt` built the same way
`tests/reasoning/test_laboratory_chicago.py` and
`tests/reasoning/test_gymact_world_experiment_provider_chicago.py` already
build one, the real `experiment_receipt_production_claim`, and the real
`derive_enterprise_standing` over the same committed Turtle fixture the
other two boundary test files use. Assertions are on returned state only.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from autofde_lab.fabric.enterprise_standing import derive_enterprise_standing
from autofde_lab.fabric.fde import parse_authority_turtle
from autofde_lab.reasoning.exploration_payoff_bridge import (
    ExplorationPayoffOutcome,
)
from autofde_lab.reasoning.lab_standing import (
    PRODUCTION_CLAIM_REFUSAL,
    experiment_receipt_production_claim,
    exploration_payoff_production_claim,
)
from autofde_lab.reasoning.laboratory import ExperimentReceipt

FIXTURES = Path(__file__).resolve().parents[1] / "ecosystem" / "fixtures" / "fde"
BASE = FIXTURES / "customer-authority.ttl"


def test_alive_standing_receipt_still_refuses_a_production_claim() -> None:
    """The most dangerous-looking case: a receipt whose own `standing` and
    `authority_standing` are both the literal success token `'ALIVE'`, with
    no violated postconditions -- still refuses identically."""
    receipt = ExperimentReceipt(
        intent_id="intent-alive-1",
        observed_outcome_refs=("outcome-alive-1",),
        standing="ALIVE",
        authority_standing="ALIVE",
        postconditions_observed=("p95_reduced",),
    )

    claim = experiment_receipt_production_claim(receipt)

    assert claim == "UNKNOWN:LAB_RESULT_NOT_PRODUCTION_EVIDENCE"
    assert claim == PRODUCTION_CLAIM_REFUSAL
    assert claim != "ALIVE"


def test_refusal_forwarded_into_enterprise_standing_fails_closed() -> None:
    model = parse_authority_turtle(BASE.read_text(encoding="utf-8"))
    receipt = ExperimentReceipt(
        intent_id="intent-alive-2",
        observed_outcome_refs=("outcome-alive-2",),
        standing="ALIVE",
        authority_standing="ALIVE",
    )
    claim = experiment_receipt_production_claim(receipt)

    standing = derive_enterprise_standing(model, technical_standing=claim)

    assert standing.technical_standing == claim
    assert standing.enterprise_standing == "UNKNOWN"
    assert standing.organizational_standing == "UNKNOWN"


def test_default_unknown_standing_receipt_refuses_identically() -> None:
    """The boundary does not depend on the receipt's own internal
    standing at all: the dataclass-default `'UNKNOWN'` receipt refuses the
    exact same way the `'ALIVE'` receipt above did."""
    receipt = ExperimentReceipt(
        intent_id="intent-default-1",
        observed_outcome_refs=("outcome-default-1",),
    )

    assert receipt.standing == "UNKNOWN"
    assert experiment_receipt_production_claim(receipt) == PRODUCTION_CLAIM_REFUSAL


def test_receipt_claim_reuses_the_exact_same_refusal_object_as_the_other_boundaries() -> (
    None
):
    """Catches a second definition of the same refusal string: this must
    be the identical object the `LabResultStanding` and
    `ExplorationPayoffOutcome` boundaries already return, not a
    look-alike."""
    receipt = ExperimentReceipt(
        intent_id="intent-identity-1",
        observed_outcome_refs=("outcome-identity-1",),
        standing="ALIVE",
    )

    receipt_claim = experiment_receipt_production_claim(receipt)

    assert receipt_claim is PRODUCTION_CLAIM_REFUSAL

    payoff_outcome = ExplorationPayoffOutcome(
        observation=None,
        standing="REFUSED",
        reason="test-double-checking-refusal-identity",
    )
    payoff_claim = exploration_payoff_production_claim(payoff_outcome)

    assert receipt_claim == payoff_claim
    assert receipt_claim is payoff_claim


def test_receipt_claim_requires_a_real_experiment_receipt() -> None:
    with pytest.raises(
        TypeError, match="EXPERIMENT_RECEIPT_CLAIM_REQUIRES_REAL_RECEIPT"
    ):
        experiment_receipt_production_claim("ALIVE")  # type: ignore[arg-type]
