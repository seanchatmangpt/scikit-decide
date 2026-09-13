# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for :mod:`autofde_lab.case_library`.

Real collaborators throughout: real :class:`Case`/:class:`ProblemSignature`
dataclasses, a real SQLite file on a real ``tmp_path``, real
:class:`CaseLibraryStore` reads/writes, real Jaccard arithmetic. No
``unittest.mock``/``Mock``/``MagicMock``/``patch``/``monkeypatch`` anywhere
in this module -- verified by ``grep`` as part of the task's own evidence
requirement, not merely asserted here.
"""

from __future__ import annotations

from pathlib import Path

from autofde_lab.case_library import (
    Case,
    CaseLibraryStore,
    ProblemSignature,
    jaccard_similarity,
    retrieve_best_match,
    retrieve_from_store,
    retrieve_similar_cases,
)

# ---------------------------------------------------------------------------
# Fixture cases: a real, hand-checkable near-match and a real non-match.
# ---------------------------------------------------------------------------

_STORED_CASE = Case(
    case_id="trial-001",
    signature=ProblemSignature(
        namespace="payments",
        anomalous_kinds=frozenset({"Deployment", "Service"}),
        diverged_fields=frozenset(
            {"Deployment.spec.template.spec.containers[0].readinessProbe.path=/wrong"}
        ),
    ),
    diagnosis="Readiness probe path misconfigured on the payments Deployment.",
    mitigation_commands=(
        "kubectl -n payments patch deployment payments-api "
        "--type=json -p='[{\"op\":\"replace\",\"path\":"
        "\"/spec/template/spec/containers/0/readinessProbe/httpGet/path\","
        "\"value\":\"/healthz\"}]'",
    ),
    outcome=True,
)

# Near-match query: same namespace token, same 2 kind tokens, DIFFERENT
# single field token. Stored feature set (namespace ProblemSignature.feature_set()):
#   {namespace=payments, kind=Deployment, kind=Service, field=...readinessProbe.path=/wrong}
# -> 4 tokens.
# Query feature set:
#   {namespace=payments, kind=Deployment, kind=Service, field=...readinessProbe.path=/also-wrong}
# -> 4 tokens.
# Intersection = {namespace=payments, kind=Deployment, kind=Service} = 3 tokens.
# Union = 4 + 4 - 3 = 5 tokens.
# Jaccard = 3/5 = 0.6 exactly.
_NEAR_MATCH_QUERY = ProblemSignature(
    namespace="payments",
    anomalous_kinds=frozenset({"Deployment", "Service"}),
    diverged_fields=frozenset(
        {"Deployment.spec.template.spec.containers[0].readinessProbe.path=/also-wrong"}
    ),
)

# Non-match query: different namespace, disjoint kinds, disjoint field.
# Stored feature set (4 tokens, as above).
# Query feature set:
#   {namespace=checkout, kind=CronJob, field=CronJob.spec.schedule=* * * * *}
# -> 3 tokens.
# Intersection = {} (namespace differs, kinds differ, field differs) = 0 tokens.
# Union = 4 + 3 - 0 = 7 tokens.
# Jaccard = 0/7 = 0.0 exactly.
_NON_MATCH_QUERY = ProblemSignature(
    namespace="checkout",
    anomalous_kinds=frozenset({"CronJob"}),
    diverged_fields=frozenset({"CronJob.spec.schedule=* * * * *"}),
)


def test_jaccard_similarity_near_match_is_exactly_three_fifths() -> None:
    score = jaccard_similarity(_NEAR_MATCH_QUERY, _STORED_CASE.signature)
    assert score == 3 / 5


def test_jaccard_similarity_non_match_is_exactly_zero() -> None:
    score = jaccard_similarity(_NON_MATCH_QUERY, _STORED_CASE.signature)
    assert score == 0.0


def test_jaccard_similarity_identical_signature_is_one() -> None:
    identical = ProblemSignature(
        namespace=_STORED_CASE.signature.namespace,
        anomalous_kinds=_STORED_CASE.signature.anomalous_kinds,
        diverged_fields=_STORED_CASE.signature.diverged_fields,
    )
    assert jaccard_similarity(identical, _STORED_CASE.signature) == 1.0


def test_retrieve_best_match_finds_near_match_above_threshold() -> None:
    match = retrieve_best_match(_NEAR_MATCH_QUERY, [_STORED_CASE], threshold=0.5)
    assert match is not None
    assert match.case.case_id == "trial-001"
    assert match.score == 3 / 5


def test_retrieve_best_match_returns_none_for_non_match_below_threshold() -> None:
    match = retrieve_best_match(_NON_MATCH_QUERY, [_STORED_CASE], threshold=0.5)
    assert match is None


def test_retrieve_similar_cases_orders_by_descending_score() -> None:
    # exact_match's signature IS the query's signature -> Jaccard 1.0 against
    # the query, strictly higher than _STORED_CASE's 3/5 computed above.
    exact_match = Case(
        case_id="trial-exact",
        signature=_NEAR_MATCH_QUERY,
        diagnosis="Identical fault, replayed.",
        mitigation_commands=_STORED_CASE.mitigation_commands,
        outcome=True,
    )
    matches = retrieve_similar_cases(
        _NEAR_MATCH_QUERY, [_STORED_CASE, exact_match], threshold=0.0
    )
    assert [m.case.case_id for m in matches] == ["trial-exact", "trial-001"]
    assert matches[0].score == 1.0
    assert matches[1].score == 3 / 5


# ---------------------------------------------------------------------------
# Persistence: a real SQLite file on a real tmp_path, real round-trip.
# ---------------------------------------------------------------------------


def test_sqlite_store_persists_and_reloads_a_case_bit_for_bit(tmp_path: Path) -> None:
    db_path = tmp_path / "cases.sqlite"

    with CaseLibraryStore(db_path) as store:
        store.put(_STORED_CASE)

    # Fresh store instance against the same real file -- proves the write
    # actually reached disk, not just an in-process cache.
    reopened = CaseLibraryStore(db_path)
    try:
        assert len(reopened) == 1
        loaded = reopened.get("trial-001")
        assert loaded is not None
        assert loaded.case_id == _STORED_CASE.case_id
        assert loaded.signature == _STORED_CASE.signature
        assert loaded.diagnosis == _STORED_CASE.diagnosis
        assert loaded.mitigation_commands == _STORED_CASE.mitigation_commands
        assert loaded.outcome is True
    finally:
        reopened.close()

    assert db_path.exists()
    assert db_path.stat().st_size > 0


def test_sqlite_store_round_trips_outcome_none_as_none_not_false(tmp_path: Path) -> None:
    unknown_outcome_case = Case(
        case_id="trial-unknown",
        signature=_NON_MATCH_QUERY,
        diagnosis="Diagnosed but mitigation never confirmed.",
        mitigation_commands=("kubectl -n checkout get cronjob",),
        outcome=None,
    )
    with CaseLibraryStore(tmp_path / "cases.sqlite") as store:
        store.put(unknown_outcome_case)
        loaded = store.get("trial-unknown")

    assert loaded is not None
    assert loaded.outcome is None  # must not have been coerced to False


def test_sqlite_store_get_missing_case_returns_none(tmp_path: Path) -> None:
    with CaseLibraryStore(tmp_path / "cases.sqlite") as store:
        assert store.get("does-not-exist") is None


def test_sqlite_store_put_is_upsert_by_case_id(tmp_path: Path) -> None:
    with CaseLibraryStore(tmp_path / "cases.sqlite") as store:
        store.put(_STORED_CASE)
        revised = Case(
            case_id=_STORED_CASE.case_id,
            signature=_STORED_CASE.signature,
            diagnosis="Revised diagnosis after a second look.",
            mitigation_commands=_STORED_CASE.mitigation_commands,
            outcome=False,
        )
        store.put(revised)

        assert len(store) == 1
        loaded = store.get(_STORED_CASE.case_id)
        assert loaded is not None
        assert loaded.diagnosis == "Revised diagnosis after a second look."
        assert loaded.outcome is False


def test_retrieve_from_store_uses_persisted_cases_for_a_real_end_to_end_lookup(
    tmp_path: Path,
) -> None:
    with CaseLibraryStore(tmp_path / "cases.sqlite") as store:
        store.put(_STORED_CASE)

        near_match = retrieve_from_store(_NEAR_MATCH_QUERY, store, threshold=0.5)
        assert near_match is not None
        assert near_match.case.case_id == "trial-001"
        assert near_match.score == 3 / 5

        non_match = retrieve_from_store(_NON_MATCH_QUERY, store, threshold=0.5)
        assert non_match is None


def test_case_library_store_creates_default_parent_directory(tmp_path: Path) -> None:
    nested_path = tmp_path / "docs" / "case_library" / "cases.sqlite"
    assert not nested_path.parent.exists()

    with CaseLibraryStore(nested_path) as store:
        store.put(_STORED_CASE)

    assert nested_path.exists()
