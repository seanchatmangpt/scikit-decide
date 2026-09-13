"""Chicago-style tests for
:mod:`autofde_lab_planner.scanner.taxonomy_growth`.

Real collaborators throughout: real :class:`Anomaly` construction, the real
:func:`taxonomy.classify` decision function, and a real SQLite
(``:memory:``) :class:`TaxonomyGrowthStore`. No
``unittest.mock``/``Mock``/``MagicMock``/``patch``/``monkeypatch`` anywhere
in this module -- verified by grep, per
``.claude/rules/testing-chicago-style.md``.
"""

from __future__ import annotations

from autofde_lab_planner.scanner.models import Anomaly
from autofde_lab_planner.scanner.taxonomy import UNCLASSIFIED, classify
from autofde_lab_planner.scanner.taxonomy_growth import (
    TaxonomyGrowthCandidate,
    TaxonomyGrowthStore,
    retain_if_unclassified,
)

_UNCLASSIFIABLE_ANOMALY = Anomaly(
    kind="StatefulSet",
    object_name="weird-thing",
    namespace="prod",
    relation_class="declared_vs_observed",
    field="spec.updateStrategy",
    observed="RollingUpdate",
    expected="OnDelete",
    detail="StatefulSet updateStrategy does not match any known taxonomy signature.",
)

_CLASSIFIABLE_ANOMALY = Anomaly(
    kind="Deployment",
    object_name="billing-api",
    namespace="prod",
    relation_class="declared_vs_observed",
    field="readyReplicas",
    observed="0",
    expected="3",
    detail="Deployment scaled to zero.",
)


def test_real_classify_confirms_the_fixture_is_actually_unclassified() -> None:
    """Precondition check: the "unclassifiable" fixture above is genuinely
    unclassified under the real `classify()` -- not merely assumed to be."""
    assert classify(_UNCLASSIFIABLE_ANOMALY) == UNCLASSIFIED
    assert classify(_CLASSIFIABLE_ANOMALY) != UNCLASSIFIED


def test_retain_if_unclassified_persists_a_real_unclassified_anomaly() -> None:
    store = TaxonomyGrowthStore(":memory:")
    assert len(store) == 0

    candidate = retain_if_unclassified(
        _UNCLASSIFIABLE_ANOMALY, store, candidate_id="candidate-001"
    )

    assert candidate is not None
    assert isinstance(candidate, TaxonomyGrowthCandidate)
    assert candidate.candidate_id == "candidate-001"
    assert candidate.anomaly == _UNCLASSIFIABLE_ANOMALY
    assert len(store) == 1

    reloaded = store.get("candidate-001")
    assert reloaded is not None
    assert reloaded.anomaly == _UNCLASSIFIABLE_ANOMALY
    assert reloaded.first_seen_at == candidate.first_seen_at


def test_retain_if_unclassified_refuses_a_real_classified_anomaly() -> None:
    """A classified anomaly is not a taxonomy gap -- nothing is retained,
    and the store stays empty, proving this mechanism never manufactures a
    growth candidate out of an anomaly the real taxonomy already covers."""
    store = TaxonomyGrowthStore(":memory:")

    result = retain_if_unclassified(_CLASSIFIABLE_ANOMALY, store)

    assert result is None
    assert len(store) == 0
    assert store.all_candidates() == []


def test_repeat_retain_of_same_candidate_id_keeps_first_seen_at() -> None:
    """Retaining the same candidate_id twice must not overwrite
    first_seen_at -- INSERT OR IGNORE, not OR REPLACE."""
    store = TaxonomyGrowthStore(":memory:")

    first = retain_if_unclassified(
        _UNCLASSIFIABLE_ANOMALY, store, candidate_id="candidate-repeat"
    )
    assert first is not None

    second = retain_if_unclassified(
        _UNCLASSIFIABLE_ANOMALY, store, candidate_id="candidate-repeat"
    )
    assert second is not None
    assert len(store) == 1  # still just one row, not two

    reloaded = store.get("candidate-repeat")
    assert reloaded is not None
    assert reloaded.first_seen_at == first.first_seen_at


def test_all_candidates_returns_every_persisted_unclassified_anomaly() -> None:
    store = TaxonomyGrowthStore(":memory:")
    other_anomaly = Anomaly(
        kind="HorizontalPodAutoscaler",
        object_name="hpa-weird",
        namespace="prod",
        relation_class="aggregate_threshold",
        field="spec.minReplicas",
        observed="0",
        expected=None,
        detail="HPA minReplicas is zero, no known taxonomy signature covers this.",
    )
    assert classify(other_anomaly) == UNCLASSIFIED

    retain_if_unclassified(_UNCLASSIFIABLE_ANOMALY, store, candidate_id="c-1")
    retain_if_unclassified(other_anomaly, store, candidate_id="c-2")

    all_candidates = store.all_candidates()
    assert len(all_candidates) == 2
    assert {c.candidate_id for c in all_candidates} == {"c-1", "c-2"}
