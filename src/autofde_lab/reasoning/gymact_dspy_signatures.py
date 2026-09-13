# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""A staged, typed ``dspy.Signature`` decomposition of the sregym
diagnosis/mitigation challenge -- replacing ``gymact_dspy_react.py``'s
single flat ``DiagnoseClusterFault`` signature with five focused reasoning
stages, per https://dspy.ai/tutorials/mcp/'s typed-``Signature`` pattern.

What this module deliberately does NOT copy from that tutorial
------------------------------------------------------------------
The tutorial's ``dspy.Tool.from_mcp_tool(session, tool)`` pattern hands an
MCP session's raw tools straight to ``dspy.ReAct``, bypassing this repo's
``CapabilityGate`` entirely. Every tool call in this module -- exactly one,
inside :class:`ObserveClusterStage` -- is routed through the same real,
TOML-manifest-checked ``CapabilityGate.guard_capability()`` gate
``gymact_dspy_react.py`` already uses, reusing that module's own
``build_gated_react_tools``/``_run_coroutine_sync`` pattern rather than a
second, ungated tool-construction path.

The five real stages
----------------------
1. :class:`ObserveCluster` -- gather real cluster state via gated tool
   calls; output a structured text summary. The only stage that touches a
   live environment.
2. :class:`ClassifyAnomaly` -- given that summary, propose candidate fault
   labels from the REAL taxonomy label set in
   ``autofde_lab_planner.scanner.taxonomy`` (the ``inject_*`` names grepped
   from sregym's own fault-injector method names -- see that module's
   docstring). This is the one reasoning role the existing rule-based
   ``classify()`` cannot fill: reasoning about anomalies the structural
   scanner (``autofde_lab_planner.scanner.registry.scan``) did not cleanly
   match to one of its own hardcoded structural signatures.
3. :class:`DiagnoseRootCause` -- turn a cluster summary + candidate labels
   into the actual diagnosis text/confidence submitted via the real, gated
   ``submit_diagnosis`` capability.
4. :class:`SynthesizeMitigation` -- **the one real, currently-nonexistent
   piece.** ``gymact_diagnosis_driver.py``'s ``_submit_mitigation`` is
   PERMANENTLY hardcoded to ``{"mitigation": "not_attempted", "reason":
   "no_automated_command_synthesis_yet"}`` (see that module's own
   docstring) -- this signature is a NEW, separate, opt-in capability for
   generating a real, single, syntactically valid kubectl command from a
   diagnosis. It is never wired into ``gymact_diagnosis_driver.py`` and
   never overwrites that module's honest ``"not_attempted"`` default; it is
   only consumed by this module's own :func:`run_staged_dspy_diagnosis`
   when a caller explicitly opts in with ``attempt_mitigation=True``.
5. :class:`VerifyMitigationOutcome` -- an LLM-assisted second opinion on
   whether a post-mitigation cluster summary looks fixed. This is
   explicitly NOT a replacement for GymAct's own independent
   ``env.verify()``/``PostconditionVerifier`` oracle call -- its ``outcome``
   is advisory reasoning support only, never itself the authoritative
   verified-consequence signal GymAct's kernel produces. See
   ``.claude/rules/actuation-authority.md``'s
   ``Intent != Action != Effect != Verified Effect`` law: this signature's
   output is reasoning about an *intent* to have fixed something, not a
   *verified effect*.

