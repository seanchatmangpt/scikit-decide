from autofde_lab.fabric.crown import (
    CrownReport,
    CrownRequirement,
    RequirementStatus,
    crown_report,
)
from autofde_lab.fabric.crown_errc import (
    ELIGIBLE_EVIDENCE,
    ERRC,
    ErrcAction,
    ExecutionReceipt,
    closure_delta,
    errc_crown_report,
)

SUBJECT = "a" * 40


def receipt(*requirement_ids: str, exit_code: int = 0) -> ExecutionReceipt:
    paths = tuple(
        dict.fromkeys(
            path
            for requirement_id in requirement_ids
            for path in ELIGIBLE_EVIDENCE[requirement_id]
        )
    )
    return ExecutionReceipt(
        subject_sha=SUBJECT,
        command="python -m pytest -q tests/fabric",
        exit_code=exit_code,
        requirement_ids=requirement_ids,
        evidence_paths=paths,
        replay_key="pytest:fabric@" + SUBJECT,
    )


def d8_candidate_report() -> CrownReport:
    partial = RequirementStatus.PARTIAL
    return CrownReport(
        (
            CrownRequirement("R-400", "hot exact route", partial),
            CrownRequirement("R-402", "cold discovery", partial),
            CrownRequirement("R-500", "cognition compilation", partial),
            CrownRequirement("R-503", "authority-safe reuse", partial),
            CrownRequirement(
                "D8", "cold cognition becomes durable capability", partial
            ),
            CrownRequirement(
                "R-1501",
                "external adoption",
                RequirementStatus.BLOCKED,
                external_dependency="real external operator",
            ),
        )
    )


def test_terminal_registry_is_not_rewritten_without_execution_receipts():
    base = crown_report()
    report = errc_crown_report(base)
    assert report == base
    assert report.get("R-1301").status is RequirementStatus.BLOCKED
    assert report.get("R-1501").status is RequirementStatus.BLOCKED


def test_successful_exact_subject_receipt_promotes_only_covered_requirements():
    report = errc_crown_report(
        d8_candidate_report(),
        receipts=(receipt("R-400", "R-500", "R-503"),),
    )
    assert report.get("R-400").status is RequirementStatus.SATISFIED
    assert report.get("R-500").status is RequirementStatus.SATISFIED
    assert report.get("R-503").status is RequirementStatus.SATISFIED
    assert report.get("R-402").status is RequirementStatus.PARTIAL
    assert report.get("D8").status is RequirementStatus.PARTIAL


def test_failed_receipt_cannot_manufacture_standing():
    report = errc_crown_report(
        d8_candidate_report(),
        receipts=(receipt("R-400", exit_code=1),),
    )
    assert report.get("R-400").status is RequirementStatus.PARTIAL


def test_d8_closes_only_when_all_cognition_compilation_prerequisites_execute():
    report = errc_crown_report(
        d8_candidate_report(),
        receipts=(receipt("R-400", "R-402", "R-500", "R-503"),),
    )
    assert report.get("D8").status is RequirementStatus.SATISFIED
    assert report.get("D8").evidence
    assert report.get("R-1501").status is RequirementStatus.BLOCKED


def test_closure_delta_preserves_external_blockers():
    delta = closure_delta(
        d8_candidate_report(),
        receipts=(receipt("R-400", "R-500", "R-503"),),
    )
    assert delta["after_satisfied"] > delta["before_satisfied"]
    assert delta["blocked_preserved"] == 1
    assert delta["remaining_partial"] > 0


def test_errc_preserves_all_four_actions_without_adding_execution_authority():
    assert set(ERRC.values()) == set(ErrcAction)
    assert ERRC["duplicate_candidate_selection_work"] is ErrcAction.ELIMINATE
    assert ERRC["independent_postcondition_verification"] is ErrcAction.RAISE
    assert ERRC["execution_receipt_derived_gate_court"] is ErrcAction.CREATE
