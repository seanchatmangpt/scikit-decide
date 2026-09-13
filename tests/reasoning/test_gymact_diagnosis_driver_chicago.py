# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style test for `autofde_lab.reasoning.gymact_diagnosis_driver`.

Real collaborators throughout:

- The real `autofde_lab.powl.runner.build_pipeline_powl_node` tree and the
  real `autofde_lab.powl.runner.run_pipeline` structural replay driver --
  never re-implemented or stubbed here.
- The real `autofde_lab_planner.scanner.registry.scan` /
  `autofde_lab_planner.scanner.taxonomy.classify` sequence, exercised on
  real (if small) kubectl-JSON-shaped dicts constructed to deterministically
  produce one real `Anomaly`.
- The real `autofde_lab.fabric.gymact_capability_gate.CapabilityGate`, real
  `autofde_lab.powl.runner.GatedCapabilityBinding` -- real TOML parsing
  against the real, checked-in `gymact_capabilities.toml`.
- The real `autofde_lab.case_library.outcome_predicate.evaluate_outcome`.

The ONE test double is `_FakeSregymEnvironment`: a small, hand-written,
honest implementation of exactly the four methods
`run_gymact_mediated_diagnosis` calls on its environment
(`actuate`/`verify`/`teardown`; `observe` is never called by this driver --
the gymact_observe binding reads cluster state via `actuate`, matching the
real spike's own real behavior). Per
`.claude/rules/testing-chicago-style.md`: a real environment materializes a
real Kubernetes cluster and a real subprocess (`SregymVendorProvider().
materialize()`), which is genuinely infeasible in a unit test -- this is the
repo's own named "real degraded alternative" pattern (a real, simple,
non-interaction-verifying implementation of the same interface, injected via
the driver's test-only `_environment_factory`/`_capabilities` parameters),
not an interaction-verifying `Mock`.

No `unittest.mock` / `Mock` / `MagicMock` / `patch` / `monkeypatch` anywhere
in this file.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections import Counter
from dataclasses import dataclass, field

import pytest

from autofde_lab.case_library.outcome_predicate import OutcomeVerdict
from autofde_lab.powl.runner import (
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
)
from autofde_lab.reasoning.gymact_diagnosis_driver import (
    GymactMediatedDiagnosisResult,
    run_gymact_mediated_diagnosis,
)


@dataclass(frozen=True, slots=True)
class _FakeCapability:
    """Real, minimal stand-in for `gymact.models.Capability` -- carries only
    the `.binding` attribute the real `CapabilityGate.guard_capability` and
    this driver's `_capability()` lookup actually read."""

    binding: str


_FAKE_CAPABILITIES: tuple[_FakeCapability, ...] = (
    _FakeCapability(binding="observe_cluster_state"),
    _FakeCapability(binding="run_kubectl"),
    _FakeCapability(binding="submit_diagnosis"),
    _FakeCapability(binding="submit_mitigation"),
)

# A real kubectl-JSON-shaped deployment with 0 Ready pods against a declared
# replica count of 2 -- deterministically produces one real
# `declared_vs_observed` Anomaly via the real `scan_deployments` analyzer,
# no fabricated Anomaly object.
_DEPLOYMENTS = {
    "items": [
        {
            "metadata": {"name": "api", "namespace": "social-network"},
            "spec": {
                "replicas": 2,
                "selector": {"matchLabels": {"app": "api"}},
                "template": {"spec": {"containers": [{"image": "api:v1"}]}},
            },
            "status": {},
        }
    ]
}
_PODS: dict = {"items": []}
_SERVICES: dict = {"items": []}

# `scan_deployments` computes readiness from real Pod objects matching the
# Deployment's selector with a Ready=True condition -- NOT a deployment
# status field -- so a real "recovered" snapshot for the fake env's SECOND
# pods read (the remediate-stage re-scan) needs two real matching Pod
# objects, not a deployment-status tweak.
_PODS_RECOVERED = {
    "items": [
        {
            "metadata": {"name": f"api-{i}", "namespace": "social-network", "labels": {"app": "api"}},
            "status": {"conditions": [{"type": "Ready", "status": "True"}]},
        }
        for i in range(2)
    ]
}


class _FakeSregymEnvironment:
    """Real, hand-written, honest implementation of exactly the
    `SregymEnvironment` surface this driver calls -- not gymact itself, and
    not an interaction-verifying mock: every method really computes and
    returns real data, and `call_log` records real, observable call order
    (the state under test), not "was this called" assertions.
    """

    def __init__(self, *, recover_pods_on_second_read: bool = True) -> None:
        self.call_log: list[str] = []
        self.kubectl_commands: list[str] = []
        self.verify_calls: list[dict] = []
        self.torn_down = False
        self._pods_reads = 0
        self._recover_pods_on_second_read = recover_pods_on_second_read

    async def actuate(self, capability: _FakeCapability, payload: dict) -> dict:
        if capability.binding == "run_kubectl":
            # Real, small test-fixture enhancement (not a production-code
            # change): tag each real kubectl call's `call_log` entry with
            # WHICH distinct check it was (namespace/deployments/pods/
            # services), derived from the real command text -- the bare
            # `"run_kubectl"` binding name alone can't distinguish the four
            # now-concurrent observe-block reads (or the three
            # remediate-block rereads) from one another, which a real
            # Counter-based multiset assertion over the concurrent phase
            # needs in order to verify the right DISTINCT checks ran, not
            # merely "N kubectl calls happened in some order".
            command = payload.get("command", "")
            if command.startswith("kubectl get namespace"):
                self.call_log.append("run_kubectl:namespace")
            elif "deployments" in command:
                self.call_log.append("run_kubectl:deployments")
            elif "pods" in command:
                self.call_log.append("run_kubectl:pods")
            elif "services" in command:
                self.call_log.append("run_kubectl:services")
            else:
                self.call_log.append("run_kubectl")
        else:
            self.call_log.append(capability.binding)
        if capability.binding == "observe_cluster_state":
            return {"after": {"stage": "observed"}}
        if capability.binding == "run_kubectl":
            command = payload.get("command", "")
            self.kubectl_commands.append(command)
            if "deployments" in command:
                body = _DEPLOYMENTS
            elif "pods" in command:
                self._pods_reads += 1
                if self._recover_pods_on_second_read and self._pods_reads >= 2:
                    body = _PODS_RECOVERED
                else:
                    body = _PODS
            elif "services" in command:
                body = _SERVICES
            else:
                body = {"items": []}
            return {"result_text": [{"text": json.dumps(body)}]}
        if capability.binding == "submit_diagnosis":
            return {"after": {"diagnosis": payload.get("diagnosis")}}
        if capability.binding == "submit_mitigation":
            return {"after": {"mitigation": payload.get("mitigation")}}
        raise AssertionError(f"unexpected real actuate() call for binding={capability.binding!r}")

    async def verify(self, expected: dict) -> tuple[bool, dict]:
        self.call_log.append("verify")
        self.verify_calls.append(dict(expected))
        # Real regression coverage for the defect found and fixed forward
        # this session: the real conductor's GET /status returns ONLY
        # {"stage": <value>} with real vocabulary "setup" | "diagnosis" |
        # "mitigation" | "tearing_down" | "done" -- there is no "complete"
        # stage and no "diagnosis" key at all. This fake genuinely echoes
        # back only the requested stage (never a phantom "complete"), so a
        # caller expecting the old, nonexistent stage name would correctly
        # fail to match here too, exactly as the real conductor would.
        return True, {"stage": expected.get("stage")}

    async def teardown(self) -> None:
        self.call_log.append("teardown")
        self.torn_down = True


def test_run_gymact_mediated_diagnosis_is_driven_by_run_pipeline_structural_replay():
    """The five real `gymact_*` calls fire in the real POWL tree's structural
    order, and that order is produced by `run_pipeline` -- not by this
    driver's own control flow, which never calls `env.actuate`/`env.verify`
    directly, only constructs the tree + bindings and calls `run_pipeline`
    once (verified by grep in this test's own final assertion below)."""
    fake_env = _FakeSregymEnvironment()

    async def _factory() -> _FakeSregymEnvironment:
        return fake_env

    result = asyncio.run(
        run_gymact_mediated_diagnosis(
            "wrong_dns_policy_social_network",
            mcp_server_port=1234,
            api_port=5678,
            _environment_factory=_factory,
            _capabilities=_FAKE_CAPABILITIES,
        )
    )

    assert isinstance(result, GymactMediatedDiagnosisResult)
    assert result.problem_id == "wrong_dns_policy_social_network"
    assert fake_env.torn_down is True, "env.teardown() must run in a finally block"

    # The real fake env's own call log -- observable, real state, not an
    # interaction assertion. Real POWL v2 concurrency (this session's
    # change) means the five observe-block checks and the three
    # remediate-recheck reads each fire in a real, genuinely
    # nondeterministic `ThreadPoolExecutor` order -- so this can no longer
    # be one strict-order list. Per the plan
    # (`what-are-the-current-shimmying-bear.md`, Testing Plan item h), split
    # into: a strict-order prefix (empty -- the observe block is the very
    # first thing that fires), a `Counter`-based multiset over the
    # concurrent observe-phase slice, a strict-order middle segment
    # (unchanged -- `scan_anomalies` is pure computation with no real call,
    # so the next two real calls are always `verify` then
    # `submit_diagnosis`, in that order), a second `Counter`-based multiset
    # over the concurrent remediate-recheck slice, and a strict-order
    # suffix (unchanged from today).
    # Real prefix addition (cycle 18, found via an actual live trial):
    # `gymact_wait_for_deploy` fires a real, single, strictly-ordered
    # `verify()` call BEFORE the observe block ever starts -- closing a real
    # race between gymact's `materialize()` readiness signal and the real,
    # slower app deployment. This is deliberately NOT part of the concurrent
    # observe-phase multiset below: it structurally precedes the whole block.
    assert len(fake_env.call_log) == 14
    prefix = fake_env.call_log[0:1]
    observe_phase = fake_env.call_log[1:6]
    middle = fake_env.call_log[6:8]
    remediate_phase = fake_env.call_log[8:11]
    suffix = fake_env.call_log[11:14]

    assert prefix == ["verify"], "gymact_wait_for_deploy must fire before the observe block"

    assert Counter(observe_phase) == Counter(
        {
            "observe_cluster_state": 1,
            "run_kubectl:namespace": 1,
            "run_kubectl:deployments": 1,
            "run_kubectl:pods": 1,
            "run_kubectl:services": 1,
        }
    ), f"expected exactly the five distinct observe-block checks, got {observe_phase!r}"

    assert middle == ["verify", "submit_diagnosis"], (
        "stage-wait verify() then submit_diagnosis must still fire strictly in order -- "
        "neither is part of a concurrent block"
    )

    assert Counter(remediate_phase) == Counter(
        {
            "run_kubectl:deployments": 1,
            "run_kubectl:pods": 1,
            "run_kubectl:services": 1,
        }
    ), f"expected exactly the three distinct remediate-recheck reads, got {remediate_phase!r}"

    assert suffix == ["submit_mitigation", "verify", "teardown"]

    # Cross-check: the real OCEL log `run_pipeline` produced independently
    # records one `powl_structural_fire` event per real Atom fire, in the
    # same real tree-traversal order. The real gymact_* labels appear in
    # that structural log in the same segmented shape as the real calls
    # above -- direct evidence that `run_pipeline`'s own structural replay
    # (not this driver's own control flow) is what triggered each call
    # (this driver's code calls `run_pipeline` exactly once and never calls
    # `env.actuate`/`env.verify` from inside
    # `run_gymact_mediated_diagnosis`'s own body -- it only builds bindings
    # for `run_pipeline` to invoke).
    fired_labels = [
        next(a.value.value for a in e.attributes if a.key == "detail")
        for e in result.ocel_log.events
        if e.activity == "powl_structural_fire"
    ]
    gymact_all_labels = {
        GYMACT_WAIT_FOR_DEPLOY_LABEL,
        GYMACT_CHECK_STATUS_LABEL,
        GYMACT_CHECK_NAMESPACE_LABEL,
        GYMACT_CHECK_DEPLOYMENTS_LABEL,
        GYMACT_CHECK_PODS_LABEL,
        GYMACT_CHECK_SERVICES_LABEL,
        GYMACT_SCAN_ANOMALIES_LABEL,
        GYMACT_SUBMIT_DIAGNOSIS_LABEL,
        GYMACT_RECHECK_DEPLOYMENTS_LABEL,
        GYMACT_RECHECK_PODS_LABEL,
        GYMACT_RECHECK_SERVICES_LABEL,
        GYMACT_RECHECK_SCAN_LABEL,
        GYMACT_SUBMIT_MITIGATION_LABEL,
        GYMACT_VERIFY_LABEL,
    }
    gymact_labels_in_fire_order = [label for label in fired_labels if label in gymact_all_labels]
    assert len(gymact_labels_in_fire_order) == 14

    assert gymact_labels_in_fire_order[0] == GYMACT_WAIT_FOR_DEPLOY_LABEL, (
        "gymact_wait_for_deploy must be the first real gymact_* atom to fire"
    )

    observe_block_labels = gymact_labels_in_fire_order[1:6]
    assert Counter(observe_block_labels) == Counter(
        {
            GYMACT_CHECK_STATUS_LABEL: 1,
            GYMACT_CHECK_NAMESPACE_LABEL: 1,
            GYMACT_CHECK_DEPLOYMENTS_LABEL: 1,
            GYMACT_CHECK_PODS_LABEL: 1,
            GYMACT_CHECK_SERVICES_LABEL: 1,
        }
    )
    assert gymact_labels_in_fire_order[6:8] == [GYMACT_SCAN_ANOMALIES_LABEL, GYMACT_SUBMIT_DIAGNOSIS_LABEL]

    remediate_block_labels = gymact_labels_in_fire_order[8:11]
    assert Counter(remediate_block_labels) == Counter(
        {
            GYMACT_RECHECK_DEPLOYMENTS_LABEL: 1,
            GYMACT_RECHECK_PODS_LABEL: 1,
            GYMACT_RECHECK_SERVICES_LABEL: 1,
        }
    )
    assert gymact_labels_in_fire_order[11:14] == [
        GYMACT_RECHECK_SCAN_LABEL,
        GYMACT_SUBMIT_MITIGATION_LABEL,
        GYMACT_VERIFY_LABEL,
    ]

    assert result.stall.final is True
    assert result.verdict == OutcomeVerdict.CONFIRMED
    assert result.confirmed_via == "structural_and_oracle"
    assert result.verify_observed["stage"] == "done"
    # Real regression coverage for a real observability gap found and fixed
    # this cycle: `submit_diagnosis_stage_wait_passed` was tracked in
    # `diagnosis_state` (exactly the diagnostic this session's own
    # submission-timing-race fix relies on) but silently dropped at
    # result-construction time -- now surfaced for real.
    assert result.submit_diagnosis_stage_wait_passed is True
    # Real regression coverage for the DISPUTED-unreachable defect found and
    # fixed forward this cycle: the remediate re-read now genuinely re-scans
    # (see `_FakeSregymEnvironment`'s "recovered by the time of the second
    # deployments read" behavior below) -- 0 real anomalies found on the
    # real recheck, agreeing with the conductor's own oracle verdict above.
    assert result.structural_recheck_anomaly_count == 0

    # Real regression coverage for the two-part defect found and fixed
    # live this cycle, source-confirmed in
    # sregym/conductor/conductor_api.py: GET /status returns ONLY
    # {"stage": <value>}, real vocabulary "setup" | "diagnosis" |
    # "mitigation" | "tearing_down" | "done" -- there is no "complete"
    # stage (the driver's old expected value never existed) and no
    # "diagnosis" key in the response at all (the old expected dict's
    # second key could never match). The final gymact_verify call must now
    # request exactly {"stage": "done"}, nothing else.
    assert fake_env.verify_calls[-1] == {"stage": "done"}

    # Real regression coverage for the significant defect found and fixed
    # live this cycle: the real exec_kubectl_cmd_safely tool rejects any
    # command not literally starting with "kubectl" -- confirmed in source
    # (mcp_server/kubectl_server_helper/kubectl_cmd_runner.py). Every real
    # command this driver ever sent (deployments/pods/services scan reads,
    # the remediate re-read) must now carry that literal prefix.
    assert fake_env.kubectl_commands, "expected at least one real kubectl call to have fired"
    for real_command in fake_env.kubectl_commands:
        assert real_command.startswith("kubectl "), (
            f"real command {real_command!r} is missing the literal 'kubectl' prefix the "
            "real sregym tool requires -- this is exactly the defect this test guards"
        )

    # Real regression coverage for the dual-bookkeeping gap found and fixed
    # this cycle: the final verdict must be its OWN durable OCEL event, not
    # only a field on the Python dataclass this function returns -- proven
    # here by reading it straight off `result.ocel_log`, never off
    # `result.verdict` (which the fix under test does not touch).
    verdict_events = [e for e in result.ocel_log.events if e.activity == "gymact_verdict_computed"]
    assert len(verdict_events) == 1, "expected exactly one real verdict-recording OCEL event"
    verdict_event = verdict_events[0]
    verdict_attrs = {a.key: a.value.value for a in verdict_event.attributes}
    assert verdict_attrs["standing"] == "CONFIRMED"
    assert verdict_attrs["detail"] == "structural_and_oracle"
    # The verdict event must be linked to the same real session object every
    # other event in this run is linked to -- not a free-floating event with
    # no real object-centric relationship to the rest of the log.
    session_object_id = f"gymact-mediated-{result.problem_id}"
    linked_object_ids = {
        link.object_id for link in result.ocel_log.event_object_links if link.event_id == verdict_event.id
    }
    assert session_object_id in linked_object_ids


class _FakeSregymEnvironmentRejectingKubectl(_FakeSregymEnvironment):
    """Real regression fixture for the false-anomaly-detection risk found
    live this cycle: a real command-rejection response
    ("Command Rejected: Only kubectl commands are allowed...") must never
    be silently absorbed into a plausible-looking `{"raw": ...}` dict a
    caller could mistake for real cluster data -- it must raise."""

    async def actuate(self, capability: _FakeCapability, payload: dict) -> dict:
        if capability.binding == "run_kubectl":
            self.call_log.append(capability.binding)
            self.kubectl_commands.append(payload.get("command", ""))
            return {
                "result_text": [
                    {"text": "Command Rejected: Only kubectl commands are allowed. Please check the command and try again."}
                ]
            }
        return await super().actuate(capability, payload)


def test_a_real_command_rejection_response_raises_rather_than_being_silently_absorbed():
    fake_env = _FakeSregymEnvironmentRejectingKubectl()

    async def _factory() -> _FakeSregymEnvironmentRejectingKubectl:
        return fake_env

    with pytest.raises(Exception):
        asyncio.run(
            run_gymact_mediated_diagnosis(
                "wrong_dns_policy_social_network",
                mcp_server_port=1234,
                api_port=5678,
                _environment_factory=_factory,
                _capabilities=_FAKE_CAPABILITIES,
            )
        )
    # Real, order-independent assertion (updated per the plan's concurrency
    # pass): the four real observe-block kubectl checks
    # (namespace/deployments/pods/services) now fire concurrently via a real
    # `ThreadPoolExecutor`, so which one is issued first is genuinely
    # nondeterministic -- `kubectl_commands[0]` is no longer guaranteed to
    # be any particular check. What remains a real, deterministic guarantee
    # is that every real kubectl call this rejecting fixture ever received
    # carries the real "kubectl " prefix, and that at least one really was
    # issued and rejected (the rejection is what makes the whole run raise,
    # asserted above via `pytest.raises`).
    assert fake_env.kubectl_commands, "expected at least one real kubectl call to have fired"
    for real_command in fake_env.kubectl_commands:
        assert real_command.startswith("kubectl "), (
            f"real command {real_command!r} is missing the literal 'kubectl' prefix"
        )


class _FakeSregymEnvironmentRejectingOnlyNamespaceCheck(_FakeSregymEnvironment):
    """Real regression fixture for the namespace-existence gap found and
    fixed this cycle (verified live against a real cluster): `kubectl get
    deployments -n <nonexistent> -o json` returns real exit 0 with a real,
    valid, EMPTY `{"items": []}` body -- NOT an error -- while real `kubectl
    get namespace <nonexistent>` DOES raise (non-zero exit, wrapped as a
    real `"Command Rejected: ..."` response by the real
    `kubectl_cmd_runner.py`). This fixture models exactly that asymmetry:
    only the namespace pre-check is rejected; deployments/pods/services
    reads would otherwise succeed with real (if empty) data, same as they
    genuinely do against a nonexistent namespace on a real cluster."""

    async def actuate(self, capability: _FakeCapability, payload: dict) -> dict:
        if capability.binding == "run_kubectl":
            command = payload.get("command", "")
            self.call_log.append(capability.binding)
            self.kubectl_commands.append(command)
            if command.startswith("kubectl get namespace"):
                return {
                    "result_text": [
                        {
                            "text": (
                                'Command Rejected: Error executing kubectl command:\n'
                                'Error from server (NotFound): namespaces "does-not-exist" not found'
                            )
                        }
                    ]
                }
            return {"result_text": [{"text": json.dumps({"items": []})}]}
        return await super().actuate(capability, payload)


def test_observe_refuses_a_nonexistent_namespace_instead_of_silently_scanning_it_empty():
    """Proves the real fix this cycle: before this fix, a resolved-but-
    never-deployed (or genuinely wrong) namespace would silently produce a
    plausible-looking `{"items": []}` scan and a false `no_anomaly_detected`
    verdict -- indistinguishable from a genuinely healthy app. Now the real
    namespace-existence pre-check raises first, before that silent false
    negative can ever be reached."""
    fake_env = _FakeSregymEnvironmentRejectingOnlyNamespaceCheck()

    async def _factory() -> _FakeSregymEnvironmentRejectingOnlyNamespaceCheck:
        return fake_env

    with pytest.raises(RuntimeError, match="Command Rejected"):
        asyncio.run(
            run_gymact_mediated_diagnosis(
                "wrong_dns_policy_social_network",
                mcp_server_port=1234,
                api_port=5678,
                _environment_factory=_factory,
                _capabilities=_FAKE_CAPABILITIES,
            )
        )
    # Real, accepted behavior change from this cycle's concurrency pass
    # (named explicitly in the plan, section 5 -- not a silent regression):
    # `_check_namespace` no longer STRUCTURALLY prevents
    # `_check_deployments`/`_check_pods`/`_check_services` from firing --
    # all four observe-block kubectl checks now fire concurrently in the
    # same real `ThreadPoolExecutor` batch, so this fixture's otherwise-
    # successful deployments/pods/services reads (real, valid, empty data)
    # may also have run before the namespace rejection surfaces. The
    # durable guarantee is no longer "only the namespace check ran" -- it is
    # "the namespace check ran, and its rejection is what ultimately made
    # the whole diagnosis raise" (already proven above via
    # `pytest.raises(RuntimeError, match="Command Rejected")`).
    assert "kubectl get namespace social-network -o json" in fake_env.kubectl_commands


class _FakeSregymEnvironmentDisputedOracle(_FakeSregymEnvironment):
    """Real regression fixture for the DISPUTED-unreachable defect found and
    fixed forward this cycle: a real, independent structural recheck (the
    inherited pods-recovery behavior) passes, but the conductor's own oracle
    (`env.verify()`) explicitly disagrees -- the exact real-world shape
    `evaluate_outcome`'s own docstring names DISPUTED for: "the fix took
    structurally but an independent signal disagrees."
    """

    async def verify(self, expected: dict) -> tuple[bool, dict]:
        self.call_log.append("verify")
        self.verify_calls.append(dict(expected))
        if expected.get("stage") == "done":
            # The real conductor oracle disagrees even though the structural
            # recheck (pods recovered) will independently pass.
            return False, {"stage": "mitigation"}
        return True, {"stage": expected.get("stage")}


def test_disputed_verdict_reachable_when_structural_recheck_passes_but_oracle_disagrees():
    fake_env = _FakeSregymEnvironmentDisputedOracle()

    async def _factory() -> _FakeSregymEnvironmentDisputedOracle:
        return fake_env

    result = asyncio.run(
        run_gymact_mediated_diagnosis(
            "wrong_dns_policy_social_network",
            mcp_server_port=1234,
            api_port=5678,
            _environment_factory=_factory,
            _capabilities=_FAKE_CAPABILITIES,
        )
    )

    # Real proof the fix works: before this cycle's fix, `structural_passed`
    # and `oracle.passed` were always the SAME boolean (both derived from
    # `env.verify()`), so DISPUTED could never be returned regardless of
    # fixture shape. This fixture's structural recheck genuinely passes (0
    # real anomalies on the second pods read) while the real oracle
    # genuinely disagrees (`verify({"stage": "done"})` returns `False`) --
    # DISPUTED is the only honest verdict for this combination.
    assert result.structural_recheck_anomaly_count == 0
    assert result.verdict == OutcomeVerdict.DISPUTED
    assert result.confirmed_via == "n/a"


class _FakeSregymEnvironmentRaisingOnTeardown(_FakeSregymEnvironment):
    """Real regression fixture for the bug found and fixed forward this
    session: `finally: await env.teardown()` with no exception handling
    meant a teardown-only failure discarded an already-successful `result`
    (Python replaces a `try` block's `return` value with any exception a
    matching `finally` raises). Confirmed live: `httpx.ReadError` inside the
    real `_kubectl_client.__aexit__` during a real trial's teardown, after
    the real diagnosis had already completed successfully."""

    async def teardown(self) -> None:
        self.call_log.append("teardown")
        self.torn_down = True
        raise RuntimeError("real teardown-only failure, e.g. a client disconnect race")


def test_teardown_failure_does_not_discard_an_already_computed_result():
    fake_env = _FakeSregymEnvironmentRaisingOnTeardown()

    async def _factory() -> _FakeSregymEnvironmentRaisingOnTeardown:
        return fake_env

    result = asyncio.run(
        run_gymact_mediated_diagnosis(
            "wrong_dns_policy_social_network",
            mcp_server_port=1234,
            api_port=5678,
            _environment_factory=_factory,
            _capabilities=_FAKE_CAPABILITIES,
        )
    )

    # The real diagnosis result survives a real teardown failure -- this is
    # the whole point of the fix. Before the fix, this call raised
    # RuntimeError instead of returning, silently discarding a real,
    # already-computed CONFIRMED verdict.
    assert isinstance(result, GymactMediatedDiagnosisResult)
    assert result.verdict == OutcomeVerdict.CONFIRMED
    assert fake_env.torn_down is True, "teardown was still attempted, just its failure didn't mask the result"


def test_namespace_is_resolved_from_the_real_problem_id_when_not_given_explicitly():
    """Real regression coverage for the namespace-hardcoding defect found
    and fixed this cycle: this driver used to default `namespace` to the
    single literal `"social-network"` for every real problem_id, correct
    only by coincidence for this session's sole live test problem. A real
    `hotel-reservation`-app problem_id must now resolve to the real
    `"hotel-reservation"` namespace (source-derived from
    `sregym/conductor/problems/registry.py`'s own `PROBLEM_REGISTRY`, not
    guessed from the problem_id's own text) -- proven here by observing the
    real fake environment's own kubectl command text, not by re-deriving
    the mapping inline."""
    from autofde_lab.reasoning.gymact_diagnosis_driver import PROBLEM_ID_NAMESPACE

    fake_env = _FakeSregymEnvironment()

    async def _factory() -> _FakeSregymEnvironment:
        return fake_env

    hotel_problem_id = "expired_tls_hotel_reservation"
    assert PROBLEM_ID_NAMESPACE[hotel_problem_id] == "hotel-reservation"

    asyncio.run(
        run_gymact_mediated_diagnosis(
            hotel_problem_id,
            mcp_server_port=1234,
            api_port=5678,
            _environment_factory=_factory,
            _capabilities=_FAKE_CAPABILITIES,
        )
    )

    real_deployments_command = next(c for c in fake_env.kubectl_commands if "deployments" in c)
    assert "-n hotel-reservation" in real_deployments_command, (
        f"real command {real_deployments_command!r} should have scanned the real "
        "hotel-reservation namespace, not the old hardcoded social-network default"
    )


def test_unknown_problem_id_refuses_rather_than_guessing_a_namespace():
    """A problem_id absent from the real, source-derived
    `PROBLEM_ID_NAMESPACE` table must raise, naming the gap honestly --
    never silently fall back to a namespace that is probably wrong."""
    fake_env = _FakeSregymEnvironment()

    async def _factory() -> _FakeSregymEnvironment:
        return fake_env

    with pytest.raises(ValueError, match="no known real namespace"):
        asyncio.run(
            run_gymact_mediated_diagnosis(
                "not_a_real_registered_problem_id",
                mcp_server_port=1234,
                api_port=5678,
                _environment_factory=_factory,
                _capabilities=_FAKE_CAPABILITIES,
            )
        )


def test_run_gymact_mediated_diagnosis_calls_run_pipeline_exactly_once():
    """Structural proof, via real source inspection (not a mock), that
    `run_gymact_mediated_diagnosis`'s own body contains exactly one call to
    `run_pipeline` -- the runner is invoked once and drives the whole
    sequence structurally; this function does not manually re-order calls
    around it."""
    import inspect

    from autofde_lab.reasoning import gymact_diagnosis_driver

    source = inspect.getsource(gymact_diagnosis_driver.run_gymact_mediated_diagnosis)
    assert source.count("run_pipeline(") == 1


class _FakeSregymEnvironmentWithRealSleep(_FakeSregymEnvironment):
    """Real regression fixture for
    ``test_five_concurrent_check_bindings_each_write_their_own_diagnosis_state_key_without_loss``
    ONLY -- never reused by any other test, so the other ~15+ tests reusing
    the base `_FakeSregymEnvironment` pay none of this cost. A small, real
    `time.sleep` inside `actuate()` (blocking only the one dedicated worker
    thread each concurrently-fired binding runs in via
    `_run_coroutine_sync` -- never the driver's own event loop) makes
    genuine OS-thread interleaving of the five real observe-block checks
    likely, rather than merely possible."""

    async def actuate(self, capability: _FakeCapability, payload: dict) -> dict:
        time.sleep(0.01)
        return await super().actuate(capability, payload)


def test_five_concurrent_check_bindings_each_write_their_own_diagnosis_state_key_without_loss():
    """Real, state-based proof of the plan's decision-4 thread-safety
    argument (distinct `diagnosis_state` dict keys, GIL-atomic
    `dict.__setitem__`, no lock needed): run the real driver end to end
    through the real `run_pipeline` structural replay against the real
    `_FakeSregymEnvironmentWithRealSleep`, and assert every one of the five
    real observe-block writes landed with its correct real value -- nothing
    lost or overwritten by a concurrently-running sibling coroutine.

    Uses the real `_diagnosis_state_sink` test-only injection point (see
    `gymact_diagnosis_driver.py`'s docstring) since `diagnosis_state` is
    otherwise a closure-local variable with no other externally observable
    projection of its full key set -- a genuine diagnostic seam, not a
    mock: the sink is a real, empty dict, updated in place with the real
    dict the real bindings really wrote to.
    """
    fake_env = _FakeSregymEnvironmentWithRealSleep()
    diagnosis_state_sink: dict = {}

    async def _factory() -> _FakeSregymEnvironmentWithRealSleep:
        return fake_env

    result = asyncio.run(
        run_gymact_mediated_diagnosis(
            "wrong_dns_policy_social_network",
            mcp_server_port=1234,
            api_port=5678,
            _environment_factory=_factory,
            _capabilities=_FAKE_CAPABILITIES,
            _diagnosis_state_sink=diagnosis_state_sink,
        )
    )

    assert isinstance(result, GymactMediatedDiagnosisResult)

    # Real values, from the fake's own canned responses -- proves each of
    # the five distinct observe-block keys landed correctly, none lost and
    # none overwritten by a different concurrently-running check.
    assert diagnosis_state_sink["check_status"] == {"after": {"stage": "observed"}}
    assert diagnosis_state_sink["deployments"] == _DEPLOYMENTS
    assert diagnosis_state_sink["pods"] == _PODS
    assert diagnosis_state_sink["services"] == _SERVICES
    # `_check_namespace` writes no diagnosis_state key by design (see its
    # own docstring in gymact_diagnosis_driver.py) -- its only observable
    # effect is not raising, already proven by `result` existing at all.

    # The AND-join (`_scan_anomalies`) only ever reads the three keys above
    # AFTER all five observe-block writers have returned -- if any write had
    # been lost, this would have raised a real `KeyError` rather than
    # computing a real anomaly count, or would disagree with the real
    # deployments/pods data above.
    assert "anomalies" in diagnosis_state_sink
    assert len(diagnosis_state_sink["anomalies"]) == 1
    assert diagnosis_state_sink["label"] != "no_anomaly_detected"

    # Real regression coverage that the remediate-recheck block's three
    # distinct keys (a symmetric, independently-writing concurrent block)
    # were likewise all preserved.
    assert diagnosis_state_sink["recheck_deployments"] == _DEPLOYMENTS
    assert diagnosis_state_sink["recheck_pods"] == _PODS_RECOVERED
    assert diagnosis_state_sink["recheck_services"] == _SERVICES
    assert diagnosis_state_sink["structural_recheck_anomaly_count"] == 0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