Real remediation-command grounding
-------------------------------------
:class:`SynthesizeMitigation`'s docstring below names concrete,
taxonomy-grounded kubectl shapes for three real ``inject_*`` fault labels
(``inject_wrong_dns_policy``, ``inject_liveness_probe_too_aggressive``,
``inject_missing_configmap``) so the LM has real domain grounding to draw
on, not just free-floating kubectl syntax.
"""

from __future__ import annotations

import concurrent.futures
import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal

import dspy

from autofde_lab.fabric.gymact_capability_gate import DEFAULT_MANIFEST_PATH, CapabilityGate
from autofde_lab_planner.scanner.taxonomy import (
    INJECT_CONFIGMAP_DRIFT,
    INJECT_DUPLICATE_PVC_MOUNTS,
    INJECT_LIVENESS_PROBE_MISCONFIGURATION,
    INJECT_LIVENESS_PROBE_TOO_AGGRESSIVE,
    INJECT_MISCONFIG_K8S,
    INJECT_MISSING_CONFIGMAP,
    INJECT_MISSING_SERVICE,
    INJECT_MISSING_SERVICE_INGRESS,
    INJECT_PVC_CLAIM_MISMATCH,
    INJECT_RBAC_MISCONFIGURATION,
    INJECT_RESOURCE_REQUEST,
    INJECT_ROLLING_UPDATE_MISCONFIGURED,
    INJECT_SCALE_PODS_TO_ZERO,
    INJECT_SERVICE_WRONG_POD_SELECTION,
    INJECT_SIDECAR_PORT_CONFLICT,
    INJECT_WRONG_DNS_POLICY,
    INJECT_WRONG_SERVICE_SELECTOR,
    UNCLASSIFIED,
)

__all__ = [
    "REAL_FAULT_LABELS",
    "ObserveCluster",
    "ClassifyAnomaly",
    "DiagnoseRootCause",
    "SynthesizeMitigation",
    "VerifyMitigationOutcome",
    "StagedDiagnosisResult",
    "StagedGymActDiagnoser",
    "build_gated_observe_tools",
    "run_staged_dspy_diagnosis",
]

# The real, closed label set this repo's rule-based classifier can produce,
# sourced directly from `autofde_lab_planner.scanner.taxonomy` (itself
# grepped from sregym's own `inject_*` fault-injector method names -- see
# that module's docstring). `ClassifyAnomaly` is instructed to draw from
# this real vocabulary, never invent new fault names.
REAL_FAULT_LABELS: tuple[str, ...] = (
    INJECT_SCALE_PODS_TO_ZERO,
    INJECT_PVC_CLAIM_MISMATCH,
    INJECT_DUPLICATE_PVC_MOUNTS,
    INJECT_MISSING_CONFIGMAP,
    INJECT_CONFIGMAP_DRIFT,
    INJECT_MISSING_SERVICE,
    INJECT_WRONG_SERVICE_SELECTOR,
    INJECT_SERVICE_WRONG_POD_SELECTION,
    INJECT_RBAC_MISCONFIGURATION,
    INJECT_ROLLING_UPDATE_MISCONFIGURED,
    INJECT_MISCONFIG_K8S,
    INJECT_RESOURCE_REQUEST,
    INJECT_WRONG_DNS_POLICY,
    INJECT_LIVENESS_PROBE_TOO_AGGRESSIVE,
    INJECT_LIVENESS_PROBE_MISCONFIGURATION,
    INJECT_SIDECAR_PORT_CONFLICT,
    INJECT_MISSING_SERVICE_INGRESS,
    UNCLASSIFIED,
)
_REAL_FAULT_LABELS_DESC = ", ".join(REAL_FAULT_LABELS)


def _run_coroutine_sync(coro: Any) -> Any:
    """Run a real coroutine to completion from a synchronous tool call,
    without colliding with a caller's already-running event loop.

    Duplicated from (not imported from) ``gymact_dspy_react.py`` /
    ``gymact_diagnosis_driver.py`` -- both those modules are named
    not-to-be-touched by this task, and this three-line helper is not worth
    coupling this new module to either of them."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def _capability(capabilities: Any, name: str) -> Any:
    for cap in capabilities:
        if cap.binding == name:
            return cap
    raise KeyError(f"no real gymact capability named {name!r}")


# ---------------------------------------------------------------------------
# Stage 1: ObserveCluster (real gated tool calls)
# ---------------------------------------------------------------------------


class ObserveCluster(dspy.Signature):
    """Gather real, current Kubernetes cluster state for the given
    namespace via the provided gated tools (real kubectl reads, the real
    conductor status observation) and summarize it. Never fabricate
    resource state the tools did not actually return."""

    namespace: str = dspy.InputField(desc="the real Kubernetes namespace to observe")
    cluster_summary: str = dspy.OutputField(
        desc=(
            "a structured, factual natural-language summary of real observed "
            "deployments/pods/services/events in this namespace, grounded "
            "only in real tool output -- no speculation about causes here"
        )
    )


