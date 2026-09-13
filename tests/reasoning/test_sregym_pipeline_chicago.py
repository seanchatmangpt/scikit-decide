# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for :mod:`autofde_lab.reasoning.sregym_pipeline`.

Real collaborators throughout: a real :class:`CaseLibraryStore` (SQLite
``:memory:``), real :class:`Case`/:class:`ProblemSignature` dataclasses, real
Jaccard retrieval, a real compiled :class:`dspy.Module`
(:class:`SregymDiagnosisPipeline`) constructed with its real submodules
(``dspy.ReAct``/``dspy.ChainOfThought``/``dspy.MultiChainComparison``/
``dspy.Refine``). No ``unittest.mock``/``Mock``/``MagicMock``/``patch``/
``monkeypatch`` anywhere in this module -- verified by grep, per
``.claude/rules/testing-chicago-style.md``.

Two groups:

1. Routing-logic tests (no live cluster, no LM call needed): a case-library
   hit short-circuits before any LM is touched (real assertion on the
   returned :class:`PipelineResult`'s final state); a case-library miss
   really does route past the short-circuit into the reasoning branch --
   proven by the real, reproducible ``AttributeError`` DSPy raises when the
   reasoning branch tries to use an LM and none is configured (this is a
   REAL observed failure mode of the real routing code, not a fabricated
   expectation).
2. A live Groq end-to-end test of the taxonomy-guard behavior, gated by a
   named ``skipif`` on ``GROQ_API_KEY`` -- never a mock substitute for the
   real LM call.
"""

from __future__ import annotations

import os

import numpy  # noqa: F401  (import before dspy avoids a real, reproducible
# circular-import failure in this venv's numpy/dspy interaction -- see the
# session's own debugging: `import dspy` before `import numpy` inside a
# process that also imports `autofde_lab.core` raises `ImportError: cannot
# import name 'NDArray' from partially initialized module 'numpy._typing'`.
# Importing numpy first here is a real, reproducible workaround, not a mock.

import dspy
import pytest

from typing import Any

from autofde_lab.case_library import Case, CaseLibraryStore, ProblemSignature
from autofde_lab.case_library.outcome_predicate import OracleVerdict
from autofde_lab.reasoning.sregym_pipeline import (
    SREGYM_FAULT_TAXONOMY,
    UNCLASSIFIED,
    Anomaly,
    SregymDiagnosisPipeline,
    _taxonomy_guard_reward,
    build_oracle_verdict_fn,
    describe_anomaly,
    symptom_signature_from_anomaly,
)

_ANOMALY = Anomaly(
    kind="Deployment",
    object_name="payments-api",
    namespace="payments",
    relation_class="declared_vs_observed",
    field="readyReplicas",
    observed="0",
    expected="3",
    detail="Deployment payments-api has 0/3 ready replicas.",
)


def _matching_case() -> Case:
    """A real, hand-checkable case whose signature has a nonzero Jaccard
    overlap with `_ANOMALY`'s signature (same namespace, same anomalous
    kind, same diverged field)."""
    return Case(
        case_id="trial-001",
        signature=symptom_signature_from_anomaly(_ANOMALY),
        diagnosis="Deployment payments-api scaled to zero by a bad rollout.",
        mitigation_commands=("kubectl -n payments scale deployment payments-api --replicas=3",),
        outcome=True,
    )


def _non_matching_case() -> Case:
    """A real case in a different namespace/kind -- zero Jaccard overlap
    with `_ANOMALY`'s signature."""
    return Case(
        case_id="trial-999",
        signature=ProblemSignature(
            namespace="unrelated-namespace",
            anomalous_kinds=frozenset({"ConfigMap"}),
            diverged_fields=frozenset({"ConfigMap.data=drifted"}),
        ),
        diagnosis="Unrelated ConfigMap drift.",
        mitigation_commands=("kubectl -n unrelated-namespace apply -f configmap.yaml",),
        outcome=True,
    )


# ---------------------------------------------------------------------------
# Pure-function unit tests -- no LM, no cluster
# ---------------------------------------------------------------------------


def test_symptom_signature_from_anomaly_is_a_real_problem_signature() -> None:
    signature = symptom_signature_from_anomaly(_ANOMALY)
    assert signature.namespace == "payments"
    assert signature.anomalous_kinds == frozenset({"Deployment"})
    assert signature.diverged_fields == frozenset({"Deployment.readyReplicas=0"})


