from datetime import datetime, timedelta, timezone

from autofde_lab.evidence.closed_world import (
    ClosureWitness,
    Knowledge,
    Observation,
    ObservationKind,
    ObservationScope,
    RefusalReason,
    admit_absence,
)

NOW = datetime(2026, 8, 18, 2, 0, tzinfo=timezone.utc)
SUBJECT = "/subscriptions/s1/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1"


def scope(*, authority: str = "principal:a") -> ObservationScope:
    return ObservationScope(
        provider="azure",
        tenant="tenant-1",
        account="subscription-s1",
        container="resource-group-rg",
        resource_type="Microsoft.Compute/virtualMachines",
        api_version="2025-04-01",
        authority_fingerprint=authority,
    )


def not_found(s: ObservationScope | None = None) -> Observation:
    return Observation(
        subject=SUBJECT,
        scope=s or scope(),
        kind=ObservationKind.NOT_FOUND,
        observed_at=NOW - timedelta(seconds=5),
    )


def closed(
    *,
    witness_scope: ObservationScope | None = None,
    subjects: frozenset[str] = frozenset(),
    enumeration_succeeded: bool = True,
    pagination_complete: bool = True,
    authority_complete: bool = True,
    consistency_window_closed: bool = True,
    fresh_until: datetime | None = None,
) -> ClosureWitness:
    return ClosureWitness(
        scope=witness_scope or scope(),
        subjects=subjects,
        enumerated_at=NOW - timedelta(seconds=10),
        fresh_until=fresh_until or NOW + timedelta(minutes=1),
        enumeration_succeeded=enumeration_succeeded,
        pagination_complete=pagination_complete,
        authority_complete=authority_complete,
        consistency_window_closed=consistency_window_closed,
    )


def test_404_alone_cannot_manufacture_absent() -> None:
    decision = admit_absence(
        not_found(),
        closed(pagination_complete=False),
        now=NOW,
    )

    assert decision.knowledge is Knowledge.UNKNOWN
    assert RefusalReason.INCOMPLETE_PAGINATION in decision.reasons


def test_exact_closed_world_can_admit_absent() -> None:
    decision = admit_absence(not_found(), closed(), now=NOW)

    assert decision.knowledge is Knowledge.ABSENT
    assert decision.reasons == ()


def test_authority_mismatch_refuses_negative_knowledge() -> None:
    decision = admit_absence(
        not_found(scope(authority="principal:a")),
        closed(witness_scope=scope(authority="principal:b")),
        now=NOW,
    )

    assert decision.knowledge is Knowledge.UNKNOWN
    assert RefusalReason.SCOPE_MISMATCH in decision.reasons
    assert RefusalReason.AUTHORITY_MISMATCH in decision.reasons


def test_insufficient_list_authority_refuses_negative_knowledge() -> None:
    decision = admit_absence(
        not_found(),
        closed(authority_complete=False),
        now=NOW,
    )

    assert decision.knowledge is Knowledge.UNKNOWN
    assert decision.reasons == (RefusalReason.INSUFFICIENT_AUTHORITY,)


def test_enumeration_failure_refuses_negative_knowledge() -> None:
    decision = admit_absence(
        not_found(),
        closed(enumeration_succeeded=False),
        now=NOW,
    )

    assert decision.knowledge is Knowledge.UNKNOWN
    assert decision.reasons == (RefusalReason.ENUMERATION_FAILED,)


def test_open_consistency_window_refuses_negative_knowledge() -> None:
    decision = admit_absence(
        not_found(),
        closed(consistency_window_closed=False),
        now=NOW,
    )

    assert decision.knowledge is Knowledge.UNKNOWN
    assert decision.reasons == (RefusalReason.EVENTUAL_CONSISTENCY_WINDOW,)


def test_stale_closure_refuses_negative_knowledge() -> None:
    decision = admit_absence(
        not_found(),
        closed(fresh_until=NOW - timedelta(microseconds=1)),
        now=NOW,
    )

    assert decision.knowledge is Knowledge.UNKNOWN
    assert decision.reasons == (RefusalReason.STALE,)


def test_enumeration_conflict_beats_404() -> None:
    decision = admit_absence(
        not_found(),
        closed(subjects=frozenset({SUBJECT})),
        now=NOW,
    )

    assert decision.knowledge is Knowledge.UNKNOWN
    assert decision.reasons == (RefusalReason.CONFLICT,)


def test_scope_is_closed_at_resource_type_not_resource_group_only() -> None:
    vm_scope = scope()
    storage_scope = ObservationScope(
        provider=vm_scope.provider,
        tenant=vm_scope.tenant,
        account=vm_scope.account,
        container=vm_scope.container,
        resource_type="Microsoft.Storage/storageAccounts",
        api_version=vm_scope.api_version,
        authority_fingerprint=vm_scope.authority_fingerprint,
    )

    decision = admit_absence(
        not_found(vm_scope),
        closed(witness_scope=storage_scope),
        now=NOW,
    )

    assert decision.knowledge is Knowledge.UNKNOWN
    assert RefusalReason.SCOPE_MISMATCH in decision.reasons


def test_non_404_observation_cannot_enter_absence_path() -> None:
    observation = Observation(
        subject=SUBJECT,
        scope=scope(),
        kind=ObservationKind.UNKNOWN,
        observed_at=NOW,
    )

    decision = admit_absence(observation, closed(), now=NOW)

    assert decision.knowledge is Knowledge.UNKNOWN
    assert decision.reasons == (RefusalReason.OBSERVATION_NOT_NOT_FOUND,)
