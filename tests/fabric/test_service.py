from __future__ import annotations

import pytest

from autofde_lab.fabric.models import (
    CacheStatus,
    DecisionRefusal,
    DecisionRequest,
    DecisionStanding,
    RefusalCode,
)
from autofde_lab.fabric.service import DecisionFabric


def exact_request(**overrides: object) -> DecisionRequest:
    values = {
        "domain": "Counter",
        "subject_digest": "subject:a",
        "policy_digest": "policy:a",
        "environment_digest": "environment:a",
        "randomness_digest": "randomness:deterministic",
    }
    values.update(overrides)
    return DecisionRequest(**values)


def test_catalog_and_match_share_one_registry(fabric: DecisionFabric) -> None:
    assert fabric.catalog().domains == ("Counter",)
    assert fabric.catalog().solvers == ("CounterSolver",)

    first = fabric.match("Counter", domain_arguments={"limit": 3})
    second = fabric.match("Counter", domain_arguments={"limit": 3})

    assert first.cache_status is CacheStatus.MISS
    assert second.cache_status is CacheStatus.HIT
    assert first.compatible_solvers == ("CounterSolver",)
    assert first.identity_sha256 == second.identity_sha256


def test_solve_emits_receipt_and_second_run_is_cache_hit(
    fabric: DecisionFabric,
) -> None:
    request = exact_request(domain_arguments={"limit": 2})

    first = fabric.solve(request)
    second = fabric.solve(request)

    assert first.standing is DecisionStanding.SOLVED
    assert first.cache_status is CacheStatus.MISS
    assert second.cache_status is CacheStatus.HIT
    assert len(first.steps) == 2
    assert first.solver == "CounterSolver"
    assert first.receipt_sha256 == second.receipt_sha256
    assert first.trajectory_sha256 == second.trajectory_sha256


@pytest.mark.parametrize(
    ("axis", "before", "after"),
    [
        ("policy_digest", "policy:a", "policy:b"),
        ("randomness_digest", "seed:1", "seed:2"),
    ],
)
def test_identity_change_invalidates_exact_reuse(
    fabric: DecisionFabric,
    axis: str,
    before: str,
    after: str,
) -> None:
    """Each parameter is a distinct identity axis, not a redraw of one.

    Collapsed from two byte-identical sibling tests differing only in the
    field they vary; both axes still fail independently.
    """
    first = fabric.solve(exact_request(**{axis: before}))
    changed = fabric.solve(exact_request(**{axis: after}))

    assert first.cache_status is CacheStatus.MISS
    assert changed.cache_status is CacheStatus.MISS
    assert first.input_sha256 != changed.input_sha256


def test_unbound_identity_bypasses_solve_cache(fabric: DecisionFabric) -> None:
    request = DecisionRequest(domain="Counter")

    first = fabric.solve(request)
    second = fabric.solve(request)

    assert first.cache_status is CacheStatus.BYPASS
    assert second.cache_status is CacheStatus.BYPASS


def test_bounded_run_does_not_claim_goal_completion(fabric: DecisionFabric) -> None:
    result = fabric.solve(
        DecisionRequest(
            domain="Counter",
            domain_arguments={"limit": 5},
            max_steps=2,
            use_cache=False,
        )
    )

    assert result.standing is DecisionStanding.BOUNDED
    assert result.terminal is False
    assert result.cache_status is CacheStatus.BYPASS


def test_deterministic_refusal_is_cached(fabric: DecisionFabric) -> None:
    request = exact_request(solver="Other")

    with pytest.raises(DecisionRefusal) as first:
        fabric.solve(request)
    with pytest.raises(DecisionRefusal) as second:
        fabric.solve(request)

    assert first.value.code is RefusalCode.SOLVER_INCOMPATIBLE
    assert second.value.code is RefusalCode.SOLVER_INCOMPATIBLE
    assert second.value.cache_status is CacheStatus.HIT