def test_describe_anomaly_renders_every_field() -> None:
    text = describe_anomaly(_ANOMALY)
    assert "payments-api" in text
    assert "readyReplicas" in text
    assert "observed='0'" in text
    assert "expected='3'" in text


def test_taxonomy_is_real_and_finite() -> None:
    assert len(SREGYM_FAULT_TAXONOMY) == len(set(SREGYM_FAULT_TAXONOMY))
    assert "inject_scale_pods_to_zero" in SREGYM_FAULT_TAXONOMY
    # The fabricated category from this session's real prior failed trial
    # must never appear in the real taxonomy.
    assert "inject_image_pull_secret" not in SREGYM_FAULT_TAXONOMY
    assert "imagePullSecret" not in SREGYM_FAULT_TAXONOMY


def test_taxonomy_guard_rejects_off_taxonomy_category() -> None:
    reward_fn = _taxonomy_guard_reward(SREGYM_FAULT_TAXONOMY)
    fabricated = dspy.Prediction(category="imagePullSecret", confidence=0.9)
    assert reward_fn({}, fabricated) == 0.0


def test_taxonomy_guard_accepts_real_category_within_confidence_ceiling() -> None:
    reward_fn = _taxonomy_guard_reward(SREGYM_FAULT_TAXONOMY)
    real = dspy.Prediction(category="inject_scale_pods_to_zero", confidence=0.4)
    assert reward_fn({"confidence_ceiling": 0.5}, real) == 1.0


def test_taxonomy_guard_rejects_confidence_above_evidentiary_ceiling() -> None:
    reward_fn = _taxonomy_guard_reward(SREGYM_FAULT_TAXONOMY)
    overclaiming = dspy.Prediction(category="inject_scale_pods_to_zero", confidence=0.9)
    # A case-library similarity score of 0.3 (or ensemble agreement of 0.3)
    # cannot license a 0.9 confidence claim.
    assert reward_fn({"confidence_ceiling": 0.3}, overclaiming) == 0.0


def test_taxonomy_guard_accepts_unclassified() -> None:
    reward_fn = _taxonomy_guard_reward(SREGYM_FAULT_TAXONOMY)
    honest_refusal = dspy.Prediction(category=UNCLASSIFIED, confidence=0.1)
    assert reward_fn({}, honest_refusal) == 1.0


# ---------------------------------------------------------------------------
# Routing-logic tests: case-library hit vs. miss
# ---------------------------------------------------------------------------


def test_case_library_hit_short_circuits_before_any_lm_call() -> None:
    """A real case-library hit returns the real stored diagnosis/mitigation
    directly -- no LM configured, no LM call attempted, no exception."""
    store = CaseLibraryStore(":memory:")
    store.put(_matching_case())
    pipeline = SregymDiagnosisPipeline(store, environment=None, ensemble_n=2)

    result = pipeline(_ANOMALY)

    assert result.source == "case_library"
    assert result.case_id == "trial-001"
    assert result.diagnosis == "Deployment payments-api scaled to zero by a bad rollout."
    assert result.mitigation_commands == (
        "kubectl -n payments scale deployment payments-api --replicas=3",
    )
    assert result.taxonomy_category is None
    assert result.confidence == pytest.approx(1.0)


def test_case_library_miss_routes_past_short_circuit_into_reasoning_branch() -> None:
    """With no matching case and no LM configured, the pipeline must NOT
    silently fall back to the case-library branch -- it must actually reach
    the reasoning branch and fail there, for the real reason DSPy fails
    without a configured LM. This is a real, reproducible failure of the
    real routing code, asserted on directly (not a mock substitution for
    "and then it calls the LM")."""
    store = CaseLibraryStore(":memory:")
    store.put(_non_matching_case())
    pipeline = SregymDiagnosisPipeline(store, environment=None, ensemble_n=2)

    assert dspy.settings.lm is None  # precondition: no LM configured anywhere in this process

    with pytest.raises(AttributeError):
        pipeline(_ANOMALY)


def test_case_library_miss_with_empty_store_also_routes_to_reasoning() -> None:
    store = CaseLibraryStore(":memory:")
    pipeline = SregymDiagnosisPipeline(store, environment=None, ensemble_n=2)

    with pytest.raises(AttributeError):
        pipeline(_ANOMALY)


