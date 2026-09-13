from dataclasses import dataclass

from autofde_lab.fabric.coverage_bridge import coverage_row_to_receipt, measured_cost
from autofde_lab.fabric.selection import EvidenceStanding


@dataclass
class Row:
    capability: str = "Astar"
    standing: str = "ALIVE"
    disposition: str = "selected"
    execution_evidence: str = "solved, 4 step(s), cost 7.5"


def test_goal_reaching_coverage_cost_becomes_monotone_quality():
    receipt = coverage_row_to_receipt(Row(), signature_key="sig")
    assert receipt is not None
    assert receipt.quality == 1.0 / 8.5
    assert receipt.verified
    assert receipt.standing is EvidenceStanding.ALIVE


def test_failed_row_does_not_manufacture_positive_receipt():
    row = Row(disposition="failed", execution_evidence="TimeoutError: wall-clock bound")
    assert coverage_row_to_receipt(row, signature_key="sig") is None


def test_free_text_with_unbound_cost_is_not_accepted():
    row = Row(execution_evidence="I think the cost might be 7.5")
    assert measured_cost(row) is None


def test_scientific_notation_is_supported():
    assert (
        measured_cost(Row(execution_evidence="solved, 1 step(s), cost 1.2e-3"))
        == 0.0012
    )


def test_partial_alive_remains_partial_and_cannot_self_promote():
    receipt = coverage_row_to_receipt(
        Row(standing="PARTIAL_ALIVE"), signature_key="sig"
    )
    assert receipt is not None
    assert receipt.standing is EvidenceStanding.PARTIAL_ALIVE
