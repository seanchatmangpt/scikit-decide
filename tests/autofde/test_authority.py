from autofde_lab.autofde.authority import (
    AcceptanceRecord,
    AuthorityGrant,
    AuthorityStanding,
    EnterpriseStanding,
    RetirementGrant,
    admit_acceptance,
    admit_authority,
    admit_retirement,
)


def grant(**overrides):
    values = dict(
        principal_id="customer:ops-owner",
        decision_right="replace:legacy-system",
        subject_id="legacy:v1",
        intended_effect_id="replacement:v2",
        evidence_ids=("receipt:1",),
        allowed_capabilities=frozenset({"deploy"}),
        allowed_resources=frozenset({"prod:service-a"}),
        issued_at="2026-08-08T06:00:00Z",
    )
    values.update(overrides)
    return AuthorityGrant(**values)


def test_authority_is_attributable_and_bounded():
    assert admit_authority(grant()) is AuthorityStanding.ADMITTED
    assert (
        admit_authority(grant(principal_id=""))
        is AuthorityStanding.REFUSED_MISSING_PRINCIPAL
    )
    assert (
        admit_authority(grant(evidence_ids=()))
        is AuthorityStanding.REFUSED_MISSING_EVIDENCE
    )
    assert (
        admit_authority(grant(allowed_resources=frozenset()))
        is AuthorityStanding.REFUSED_SCOPE
    )


def test_acceptance_cannot_promote_unverified_replacement():
    record = AcceptanceRecord(
        authority=grant(),
        replacement_id="replacement:v2",
        replacement_verified=False,
        accepted_postconditions=("latency<100ms",),
        operating_owner_id="customer:ops-owner",
        accepted_at="2026-08-08T06:10:00Z",
    )
    assert admit_acceptance(record) is AuthorityStanding.REFUSED_UNVERIFIED_REPLACEMENT


def test_acceptance_requires_named_operating_owner():
    record = AcceptanceRecord(
        authority=grant(),
        replacement_id="replacement:v2",
        replacement_verified=True,
        accepted_postconditions=("latency<100ms",),
        operating_owner_id="",
        accepted_at="2026-08-08T06:10:00Z",
    )
    assert (
        admit_acceptance(record) is AuthorityStanding.REFUSED_UNATTRIBUTABLE_ACCEPTANCE
    )


def test_retirement_boolean_is_replaced_by_attributable_record():
    record = RetirementGrant(
        authority=grant(decision_right="retire:legacy-system"),
        predecessor_id="legacy:v1",
        replacement_id="replacement:v2",
        replacement_verified=True,
        reviewed_evidence_ids=("receipt:1", "replay:1"),
        authorized_at="2026-08-08T06:20:00Z",
    )
    assert admit_retirement(record) is AuthorityStanding.ADMITTED


def test_enterprise_standing_is_conjunction_not_technical_alias():
    assert not EnterpriseStanding(True, False).alive
    assert not EnterpriseStanding(False, True).alive
    assert EnterpriseStanding(True, True).alive