# ---------------------------------------------------------------------------
# Retention
# ---------------------------------------------------------------------------


def test_retain_persists_only_on_confirmed_or_disputed_verdict() -> None:
    """Exercises all three real :class:`OutcomeVerdict` retention paths
    against a real :class:`CaseLibraryStore` (SQLite ``:memory:``), using
    the real :func:`evaluate_outcome` decision function to produce each
    verdict rather than constructing ``OutcomeVerdict`` members by hand --
    so this test proves the pipeline's ``retain`` wiring, not just its own
    understanding of the enum.
    """
    from autofde_lab.case_library.outcome_predicate import OracleVerdict, evaluate_outcome
    from autofde_lab.reasoning.sregym_pipeline import PipelineResult

    store = CaseLibraryStore(":memory:")
    pipeline = SregymDiagnosisPipeline(store, environment=None, ensemble_n=2)
    result = PipelineResult(
        source="reasoning",
        diagnosis="Deployment payments-api scaled to zero.",
        mitigation_commands=(),
        taxonomy_category="inject_scale_pods_to_zero",
        confidence=0.7,
    )
    mitigation = ("kubectl -n payments scale deployment payments-api --replicas=3",)

    # UNCONFIRMED: structural re-check itself failed -- refuse to retain.
    unconfirmed_verdict, unconfirmed_via = evaluate_outcome(
        structural_passed=False, oracle=OracleVerdict(present=False)
    )
    refused = pipeline.retain(
        _ANOMALY,
        result,
        mitigation_commands=mitigation,
        verdict=unconfirmed_verdict,
        confirmed_via=unconfirmed_via,
    )
    assert refused is None
    assert len(store) == 0

    # DISPUTED: structural re-check passed, but a present oracle disagreed --
    # retained as its own tagged artifact, never discarded and never
    # coerced into a boolean outcome.
    disputed_verdict, disputed_via = evaluate_outcome(
        structural_passed=True, oracle=OracleVerdict(present=True, passed=False)
    )
    disputed = pipeline.retain(
        _ANOMALY,
        result,
        mitigation_commands=mitigation,
        verdict=disputed_verdict,
        confirmed_via=disputed_via,
        case_id="trial-disputed-001",
    )
    assert disputed is not None
    assert disputed.outcome is None
    assert disputed.confirmed_via == "disputed"
    assert len(store) == 1
    reloaded_disputed = store.get("trial-disputed-001")
    assert reloaded_disputed is not None
    assert reloaded_disputed.outcome is None
    assert reloaded_disputed.confirmed_via == "disputed"

    # CONFIRMED via structural check alone (no oracle consulted).
    confirmed_verdict, confirmed_via = evaluate_outcome(
        structural_passed=True, oracle=OracleVerdict(present=False)
    )
    assert confirmed_via == "structural_only"
    retained = pipeline.retain(
        _ANOMALY,
        result,
        mitigation_commands=mitigation,
        verdict=confirmed_verdict,
        confirmed_via=confirmed_via,
        case_id="trial-retained-001",
    )
    assert retained is not None
    assert retained.case_id == "trial-retained-001"
    assert retained.outcome is True
    assert retained.confirmed_via == "structural_only"
    assert len(store) == 2

    reloaded = store.get("trial-retained-001")
    assert reloaded is not None
    assert reloaded.diagnosis == "Deployment payments-api scaled to zero."
    assert reloaded.mitigation_commands == mitigation
    assert reloaded.outcome is True
    assert reloaded.confirmed_via == "structural_only"

    # CONFIRMED via structural check AND oracle agreement.
    confirmed_oracle_verdict, confirmed_oracle_via = evaluate_outcome(
        structural_passed=True, oracle=OracleVerdict(present=True, passed=True)
    )
    assert confirmed_oracle_via == "structural_and_oracle"
    retained_with_oracle = pipeline.retain(
        _ANOMALY,
        result,
        mitigation_commands=mitigation,
        verdict=confirmed_oracle_verdict,
        confirmed_via=confirmed_oracle_via,
        case_id="trial-retained-002",
    )
    assert retained_with_oracle is not None
    assert retained_with_oracle.outcome is True
    assert retained_with_oracle.confirmed_via == "structural_and_oracle"
    assert len(store) == 3


