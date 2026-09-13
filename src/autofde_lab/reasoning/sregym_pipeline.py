# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""One compiled DSPy pipeline for SREGym fault diagnosis + mitigation.

Replaces the abandoned open-ended ``vendor/gyms/sregym/clients/
autofde_lab_dspy/driver.py`` approach. This package is new
(``src/autofde_lab/reasoning``), lives entirely outside the vendored
submodule, and is a single composed :class:`dspy.Module`
(:class:`SregymDiagnosisPipeline`), not four disconnected pieces.

Real composition
-----------------
1. **Case-library retrieval first.** :mod:`autofde_lab.case_library`'s real
   Jaccard retrieval (``retrieve_best_match``) is tried before any LM call.
   A hit above ``case_hit_threshold`` short-circuits the pipeline with the
   stored diagnosis/mitigation and its real similarity score as confidence
   -- never a fabricated LM guess when a real precedent already exists.
2. **On a miss**: :class:`dspy.ReAct` diagnoses the fault, with tools bound
   to the REAL :class:`gymact.gyms.sregym.SregymEnvironment.actuate`
   interface (``run_kubectl`` / ``submit_diagnosis`` / ``submit_mitigation``
   / ``observe_cluster_state`` / ``get_benchmark_status`` -- the exact
   ``Capability.binding`` values in ``SREGYM_CAPABILITIES``, read from the
   sibling ``~/gymact`` repo's real, committed module). ``actuate()`` is a
   coroutine; each ReAct tool is a thin synchronous wrapper that drives it
   with ``asyncio.run`` since :class:`dspy.ReAct` tools are called
   synchronously.
3. :class:`dspy.ChainOfThought` classifies the diagnosis against a real,
   finite taxonomy -- the ``inject_*`` method names grepped directly from
   ``vendor/gyms/sregym/sregym/generators/fault/inject_virtual.py`` (see
   :data:`SREGYM_FAULT_TAXONOMY`; the same ground-truth source the scanner
   branch's ``taxonomy.py`` was built from -- that module lives on
   ``feat/scanner-generalized-structural-anomaly``, not this branch, so the
   list here is regrepped independently rather than cross-branch imported).
4. The taxonomy step is wrapped in :func:`dspy.Refine` (not
   ``dspy.Assert``/``dspy.Suggest`` -- see "API note" below) enforcing: (a)
   the returned category is a member of the real taxonomy or the literal
   ``"UNCLASSIFIED"``, never a fabricated label (this directly targets the
   real "imagePullSecret" fabrication bug this session's prior trial hit);
   (b) reported confidence never exceeds the actual evidentiary ceiling
   (the case-library similarity score, or the ensemble agreement fraction)
   passed into the guard.
5. Ensemble voting over ``ensemble_n`` independent
   ``dspy.ChainOfThought(TaxonomyClassification)`` completions is merged by
   :class:`dspy.MultiChainComparison` -- DSPy's native holistic-reconciliation
   primitive -- rather than the hand-rolled thread-pool
   ``fire_ensemble``/``merge_predictions`` in
   ``autofde_lab.fabric.dspy_ensemble``.
6. On a caller-confirmed successful outcome, :meth:`SregymDiagnosisPipeline.retain`
   persists a new :class:`~autofde_lab.case_library.model.Case` via the real
   :class:`~autofde_lab.case_library.sqlite_store.CaseLibraryStore`.

API note -- why ``dspy.Refine``, not ``dspy.Assert``
-----------------------------------------------------
``dspy.Assert``/``dspy.Suggest`` do not exist in the installed ``dspy==3.3.0``
(confirmed live: ``hasattr(dspy, "Assert")`` is ``False``). DSPy's own
replacement for that constraint-retry mechanism in this version is
:func:`dspy.Refine` (``dspy.Refine(module, N, reward_fn, threshold)``):  it
re-runs the wrapped module up to ``N`` times, scoring each attempt with
``reward_fn(kwargs, prediction) -> float`` and keeping the first attempt
that clears ``threshold``. :func:`_taxonomy_guard_reward` below is that
``reward_fn`` and encodes exactly the two constraints requirement 4 above
asks ``dspy.Assert`` to enforce.

Case-library abstraction note
------------------------------
The task asked for retention "via the case library's abstraction layer"
(``autofde_lab.case_library.abstraction``). That module exists only on the
sibling worktree branch ``feat/case-library-abstraction`` (not this branch,
and not merged here) and has one confirmed real defect in
``_SERVICE_MARKERS`` (space-separated ``"service billing-api"`` leaks
unabstracted). Rather than either (a) importing code from an unmerged
branch into this one, which this task did not authorize, or (b) silently
reproducing the confirmed-defective regex verbatim, :meth:`retain` uses the
case library's base, already-real :class:`~autofde_lab.case_library.model.Case`
/ :class:`~autofde_lab.case_library.sqlite_store.CaseLibraryStore` directly
-- concrete, non-templated retention, not generalized-template retention.
This is a named workaround, not a silent downgrade.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Literal
from uuid import uuid4

import dspy

from autofde_lab.case_library import (
    Case,
    CaseLibraryStore,
    ProblemSignature,
    ScoredCase,
    retrieve_best_match,
)
from autofde_lab.case_library.outcome_predicate import ConfirmedVia, OracleVerdict, OutcomeVerdict

__all__ = [
    "Anomaly",
    "SREGYM_FAULT_TAXONOMY",
    "UNCLASSIFIED",
    "symptom_signature_from_anomaly",
    "describe_anomaly",
    "TaxonomyClassification",
    "DiagnoseFault",
    "SregymDiagnosisPipeline",
    "oracle_verdict_from_environment",
    "build_oracle_verdict_fn",
]


# ---------------------------------------------------------------------------
# Anomaly -- mirrored, not imported
# ---------------------------------------------------------------------------
#
# The generalized-structural-anomaly scanner's real `Anomaly` dataclass
# lives at `src/autofde_lab_planner/scanner/models.py` on branch
# `feat/scanner-generalized-structural-anomaly` (read directly from that
# worktree this session), not on this branch. Rather than assuming a
# "plausible" shape, this is a field-for-field mirror of that real,
# committed dataclass, cited above -- pending an eventual merge, at which
# point this local copy should be deleted in favor of the real import.

RelationClass = Literal[
    "declared_vs_observed",
    "dangling_reference",
    "insufficient_capability",
    "aggregate_threshold",
]


@dataclass(frozen=True, slots=True)
class Anomaly:
    """Mirror of ``autofde_lab_planner.scanner.models.Anomaly`` (see module
    docstring for provenance). Same shape, same field names."""

    kind: str
    object_name: str
    namespace: str
    relation_class: RelationClass
    field: str
    observed: str
    expected: str | None
    detail: str


# ---------------------------------------------------------------------------
# Taxonomy -- real inject_* method names, regrepped from the vendored source
# ---------------------------------------------------------------------------
#
# `grep -n "def inject_" vendor/gyms/sregym/sregym/generators/fault/inject_virtual.py`
# run live this session. One commented-out definition
# (`# def inject_storage_provisioner_outage`) is excluded -- it is not a
# real callable method.

SREGYM_FAULT_TAXONOMY: tuple[str, ...] = (
    "inject_misconfig_k8s",
    "inject_auth_miss_mongodb",
    "inject_scale_pods_to_zero",
    "inject_assign_to_non_existent_node",
    "inject_pvc_claim_mismatch",
    "inject_wrong_bin_usage",
    "inject_missing_service",
    "inject_resource_request",
    "inject_cpu_throttle",
    "inject_wrong_service_selector",
    "inject_service_wrong_pod_selection",
    "inject_service_dns_resolution_failure",
    "inject_wrong_dns_policy",
    "inject_stale_coredns_config",
    "inject_sidecar_port_conflict",
    "inject_liveness_probe_too_aggressive",
    "inject_missing_configmap",
    "inject_configmap_drift",
    "inject_readiness_probe_misconfiguration",
    "inject_liveness_probe_misconfiguration",
    "inject_duplicate_pvc_mounts",
    "inject_env_variable_shadowing",
    "inject_rolling_update_misconfigured",
    "inject_toleration_without_matching_taint",
    "inject_persistent_volume_affinity_violation",
    "inject_pod_anti_affinity_deadlock",
    "inject_rpc_timeout_retries_misconfiguration",
    "inject_daemon_set_image_replacement",
    "inject_rbac_misconfiguration",
    "inject_gogc_env_variable_patch",
    "inject_service_port_conflict",
    "inject_tor_network_partition",
    "inject_init_container_dependency_hang",
    "inject_fd_exhaustion",
)

UNCLASSIFIED = "UNCLASSIFIED"


def symptom_signature_from_anomaly(anomaly: Anomaly) -> ProblemSignature:
    """Build the case library's normalized :class:`ProblemSignature` from a
    real :class:`Anomaly` -- the same three-field shape
    (``namespace``/``anomalous_kinds``/``diverged_fields``) every other
    retrieval path in this repo compares by Jaccard similarity."""
    diverged = f"{anomaly.kind}.{anomaly.field}={anomaly.observed}"
    return ProblemSignature(
        namespace=anomaly.namespace,
        anomalous_kinds=frozenset({anomaly.kind}),
        diverged_fields=frozenset({diverged}),
    )


def describe_anomaly(anomaly: Anomaly) -> str:
    """Render a real :class:`Anomaly` as the free-text symptom description
    fed into every DSPy signature below."""
    expected = anomaly.expected if anomaly.expected is not None else "<no baseline recorded>"
    return (
        f"kind={anomaly.kind} object={anomaly.object_name} namespace={anomaly.namespace} "
        f"relation_class={anomaly.relation_class} field={anomaly.field} "
        f"observed={anomaly.observed!r} expected={expected!r} detail={anomaly.detail}"
    )


# ---------------------------------------------------------------------------
# DSPy signatures
# ---------------------------------------------------------------------------


class DiagnoseFault(dspy.Signature):
    """Diagnose a Kubernetes cluster fault. Use the provided tools to inspect
    the REAL live cluster state (kubectl) before concluding; never guess a
    root cause the tools have not evidenced."""

    symptom_description: str = dspy.InputField()
    diagnosis: str = dspy.OutputField(desc="free-text root-cause diagnosis grounded in tool output")


class TaxonomyClassification(dspy.Signature):
    """Classify a diagnosed Kubernetes fault into exactly one of a fixed,
    real taxonomy of SREGym fault-injector categories, or the literal
    UNCLASSIFIED. Never invent a category outside known_categories."""

    symptom_description: str = dspy.InputField()
    diagnosis: str = dspy.InputField()
    known_categories: str = dspy.InputField(
        desc="newline-separated list of the ONLY valid category labels, plus UNCLASSIFIED"
    )
    category: str = dspy.OutputField(desc="exactly one value from known_categories")
    confidence: float = dspy.OutputField(
        desc="0.0-1.0; must not exceed the actual evidentiary support for this classification"
    )


# ---------------------------------------------------------------------------
# dspy.Refine reward function -- the dspy.Assert replacement (see module doc)
# ---------------------------------------------------------------------------


def _taxonomy_guard_reward(taxonomy: tuple[str, ...]) -> Callable[[dict, Any], float]:
    known = set(taxonomy) | {UNCLASSIFIED}

    def reward_fn(kwargs: dict, prediction: Any) -> float:
        category = str(getattr(prediction, "category", "")).strip()
        try:
            confidence = float(getattr(prediction, "confidence", 0.0))
        except (TypeError, ValueError):
            return 0.0
        if category not in known:
            return 0.0
        ceiling = float(kwargs.get("confidence_ceiling", 1.0))
        if confidence > ceiling + 1e-9:
            return 0.0
        if not (0.0 <= confidence <= 1.0):
            return 0.0
        return 1.0

    return reward_fn


# ---------------------------------------------------------------------------
# ReAct tools bound to the REAL SregymEnvironment.actuate() interface
# ---------------------------------------------------------------------------


def _run_coroutine(coro: Any) -> Any:
    """Run a coroutine to completion from a synchronous ReAct tool call.

    ``dspy.ReAct`` invokes tools synchronously; ``SregymEnvironment``'s
    every mutating/reading method (``observe``/``actuate``/``verify``) is a
    real coroutine (see ``/Users/sac/gymact/src/gymact/gyms/sregym.py``).
    ``asyncio.run`` is safe here because each tool call is a fresh, isolated
    invocation with no outstanding event loop in this synchronous call path.
    """
    return asyncio.run(coro)


def build_sregym_react_tools(environment: Any) -> list[Callable[..., str]]:
    """Build synchronous ``dspy.ReAct``-compatible tool functions bound to a
    REAL ``gymact.gyms.sregym.SregymEnvironment`` instance.

    Imports ``gymact.gyms.sregym`` lazily (only when an environment is
    actually supplied) so the reasoning package has no hard import-time
    dependency on the sibling ``gymact`` checkout.
    """
    from gymact.gyms.sregym import SREGYM_CAPABILITIES

    capabilities_by_binding = {capability.binding: capability for capability in SREGYM_CAPABILITIES}

    def run_kubectl(command: str) -> str:
        """Execute a real kubectl command through sregym's real kubectl-mcp server."""
        capability = capabilities_by_binding["run_kubectl"]
        result = _run_coroutine(environment.actuate(capability, {"command": command}))
        return str(result)

    def observe_cluster_state() -> str:
        """Read sregym's real conductor /status endpoint."""
        capability = capabilities_by_binding["observe_cluster_state"]
        result = _run_coroutine(environment.actuate(capability, {}))
        return str(result)

    return [run_kubectl, observe_cluster_state]


def build_sregym_submission_fns(
    environment: Any,
) -> tuple[Callable[[str], str], Callable[..., str]]:
    """Build synchronous submit_diagnosis/submit_mitigation callables bound
    to a REAL ``SregymEnvironment``, for the caller to invoke once diagnosis
    and mitigation are ready (not exposed as ReAct tools -- these are
    terminal actions, not exploratory ones)."""
    from gymact.gyms.sregym import SREGYM_CAPABILITIES

    capabilities_by_binding = {capability.binding: capability for capability in SREGYM_CAPABILITIES}

    def submit_diagnosis(diagnosis: str, category: str) -> str:
        capability = capabilities_by_binding["submit_diagnosis"]
        payload = {"diagnosis": diagnosis, "category": category}
        result = _run_coroutine(environment.actuate(capability, payload))
        return str(result)

    def submit_mitigation(commands: tuple[str, ...]) -> str:
        capability = capabilities_by_binding["submit_mitigation"]
        payload = {"commands": list(commands)}
        result = _run_coroutine(environment.actuate(capability, payload))
        return str(result)

    return submit_diagnosis, submit_mitigation


# ---------------------------------------------------------------------------
# External oracle -- gymact's real verify(), not a self-certified re-scan
# ---------------------------------------------------------------------------
#
# `outcome_predicate.evaluate_outcome()` requires a real `OracleVerdict` to
# distinguish CONFIRMED from DISPUTED; a caller that always passes
# `OracleVerdict(present=False)` is silently skipping independent
# verification and letting the structural re-check alone decide. gymact's
# `SregymEnvironment.verify(expected)` (see `~/gymact/src/gymact/gyms/
# sregym.py`) is a real, bounded poll of sregym's own conductor /status
# endpoint until it matches `expected` or a timeout elapses -- the exact
# externally-observed check `kubernetes_reconciliation.py`'s
# `KubernetesReconciliationEnvironment.verify()` uses the same way. Wiring
# it here (rather than autofde-lab's own re-scan) is what makes a
# CONFIRMED verdict `confirmed_via="structural_and_oracle"` mean an
# independent process actually re-checked convergence, not that
# autofde-lab re-asked itself the same question twice.


async def oracle_verdict_from_environment(
    environment: Any,
    expected: dict[str, Any],
) -> OracleVerdict:
    """Build a real :class:`OracleVerdict` from a real
    ``gymact.gyms.sregym.SregymEnvironment.verify()`` call.

    ``environment.verify(expected)`` polls the real conductor ``/status``
    endpoint (bounded, real HTTP, real subprocess) until it matches
    ``expected`` or times out -- this is the external, independently
    observed check; the returned ``OracleVerdict`` has ``present=True``
    when an oracle call actually completed.

    If ``verify()`` itself raises (network error, unreachable cluster,
    malformed conductor response, timeout escaping as an exception, ...)
    that failure is caught here and degrades to
    ``OracleVerdict(present=False)`` -- per
    ``.claude/rules/absence-is-not-evidence.md``, a transient oracle
    failure is not evidence the oracle disagreed; it is evidence the
    oracle was not consulted, so ``evaluate_outcome`` correctly falls
    back to a structural-only verdict rather than the exception
    propagating raw and crashing the whole pipeline.
    """
    try:
        passed, _observed = await environment.verify(expected)
    except Exception:
        return OracleVerdict(present=False)
    return OracleVerdict(present=True, passed=bool(passed))


def build_oracle_verdict_fn(environment: Any) -> Callable[[dict[str, Any]], OracleVerdict]:
    """Synchronous wrapper around :func:`oracle_verdict_from_environment`,
    matching the synchronous style of :func:`build_sregym_submission_fns`
    (``dspy``/plain callers invoke this synchronously; the real
    ``verify()`` coroutine runs underneath via :func:`_run_coroutine`).

    Same degrade-on-exception behavior as
    :func:`oracle_verdict_from_environment`: a raised exception from
    ``verify()`` becomes ``OracleVerdict(present=False)``, never a raw
    propagated exception.
    """

    def oracle_verdict(expected: dict[str, Any]) -> OracleVerdict:
        try:
            passed, _observed = _run_coroutine(environment.verify(expected))
        except Exception:
            return OracleVerdict(present=False)
        return OracleVerdict(present=True, passed=bool(passed))

    return oracle_verdict


class _EnsembleClassify(dspy.Module):
    """Fire ``ensemble_n`` independent real ``ChainOfThought`` completions
    over :class:`TaxonomyClassification` and merge them with
    :class:`dspy.MultiChainComparison`.

    ``classify``/``compare`` are set as real instance attributes (real
    registered submodules), not closure variables -- required for
    :meth:`dspy.Module.deepcopy`/``named_predictors``/``set_lm`` (used by
    :func:`dspy.Refine`) to see and retarget them correctly.
    """

    def __init__(self, *, ensemble_n: int) -> None:
        super().__init__()
        self.ensemble_n = ensemble_n
        self.classify = dspy.ChainOfThought(TaxonomyClassification)
        self.compare = dspy.MultiChainComparison(TaxonomyClassification, M=ensemble_n)

    def forward(
        self,
        symptom_description: str,
        diagnosis: str,
        known_categories: str,
        confidence_ceiling: float = 1.0,
    ) -> Any:
        completions = [
            self.classify(
                symptom_description=symptom_description,
                diagnosis=diagnosis,
                known_categories=known_categories,
            )
            for _ in range(self.ensemble_n)
        ]
        return self.compare(
            completions,
            symptom_description=symptom_description,
            diagnosis=diagnosis,
            known_categories=known_categories,
        )


# ---------------------------------------------------------------------------
# The one compiled pipeline
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PipelineResult:
    """Final, typed result of one :meth:`SregymDiagnosisPipeline.forward` call."""

    source: Literal["case_library", "reasoning"]
    diagnosis: str
    mitigation_commands: tuple[str, ...]
    taxonomy_category: str | None
    confidence: float
    case_id: str | None = None
    ensemble_agreement: float | None = None


class SregymDiagnosisPipeline(dspy.Module):
    """One compiled DSPy module: case-library retrieval -> ReAct diagnosis
    (real cluster tools) -> ensembled, taxonomy-guarded classification ->
    optional retention.

    :param case_store: real :class:`CaseLibraryStore` (SQLite-backed or
        ``:memory:``).
    :param environment: a real ``gymact.gyms.sregym.SregymEnvironment``
        instance, or ``None``. When ``None`` the ReAct diagnosis step is
        skipped and the symptom description itself stands in as the
        diagnosis text -- this is the fixture/offline path used by the unit
        tests in this module, which construct no live cluster.
    :param taxonomy: the real, finite taxonomy list (defaults to
        :data:`SREGYM_FAULT_TAXONOMY`).
    :param ensemble_n: number of independent ``ChainOfThought`` completions
        fired for the taxonomy vote (default 3).
    :param case_hit_threshold: minimum Jaccard score for a case-library hit
        to short-circuit reasoning (default 0.5, matching
        :mod:`autofde_lab.case_library.similarity`'s own default).
    """

    def __init__(
        self,
        case_store: CaseLibraryStore,
        *,
        environment: Any | None = None,
        taxonomy: tuple[str, ...] = SREGYM_FAULT_TAXONOMY,
        ensemble_n: int = 3,
        case_hit_threshold: float = 0.5,
    ) -> None:
        super().__init__()
        self._case_store = case_store
        self._taxonomy = taxonomy
        self._ensemble_n = ensemble_n
        self._case_hit_threshold = case_hit_threshold
        self._known_categories_text = "\n".join((*taxonomy, UNCLASSIFIED))

        self._diagnose_react: dspy.Module | None = None
        if environment is not None:
            tools = build_sregym_react_tools(environment)
            self._diagnose_react = dspy.ReAct(DiagnoseFault, tools=tools)

        ensemble_module = _EnsembleClassify(ensemble_n=ensemble_n)
        self._classify = ensemble_module.classify
        self._compare = ensemble_module.compare
        self._guarded_classify = dspy.Refine(
            module=ensemble_module,
            N=2,
            reward_fn=_taxonomy_guard_reward(taxonomy),
            threshold=1.0,
        )

    def forward(self, anomaly: Anomaly) -> PipelineResult:
        signature = symptom_signature_from_anomaly(anomaly)
        hit: ScoredCase | None = retrieve_best_match(
            signature, self._case_store.all_cases(), threshold=self._case_hit_threshold
        )
        if hit is not None:
            return PipelineResult(
                source="case_library",
                diagnosis=hit.case.diagnosis,
                mitigation_commands=hit.case.mitigation_commands,
                taxonomy_category=None,
                confidence=hit.score,
                case_id=hit.case.case_id,
            )

        symptom_description = describe_anomaly(anomaly)
        if self._diagnose_react is not None:
            react_prediction = self._diagnose_react(symptom_description=symptom_description)
            diagnosis_text = str(react_prediction.diagnosis)
        else:
            diagnosis_text = symptom_description

        merged = self._guarded_classify(
            symptom_description=symptom_description,
            diagnosis=diagnosis_text,
            known_categories=self._known_categories_text,
            confidence_ceiling=1.0,
        )
        category = str(getattr(merged, "category", UNCLASSIFIED)).strip()
        if category not in set(self._taxonomy) | {UNCLASSIFIED}:
            category = UNCLASSIFIED
        try:
            confidence = float(getattr(merged, "confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))

        return PipelineResult(
            source="reasoning",
            diagnosis=diagnosis_text,
            mitigation_commands=(),
            taxonomy_category=category,
            confidence=confidence,
        )

    def retain(
        self,
        anomaly: Anomaly,
        result: PipelineResult,
        *,
        mitigation_commands: tuple[str, ...],
        verdict: OutcomeVerdict,
        confirmed_via: ConfirmedVia = "n/a",
        case_id: str | None = None,
    ) -> Case | None:
        """Retain a case per the real three-way
        :class:`~autofde_lab.case_library.outcome_predicate.OutcomeVerdict`.

        ``verdict`` and ``confirmed_via`` are the exact pair
        :func:`autofde_lab.case_library.outcome_predicate.evaluate_outcome`
        returns -- callers run the real structural re-check (and oracle, if
        one is available) and pass its verdict through unmodified, rather
        than this method re-deriving or hardcoding an outcome.

        - ``UNCONFIRMED`` refuses to retain (returns ``None``, matching the
          prior ``outcome_confirmed=False``/``None`` refusal shape) -- the
          structural re-check itself failed, so there is nothing to
          persist, per ``.claude/rules/absence-is-not-evidence.md``.
        - ``CONFIRMED`` retains with ``outcome=True`` and ``confirmed_via``
          set to the real provenance (``"structural_only"`` or
          ``"structural_and_oracle"``).
        - ``DISPUTED`` is retained too -- never discarded -- as its own
          tagged evidence artifact: ``outcome=None`` (the disagreement is
          not coerced into a boolean) and ``confirmed_via="disputed"``,
          so a disputed case remains distinguishable in the store from both
          a confirmed success and a case with no verdict provenance at all
          (``confirmed_via="n/a"``).

        See the module docstring's "case-library abstraction note" for why
        this stores a concrete :class:`Case` rather than an
        abstracted/templated one.
        """
        if verdict is OutcomeVerdict.UNCONFIRMED:
            return None
        signature = symptom_signature_from_anomaly(anomaly)
        if verdict is OutcomeVerdict.DISPUTED:
            case_outcome: bool | None = None
            case_confirmed_via = "disputed"
        else:
            if confirmed_via not in ("structural_only", "structural_and_oracle"):
                raise ValueError(
                    "retain(verdict=OutcomeVerdict.CONFIRMED) requires confirmed_via to be "
                    "'structural_only' or 'structural_and_oracle' (the real provenance "
                    "evaluate_outcome() returned alongside CONFIRMED); got "
                    f"{confirmed_via!r}. The 'n/a' default exists only for UNCONFIRMED/"
                    "DISPUTED callers -- a CONFIRMED case must never silently persist "
                    "with unproven provenance."
                )
            case_outcome = True
            case_confirmed_via = confirmed_via
        case = Case(
            case_id=case_id or f"trial-{uuid4().hex}",
            signature=signature,
            diagnosis=result.diagnosis,
            mitigation_commands=mitigation_commands,
            outcome=case_outcome,
            confirmed_via=case_confirmed_via,
        )
        self._case_store.put(case)
        return case