def build_gated_observe_tools(
    environment: Any,
    gate: CapabilityGate,
    capabilities: Any,
    *,
    namespace: str,
) -> list[Callable[..., str]]:
    """Real, gated tool functions for the :class:`ObserveCluster` stage --
    the SAME ``CapabilityGate.guard_capability()`` routing
    ``gymact_dspy_react.build_gated_react_tools`` uses, deliberately
    duplicated (not imported) per this task's "do not modify
    ``gymact_dspy_react.py``" constraint. Only read-consequence and
    namespace-scoped kubectl-read tools are exposed at this stage --
    ``run_kubectl`` is reused for reads here (its own consequence class is
    DO per ``SREGYM_CAPABILITIES``, but every call this function makes is a
    non-mutating ``get``/``describe`` read)."""
    capabilities_by_binding = {cap.binding: cap for cap in capabilities}

    def run_kubectl(command: str) -> str:
        """Run a real, namespace-scoped read-only kubectl command (e.g.
        'get pods -o json', 'get deployments -o json', 'get events
        --sort-by=.lastTimestamp'). Namespace is applied automatically."""
        cap = capabilities_by_binding["run_kubectl"]
        gate.guard_capability(cap)
        stripped = command.strip()
        if not stripped.startswith("kubectl"):
            stripped = f"kubectl {stripped}"
        if " -n " not in stripped and "--namespace" not in stripped:
            stripped = f"{stripped} -n {namespace}"
        result = _run_coroutine_sync(environment.actuate(cap, {"command": stripped}))
        return str(result)

    def observe_cluster_state() -> str:
        """Read sregym's real conductor /status endpoint."""
        cap = capabilities_by_binding["observe_cluster_state"]
        gate.guard_capability(cap)
        result = _run_coroutine_sync(environment.actuate(cap, {}))
        return str(result)

    return [run_kubectl, observe_cluster_state]


class ObserveClusterStage(dspy.Module):
    """Real ``dspy.ReAct(ObserveCluster, tools=...)`` wrapper -- the only
    stage in the staged pipeline that touches a live environment."""

    def __init__(
        self,
        *,
        environment: Any,
        gate: CapabilityGate,
        capabilities: Any,
        namespace: str,
        max_iters: int = 6,
    ) -> None:
        super().__init__()
        tools = build_gated_observe_tools(environment, gate, capabilities, namespace=namespace)
        self.react = dspy.ReAct(ObserveCluster, tools=tools, max_iters=max_iters)

    def forward(self, namespace: str) -> Any:
        return self.react(namespace=namespace)


# ---------------------------------------------------------------------------
# Stage 2: ClassifyAnomaly (pure reasoning)
# ---------------------------------------------------------------------------


class ClassifyAnomaly(dspy.Signature):
    """Given a real observed cluster summary, propose candidate fault
    labels. Choose ONLY from this repo's real, closed fault-label
    vocabulary (grepped from sregym's own inject_* fault-injector method
    names, never invented): """ + _REAL_FAULT_LABELS_DESC + (
        ". If no real evidence in the summary matches any of these labels, "
        "return only 'UNCLASSIFIED' -- never fabricate a label outside "
        "this list."
    )

    cluster_summary: str = dspy.InputField(desc="the real observed cluster state summary")
    candidate_fault_labels: list[Literal[*REAL_FAULT_LABELS]] = dspy.OutputField(
        desc=(
            "one or more labels drawn strictly, verbatim, from this real "
            "closed enum -- never a paraphrase or invented label; "
            "['UNCLASSIFIED'] if nothing in the summary matches any of the others"
        )
    )


# ---------------------------------------------------------------------------
# Stage 3: DiagnoseRootCause (pure reasoning)
# ---------------------------------------------------------------------------