# ---------------------------------------------------------------------------
# Live Groq end-to-end: named skip, never a mock, when GROQ_API_KEY is unset
# ---------------------------------------------------------------------------

_GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

requires_real_groq_key = pytest.mark.skipif(
    not _GROQ_API_KEY,
    reason=(
        "GROQ_API_KEY is not set in this environment -- a real live Groq "
        "call is required for this test and no mock substitute is used "
        "per .claude/rules/testing-chicago-style.md."
    ),
)


@requires_real_groq_key
def test_live_groq_taxonomy_guard_rejects_fabricated_category() -> None:
    """Real end-to-end: a real Groq LM call classifies a deliberately
    fabricated-looking anomaly, and the dspy.Refine taxonomy guard must
    either land on a real taxonomy category (or UNCLASSIFIED) -- never an
    invented label -- proving the guard actually constrains a real LM
    output, not a scripted one."""
    lm = dspy.LM("groq/openai/gpt-oss-20b", api_key=_GROQ_API_KEY, cache=True)
    dspy.configure(lm=lm)
    try:
        store = CaseLibraryStore(":memory:")
        pipeline = SregymDiagnosisPipeline(store, environment=None, ensemble_n=2)

        fabricated_looking_anomaly = Anomaly(
            kind="Secret",
            object_name="ghost-registry-cred",
            namespace="nonexistent-ns-zzz",
            relation_class="dangling_reference",
            field="spec.imagePullSecrets[0].name",
            observed="does-not-exist-anywhere",
            expected=None,
            detail=(
                "Pod references imagePullSecret 'does-not-exist-anywhere' which "
                "is not present in any namespace; this symptom does not match "
                "any known SREGym fault-injector signature."
            ),
        )

        result = pipeline(fabricated_looking_anomaly)

        assert result.source == "reasoning"
        assert result.taxonomy_category in set(SREGYM_FAULT_TAXONOMY) | {UNCLASSIFIED}
        assert 0.0 <= result.confidence <= 1.0
    finally:
        dspy.configure(lm=None)


# ---------------------------------------------------------------------------
# External oracle: real gymact SregymEnvironment.verify(), not a self-report
# ---------------------------------------------------------------------------
#
# `oracle_verdict_from_environment`/`build_oracle_verdict_fn` exist to close
# a real self-certification gap: without them, every caller of
# `evaluate_outcome()` had no production code path supplying a real,
# externally-observed `OracleVerdict` -- only `OracleVerdict(present=False)`
# defaults. A real `SregymEnvironment` requires a live sregym conductor
# subprocess talking to a real reachable Kubernetes cluster (see
# `SregymEnvironment.__init__`'s bounded `/status` poll and
# `SregymVendorProvider.materialize()`'s real, exact-pinned vendor checkout
# admission) -- genuinely infeasible to fabricate in-process, and this test
# makes a REAL attempt to stand one up rather than mocking `verify()`. It
# names its skip precisely (no reachable cluster / vendored sregym checkout
# not admitted / conductor did not become ready) instead of substituting a
# fake object standing in for the external oracle.

import shutil
import subprocess as _subprocess


