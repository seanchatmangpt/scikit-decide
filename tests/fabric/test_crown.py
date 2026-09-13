from autofde_lab.fabric.crown import (
    CrownReport,
    CrownRequirement,
    RequirementStatus,
    crown_report,
)


def test_canonical_registry_is_machine_valid_and_terminal():
    report = crown_report()
    assert report.validate() == ()
    assert len(report.requirements) == 83
    assert report.internally_closed
    assert report.by_status(RequirementStatus.PARTIAL) == ()
    assert report.by_status(RequirementStatus.MISSING) == ()


def test_competitive_crown_stays_closed_on_named_unexecuted_gates():
    report = crown_report()
    assert report.palantir_defeat_ready is False
    blocked_gates = {
        row.requirement_id
        for row in report.requirements
        if (row.requirement_id.startswith("P") or row.requirement_id.startswith("D"))
        and row.status is RequirementStatus.BLOCKED
    }
    assert blocked_gates == {
        "P1",
        "P2",
        "P3",
        "P4",
        "P5",
        "P6",
        "P7",
        "D5",
        "D6",
        "D8",
    }


def test_satisfied_without_evidence_is_invalid():
    report = CrownReport((CrownRequirement("X", "claim", RequirementStatus.SATISFIED),))
    assert report.validate() == ("X: SATISFIED without evidence",)


def test_blocked_without_named_dependency_is_invalid():
    report = CrownReport((CrownRequirement("X", "claim", RequirementStatus.BLOCKED),))
    assert report.validate() == ("X: BLOCKED without named dependency",)


def test_external_dependency_cannot_be_internally_satisfied():
    report = CrownReport(
        (
            CrownRequirement(
                "X",
                "claim",
                RequirementStatus.SATISFIED,
                ("tests/fake.py",),
                external_dependency="customer",
            ),
        )
    )
    assert "external dependency" in report.validate()[0]


def test_customer_adoption_cannot_be_manufactured_from_internal_fixture():
    report = CrownReport(
        (
            CrownRequirement(
                "R-1501",
                "ADOPTED",
                RequirementStatus.SATISFIED,
                ("tests/fixtures/fake_customer.json",),
            ),
        )
    )
    assert any("ADOPTED" in problem for problem in report.validate())


def test_zero_unreceipted_actuation_is_preserved_as_executed_requirement():
    row = crown_report().get("R-001")
    assert "Zero unreceipted actuation" in row.statement
    assert row.status is RequirementStatus.SATISFIED
    assert "tests/fabric/test_brce.py" in row.evidence


def test_irreducibly_external_requirements_remain_blocked():
    report = crown_report()
    for requirement_id in (
        "R-502",
        "R-800",
        "R-801",
        "R-1101",
        "R-1301",
        "R-1501",
    ):
        row = report.get(requirement_id)
        assert row.status is RequirementStatus.BLOCKED
        assert row.external_dependency