class DiagnoseRootCause(dspy.Signature):
    """Given a real cluster summary and candidate fault labels, produce the
    root-cause diagnosis text and confidence that will be submitted via the
    real, gated `submit_diagnosis` sregym capability. Confidence must
    reflect actual evidentiary support in `cluster_summary` -- never a
    default/round number chosen without real grounding."""

    cluster_summary: str = dspy.InputField(desc="the real observed cluster state summary")
    candidate_fault_labels: list[str] = dspy.InputField(
        desc="candidate fault labels from the ClassifyAnomaly stage, real taxonomy vocabulary"
    )
    diagnosis: str = dspy.OutputField(
        desc="free-text root-cause diagnosis grounded in cluster_summary and candidate_fault_labels"
    )
    confidence: float = dspy.OutputField(desc="0.0-1.0, must reflect actual evidentiary support")


# ---------------------------------------------------------------------------
# Stage 4: SynthesizeMitigation (pure reasoning; the real, missing piece)
# ---------------------------------------------------------------------------


class SynthesizeMitigation(dspy.Signature):
    """Given a diagnosed root cause, synthesize ONE real, syntactically
    valid `kubectl` command that would plausibly remediate it. This is a
    NEW capability with no rule-based equivalent in this repo today --
    `gymact_diagnosis_driver.py`'s `_submit_mitigation` is permanently
    hardcoded to `mitigation="not_attempted"` because no automated
    remediation-command synthesis has ever been built here. This
    signature's output is never wired into that driver's behavior; it is
    only used by this module's own opt-in `attempt_mitigation=True` path.

    Real grounding for at least three of this repo's real `inject_*` fault
    labels (see `autofde_lab_planner.scanner.taxonomy`), so the synthesized
    command is not hallucinated syntax:

    - `inject_wrong_dns_policy`: sregym's real injector sets a Pod's
      `spec.dnsPolicy` to an invalid/wrong value (e.g. patches it away from
      `ClusterFirst`). A real fix is a strategic-merge patch restoring the
      correct policy, e.g.:
      `kubectl patch deployment <name> -n <namespace> --type merge -p
      '{"spec":{"template":{"spec":{"dnsPolicy":"ClusterFirst"}}}}'`
    - `inject_liveness_probe_too_aggressive`: the injector lowers a
      container's liveness probe `failureThreshold`/`periodSeconds` so the
      probe kills healthy pods. A real fix restores reasonable probe
      timing via a JSON patch on the container's `livenessProbe`, e.g.:
      `kubectl patch deployment <name> -n <namespace> --type json -p
      '[{"op":"replace","path":"/spec/template/spec/containers/0/livenessProbe/failureThreshold","value":3}]'`
    - `inject_missing_configmap`: a Deployment references a ConfigMap that
      does not exist (dangling reference). A real fix either recreates the
      missing ConfigMap with the expected keys or removes the dangling
      volume/envFrom reference; without the original ConfigMap's real data
      the safer, honest action is often a read-only re-describe to confirm
      the missing name before proposing a create, e.g.:
      `kubectl get configmap <expected-name> -n <namespace>` (to confirm
      absence) followed by a real `kubectl create configmap <expected-name>
      -n <namespace> --from-literal=<key>=<value>` once the expected
      key/value is actually known -- never fabricate plausible-looking
      ConfigMap data with no evidentiary basis.

    Always prefer the least-destructive real command that plausibly
    addresses the diagnosed root cause; never propose a command that
    deletes a namespace, a PVC with user data, or any resource unrelated to
    the diagnosis."""

    diagnosis: str = dspy.InputField(desc="the real diagnosed root cause")
    namespace: str = dspy.InputField(desc="the real Kubernetes namespace to target")
    kubectl_command: str = dspy.OutputField(
        desc="ONE real, single, syntactically valid kubectl command string, no shell chaining"
    )
    rationale: str = dspy.OutputField(desc="why this specific command addresses the diagnosed root cause")


# ---------------------------------------------------------------------------
# Stage 5: VerifyMitigationOutcome (pure reasoning; advisory only)
# ---------------------------------------------------------------------------