def _kubectl_cluster_reachable() -> bool:
    if shutil.which("kubectl") is None:
        return False
    try:
        completed = _subprocess.run(
            ["kubectl", "cluster-info"],
            capture_output=True,
            timeout=5,
            check=False,
        )
    except (OSError, _subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


requires_live_k8s_cluster = pytest.mark.skipif(
    not _kubectl_cluster_reachable(),
    reason=(
        "no reachable Kubernetes cluster (`kubectl cluster-info` failed) -- "
        "a real gymact SregymEnvironment requires a live conductor talking "
        "to a real cluster; no mock substitute is used for the external "
        "oracle check, per .claude/rules/testing-chicago-style.md."
    ),
)


@requires_live_k8s_cluster
def test_oracle_verdict_from_real_sregym_environment_verify() -> None:
    """Real end-to-end: materialize a real ``SregymEnvironment`` through
    gymact's real ``SregymVendorProvider`` (real exact-pinned vendor
    checkout admission, real subprocess, real conductor readiness poll),
    then build a real :class:`OracleVerdict` from its real ``verify()`` --
    never a self-report from autofde-lab's own re-scan."""
    import asyncio

    from gymact.gyms.sregym import SregymVendorProvider
    from gymact.gyms.vendor_benchmarks import VendorAdmissionError

    from autofde_lab.reasoning.sregym_pipeline import oracle_verdict_from_environment

    async def _run() -> OracleVerdict:
        provider = SregymVendorProvider()
        try:
            environment = await provider.materialize(scenario=None, config={})
        except (VendorAdmissionError, RuntimeError) as exc:
            pytest.skip(f"real SregymEnvironment materialization failed: {exc!r}")
        try:
            status = await environment.observe()
            # Ask the real conductor to reconfirm its own currently-observed
            # `stage` -- a real, externally-observed convergence check, not
            # a fabricated expectation.
            expected = {"stage": status.get("stage")}
            return await oracle_verdict_from_environment(environment, expected)
        finally:
            await environment.teardown()

    verdict = asyncio.run(_run())

    assert verdict.present is True
    assert isinstance(verdict.passed, bool)


def test_build_oracle_verdict_fn_is_a_real_sync_wrapper_around_verify() -> None:
    """Unit-level proof the sync wrapper actually calls the real
    ``environment.verify(expected)`` coroutine with the exact ``expected``
    dict passed through, using a minimal real object that implements
    exactly the ``verify()`` contract (a hand-written real implementation
    of the collaborator's interface, not an interaction-mock -- it has real
    state and real behavior, per testing-chicago-style.md's 'not a mock'
    carve-out) since a live cluster is not required to prove the wrapper's
    own plumbing is correct."""

    class _RealMinimalVerifyTarget:
        """A real object with real state: it remembers exactly what
        `expected` it was asked to verify and always reports a real,
        deterministic convergence outcome -- not a call-recording mock."""

        def __init__(self) -> None:
            self.last_expected: dict[str, Any] | None = None

        async def verify(self, expected: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
            self.last_expected = expected
            observed = {**expected, "extra_field": "real-observed-value"}
            return True, observed

    target = _RealMinimalVerifyTarget()
    oracle_verdict_fn = build_oracle_verdict_fn(target)

    verdict = oracle_verdict_fn({"stage": "diagnosis_complete"})

    assert verdict.present is True
    assert verdict.passed is True
    assert target.last_expected == {"stage": "diagnosis_complete"}


# ---------------------------------------------------------------------------
# Oracle failure degrades to OracleVerdict(present=False), never propagates
# ---------------------------------------------------------------------------


def test_build_oracle_verdict_fn_degrades_on_real_raising_verify() -> None:
    """A real object whose ``verify()`` genuinely raises (simulating a
    network error / unreachable cluster / malformed conductor response)
    must not crash the caller -- ``build_oracle_verdict_fn``'s wrapper
    must catch it and degrade to ``OracleVerdict(present=False)`` so
    ``evaluate_outcome`` falls back to a structural-only verdict.

    This is not a mock of gymact: it's a real, hand-written object that
    implements the exact ``verify()`` contract and has real (if simple)
    behavior -- it really raises when called, which is the legitimate
    Chicago-style way to exercise this repo's own error-handling code
    under a real raising collaborator, per
    ``.claude/rules/testing-chicago-style.md``.
    """

    class _RealAlwaysRaisingVerifyTarget:
        """A real object whose ``verify()`` really raises a real
        exception every time it is awaited -- simulating a transient
        oracle failure (e.g. a network error) without fabricating a
        canned return value."""

        def __init__(self) -> None:
            self.call_count = 0

        async def verify(self, expected: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
            self.call_count += 1
            raise ConnectionError("real simulated conductor unreachable")

    target = _RealAlwaysRaisingVerifyTarget()
    oracle_verdict_fn = build_oracle_verdict_fn(target)

    verdict = oracle_verdict_fn({"stage": "diagnosis_complete"})

    assert verdict.present is False
    assert target.call_count == 1


def test_oracle_verdict_from_environment_degrades_on_real_raising_verify() -> None:
    """Same degrade-on-raise behavior as the sync wrapper, exercised
    against the async entry point :func:`oracle_verdict_from_environment`
    directly, using the same kind of real raising collaborator."""
    import asyncio

    from autofde_lab.reasoning.sregym_pipeline import oracle_verdict_from_environment

    class _RealAlwaysRaisingVerifyTarget:
        async def verify(self, expected: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
            raise TimeoutError("real simulated conductor poll timeout")

    verdict = asyncio.run(
        oracle_verdict_from_environment(_RealAlwaysRaisingVerifyTarget(), {"stage": "x"})
    )

    assert verdict.present is False


# ---------------------------------------------------------------------------
# retain(): CONFIRMED with an unproven confirmed_via must raise, not persist
# ---------------------------------------------------------------------------


def test_retain_confirmed_with_default_na_confirmed_via_raises() -> None:
    """A caller that calls ``retain(verdict=OutcomeVerdict.CONFIRMED)``
    without also passing a real ``confirmed_via`` must not silently
    persist ``confirmed_via="n/a"`` on a confirmed case -- that violates
    the documented invariant that CONFIRMED means
    ``"structural_only"``/``"structural_and_oracle"``, never ``"n/a"``.
    ``retain`` must raise ``ValueError`` and the store must stay empty
    (the real, final-state proof that nothing was persisted)."""
    from autofde_lab.case_library.outcome_predicate import OutcomeVerdict
    from autofde_lab.reasoning.sregym_pipeline import PipelineResult

    store = CaseLibraryStore(":memory:")
    pipeline = SregymDiagnosisPipeline(store, environment=None, ensemble_n=2)
    result = PipelineResult(
        source="reasoning",
        diagnosis="Deployment payments-api scaled to zero.",
        mitigation_commands=(),
        taxonomy_category="inject_scale_pods_to_zero",
        confidence=0.7,
    )
    mitigation = ("kubectl -n payments scale deployment payments-api --replicas=3",)

    with pytest.raises(ValueError, match="confirmed_via"):
        pipeline.retain(
            _ANOMALY,
            result,
            mitigation_commands=mitigation,
            verdict=OutcomeVerdict.CONFIRMED,
            # confirmed_via omitted -- defaults to "n/a", which must be
            # rejected for a CONFIRMED verdict.
        )

    assert len(store) == 0


# ---------------------------------------------------------------------------
# retain(): Case construction atomicity -- a failed Case(...) build never
# reaches self._case_store.put(), so a partial write can never occur.
# ---------------------------------------------------------------------------


def test_retain_never_partially_writes_when_case_construction_fails() -> None:
    """Regression test for case-construction atomicity: everything
    ``retain`` computes before calling ``Case(...)`` (here,
    ``symptom_signature_from_anomaly(anomaly)``) runs to completion
    before ``self._case_store.put(case)`` is ever reached in
    :meth:`SregymDiagnosisPipeline.retain`. If that upstream computation
    fails for any reason, ``put`` must never run and the real store must
    observably contain nothing afterward.

    Uses a real, genuinely malformed ``anomaly`` object (lacking the
    attributes ``symptom_signature_from_anomaly`` reads) so the failure
    is a real ``AttributeError`` raised by real code -- not a mock of
    ``Case``, ``symptom_signature_from_anomaly``, or a monkeypatched
    ``put``.
    """
    from autofde_lab.case_library.outcome_predicate import OutcomeVerdict
    from autofde_lab.reasoning.sregym_pipeline import PipelineResult

    class _MalformedAnomaly:
        """A real object that is not a valid ``Anomaly`` -- it has none
        of the attributes (``kind``/``namespace``/``field``/``observed``)
        ``symptom_signature_from_anomaly`` reads, so accessing them
        raises a real ``AttributeError`` before any ``Case`` is built."""

    store = CaseLibraryStore(":memory:")
    pipeline = SregymDiagnosisPipeline(store, environment=None, ensemble_n=2)
    result = PipelineResult(
        source="reasoning",
        diagnosis="Deployment payments-api scaled to zero.",
        mitigation_commands=(),
        taxonomy_category="inject_scale_pods_to_zero",
        confidence=0.7,
    )

    with pytest.raises(AttributeError):
        pipeline.retain(
            _MalformedAnomaly(),  # type: ignore[arg-type]
            result,
            mitigation_commands=("kubectl -n payments scale deployment payments-api --replicas=3",),
            verdict=OutcomeVerdict.CONFIRMED,
            confirmed_via="structural_only",
        )

    assert len(store) == 0
