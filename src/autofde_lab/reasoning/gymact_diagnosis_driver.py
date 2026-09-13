# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""The real gymact-mediated diagnosis driver, wired through
:func:`autofde_lab.powl.runner.run_pipeline` -- the answer
``scripts/run_gymact_mediated_trial.py`` (a real, deliberately-kept
throwaway spike, not deleted by this module) named as still missing: "never
actually wired despite runner.py's docstring naming it."

What changed relative to the spike
------------------------------------
The spike drives ``observe -> kubectl reads -> scan -> phi -> classify ->
submit_diagnosis -> (no remediation synthesis yet) -> submit_mitigation ->
verify`` with hand-ordered ``await`` calls in a linear script. This module
builds the exact same real collaborators (real ``SregymEnvironment`` via
``SregymVendorProvider().materialize()``, the real
``autofde_lab_planner.scanner.registry.scan`` /
``autofde_lab_planner.scanner.taxonomy.classify`` sequence, the real
``CapabilityGate``-gated ``env.actuate()`` calls) but never calls them
directly in this module's own control flow. Instead:

1. :func:`autofde_lab.powl.runner.build_pipeline_powl_node` builds the real
   POWL pipeline tree, whose terminal ``gymact_*`` Atom labels
   (``ALLOWED_ACTUATION_BINDING_LABELS`` in that module) are the real
   actuation-class labels this driver binds to. **Correction (2026-08-12)**:
   this paragraph previously said "five" -- re-verified this session
   directly against the real frozenset literal in ``runner.py``, the real
   current count is **11** (grew via later, separate work adding the
   recheck/mitigation labels; ``runner.py``'s own docstring carried the
   same stale "four" count, corrected in the same pass -- see that
   module's own correction note). This driver's real ``action_bindings``
   dict (below) currently binds all 14 real ``GYMACT_*_LABEL`` constants
   it imports (10 as gated capability bindings, 4 as bare action bindings
   for labels with no real gymact ``Capability`` behind them) -- the 14
   total is a different, larger count than the 11-member
   ``ALLOWED_ACTUATION_BINDING_LABELS`` set itself, since this driver also
   binds real non-actuation-class labels (status/namespace/pod/scan reads)
   that were never part of that frozenset.
2. Each of the 11 real actuation-class labels is bound to a real
   :class:`~autofde_lab.powl.runner.GatedCapabilityBinding` -- a closure over
   the one materialized ``env``, wrapping a real ``CapabilityGate``-checked
   gymact capability name -- never a bare callable (``run_pipeline`` itself
   refuses a bare callable for these actuation-class labels; see that
   module).
3. :func:`autofde_lab.powl.runner.run_pipeline` is called exactly once. THAT
   call is what fires each bound closure, in the order the real POWL tree's
   structural replay enables them -- this module's own code never calls
   ``env.observe()``/``env.actuate()``/``env.verify()`` directly; it only
   constructs the tree and the bindings and hands both to ``run_pipeline``.

Why bindings run each coroutine in a dedicated thread, not ``asyncio.run``
----------------------------------------------------------------------------
``sregym_pipeline.py``'s ReAct tools call ``asyncio.run(coro)`` directly
because a ``dspy.ReAct`` tool call happens with no event loop already
running. This driver is different: ``run_gymact_mediated_diagnosis`` is
itself ``async def`` (this task's own required signature), so by the time
``run_pipeline`` (a plain synchronous function) invokes a bound closure
synchronously, a real event loop IS already running for the driver's own
coroutine -- ``asyncio.run()`` inside that closure would raise
``RuntimeError: asyncio.run() cannot be called from a running event loop``.
``_run_coroutine_sync`` below runs each closure's coroutine to completion in
a short-lived dedicated thread with its own fresh event loop instead --
still a real, unmocked ``asyncio.run`` underneath, just executed off the
driver's own running loop so the two never collide.

Real remediation synthesis: not built yet, named honestly
-------------------------------------------------------------
Per the spike's own step [6/7] comment: automated mitigation-command
synthesis from a real ``Anomaly`` is real, unbuilt scope. The
``gymact_actuate_remediate`` binding therefore performs a real, non-mutating
``run_kubectl`` re-read (never a fabricated "fix" command) -- a real
``env.actuate()`` call through the real gated capability, honestly scoped to
"confirm current state before mitigation", not to a remediation this repo
cannot yet synthesize. ``submit_mitigation`` reports
``mitigation="not_attempted"`` for the same reason the spike does.

``verify`` is not a gymact ``Capability``
--------------------------------------------
``SregymEnvironment.verify()`` is a plain coroutine, never wired into
``actuate()``'s dispatch table (see ``gymact_capability_gate.py``'s module
docstring) -- so the ``gymact_verify`` binding calls ``env.verify()``
directly, not through ``env.actuate()``, and takes a bare ``ActionBinding``
rather than a ``GatedCapabilityBinding``: there is no real gymact
``Capability`` behind it to gate against. An earlier pass in this session
added a fictitious ``"verify"`` entry to ``gymact_capabilities.toml`` just to
satisfy the (incorrect) requirement that every actuation-class label be
capability-gated; ``CapabilityGate.stale_entries()`` correctly caught it as
drift (no real ``SREGYM_CAPABILITIES`` entry named ``"verify"`` exists), and
it was removed. Fixed forward in both ``runner.py`` (``gymact_verify`` moved
to its own ``ALLOWED_ACTUATION_ORACLE_LABELS`` set, bare-binding-only, not
required by the default completeness check) and here.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from autofde_lab.case_library.outcome_predicate import OracleVerdict, OutcomeVerdict, evaluate_outcome
from autofde_lab.fabric.gymact_capability_gate import DEFAULT_MANIFEST_PATH, CapabilityGate
from autofde_lab.ocel.log import OcelLog
from autofde_lab.ocel.mcp_session import append_tool_call_event
from autofde_lab.fabric.gymact_pipeline import (
    GYMACT_CHECK_DEPLOYMENTS_LABEL,
    GYMACT_CHECK_NAMESPACE_LABEL,
    GYMACT_CHECK_PODS_LABEL,
    GYMACT_CHECK_SERVICES_LABEL,
    GYMACT_CHECK_STATUS_LABEL,
    GYMACT_RECHECK_DEPLOYMENTS_LABEL,
    GYMACT_RECHECK_PODS_LABEL,
    GYMACT_RECHECK_SCAN_LABEL,
    GYMACT_RECHECK_SERVICES_LABEL,
    GYMACT_SCAN_ANOMALIES_LABEL,
    GYMACT_SUBMIT_DIAGNOSIS_LABEL,
    GYMACT_SUBMIT_MITIGATION_LABEL,
    GYMACT_VERIFY_LABEL,
    GYMACT_WAIT_FOR_DEPLOY_LABEL,
    PIPELINE_SPEC,
    build_pipeline_powl_node,
    ocel_dict_to_log,
)
from gymact.powl.runner import PipelineStallResult, run_pipeline
from gymact.powl.spec import GatedCapabilityBinding
from autofde_lab_planner.scanner.registry import ClusterState, scan
from autofde_lab_planner.scanner.taxonomy import classify

__all__ = [
    "GymactMediatedDiagnosisResult",
    "run_gymact_mediated_diagnosis",
]


def _run_coroutine_sync(coro: Any) -> Any:
    """Run a real coroutine to completion from a synchronous binding
    closure, without colliding with the driver's own already-running event
    loop -- see this module's docstring for why plain ``asyncio.run`` cannot
    be used here. A real ``asyncio.run`` call still happens, just inside a
    dedicated worker thread with its own fresh loop."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def _capability(capabilities: Any, name: str) -> Any:
    for cap in capabilities:
        if cap.binding == name:
            return cap
    raise KeyError(f"no real gymact capability named {name!r}")


@dataclass(frozen=True, slots=True)
class GymactMediatedDiagnosisResult:
    """Real, typed result of one gymact-mediated diagnosis run.

    ``ocel_log``/``stall`` are exactly what ``run_pipeline`` returned for
    this run's real structural replay. ``verdict``/``confirmed_via`` are
    :func:`autofde_lab.case_library.outcome_predicate.evaluate_outcome`'s
    real output, computed from the real ``env.verify()`` oracle call fired
    by the ``gymact_verify`` binding -- never a self-certified re-scan.
    """

    problem_id: str
    ocel_log: OcelLog
    stall: PipelineStallResult
    verdict: OutcomeVerdict
    confirmed_via: str
    verify_observed: dict[str, Any]
    structural_recheck_anomaly_count: int | None
    submit_diagnosis_stage_wait_passed: bool | None
    """Real, observable state for diagnosing a submission-timing race,
    exactly the class of defect found and fixed forward earlier this
    session ("Cannot submit at stage: 'setup'" -- the real conductor
    correctly rejecting a submission attempted before its own stage
    machine reached 'diagnosis'). ``None`` when ``_submit_diagnosis``'s
    binding never fired at all (distinct from ``False``, which means it
    fired and the real bounded wait for stage 'diagnosis' timed out) --
    was previously tracked in ``diagnosis_state`` but silently dropped at
    result-construction time, unavailable for a caller diagnosing a real
    failure without re-reading the raw OCEL log."""


# Real, source-derived map from every real SREGym problem_id (as registered
# in the real `sregym/conductor/problems/registry.py`'s own
# `PROBLEM_REGISTRY` dict) to the real k8s namespace that problem's app
# deploys into. Found and fixed forward this cycle: this driver previously
# hardcoded `namespace="social-network"` as the ONE default for every
# problem_id, correct only by coincidence for this session's sole live test
# problem (`wrong_dns_policy_social_network`) -- 101 of these 123 real
# problem IDs deploy a DIFFERENT app into a DIFFERENT real namespace
# (`hotel-reservation`, `astronomy-shop`, `train-ticket`,
# `blueprint-hotel-reservation`, or `fleetcast`, confirmed by directly
# reading each app's own `service/metadata/*.json` "Namespace" key -- NOT
# guessed from a naming convention: `fleet_cast` -> `"fleetcast"`, no dash,
# breaking the pattern every other app happened to follow). A live trial
# against any of those 101 problems using the old hardcoded default would
# have silently scanned the WRONG (or a nonexistent) namespace, producing a
# false `no_anomaly_detected` -- exactly the confident-wrong-plan failure
# `.claude/rules/absence-is-not-evidence.md` names.
#
# Derived by statically parsing (Python `ast`, no execution, no side
# effects) `registry.py`'s real `PROBLEM_REGISTRY` dict: for each entry
# either read the literal `app_name=` keyword argument the lambda passes to
# its problem class (e.g. `WrongDNSPolicy(app_name="hotel_reservation", ...)`
# for the 22 parameterized entries), or -- for the 101 entries that are bare
# class references with no `app_name` kwarg -- resolve which
# `sregym.service.apps.*` module that class's own file imports and hardcodes
# via `super().__init__(app=...)`. Every one of the 123 real registry
# entries resolved this way (zero guessed). `multiple_failures` (a real,
# dynamically-composed multi-app problem) is not a static registry entry and
# is intentionally absent from this table -- a caller for that one real
# problem must pass `namespace=` explicitly, honestly, since no single
# static namespace exists for it.
PROBLEM_ID_NAMESPACE: dict[str, str] = {
    "admission_webhook_outage_hotel_reservation": "hotel-reservation",
    "admission_webhook_tls_mismatch_hotel_reservation": "hotel-reservation",
    "assign_to_non_existent_node": "social-network",
    "astronomy_shop_ad_service_failure": "astronomy-shop",
    "astronomy_shop_ad_service_high_cpu": "astronomy-shop",
    "astronomy_shop_ad_service_image_slow_load": "astronomy-shop",
    "astronomy_shop_ad_service_manual_gc": "astronomy-shop",
    "astronomy_shop_cart_service_failure": "astronomy-shop",
    "astronomy_shop_failed_readiness_probe": "astronomy-shop",
    "astronomy_shop_payment_service_failure": "astronomy-shop",
    "astronomy_shop_payment_service_unreachable": "astronomy-shop",
    "astronomy_shop_product_catalog_service_failure": "astronomy-shop",
    "auth_miss_mongodb": "social-network",
    "calico_route_reflector_label_drift_hotel_reservation": "hotel-reservation",
    "capacity_decrease_rpc_retry_storm": "blueprint-hotel-reservation",
    "cfs_cpu_throttling_hotel_reservation": "hotel-reservation",
    "configmap_drift_hotel_reservation": "hotel-reservation",
    "cronjob_sidecar_blocks_completion_hotel_reservation": "hotel-reservation",
    "cumulative_admission_webhook_timeout_hotel_reservation": "hotel-reservation",
    "dev_shm_exhaustion_hotel_reservation": "hotel-reservation",
    "duplicate_pvc_mounts_astronomy_shop": "astronomy-shop",
    "duplicate_pvc_mounts_hotel_reservation": "hotel-reservation",
    "duplicate_pvc_mounts_social_network": "social-network",
    "edge_request_filter_cpu_saturation": "astronomy-shop",
    "env_variable_shadowing_astronomy_shop": "astronomy-shop",
    "ephemeral_port_range_hotel_reservation": "hotel-reservation",
    "expired_tls_hotel_reservation": "hotel-reservation",
    "faulty_image_correlated": "hotel-reservation",
    "feature_flag_latent_bug_hotel_reservation": "hotel-reservation",
    "file_descriptor_exhaustion": "hotel-reservation",
    "finalizer_deadlock_controller_hotel_reservation": "hotel-reservation",
    "gc_capacity_degradation": "blueprint-hotel-reservation",
    "hpa_missing_effective_cpu_request_hotel_reservation": "hotel-reservation",
    "incorrect_image": "astronomy-shop",
    "incorrect_port_assignment": "astronomy-shop",
    "ingress_misroute": "hotel-reservation",
    "init_container_dependency_hang_astronomy_shop": "astronomy-shop",
    "init_container_dependency_hang_hotel_reservation": "hotel-reservation",
    "init_container_dependency_hang_social_network": "social-network",
    "internal_traffic_policy_local_astronomy_shop": "astronomy-shop",
    "k8s_target_port-misconfig": "social-network",
    "kafka_poison_pill_hol_block": "astronomy-shop",
    "kafka_producer_leak": "astronomy-shop",
    "kafka_queue_problems": "astronomy-shop",
    "kubelet_crash": "astronomy-shop",
    "kubelet_eviction_threshold_misconfig": "astronomy-shop",
    "latent_sector_error": "hotel-reservation",
    "liveness_probe_misconfiguration_astronomy_shop": "astronomy-shop",
    "liveness_probe_misconfiguration_hotel_reservation": "hotel-reservation",
    "liveness_probe_misconfiguration_social_network": "social-network",
    "liveness_probe_too_aggressive_astronomy_shop": "astronomy-shop",
    "liveness_probe_too_aggressive_hotel_reservation": "hotel-reservation",
    "liveness_probe_too_aggressive_social_network": "social-network",
    "load_spike_rpc_retry_storm": "blueprint-hotel-reservation",
    "loadgenerator_flood_homepage": "astronomy-shop",
    "misconfig_app_hotel_res": "hotel-reservation",
    "missing_configmap_hotel_reservation": "hotel-reservation",
    "missing_configmap_social_network": "social-network",
    "missing_env_variable_astronomy_shop": "astronomy-shop",
    "missing_service_astronomy_shop": "astronomy-shop",
    "missing_service_hotel_reservation": "hotel-reservation",
    "missing_service_social_network": "social-network",
    "mutating_webhook_resource_limits_social_network": "social-network",
    "namespace_memory_limit": "hotel-reservation",
    "network_policy_block": "hotel-reservation",
    "nightly_rebalance_oom_hotel_reservation": "hotel-reservation",
    "node_clock_drift_hotel_reservation": "hotel-reservation",
    "node_conntrack_exhaustion_hotel_reservation": "hotel-reservation",
    "operator_invalid_affinity_toleration": "fleetcast",
    "operator_non_existent_storage": "fleetcast",
    "operator_overload_replicas": "fleetcast",
    "operator_security_context_fault": "fleetcast",
    "operator_wrong_operator_image": "fleetcast",
    "operator_wrong_update_strategy_fault": "fleetcast",
    "persistent_volume_affinity_violation": "social-network",
    "pod_anti_affinity_deadlock": "social-network",
    "pod_cidr_exhaustion_hotel_reservation": "hotel-reservation",
    "postgres_lock_contention_product_catalog": "astronomy-shop",
    "priority_preemption_cascade_hotel_reservation": "hotel-reservation",
    "psa_restricted_blocks_recreation_hotel_reservation": "hotel-reservation",
    "pvc_claim_mismatch": "hotel-reservation",
    "rbac_misconfiguration": "astronomy-shop",
    "readiness_probe_misconfiguration_astronomy_shop": "astronomy-shop",
    "readiness_probe_misconfiguration_hotel_reservation": "hotel-reservation",
    "readiness_probe_misconfiguration_social_network": "social-network",
    "resource_request_too_large": "hotel-reservation",
    "resource_request_too_small": "hotel-reservation",
    "revoke_auth_mongodb-1": "hotel-reservation",
    "revoke_auth_mongodb-2": "hotel-reservation",
    "rolling_update_misconfigured_hotel_reservation": "hotel-reservation",
    "rolling_update_misconfigured_social_network": "social-network",
    "scale_pod_zero_social_net": "social-network",
    "search_rate_retry_collapse_hotel_reservation": "hotel-reservation",
    "secret_rotation_stale_env_credentials_astronomy_shop": "astronomy-shop",
    "service_dns_resolution_failure_astronomy_shop": "astronomy-shop",
    "service_dns_resolution_failure_social_network": "social-network",
    "service_port_conflict_astronomy_shop": "astronomy-shop",
    "service_port_conflict_hotel_reservation": "hotel-reservation",
    "service_port_conflict_social_network": "social-network",
    "service_wrong_pod_selection_hotel_reservation": "hotel-reservation",
    "sidecar_port_conflict_astronomy_shop": "astronomy-shop",
    "sidecar_port_conflict_hotel_reservation": "hotel-reservation",
    "sidecar_port_conflict_social_network": "social-network",
    "silent_data_corruption": "hotel-reservation",
    "stale_coredns_config_astronomy_shop": "astronomy-shop",
    "stale_coredns_config_social_network": "social-network",
    "storage_user_unregistered-1": "hotel-reservation",
    "storage_user_unregistered-2": "hotel-reservation",
    "taint_no_toleration_social_network": "social-network",
    "trainticket_f17_nested_sql_select_clause_error": "train-ticket",
    "trainticket_f22_sql_column_name_mismatch_error": "train-ticket",
    "unschedulable_incorrect_port_assignment": "astronomy-shop",
    "update_incompatible_correlated": "hotel-reservation",
    "valkey_auth_disruption": "astronomy-shop",
    "valkey_memory_disruption": "astronomy-shop",
    "workload_imbalance": "astronomy-shop",
    "wrong_bin_usage": "hotel-reservation",
    "wrong_dns_policy_astronomy_shop": "astronomy-shop",
    "wrong_dns_policy_hotel_reservation": "hotel-reservation",
    "wrong_dns_policy_social_network": "social-network",
    "wrong_service_selector_astronomy_shop": "astronomy-shop",
    "wrong_service_selector_hotel_reservation": "hotel-reservation",
    "wrong_service_selector_social_network": "social-network",
}


async def run_gymact_mediated_diagnosis(
    problem_id: str,
    *,
    mcp_server_port: int,
    api_port: int,
    judge_model_id: str = "groq/openai/gpt-oss-20b",
    judge_api_base: str = "https://api.groq.com/openai/v1",
    wall_clock_timeout_s: int = 900,
    startup_timeout_seconds: float = 900.0,
    verify_timeout_seconds: float = 300.0,
    namespace: str | None = None,
    manifest_path: Path | str = DEFAULT_MANIFEST_PATH,
    _environment_factory: Callable[[], Any] | None = None,
    _capabilities: Any = None,
    _diagnosis_state_sink: dict[str, Any] | None = None,
) -> GymactMediatedDiagnosisResult:
    """Materialize a real ``SregymEnvironment``, build the real POWL
    pipeline tree extended with the real ``gymact_*`` actuation Atoms (11
    real actuation-class labels as of this session's re-verified count --
    see the module docstring's 2026-08-12 correction), bind
    each to a real, capability-gated closure over that one environment, and
    call ``run_pipeline`` exactly once -- the runner's own structural replay
    is what triggers each real call, in tree order, not this function.

    ``startup_timeout_seconds`` defaults to 900s, not gymact's own 120s
    default: a real trial this session hit
    ``RuntimeError: sregym conductor API ... did not become ready within
    120.0s`` -- confirmed live, the full observability+app deploy this
    problem set requires genuinely takes 5-15+ real minutes (measured this
    session, multiple live attempts), so the 120s default was never
    sufficient for this workload, not a transient flake.

    ``verify_timeout_seconds`` defaults to 300s, not gymact's own 120s
    default: real trials this session (with the now-fixed real
    ``{"stage": "done"}`` expectation) genuinely reached ``'mitigation'``
    with both submissions accepted, then exhausted the 120s bound still
    observing ``'mitigation'`` -- real evidence the conductor's own
    internal evaluation between accepting a submission and transitioning
    to ``'done'`` can take longer than 120s (a real judging/grading step,
    not a hang -- both accepted submissions returned real ``200``
    responses, so the wait is for the conductor's own async work, not a
    stuck request).

    ``_environment_factory``/``_capabilities``/``_diagnosis_state_sink`` are
    test-only injection points (leading underscore -- not part of the
    public contract). ``_diagnosis_state_sink``, when given a real (empty)
    dict, is updated in place with the real, final ``diagnosis_state``
    closure once ``run_pipeline`` returns -- a genuine diagnostic seam (not
    a mock/stub) for a Chicago-style test to assert directly on real,
    per-key state written by the now-concurrent observe/remediate-recheck
    check bindings, since ``diagnosis_state`` itself is otherwise a
    closure-local variable with no other externally observable projection
    of its full key set. When
    omitted, this function materializes the one real environment via
    ``gymact.gyms.sregym.SregymVendorProvider().materialize()`` against the
    real ``SREGYM_CAPABILITIES`` tuple, exactly as
    ``scripts/run_gymact_mediated_trial.py`` does. A test supplies a real,
    hand-written fake ``SregymEnvironment``-shaped object instead (see
    ``tests/reasoning/test_gymact_diagnosis_driver_chicago.py``) so it can
    assert the runner -- not this function's own code -- is what triggers
    each call, without materializing a real subprocess/cluster.
    """
    if namespace is None:
        namespace = PROBLEM_ID_NAMESPACE.get(problem_id)
        if namespace is None:
            raise ValueError(
                f"no known real namespace for problem_id={problem_id!r} -- pass namespace= "
                f"explicitly. PROBLEM_ID_NAMESPACE covers {len(PROBLEM_ID_NAMESPACE)} real problem "
                f"IDs derived this session from sregym/conductor/problems/registry.py's own "
                f"PROBLEM_REGISTRY; an unlisted problem_id is likely a genuinely new/renamed real "
                f"registry entry (or the real, dynamically-composed 'multiple_failures' problem, "
                f"which has no single static namespace), never a namespace worth guessing at."
            )

    gate = CapabilityGate.from_toml(manifest_path)

    if _environment_factory is not None:
        env = await _environment_factory()
        SREGYM_CAPABILITIES = _capabilities
    else:
        from gymact.gyms.sregym import SREGYM_CAPABILITIES, SregymVendorProvider

        provider = SregymVendorProvider()
        env = await provider.materialize(
            scenario=problem_id,
            config={
                "problem_id": problem_id,
                "judge_model_id": judge_model_id,
                "judge_api_base": judge_api_base,
                "wall_clock_timeout_s": wall_clock_timeout_s,
                "startup_timeout_seconds": startup_timeout_seconds,
                "verify_timeout_seconds": verify_timeout_seconds,
                "mcp_server_port": mcp_server_port,
                "api_port": api_port,
            },
        )

    # Mutable closure state -- carries the diagnosis/anomaly found by the
    # concurrent observe-block checks across to the later
    # gymact_submit_diagnosis / remediate-recheck / gymact_verify bindings,
    # exactly the way a real diagnosing pipeline's steps depend on each
    # other's real output.
    #
    # Real thread-safety argument, load-bearing (per the plan's decision to
    # fire the 5 observe-block checks -- and the 3 remediate-recheck checks
    # -- concurrently via a real ThreadPoolExecutor in runner.py's
    # run_pipeline): every one of the 6 check/recheck coroutines below
    # writes to its OWN distinct diagnosis_state key
    # (check_status/deployments/pods/services; recheck_deployments/pods/
    # services), never a key another concurrently-running coroutine also
    # writes. CPython's GIL makes a single `dict.__setitem__` atomic, so N
    # threads writing to N distinct keys of the same dict can never race or
    # lose a write -- no lock is needed here. This would NOT hold if two
    # concurrent writers ever shared a key (e.g. both appending to the same
    # list) -- they deliberately never do; `_scan_anomalies()` and
    # `_recheck_scan_anomalies()` only ever READ the check-phase keys, after
    # the AND-join Atom that follows the concurrent block has already fired
    # (i.e. after all writers have already returned), so there is no
    # concurrent reader either.
    diagnosis_state: dict[str, Any] = {}

    async def _kubectl_json(command: str) -> Any:
        cap = _capability(SREGYM_CAPABILITIES, "run_kubectl")
        gate.guard_capability(cap)
        # Real, significant defect found live this cycle, source-confirmed:
        # the real exec_kubectl_cmd_safely tool
        # (mcp_server/kubectl_server_helper/kubectl_cmd_runner.py) rejects
        # any command that does not literally start with the string
        # "kubectl" -- `if not command.strip().startswith("kubectl"):
        # return "Command Rejected: Only kubectl commands are allowed...`.
        # Every call this driver has ever made omitted that prefix (e.g.
        # "get pods -n ... -o json" instead of "kubectl get pods -n ... -o
        # json") -- confirmed by a real, direct rejection observed live for
        # gymact_actuate_remediate's identically-shaped call. This means
        # gymact_observe's earlier "successful" scans this session were
        # very likely also silently operating on rejected-command garbage
        # output (`_kubectl_json`'s own `except (json.JSONDecodeError,
        # TypeError): return {"raw": raw}` fallback swallows a rejection
        # string into a plausible-looking dict rather than raising), not
        # real cluster state -- a real, serious finding, not just a syntax
        # fix. Prefixing every command with "kubectl " here closes it at
        # the single real call site all kubectl commands go through.
        full_command = command if command.strip().startswith("kubectl") else f"kubectl {command}"
        result = await env.actuate(cap, {"command": full_command})
        text_blocks = result.get("result_text", []) if isinstance(result, dict) else []
        raw = "".join(b.get("text", "") for b in text_blocks if isinstance(b, dict))
        # Real hardening added alongside the prefix fix above: a real
        # command-rejection response is real, structured text this MCP
        # tool always returns for a real reason (confirmed live) -- it must
        # never be silently absorbed by the JSONDecodeError fallback below
        # into a plausible-looking-but-fabricated {"raw": ...} dict that a
        # caller (the scanner) could mistake for real cluster data,
        # exactly the false-anomaly-detection risk this cycle's
        # investigation surfaced.
        if raw.strip().startswith("Command Rejected:"):
            raise RuntimeError(f"real kubectl command rejected by sregym: {raw.strip()}")
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {"raw": raw}

    async def _wait_for_deploy() -> dict[str, Any]:
        # Real defect found live this cycle, via an actual live trial against
        # this cycle's own newly-landed concurrent runner: a real trial failed
        # in mere SECONDS with "namespaces 'social-network' not found". Root
        # cause: `provider.materialize()`'s readiness signal answers "is the
        # real conductor's OWN API/MCP surface reachable" -- never "has the
        # target app finished deploying" (a real, separate, slower process
        # this session has measured taking 5-15 real minutes). The observe
        # block's checks used to fire the instant materialize() returned,
        # racing the real deploy.
        #
        # The first fix attempted here was a bare `kubectl get namespace`
        # poll-on-a-timer retry inside `_check_namespace` -- rejected once
        # written: it is the naive version of a pattern Kubernetes already has
        # a real, correct idiom for (watch/wait on an actual observable
        # condition, not blind interval polling), AND it duplicated a
        # mechanism this driver already has and already trusts:
        # `env.verify()`'s real, bounded stage-poll, the exact same call
        # `_submit_diagnosis` already uses to wait for the conductor's real
        # stage machine to leave `"setup"`. Reusing that -- rather than
        # inventing a second, parallel readiness mechanism -- is both more
        # correct (the conductor's own stage transition IS the real, intended
        # signal for "deploy phase complete", not a proxy we're guessing at)
        # and less code. This function is a real, explicit, separate POWL
        # atom -- structurally sequenced before the concurrent observe block
        # even starts -- rather than a wait hidden inside one of the block's
        # own concurrent checks, so the model honestly represents "wait for
        # deploy" as its own real pipeline step, not a side effect.
        #
        # Honest best-effort: if the conductor never leaves "setup" within its
        # real, already-configured bounded budget (verify_timeout_seconds),
        # this returns whatever `env.verify()` itself returns (a real, honest
        # {"passed": False, ...} on timeout, per env.verify()'s own contract)
        # rather than raising -- the observe block still fires afterward and
        # will surface its own real, precise failure if the deploy genuinely
        # never completed, exactly as it did before this fix, just no longer
        # racing a deploy that (per real measurement) usually finishes well
        # within this bound.
        passed, observed = await env.verify({"stage": "diagnosis"})
        return {"passed": passed, "observed": observed}

    async def _check_status() -> dict[str, Any]:
        obs_cap = _capability(SREGYM_CAPABILITIES, "observe_cluster_state")
        gate.guard_capability(obs_cap)
        status = await env.actuate(obs_cap, {})
        diagnosis_state["check_status"] = status
        return status

    async def _check_namespace() -> None:
        # Real, precise defect found live this cycle (verified directly
        # against a real cluster, not assumed): `kubectl get deployments -n
        # <nonexistent-namespace> -o json` returns real exit code 0 with a
        # real, valid, EMPTY `{"items": []}` body -- the k8s API server does
        # not validate namespace existence for a list query. A resolved-but-
        # never-deployed (or genuinely wrong) namespace would therefore
        # silently produce zero real anomalies, indistinguishable from a
        # genuinely healthy app -- exactly the false-negative
        # `no_anomaly_detected` risk `PROBLEM_ID_NAMESPACE` (this cycle's
        # namespace-resolution fix) reduces but cannot fully close on its
        # own. By contrast, real `kubectl get namespace <nonexistent>`
        # DOES raise: non-zero exit, non-monitoring command, so
        # `kubectl_cmd_runner.py`'s own `_execute_kubectl_command` raises a
        # real `RuntimeError`, wrapped as `"Command Rejected: ..."` by its
        # outer handler -- the exact real rejection shape `_kubectl_json`
        # above already raises on. Reusing that already-hardened path here
        # closes the gap: a namespace that doesn't exist now fails loudly,
        # rather than producing a plausible-looking false negative.
        #
        # Real, accepted behavior-change tradeoff from this cycle's
        # concurrency pass: this check no longer STRUCTURALLY prevents
        # `_check_deployments`/`_check_pods`/`_check_services` from firing
        # -- all five observe-block checks are now genuinely concurrent
        # (fired in the same real ThreadPoolExecutor batch by
        # `run_pipeline`), so a nonexistent-namespace run will still issue
        # 3 additional real kubectl calls against a namespace already known
        # to be invalid before this coroutine's own rejection surfaces and
        # fails the whole pipeline run (Step C of `run_pipeline`'s batch-fire
        # loop still raises the first recorded error). This is a real,
        # minor, accepted tradeoff -- favoring "don't lose independent
        # evidence from the other checks" over "avoid unnecessary real
        # calls" -- not a silent regression; it does not change whether the
        # overall diagnosis run fails on a bad namespace, only whether the
        # other three real kubectl calls still fire alongside it.
        #
        # Real defect found live this cycle, via an actual live trial against
        # this cycle's own newly-landed concurrent runner (not a hypothetical):
        # a real trial failed in mere SECONDS with "namespaces 'social-network'
        # not found". Root cause and fix now live upstream, in
        # `_wait_for_deploy()` (fired structurally before this whole observe
        # block even starts) -- see that function's docstring for why polling
        # `kubectl get namespace` on a timer here was rejected in favor of
        # waiting on the conductor's own real stage-transition signal. By the
        # time this check runs, the deploy phase is already known-complete, so
        # this stays a single, non-retrying, fail-loud check.
        await _kubectl_json(f"get namespace {namespace} -o json")

    async def _check_deployments() -> Any:
        deployments = await _kubectl_json(f"get deployments -n {namespace} -o json")
        diagnosis_state["deployments"] = deployments
        return deployments

    async def _check_pods() -> Any:
        pods = await _kubectl_json(f"get pods -n {namespace} -o json")
        diagnosis_state["pods"] = pods
        return pods

    async def _check_services() -> Any:
        services = await _kubectl_json(f"get services -n {namespace} -o json")
        diagnosis_state["services"] = services
        return services

    async def _scan_anomalies() -> dict[str, Any]:
        # Pure computation over the 3 real reads gathered by the concurrent
        # observe-block checks above -- no capability call of its own. Bound
        # to `GYMACT_SCAN_ANOMALIES_LABEL` as a bare `ActionBinding` (see
        # `runner.py`'s `ALLOWED_ACTION_BINDING_LABELS`), enabled only once
        # all 5 checks have fired (the AND-join `runner.py`'s
        # `_concurrent_read_block` + `build_pipeline_powl_node` construct),
        # so `diagnosis_state["deployments"/"pods"/"services"]` are always
        # already populated by the time this reads them. Content unchanged
        # from the old monolithic `_observe()`'s tail -- just relocated.
        state: ClusterState = {
            "deployments": diagnosis_state["deployments"],
            "pods": diagnosis_state["pods"],
            "services": diagnosis_state["services"],
        }
        anomalies = scan(state)
        diagnosis_state["anomalies"] = anomalies
        if anomalies:
            top = anomalies[0]
            diagnosis_state["top_anomaly"] = top
            diagnosis_state["label"] = classify(top)
        else:
            diagnosis_state["top_anomaly"] = None
            diagnosis_state["label"] = "no_anomaly_detected"
        status = diagnosis_state.get("check_status")
        return {"status": status, "anomaly_count": len(anomalies), "label": diagnosis_state["label"]}

    async def _submit_diagnosis() -> Any:
        cap = _capability(SREGYM_CAPABILITIES, "submit_diagnosis")
        gate.guard_capability(cap)
        # Real, precise defect found live this session and fixed here: a
        # full pipeline run reached this step and was correctly rejected by
        # the real conductor -- "Cannot submit at stage: 'setup'". The
        # conductor's own real stage machine had not yet transitioned to
        # 'diagnosis' when submission was attempted immediately after
        # observe() -- it did so only later, per that same run's final
        # verify() observing {'stage': 'diagnosis'}. Reusing the already-real,
        # already-tested verify() bounded poll here (rather than adding new
        # retry logic) to genuinely wait for the real stage transition
        # before attempting submission -- an honest, best-effort wait: if
        # the real conductor never reaches 'diagnosis' within the bound, the
        # submission is still attempted (surfacing the real rejection
        # rather than silently giving up), matching this session's standing
        # "never fabricate success" discipline.
        stage_ready, _ = await env.verify({"stage": "diagnosis"})
        diagnosis_state["submit_diagnosis_stage_wait_passed"] = stage_ready
        top = diagnosis_state.get("top_anomaly")
        label = diagnosis_state.get("label", "no_anomaly_detected")
        payload: dict[str, Any] = {
            "diagnosis": label,
            "confidence": 0.8 if top is not None else 0.0,
        }
        if top is not None:
            payload["anomaly"] = {
                "kind": top.kind,
                "object_name": top.object_name,
                "namespace": top.namespace,
                "field": top.field,
            }
        return await env.actuate(cap, payload)

    # No automated remediation-command synthesis from an Anomaly exists yet
    # (see this module's docstring) -- the three coroutines below are real,
    # non-mutating run_kubectl re-reads, honestly scoped as a re-confirm,
    # not a fabricated fix. Symmetric split of the old monolithic
    # `_actuate_remediate()`, writing DISTINCT `diagnosis_state` keys
    # (`recheck_deployments`/`recheck_pods`/`recheck_services`) from the
    # observe-phase checks' keys, per the same real thread-safety argument
    # given at `diagnosis_state`'s declaration above.

    async def _recheck_deployments() -> Any:
        deployments = await _kubectl_json(f"get deployments -n {namespace} -o json")
        diagnosis_state["recheck_deployments"] = deployments
        return deployments

    async def _recheck_pods() -> Any:
        pods = await _kubectl_json(f"get pods -n {namespace} -o json")
        diagnosis_state["recheck_pods"] = pods
        return pods

    async def _recheck_services() -> Any:
        services = await _kubectl_json(f"get services -n {namespace} -o json")
        diagnosis_state["recheck_services"] = services
        return services

    async def _recheck_scan_anomalies() -> dict[str, Any]:
        # Real defect found and fixed forward this session: this re-read's
        # result was previously discarded, and `evaluate_outcome` below was
        # called with the SAME `env.verify()` boolean passed as both
        # `structural_passed` AND `oracle.passed` -- since evaluate_outcome's
        # DISPUTED branch requires `structural_passed=True` AND
        # `oracle.passed=False`, passing one real boolean for both made
        # DISPUTED structurally UNREACHABLE from this driver (confirmed by
        # direct inspection of evaluate_outcome's decision table in
        # `case_library/outcome_predicate.py`), silently discarding exactly
        # the "fix took structurally but an independent signal disagrees"
        # case that module's own docstring names as the reason DISPUTED
        # exists as a third outcome, not folded into UNCONFIRMED. Fixed: this
        # re-read now also re-fetches deployments/services and re-runs the
        # real `scan()` the same way the observe block does, producing a
        # genuine, independent structural-recheck signal (anomaly gone, per
        # this scanner) distinct from the conductor's own oracle verdict
        # (`env.verify()`, still computed separately in `_verify()` below).
        # Pure computation, bare `ActionBinding` -- unchanged content from
        # the old monolithic `_actuate_remediate()`'s tail, just relocated;
        # enabled only once all 3 recheck coroutines above have fired (the
        # remediate-block AND-join, same construct as the observe block's).
        recheck_state: ClusterState = {
            "deployments": diagnosis_state["recheck_deployments"],
            "pods": diagnosis_state["recheck_pods"],
            "services": diagnosis_state["recheck_services"],
        }
        recheck_anomalies = scan(recheck_state)
        diagnosis_state["structural_recheck_anomaly_count"] = len(recheck_anomalies)
        diagnosis_state["structural_recheck_passed"] = len(recheck_anomalies) == 0
        return {
            "pods": diagnosis_state["recheck_pods"],
            "recheck_anomaly_count": len(recheck_anomalies),
        }

    async def _submit_mitigation() -> Any:
        cap = _capability(SREGYM_CAPABILITIES, "submit_mitigation")
        gate.guard_capability(cap)
        payload = {"mitigation": "not_attempted", "reason": "no_automated_command_synthesis_yet"}
        return await env.actuate(cap, payload)

    async def _verify() -> dict[str, Any]:
        # Real, two-part defect found live this cycle, source-confirmed in
        # sregym/conductor/conductor_api.py: GET /status returns ONLY
        # {"stage": <value>} -- real vocabulary documented in that file's
        # own API doc comment: "setup" | "diagnosis" | "mitigation" |
        # "tearing_down" | "done". There is no "complete" stage (this
        # driver's old expected value never existed), and no "diagnosis"
        # key in the response at all (the old expected dict's second key
        # could never match, since observed.get("diagnosis") is always
        # None). Both defects compounded: even fixing "complete" -> "done"
        # alone would still have left verify() permanently failing on the
        # phantom "diagnosis" key. Fixed: expect only the real key/value
        # the real conductor actually returns.
        # Marks that the real oracle was actually consulted at all -- set
        # BEFORE the poll result is known, since even a real "not done yet"
        # response is a real, present oracle answer, distinct from this
        # binding never firing at all (see the finally-block comment below
        # for the fabricated-DISPUTED defect this closes).
        diagnosis_state["verify_attempted"] = True
        passed, observed = await env.verify({"stage": "done"})
        diagnosis_state["verify_passed"] = passed
        diagnosis_state["verify_observed"] = observed if isinstance(observed, dict) else {"raw": observed}
        return {"passed": passed, "observed": diagnosis_state["verify_observed"]}

    def _binding(coro_factory: Callable[[], Any]) -> Callable[[dict[str, Any]], Any]:
        def _call(_atom_attrs: dict[str, Any]) -> Any:
            return _run_coroutine_sync(coro_factory())

        return _call

    action_bindings = {
        # Observe-block: 5 real, independent, now-concurrent checks (each a
        # real GatedCapabilityBinding) + 1 bare-binding AND-join
        # (_scan_anomalies, pure computation, no capability call).
        GYMACT_CHECK_STATUS_LABEL: GatedCapabilityBinding(
            capability_name="observe_cluster_state",
            callable_=_binding(_check_status),
            gate=gate,
        ),
        GYMACT_CHECK_NAMESPACE_LABEL: GatedCapabilityBinding(
            capability_name="run_kubectl",
            callable_=_binding(_check_namespace),
            gate=gate,
        ),
        GYMACT_CHECK_DEPLOYMENTS_LABEL: GatedCapabilityBinding(
            capability_name="run_kubectl",
            callable_=_binding(_check_deployments),
            gate=gate,
        ),
        GYMACT_CHECK_PODS_LABEL: GatedCapabilityBinding(
            capability_name="run_kubectl",
            callable_=_binding(_check_pods),
            gate=gate,
        ),
        GYMACT_CHECK_SERVICES_LABEL: GatedCapabilityBinding(
            capability_name="run_kubectl",
            callable_=_binding(_check_services),
            gate=gate,
        ),
        GYMACT_SCAN_ANOMALIES_LABEL: _binding(_scan_anomalies),
        GYMACT_SUBMIT_DIAGNOSIS_LABEL: GatedCapabilityBinding(
            capability_name="submit_diagnosis",
            callable_=_binding(_submit_diagnosis),
            gate=gate,
        ),
        # Remediate-recheck block: 3 real, independent, now-concurrent
        # rechecks (each a real GatedCapabilityBinding) + 1 bare-binding
        # AND-join (_recheck_scan_anomalies, pure computation).
        GYMACT_RECHECK_DEPLOYMENTS_LABEL: GatedCapabilityBinding(
            capability_name="run_kubectl",
            callable_=_binding(_recheck_deployments),
            gate=gate,
        ),
        GYMACT_RECHECK_PODS_LABEL: GatedCapabilityBinding(
            capability_name="run_kubectl",
            callable_=_binding(_recheck_pods),
            gate=gate,
        ),
        GYMACT_RECHECK_SERVICES_LABEL: GatedCapabilityBinding(
            capability_name="run_kubectl",
            callable_=_binding(_recheck_services),
            gate=gate,
        ),
        GYMACT_RECHECK_SCAN_LABEL: _binding(_recheck_scan_anomalies),
        GYMACT_SUBMIT_MITIGATION_LABEL: GatedCapabilityBinding(
            capability_name="submit_mitigation",
            callable_=_binding(_submit_mitigation),
            gate=gate,
        ),
        # gymact_verify takes a bare ActionBinding, not a GatedCapabilityBinding:
        # SregymEnvironment.verify() is a plain coroutine, never a real gymact
        # Capability, never wired into actuate()'s dispatch table -- there is no
        # real capability name to gate it against. Fixed forward this session
        # after CapabilityGate.stale_entries() caught a fictitious "verify"
        # manifest entry that had been added just to satisfy the (incorrect)
        # requirement that every actuation-class label be capability-gated.
        GYMACT_VERIFY_LABEL: _binding(_verify),
        GYMACT_WAIT_FOR_DEPLOY_LABEL: _binding(_wait_for_deploy),
    }

    try:
        model = build_pipeline_powl_node()
        raw_ocel_log, stall = run_pipeline(
            model,
            spec=PIPELINE_SPEC,
            session_id=f"gymact-mediated-{problem_id}",
            action_bindings=action_bindings,
            allow_partial_bindings=True,
        )
        ocel_log = ocel_dict_to_log(raw_ocel_log)
        if _diagnosis_state_sink is not None:
            _diagnosis_state_sink.update(diagnosis_state)

        verify_passed = bool(diagnosis_state.get("verify_passed", False))
        verify_observed = diagnosis_state.get("verify_observed", {})
        # Real, independent structural-recheck signal from `_actuate_remediate`'s
        # re-scan (see the comment there for the DISPUTED-unreachable defect
        # this fixes). Absent (binding never fired, e.g. `allow_partial_bindings`
        # short-circuited before reaching it) falls back to the conductor's own
        # oracle verdict -- the driver's prior behavior -- rather than a
        # fabricated True/False; that fallback still can't produce DISPUTED
        # (structural_passed == oracle.passed, same as before this fix), which
        # is the honest, absence-is-not-evidence-correct answer when no real
        # independent recheck ran.
        structural_recheck_ran = "structural_recheck_passed" in diagnosis_state
        structural_passed = bool(diagnosis_state.get("structural_recheck_passed", verify_passed))
        recheck_anomaly_count = diagnosis_state.get("structural_recheck_anomaly_count")
        # Real, second instance of the same class of defect the DISPUTED fix
        # above closed: `oracle=OracleVerdict(present=True, ...)` was
        # hardcoded regardless of whether `gymact_verify`'s binding ever
        # actually fired. A genuine structural stall (BOUND_EXHAUSTED /
        # DEADLOCK, no exception -- see `runner.py`'s `classify_stall()`) can
        # leave `_verify()` never called while EARLIER bindings (including
        # `_actuate_remediate`'s structural recheck) already completed. In
        # that case the old code fabricated `oracle.passed=False` (the
        # `.get(..., False)` default) as though a real conductor had
        # answered and disagreed -- capable of producing a false DISPUTED
        # verdict for a run that never actually reached the oracle at all.
        # `OracleVerdict.present` exists exactly to represent "no oracle was
        # consulted" honestly (see its own docstring) -- now used for real.
        verify_attempted = bool(diagnosis_state.get("verify_attempted", False))
        verdict, confirmed_via = evaluate_outcome(
            structural_passed=structural_passed,
            oracle=OracleVerdict(present=verify_attempted, passed=verify_passed if verify_attempted else None),
        )

        # Real dual-bookkeeping gap found and fixed forward this cycle
        # (`.claude/rules/no-dual-bookkeeping.md`: "Standing is a query over
        # one joined evidence graph. It is never a field."). `verdict` is a
        # pure, deterministic function of data already present in the
        # `ocel_log`'s own recorded events (`_verify()`'s and
        # `_actuate_remediate()`'s outcomes) -- but before this fix the
        # verdict itself was NEVER recorded as its own durable OCEL fact,
        # only as a field on this function's returned Python dataclass. A
        # caller who deleted the Python runtime and tried to recompute
        # standing from durable OCEL artifacts alone (the real threshold
        # `no-dual-bookkeeping.md` names) could still re-derive the verdict
        # by re-running `evaluate_outcome` over the sub-events -- but would
        # have to re-execute decision logic to do so, rather than reading
        # the verdict directly off the log the way `level4-completion-law.md`
        # requires goal consequence to "enter the evidence". Closing that
        # gap: the real, final verdict is now its own explicit, durable OCEL
        # event, linked to the same real session object every other event in
        # this run is linked to -- not a second, parallel source of truth,
        # since its own content is still wholly derived from (never
        # contradicts) the sub-events already in the log.
        ocel_log = append_tool_call_event(
            ocel_log,
            event_id=f"evt-gymact_verdict_computed-{problem_id}-{uuid.uuid4().hex[:8]}",
            activity="gymact_verdict_computed",
            object_ids=[f"gymact-mediated-{problem_id}"],
            outcome={
                "standing": verdict.value,
                "detail": confirmed_via,
                "structural_passed": str(structural_passed),
                "oracle_present": str(verify_attempted),
                **(
                    {"structural_recheck_anomaly_count": recheck_anomaly_count}
                    if structural_recheck_ran and recheck_anomaly_count is not None
                    else {}
                ),
            },
        )

        result = GymactMediatedDiagnosisResult(
            problem_id=problem_id,
            ocel_log=ocel_log,
            stall=stall,
            verdict=verdict,
            confirmed_via=confirmed_via,
            verify_observed=verify_observed,
            structural_recheck_anomaly_count=recheck_anomaly_count if structural_recheck_ran else None,
            submit_diagnosis_stage_wait_passed=diagnosis_state.get("submit_diagnosis_stage_wait_passed"),
        )
    finally:
        # Real bug found and fixed forward this session: `finally:
        # await env.teardown()` with no exception handling meant a
        # teardown-only failure (e.g. a real MCP client disconnect race,
        # confirmed live -- `httpx.ReadError` inside `_kubectl_client
        # .__aexit__`) silently discarded an already-successful `result`
        # from the `try` block, since Python replaces a `return`'s value
        # with any exception raised in the matching `finally`. Cleanup
        # failing must never destroy a real, already-computed diagnosis
        # result -- log it as a real, named, non-fatal teardown warning
        # instead.
        try:
            await env.teardown()
        except Exception as teardown_exc:  # noqa: BLE001 -- intentionally broad: any teardown failure must not mask `result`
            import logging

            # `result` may not be bound yet if the `try` block above itself
            # raised before reaching its own `result = ...` assignment --
            # in that case this teardown failure is a real, SEPARATE issue,
            # and Python will still (correctly) propagate the try block's
            # own original exception once this `finally` completes without
            # itself raising. Word the log accurately for both cases rather
            # than always claiming success.
            _result_was_computed = "result" in locals()
            logging.getLogger(__name__).warning(
                "gymact_diagnosis_driver: env.teardown() raised %r%s",
                teardown_exc,
                (
                    " after a real diagnosis result was already computed -- "
                    "the result is still returned; this is a real "
                    "resource-cleanup gap, not a diagnosis failure."
                    if _result_was_computed
                    else " while the try block itself was already failing for "
                    "a separate reason -- that original exception, not this "
                    "teardown failure, is what will propagate."
                ),
            )

    return result