class VerifyMitigationOutcome(dspy.Signature):
    """Advisory, LLM-assisted second opinion on whether a post-mitigation
    cluster summary looks fixed relative to the original diagnosis.

    NOT authoritative. This is explicitly NOT a replacement for GymAct's
    own independent `env.verify()` / `PostconditionVerifier` oracle call --
    per `.claude/rules/actuation-authority.md`'s `Intent != Action !=
    Effect != Verified Effect` law, this signature's `outcome` is reasoning
    support only. The only authoritative "world changed as intended" signal
    in this repo is a real, independent GymAct verification call; never
    treat this signature's output as a substitute for one."""

    post_mitigation_cluster_summary: str = dspy.InputField(
        desc="a real cluster summary gathered AFTER a mitigation command was applied"
    )
    original_diagnosis: str = dspy.InputField(desc="the diagnosis text the mitigation targeted")
    outcome: Literal["fixed", "not_fixed", "unclear"] = dspy.OutputField(
        desc="advisory-only judgment; never the authoritative verified-consequence signal"
    )
    evidence: str = dspy.OutputField(desc="the specific real evidence in the summary supporting `outcome`")


# ---------------------------------------------------------------------------
# Staged module
# ---------------------------------------------------------------------------


class StagedGymActDiagnoser(dspy.Module):
    """Chains the five real stages in order. ``observe`` uses
    ``dspy.ReAct`` over real gated tool calls; the four pure-reasoning
    stages use ``dspy.ChainOfThought``/``dspy.Predict``. Mitigation
    synthesis/verify are only invoked by :func:`run_staged_dspy_diagnosis`
    when explicitly requested -- this module exposes them as separate
    callables rather than an unconditional ``forward`` chain, since
    synthesizing+applying a mitigation is a real, consequential act that
    must stay opt-in."""

    def __init__(
        self,
        *,
        environment: Any,
        gate: CapabilityGate,
        capabilities: Any,
        namespace: str,
        max_observe_iters: int = 6,
    ) -> None:
        super().__init__()
        self.observe = ObserveClusterStage(
            environment=environment,
            gate=gate,
            capabilities=capabilities,
            namespace=namespace,
            max_iters=max_observe_iters,
        )
        self.classify = dspy.Predict(ClassifyAnomaly)
        self.diagnose = dspy.ChainOfThought(DiagnoseRootCause)
        self.synthesize = dspy.ChainOfThought(SynthesizeMitigation)
        self.verify_outcome = dspy.Predict(VerifyMitigationOutcome)

    def forward(self, namespace: str) -> dict[str, Any]:
        observed = self.observe(namespace=namespace)
        cluster_summary = str(getattr(observed, "cluster_summary", ""))

        classified = self.classify(cluster_summary=cluster_summary)
        candidate_fault_labels = list(getattr(classified, "candidate_fault_labels", []) or [])

        diagnosed = self.diagnose(
            cluster_summary=cluster_summary,
            candidate_fault_labels=candidate_fault_labels,
        )
        try:
            confidence = max(0.0, min(1.0, float(getattr(diagnosed, "confidence", 0.0))))
        except (TypeError, ValueError):
            confidence = 0.0

        return {
            "cluster_summary": cluster_summary,
            "candidate_fault_labels": candidate_fault_labels,
            "diagnosis": str(getattr(diagnosed, "diagnosis", "")),
            "confidence": confidence,
        }


@dataclass(frozen=True, slots=True)
class StagedDiagnosisResult:
    """Real, typed result of one staged diagnosis run."""

    problem_id: str
    namespace: str
    cluster_summary: str
    candidate_fault_labels: list[str]
    diagnosis: str
    confidence: float
    submit_diagnosis_response: Any
    mitigation_attempted: bool
    kubectl_command: str | None
    mitigation_rationale: str | None
    run_kubectl_response: Any | None
    submit_mitigation_response: Any | None


