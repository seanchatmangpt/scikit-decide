from dataclasses import replace

from autofde_lab.fabric.cache import SQLiteERRCCache
from autofde_lab.fabric.hot_path import (
    HotPathStanding,
    compile_hot_path,
    reuse_hot_path,
    store_hot_path,
)
from autofde_lab.fabric.selection import DecisionRegime, SelectionDecision


def hot_decision() -> SelectionDecision:
    return SelectionDecision(
        signature_key="sig-1",
        regime=DecisionRegime.HOT,
        candidates=("astar",),
        evidence_count=3,
        reason="verified repeated winner",
    )


def compile_result():
    return compile_hot_path(
        hot_decision(),
        capability_digest="cap-v1",
        policy_digest="policy-v1",
        selector_revision="selector-v1",
    )


def test_hot_route_compiles_to_candidate_only_content_bound_artifact():
    result = compile_result()
    assert result.standing is HotPathStanding.COMPILED
    assert result.artifact is not None
    assert result.artifact.candidate_only is True
    assert result.artifact.identity.planner_id == "astar"
    assert len(result.artifact.identity.digest) == 64


def test_warm_route_cannot_compile_into_false_hot_path():
    decision = SelectionDecision(
        signature_key="sig-1",
        regime=DecisionRegime.WARM,
        candidates=("astar",),
        evidence_count=1,
        reason="bounded comparison remains",
    )
    result = compile_hot_path(
        decision,
        capability_digest="cap-v1",
        policy_digest="policy-v1",
        selector_revision="selector-v1",
    )
    assert result.standing is HotPathStanding.REFUSED_NOT_HOT
    assert result.artifact is None


def test_exact_identity_reuses_compiled_candidate_without_reranking():
    compiled = compile_result()
    assert compiled.artifact is not None
    with SQLiteERRCCache(":memory:") as cache:
        store_hot_path(cache, compiled.artifact)
        replay = reuse_hot_path(cache, compiled.artifact.identity)
        assert replay.standing is HotPathStanding.REUSED
        assert replay.artifact == compiled.artifact
        assert cache.stats()["hits"] == 1


def test_policy_or_capability_drift_cannot_reuse_stale_candidate():
    compiled = compile_result()
    assert compiled.artifact is not None
    with SQLiteERRCCache(":memory:") as cache:
        store_hot_path(cache, compiled.artifact)
        stale_policy = replace(compiled.artifact.identity, policy_digest="policy-v2")
        result = reuse_hot_path(cache, stale_policy)
        assert result.standing is HotPathStanding.REFUSED_CACHE_MISS
        assert result.artifact is None


def test_cached_payload_cannot_escalate_candidate_into_authority():
    compiled = compile_result()
    assert compiled.artifact is not None
    payload = compiled.artifact.to_payload()
    payload["candidate_only"] = False
    with SQLiteERRCCache(":memory:") as cache:
        cache.put(compiled.artifact.identity.digest, "planner-hot-path", payload)
        result = reuse_hot_path(cache, compiled.artifact.identity)
        assert result.standing is HotPathStanding.REFUSED_AUTHORITY_ESCALATION
        assert result.artifact is None


def test_malformed_cached_candidate_is_typed_refusal():
    compiled = compile_result()
    assert compiled.artifact is not None
    with SQLiteERRCCache(":memory:") as cache:
        cache.put(
            compiled.artifact.identity.digest,
            "planner-hot-path",
            {"candidate_only": True, "identity": {}},
        )
        result = reuse_hot_path(cache, compiled.artifact.identity)
        assert result.standing is HotPathStanding.REFUSED_MALFORMED
        assert result.artifact is None