async def run_staged_dspy_diagnosis(
    problem_id: str,
    *,
    mcp_server_port: int = 0,
    api_port: int = 0,
    judge_model_id: str = "groq/openai/gpt-oss-20b",
    judge_api_base: str = "https://api.groq.com/openai/v1",
    wall_clock_timeout_s: int = 900,
    startup_timeout_seconds: float = 900.0,
    verify_timeout_seconds: float = 300.0,
    namespace: str | None = None,
    manifest_path: Path | str = DEFAULT_MANIFEST_PATH,
    max_observe_iters: int = 6,
    attempt_mitigation: bool = False,
    lm: Any | None = None,
    _environment_factory: Callable[[], Any] | None = None,
    _capabilities: Any = None,
) -> StagedDiagnosisResult:
    """Run the real staged pipeline against a real, materialized
    ``SregymVendorProvider`` (or an injected fake via
    ``_environment_factory``/``_capabilities``, matching
    ``gymact_dspy_react.run_dspy_diagnosis``'s test-injection contract).

    When ``attempt_mitigation=True``, this ACTUALLY calls the gated,
    DO-consequence ``run_kubectl`` capability with
    :class:`SynthesizeMitigation`'s real derived command before the final
    advisory verify stage -- real actuation, routed through
    ``CapabilityGate.guard_capability()`` exactly like every other tool
    call in this codebase, and still subject to GymAct's own
    authority-gating (an unauthorized ``AuthorityResolver`` will refuse the
    underlying ``env.actuate()`` call the same way it refuses any other
    ``run_kubectl`` call). ``submit_mitigation`` is deliberately NEVER
    called from this function -- this function only synthesizes and applies
    a command; it never touches the driver's own honest
    ``"not_attempted"`` submission semantics, per this task's explicit
    "opt-in, separate capability" constraint.
    """
    if namespace is None:
        from autofde_lab.reasoning.gymact_diagnosis_driver import PROBLEM_ID_NAMESPACE

        namespace = PROBLEM_ID_NAMESPACE.get(problem_id)
        if namespace is None:
            raise ValueError(
                f"no known real namespace for problem_id={problem_id!r} -- pass namespace= "
                "explicitly (see PROBLEM_ID_NAMESPACE in gymact_diagnosis_driver.py)."
            )

    gate = CapabilityGate.from_toml(manifest_path)

    if _environment_factory is not None:
        env = await _environment_factory()
        capabilities = _capabilities
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
        capabilities = SREGYM_CAPABILITIES

    resolved_lm = lm if lm is not None else dspy.LM(judge_model_id)

    try:
        diagnoser = StagedGymActDiagnoser(
            environment=env,
            gate=gate,
            capabilities=capabilities,
            namespace=namespace,
            max_observe_iters=max_observe_iters,
        )
        with dspy.context(lm=resolved_lm):
            staged = diagnoser(namespace=namespace)

            kubectl_command: str | None = None
            mitigation_rationale: str | None = None
            run_kubectl_response: Any | None = None
            if attempt_mitigation:
                synthesized = diagnoser.synthesize(
                    diagnosis=staged["diagnosis"], namespace=namespace
                )
                kubectl_command = str(getattr(synthesized, "kubectl_command", ""))
                mitigation_rationale = str(getattr(synthesized, "rationale", ""))

                run_kubectl_cap = _capability(capabilities, "run_kubectl")
                gate.guard_capability(run_kubectl_cap)
                run_kubectl_response = await env.actuate(
                    run_kubectl_cap, {"command": kubectl_command}
                )

        submit_cap = _capability(capabilities, "submit_diagnosis")
        gate.guard_capability(submit_cap)
        submit_response = await env.actuate(
            submit_cap, {"diagnosis": staged["diagnosis"], "confidence": float(staged["confidence"])}
        )

        return StagedDiagnosisResult(
            problem_id=problem_id,
            namespace=namespace,
            cluster_summary=staged["cluster_summary"],
            candidate_fault_labels=staged["candidate_fault_labels"],
            diagnosis=staged["diagnosis"],
            confidence=float(staged["confidence"]),
            submit_diagnosis_response=submit_response,
            mitigation_attempted=attempt_mitigation,
            kubectl_command=kubectl_command,
            mitigation_rationale=mitigation_rationale,
            run_kubectl_response=run_kubectl_response,
            submit_mitigation_response=None,
        )
    finally:
        try:
            await env.teardown()
        except Exception as teardown_exc:  # noqa: BLE001 -- teardown failure must not mask a real result
            import logging

            logging.getLogger(__name__).warning(
                "gymact_dspy_signatures: env.teardown() raised %r", teardown_exc
            )
