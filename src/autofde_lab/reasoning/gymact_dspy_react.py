# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""A small, real DSPy ``ReAct`` diagnosis loop over the real, gated sregym
capability surface.

Scope, honestly bounded
------------------------
This is deliberately smaller than ``gymact_diagnosis_driver.py``'s POWL
pipeline, and solves a genuinely different problem. The POWL driver executes
a *precomputed, fixed* process tree (``build_pipeline_powl_node`` builds it
once; ``run_pipeline`` fires bound closures in the order the tree's own
structural replay enables) -- deterministic, no LLM in that loop, matching
``CLAUDE.md``'s "planner selects, executor performs" split with POWL as the
already-computed plan. This module is for the opposite case: deciding the
*next investigation step* when the sequence can't be predetermined because
it depends on what was actually observed. It is a basic ``observe -> think ->
act (kubectl reads) -> submit_diagnosis`` loop, driven by a real, swappable
decision backend -- the "quick... basic runs" scope named in this task, not
a replacement for the POWL-mediated driver.

The decision step is a swappable seam, not a permanent DSPy commitment
----------------------------------------------------------------------------
DSPy is the interim mechanism for "decide the next investigation step",
never the permanent one. The intended end state swaps this for a real
O*/scikit-decide planner call (``solve()`` over a domain) -- this repo
computes candidate plans, it does not permanently delegate that computation
to an LLM loop. :class:`DiagnosisDecisionBackend` names that seam explicitly;
:class:`DspyReActDecisionBackend` is today's real, DSPy-``ReAct``-backed
implementation of it. A future ``PlannerDecisionBackend`` can implement the
same contract without ``GymActReActDiagnoser`` or ``run_dspy_diagnosis``
changing at all.

Why DSPy (for now)
------------------------------------
``dspy`` is already a real, installed dependency of this project (see
``pyproject.toml``'s ``[project.optional-dependencies].dspy`` and the
already-real ``dspy.ReAct`` usage in ``sregym_pipeline.py`` and
``hub/solver/dspy_policy/dspy_policy.py``). Reusing the framework's own
``ReAct`` module -- rather than hand-rolling a second, parallel
observe/think/act loop -- keeps this module's control flow (tool-call
parsing, trajectory bookkeeping, stopping condition) delegated to code this
repo already depends on and already tests elsewhere, matching
``python-native.md``'s "compose, don't generate" rule at the DSPy-usage
level, not just the FastAPI/FastMCP level it names explicitly.

Real, gated tool calls -- not a bypass of ``CapabilityGate``
-----------------------------------------------------------------
Every tool ``dspy.ReAct`` may call is a thin synchronous wrapper that (a)
looks up the real ``gymact.gyms.sregym`` ``Capability`` object for that
binding name, (b) calls ``CapabilityGate.guard_capability(capability)`` --
the SAME gate instance, loaded from the SAME
``fabric/gymact_capabilities.toml`` manifest ``gymact_diagnosis_driver.py``
uses -- before, (c) driving the real, async ``environment.actuate(...)``
call to completion via a dedicated-thread ``asyncio.run`` (see
``_run_coroutine_sync``, mirroring ``gymact_diagnosis_driver.py``'s own
helper of the same name/shape, duplicated rather than imported since that
module is explicitly not to be touched or made a dependency surface for
this new, separate module). A refused capability raises
``CapabilityRefused`` (a real ``PermissionError`` subclass) out of the tool
call, exactly as it would from the POWL-mediated driver -- there is no
second, ungated path to ``environment.actuate()`` anywhere in this file.

Grounding, not guessing
------------------------
A ``run_kubectl`` call naming a specific resource (``pod/api-0``,
``deployment/frontend``) is refused if that identifier has never appeared in
a real prior tool result this run -- the same class of defect
``gymact.dspy_agent``'s ``_assert_payload_is_grounded`` mechanically guards
against for its own, more general actuation surface. The mechanism is
ported here (not imported from ``gymact``), scoped to this module's own,
narrower ``run_kubectl``/``observe_cluster_state`` tool shapes, following
the same "small, portable, dependency-free check" precedent
``_run_coroutine_sync`` above already sets for this file. Bare list/read
commands with no specific resource reference (``get pods``) are never
flagged -- there is nothing to ground. The very first tool call in a run is
also never flagged (bootstrap: nothing has been observed yet to ground
against), matching ``gymact.dspy_agent.GymActReActAgent.run_goal``'s own
"always starts from a real observation" discipline.

``submit_mitigation``, if attempted at all
--------------------------------------------
``run_dspy_diagnosis`` only observes and diagnoses by default;
``attempt_mitigation=True`` routes to
``autofde_lab.reasoning.gymact_mitigation_actuation.execute_and_submit_mitigation``,
which constructs a real mitigation portfolio, filters it down to candidates
marked ``safe_to_actuate``, translates each surviving step into a real
``kubectl`` command via ``TranslateMitigationStepToKubectlCommand``, actuates
those commands through the same gated ``run_kubectl`` capability this module
uses elsewhere, and submits the real, non-placeholder result of that
actuation -- never a fabricated remediation command. Only when the portfolio
yields zero ``safe_to_actuate`` candidates does it fall back to an honest
``attempted=False`` early return, rather than actuating nothing and claiming
otherwise.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

import dspy

from autofde_lab.fabric.gymact_capability_gate import DEFAULT_MANIFEST_PATH, CapabilityGate
from autofde_lab.powl.algebra import ChoiceGraph, ChoiceGraphEdge, End, Guard, NodeId, Silent, Start
from autofde_lab.powl.algebra import Atom as PowlAtom
from autofde_lab.powl.guard_executor import execute as execute_powl
from autofde_lab.powl.ocel_bridge import OcelExecutionRecorder, execute_with_ocel
from autofde_lab.reasoning.breed_ensemble import BreedEnsembleMember, run_breed_ensemble
from autofde_lab.reasoning.hearsay_cross_check import _bullet_lines, hypotheses_to_breed_input
from autofde_lab.reasoning.k8s_signatures import DiagnoseKubernetesFault
from autofde_lab.reasoning.sre_troubleshooting_pipeline import SreTroubleshootingPipeline
from autofde_lab_planner.engine import CompositePlannerEngine

__all__ = [
    "DecisionOutcome",
    "DiagnosisDecisionBackend",
    "DiagnosisResult",
    "DspyReActDecisionBackend",
    "GymActReActDiagnoser",
    "SreTroubleshootingDecisionBackend",
    "UngroundedKubectlReferenceRefused",
    "build_gated_react_tools",
    "run_dspy_diagnosis",
]

# ---------------------------------------------------------------------------
# CompositePlannerEngine wiring -- the real resource kinds
# ``CompositePlannerEngine.run_diagnosis()`` reads (see
# ``autofde_lab_planner/engine.py``'s own ``run_diagnosis`` signature),
# expressed as (run_diagnosis kwarg, kubectl resource name, is-namespaced)
# triples. ``configmaps_json`` is deliberately excluded here -- it needs a
# real two-namespace merge (app namespace for flagd-config, kube-system for
# the coredns ConfigMap; see ``run_composite_diagnosis`` below for why) that
# does not fit this generic one-resource-one-field plan. ``raw_traces_by_service``
# (B6 OTel trace diffing) and ``elevated_revision_deployments`` are also
# excluded -- genuinely not derivable from a plain kubectl read (the former
# needs real Jaeger trace data, the latter needs historical revision
# comparison), an honest, named gap rather than a fabricated value.
_COMPOSITE_DIAGNOSIS_RESOURCE_PLAN: tuple[tuple[str, str, bool], ...] = (
    ("deployments_json", "deployments", True),
    ("services_json", "services", True),
    ("secrets_json", "secrets", True),
    ("pods_json", "pods", True),
    ("events_json", "events", True),
    ("ingresses_json", "ingresses", True),
    ("cronjobs_json", "cronjobs", True),
    ("pvcs_json", "persistentvolumeclaims", True),
    ("resourcequotas_json", "resourcequotas", True),
    ("limitranges_json", "limitranges", True),
    ("service_accounts_json", "serviceaccounts", True),
    ("cluster_roles_json", "clusterroles", False),
    ("cluster_role_bindings_json", "clusterrolebindings", False),
)


def _run_coroutine_sync(coro: Any) -> Any:
    """Run a real coroutine to completion from a synchronous ReAct tool
    call, without colliding with a caller's already-running event loop.

    Duplicated from (not imported from) ``gymact_diagnosis_driver.py`` --
    this task's constraints name that module as not-to-be-touched and this
    module as a new, separate, additive one; a private, three-line helper is
    not worth coupling the two modules together for.
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def _capability(capabilities: Any, name: str) -> Any:
    for cap in capabilities:
        if cap.binding == name:
            return cap
    raise KeyError(f"no real gymact capability named {name!r}")


# ---------------------------------------------------------------------------
# Grounding guard -- ported mechanism (not import) from gymact.dspy_agent's
# _assert_payload_is_grounded / _collect_string_leaves, scoped to this
# module's own run_kubectl/observe_cluster_state tool shapes.
# ---------------------------------------------------------------------------


class UngroundedKubectlReferenceRefused(ValueError):
    """A proposed ``run_kubectl`` command named a specific resource
    identifier never present in any real prior tool result this run --
    refused before the real ``kubectl`` call, not silently coerced or
    dropped."""

    def __init__(self, command: str, ungrounded_identifiers: tuple[str, ...]) -> None:
        self.command = command
        self.ungrounded_identifiers = ungrounded_identifiers
        super().__init__(
            f"REFUSED:UNGROUNDED_KUBECTL_REFERENCE command={command!r} "
            f"identifiers_not_in_prior_observation={ungrounded_identifiers!r}"
        )


def _collect_string_leaves(value: Any) -> set[str]:
    """Real, generic walk of a JSON-like structure collecting every string
    leaf value AND every dict key -- same shape as
    ``gymact.dspy_agent._collect_string_leaves`` (dict keys matter as much
    as values: a real resource name is very often a dict key, e.g.
    ``{"metadata": {"name": "api-0"}}``).

    Any string leaf that itself parses as JSON is walked too -- sregym's
    real kubectl-mcp results embed their actual payload as a JSON-encoded
    string inside a ``{"result_text": [{"text": "..."}]}`` wrapper, so a
    real resource name only becomes visible to this grounding walk by
    recursing into that embedded document, not just its outer shape."""
    import json

    found: set[str] = set()
    if isinstance(value, str):
        found.add(value)
        try:
            parsed = json.loads(value)
        except (ValueError, TypeError):
            pass
        else:
            if isinstance(parsed, (dict, list, tuple, set)):
                found |= _collect_string_leaves(parsed)
    elif isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str):
                found.add(key)
            found |= _collect_string_leaves(item)
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            found |= _collect_string_leaves(item)
    return found


def _extract_referenced_identifiers(command: str) -> set[str]:
    """Real, narrow heuristic over a kubectl command string: pull out
    slash-qualified resource refs (``deployment/frontend``, ``pod/api-0``)
    and the real positional NAME argument after ``describe``/``logs``/
    ``exec`` -- the concrete shapes a kubectl command can use to name one
    EXISTING resource. Bare list/read commands with no such token
    (``get pods -o json``) are never flagged -- there is nothing to
    ground.

    ``describe`` takes either ``<kind> <name>`` (two positional args -- the
    NAME, not the kind, is the identifier that must be grounded) or
    ``<kind>/<name>`` (one slash-qualified positional arg, handled by the
    slash pass above). ``logs``/``exec`` take the resource name directly as
    their first positional arg."""
    tokens = command.split()
    identifiers: set[str] = set()
    for tok in tokens:
        if "/" in tok and not tok.startswith("-"):
            identifiers.add(tok)

    def _positional_args(after_idx: int) -> list[str]:
        args: list[str] = []
        i = after_idx
        while i < len(tokens):
            tok = tokens[i]
            if tok in ("-n", "--namespace"):
                i += 2
                continue
            if tok.startswith("-"):
                i += 1
                continue
            args.append(tok)
            i += 1
        return args

    if "describe" in tokens:
        idx = tokens.index("describe")
        args = _positional_args(idx + 1)
        if len(args) >= 2:
            identifiers.add(args[1])
        elif len(args) == 1 and "/" not in args[0]:
            identifiers.add(args[0])

    for verb in ("logs", "exec"):
        if verb not in tokens:
            continue
        idx = tokens.index(verb)
        args = _positional_args(idx + 1)
        if args:
            identifiers.add(args[0])

    return identifiers


class DiagnoseClusterFault(dspy.Signature):
    """Diagnose a live Kubernetes cluster fault for the given sregym
    problem. Use the provided tools to inspect REAL live cluster state
    (kubectl reads, the conductor's own status observation) before
    concluding -- never guess a root cause the tools have not evidenced.

    Deprecated: superseded by ``k8s_signatures.DiagnoseKubernetesFault``.
    Kept only as a stable import path for callers that referenced this
    exact name; ``GymActReActDiagnoser`` no longer uses it."""

    problem_id: str = dspy.InputField(desc="the sregym benchmark problem id under diagnosis")
    namespace: str = dspy.InputField(desc="the real Kubernetes namespace the target app deploys into")
    diagnosis: str = dspy.OutputField(desc="free-text root-cause diagnosis grounded in real tool output")
    confidence: float = dspy.OutputField(desc="0.0-1.0, must reflect actual evidentiary support from tool calls")


def build_gated_react_tools(
    environment: Any,
    gate: CapabilityGate,
    capabilities: Any,
    *,
    namespace: str,
) -> list[Callable[..., str]]:
    """Build synchronous ``dspy.ReAct``-compatible tool functions, each
    routed through the real, ``CapabilityGate``-checked
    ``environment.actuate(capability, payload)`` surface, and each subject
    to the real grounding guard above.

    ``namespace`` is closed over rather than left to the LLM to supply on
    every call -- the LLM already knows it from the caller's own prompt
    construction; baking it into the tool functions here means a
    hallucinated/wrong namespace argument from the model can never silently
    redirect a real kubectl read at a different namespace than the one this
    run was materialized against.
    """
    capabilities_by_binding = {cap.binding: cap for cap in capabilities}
    grounded_facts: set[str] = set()

    def run_kubectl(command: str) -> str:
        """Run a real, namespace-scoped read-only kubectl command against
        the live cluster (e.g. 'get pods -o json', 'describe deployment
        <name>', 'get events --sort-by=.lastTimestamp'). The namespace is
        applied automatically -- do not include -n in `command`. Naming a
        specific resource (e.g. 'describe pod api-0') is refused unless
        that resource's identifier already appeared in a real prior tool
        result this run."""
        cap = capabilities_by_binding["run_kubectl"]
        gate.guard_capability(cap)
        stripped = command.strip()
        # Same real defect this driver's sibling module found and fixed
        # forward: sregym's real kubectl-mcp tool rejects any command that
        # does not literally start with "kubectl".
        if not stripped.startswith("kubectl"):
            stripped = f"kubectl {stripped}"
        if " -n " not in stripped and "--namespace" not in stripped:
            stripped = f"{stripped} -n {namespace}"

        if grounded_facts:
            referenced = _extract_referenced_identifiers(stripped)
            ungrounded = tuple(sorted(referenced - grounded_facts))
            if ungrounded:
                raise UngroundedKubectlReferenceRefused(stripped, ungrounded)

        result = _run_coroutine_sync(environment.actuate(cap, {"command": stripped}))
        grounded_facts.update(_collect_string_leaves(result))
        return str(result)

    def observe_cluster_state() -> str:
        """Read sregym's real conductor /status endpoint (benchmark stage,
        not raw cluster state)."""
        cap = capabilities_by_binding["observe_cluster_state"]
        gate.guard_capability(cap)
        result = _run_coroutine_sync(environment.actuate(cap, {}))
        grounded_facts.update(_collect_string_leaves(result))
        return str(result)

    def _kubectl_get_json(resource: str, *, resource_namespace: str | None) -> Any:
        """Real, gated ``kubectl get <resource> -o json`` read, parsed into
        a real Python structure -- the parsing half of ``run_kubectl``
        above, ported (not imported) from
        ``gymact_diagnosis_driver.py``'s own ``_kubectl_json`` helper for
        the same "duplicate a private driver helper rather than couple the
        two driver modules together" reason ``_run_coroutine_sync``'s
        docstring already gives. Always a bare list read (``get <kind> -o
        json``, never a specific resource name) -- nothing here can trip
        the grounding guard, matching ``run_kubectl``'s own documented
        "bare list/read commands ... are never flagged" rule.
        """
        cmd = f"kubectl get {resource} -o json"
        if resource_namespace is not None:
            cmd = f"{cmd} -n {resource_namespace}"
        cap = capabilities_by_binding["run_kubectl"]
        gate.guard_capability(cap)
        result = _run_coroutine_sync(environment.actuate(cap, {"command": cmd}))
        grounded_facts.update(_collect_string_leaves(result))
        text_blocks = result.get("result_text", []) if isinstance(result, dict) else []
        raw = "".join(b.get("text", "") for b in text_blocks if isinstance(b, dict))
        if not raw:
            # Some real environments (and this repo's own test fakes) hand
            # back an already-decoded payload directly rather than a
            # wrapped result_text block -- honor that shape too rather than
            # silently discarding real data into an empty result.
            return result if isinstance(result, (dict, list)) else None
        if raw.strip().startswith("Command Rejected:"):
            raise RuntimeError(f"real kubectl command rejected by sregym: {raw.strip()}")
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None

    def run_composite_diagnosis() -> str:
        """Deterministically diagnose (and propose remediation for) the
        real, live, namespace-scoped cluster state by gathering the real
        resource kinds ``CompositePlannerEngine.run_diagnosis()`` reads --
        via the SAME real, gated ``run_kubectl`` capability actuation
        ``run_kubectl`` above uses, just automated across every resource
        kind instead of one LLM-chosen command at a time -- and composing
        all 16 real, individually Chicago-tested detectors/remediators
        (``autofde_lab_planner.engine.CompositePlannerEngine``) over that
        real state in-process. No LLM judgment, no subprocess, no mock.

        Prefer this FIRST over a long manual run_kubectl/observe_cluster_state
        investigation whenever a deterministic pass over the well-known
        Category-B/expanded fault mechanisms (probe faults, flagd config
        drift, missing/corrupted objects, Ingress/targetPort misroutes,
        CronJob mutation, scheduling deadlocks, CoreDNS faults, workload/
        rolling-update misconfigs, DNS policy overrides, hostPort
        conflicts, PVC claim mismatch/multi-attach, RBAC misconfigs,
        ResourceQuota exhaustion, LimitRange violations) could settle the
        question outright -- use run_kubectl/observe_cluster_state
        afterward only to dig into whatever this call did not cover (e.g.
        OTel trace anomalies, which need real Jaeger data this tool does
        not gather).

        Returns a JSON string with a ``diagnosis`` field (the real,
        structured ``CategoryBDiagnosis`` -- every detector's real findings
        plus the engine's own natural-language ``diagnosis_text``) and a
        ``mitigation`` field (the real, structured ``CategoryBMitigation``
        -- the real remediation commands and deployments to wait on)."""
        fetched: dict[str, Any] = {}
        for field_name, resource, namespaced in _COMPOSITE_DIAGNOSIS_RESOURCE_PLAN:
            fetched[field_name] = _kubectl_get_json(
                resource, resource_namespace=namespace if namespaced else None
            )
        if fetched.get("deployments_json") is None:
            # run_diagnosis's deployments_json is NOT Optional -- every
            # detector iterates it unconditionally. A real but empty read
            # (no deployments, or a decode failure) must still produce a
            # real, iterable, empty structure, never None.
            fetched["deployments_json"] = {"items": []}

        # configmaps_json is a real two-namespace merge: the engine passes
        # this SAME field to both the flagd-config detector (app namespace)
        # and the CoreDNS detector (kube-system's "coredns" ConfigMap) --
        # see engine.py's own `detect_coredns_faults(configmaps_json=configmaps_json,
        # namespace="kube-system")` call, which reads from the very same
        # list the flagd detector does, not a second, separate field.
        app_configmaps = _kubectl_get_json("configmaps", resource_namespace=namespace)
        kube_system_configmaps = _kubectl_get_json("configmaps", resource_namespace="kube-system")
        app_cm_items = (
            app_configmaps.get("items", []) if isinstance(app_configmaps, dict) else (app_configmaps or [])
        )
        kube_cm_items = (
            kube_system_configmaps.get("items", [])
            if isinstance(kube_system_configmaps, dict)
            else (kube_system_configmaps or [])
        )
        fetched["configmaps_json"] = {"items": [*app_cm_items, *kube_cm_items]}
        fetched["flagd_configmap_json"] = next(
            (
                cm
                for cm in app_cm_items
                if isinstance(cm, dict) and (cm.get("metadata") or {}).get("name") == "flagd-config"
            ),
            None,
        )

        engine = CompositePlannerEngine(namespace=namespace)
        diagnosis = engine.run_diagnosis(**fetched)
        mitigation = engine.run_mitigation(diagnosis)
        return json.dumps({"diagnosis": asdict(diagnosis), "mitigation": asdict(mitigation)}, default=str)

    return [run_kubectl, observe_cluster_state, run_composite_diagnosis]


# ---------------------------------------------------------------------------
# The swappable decision seam. DSPy today; a real planner call later --
# GymActReActDiagnoser and run_dspy_diagnosis depend only on this contract.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DecisionOutcome:
    """What one bounded call to a `DiagnosisDecisionBackend` actually
    produced -- shape-compatible regardless of which backend produced it.

    ``mitigation_intent``/``safe_to_actuate``/``rollback_plan`` are optional
    (default ``None``) -- populated by backends that construct a real
    mitigation candidate (:class:`SreTroubleshootingDecisionBackend`), left
    ``None`` by backends that only diagnose (:class:`DspyReActDecisionBackend`).
    A caller must still route a non-``None`` ``mitigation_intent`` through the
    real, gated capability surface to actually apply it -- this dataclass
    never itself represents an actuation, only a candidate intent."""

    root_cause: str
    confidence: float
    supporting_evidence: str
    trajectory: dict[str, Any]
    mitigation_intent: str | None = None
    safe_to_actuate: bool | None = None
    rollback_plan: str | None = None


class DiagnosisDecisionBackend(Protocol):
    """The swappable seam this module exists to name explicitly: "decide
    the next investigation step and reach a diagnosis" is implemented by
    DSPy today (:class:`DspyReActDecisionBackend`) and is meant to be
    implemented by a real O*/scikit-decide planner call later -- neither
    :class:`GymActReActDiagnoser` nor :func:`run_dspy_diagnosis` should need
    to change when that swap happens."""

    def decide(
        self,
        *,
        namespace: str,
        symptom_description: str,
        observed_resource_state: str,
        tools: list[Callable[..., str]],
        max_iters: int,
        recorder: OcelExecutionRecorder | None = None,
    ) -> DecisionOutcome: ...


class DspyReActDecisionBackend:
    """Real, ``dspy.ReAct``-backed implementation of
    :class:`DiagnosisDecisionBackend`, reasoning over
    ``k8s_signatures.DiagnoseKubernetesFault`` (the generic, reusable
    signature, not a sregym-coupled one) and the gated tool surface.

    ``program``, when given, is a real, already-compiled ``dspy.Module``
    (e.g. the output of a real ``dspy.GEPA(...).compile(...)`` run) swapped
    in for a freshly-constructed ``dspy.ReAct(...)`` -- this is how a
    GEPA-optimized program becomes reusable without touching tool-wiring or
    the grounding guard above.
    """

    def __init__(self, *, program: dspy.Module | None = None) -> None:
        self._program = program

    def decide(
        self,
        *,
        namespace: str,
        symptom_description: str,
        observed_resource_state: str,
        tools: list[Callable[..., str]],
        max_iters: int,
        recorder: OcelExecutionRecorder | None = None,
    ) -> DecisionOutcome:
        # `recorder` is accepted for Protocol conformance but not used here
        # -- this implementation runs a real dspy.ReAct loop, not a POWL
        # graph, so there is no admitted process for execute_with_ocel to
        # attach to. Real OCEL wiring belongs to SreTroubleshootingDecisionBackend.decide
        # below, the implementation that actually calls execute_powl.
        del recorder
        program = self._program or dspy.ReAct(
            DiagnoseKubernetesFault, tools=tools, max_iters=max_iters
        )
        prediction = program(
            namespace=namespace,
            symptom_description=symptom_description,
            observed_resource_state=observed_resource_state,
        )

        try:
            confidence = float(getattr(prediction, "confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))

        return DecisionOutcome(
            root_cause=str(getattr(prediction, "root_cause", "")),
            confidence=confidence,
            supporting_evidence=str(getattr(prediction, "supporting_evidence", "")),
            trajectory=dict(getattr(prediction, "trajectory", {}) or {}),
        )


class Wasm4pmEnsembleCrossCheckOutcome(StrEnum):
    """Real, named outcome of one attempted wasm4pm breed-ensemble cross-
    check inside the investigation trajectory -- never a bare string
    constant, so every trajectory entry's `outcome` field is self-describing
    and grep/filter-able by real value, matching this repo's own
    `PowlRefusal(StrEnum)` convention (`powl/refusals.py`).

    Renamed from the earlier `HearsayCrossCheckOutcome` (same three real
    members, unchanged) now that the cross-check runs a real multi-breed
    ensemble (`breed_ensemble.run_breed_ensemble`) rather than Hearsay
    alone -- the outcome vocabulary itself didn't need to change, only its
    name, to stay honest about what it now describes."""

    CHECKED = "CHECKED"
    UNAVAILABLE = "UNAVAILABLE"
    NO_EVIDENCE = "NO_EVIDENCE"


def _count_hypothesis_labels(hypothesis_portfolio: str) -> dict[str, int]:
    """Real, deterministic, LLM-free count of how many real hypothesis
    entries in ``hypothesis_portfolio`` carry each of
    ``HypothesizeSreCauses``'s own documented labels ("supported", "refuted",
    "unknown") -- the signature's own docstring requires the model to label
    each candidate cause with exactly one of these three words.

    Counted **per bullet line** (the model's own real list-item structure,
    ``-``/``*``/numbered), taking the first matching label term on that
    line, rather than a whole-text substring count -- a naive whole-text
    count is thrown off by a single hypothesis's own rationale prose
    repeating a label word (e.g. "the evidence *supports* X, though Y is
    also *supported* by..."), which would inflate that one hypothesis into
    several. This is still a real, structural read of the model's own
    committed output, never a second LLM judgment of it -- just a more
    precise one, found necessary by this session's own live trial.

    ``"none"`` (this backend's own sentinel for "no prior hypotheses yet")
    counts as zero of everything, matching the ``exhausted`` guard's own
    "supported == 0 and unknown == 0" definition for the first round.
    """
    if hypothesis_portfolio.strip().lower() in ("", "none"):
        return {"supported": 0, "refuted": 0, "unknown": 0}

    counts = {"supported": 0, "refuted": 0, "unknown": 0}
    for raw_line in hypothesis_portfolio.splitlines():
        stripped = raw_line.strip().lstrip("*").strip()
        is_bullet = raw_line.strip().startswith(("-", "*")) or (stripped[:1].isdigit() and "." in stripped[:4])
        if not is_bullet:
            continue
        lowered = stripped.lower()
        first_index: int | None = None
        first_label: str | None = None
        for label in ("supported", "refuted", "unknown"):
            idx = lowered.find(label)
            if idx != -1 and (first_index is None or idx < first_index):
                first_index, first_label = idx, label
        if first_label is not None:
            counts[first_label] += 1
    return counts


def _hypotheses_to_abductive_ibe_input(*, admitted_facts: str, hypothesis_portfolio: str) -> dict[str, Any]:
    """Real, deterministic, LLM-free translation into wasm4pm's real
    `abductive_ibe` (Thagard ECHO) wire format -- reuses
    `hearsay_cross_check._bullet_lines` directly (the same real bullet-line
    parser `hypotheses_to_breed_input` already uses for the same real
    portfolio text), rather than a second, parallel parser.

    Each admitted fact becomes a real `evidence`-keyed `Fact`; each
    hypothesis becomes a real `Candidate`. A real `Rule` links a hypothesis
    to a fact only when they share a real, significant word (>3 chars,
    case-insensitive) -- the same "real, simple, explicit" shared-word
    overlap heuristic `hearsay_cross_check.hypotheses_agree` already
    established for a structurally identical problem (approximate
    real-world-text matching between two independently-worded systems),
    reused here for consistency rather than inventing a second convention.
    A hypothesis explaining no real fact simply gets no rules -- never
    fabricated -- and `abductive_ibe`'s own real ECHO coherence network
    then genuinely never activates it.
    """
    has_facts = admitted_facts.strip().lower() not in ("", "none")
    has_hypotheses = hypothesis_portfolio.strip().lower() not in ("", "none")
    fact_lines = _bullet_lines(admitted_facts) if has_facts else []
    hyp_lines = _bullet_lines(hypothesis_portfolio) if has_hypotheses else []

    candidates = [{"id": f"hypothesis-{i}", "score": 0.0, "eliminated": False} for i in range(len(hyp_lines))]
    facts = [{"key": "evidence", "value": line} for line in fact_lines]

    rules: list[dict[str, Any]] = []
    for i, hyp in enumerate(hyp_lines):
        hyp_words = {w for w in hyp.lower().split() if len(w) > 3}
        for j, fact in enumerate(fact_lines):
            fact_words = {w for w in fact.lower().split() if len(w) > 3}
            if hyp_words & fact_words:
                rules.append(
                    {"id": f"rule-{i}-{j}", "premise": [f"hypothesis-{i}"], "conclusion": fact, "certainty": 1.0}
                )

    return {"candidates": candidates, "facts": facts, "rules": rules}


def _capability_catalog_text(tools: list[Callable[..., str]]) -> str:
    """Real, honest rendering of the tool surface a caller actually
    provided -- name + real docstring per tool, never a hardcoded/assumed
    catalog. Fed into the pipeline's ``capability_catalog`` input fields so
    `orient`/`select_probe`/`select_mitigation` reason over what is
    genuinely available this run, not a guess."""
    lines = []
    for tool in tools:
        name = getattr(tool, "__name__", "unknown_tool")
        doc = (getattr(tool, "__doc__", None) or "").strip().splitlines()[:1]
        summary = doc[0] if doc else "(no description)"
        lines.append(f"- {name}: {summary}")
    return "\n".join(lines) if lines else "(no tools available)"


class SreTroubleshootingDecisionBackend:
    """Real, :class:`SreTroubleshootingPipeline`-backed implementation of
    :class:`DiagnosisDecisionBackend`: orient -> a bounded real
    observe/normalize/hypothesize/select-probe loop -> commit a diagnosis ->
    construct/select a mitigation.

    Per the architectural law this backend enforces mechanically: every
    stage the real ``SreTroubleshootingPipeline`` runs only REASONS and
    CONSTRUCTS candidates (`probe_intent`, `mitigation_intent`) -- this
    backend calls a real, already-gated ``observe_cluster_state``-shaped
    tool from ``tools`` (if present) to execute a probe's real observation,
    but it never itself performs a DO-consequence ``environment.actuate(...)``
    call for the constructed ``mitigation_intent``. That remains the
    caller's job (``run_dspy_diagnosis``'s own, separate ``submit_mitigation``
    capability call, unmodified by this backend), exactly matching
    :class:`DspyReActDecisionBackend`'s existing contract: this backend
    returns a :class:`DecisionOutcome`, never an actuation result.

    Translating a free-text ``probe_intent`` into a specific
    ``run_kubectl`` command is a real, separate reasoning step this pass
    does not build (it would need its own signature/stage) -- named here as
    a known, honest gap rather than silently worked around with a second
    ReAct-style tool-selection loop (which this session's Part 1 work
    already established is the exact duplication to avoid). This backend
    therefore only executes probes via a zero-argument, always-safe-to-call
    tool named ``observe_cluster_state`` when one is present in ``tools``;
    other probe intents are recorded in the trajectory but not executed.

    The investigation loop is a real, admitted POWL ``ChoiceGraph``, not a
    Python ``while``/``for`` loop
    -----------------------------------------------------------------------
    Earlier in this repo's history (this exact session), the probe/hypothesis
    refinement cycle was a fixed-count ``for round_index in range(rounds)``
    loop with no early-exit condition at all -- it could not express "stop
    because causal closure was reached," only "stop because the iteration
    budget ran out." That is now a real, four-branch, guarded
    ``ChoiceGraph`` (``causal_closure`` / ``overdetermined`` /
    ``underdetermined`` / ``exhausted``), admitted via
    ``autofde_lab.powl.validate.validate_model`` (through
    ``autofde_lab.powl.guard_executor.execute``, which always re-validates before
    walking) and walked by the real, LLM-free executor. Guard predicates are
    computed deterministically from ``hypothesis_portfolio``'s own real
    supported/refuted/unknown label counts (:func:`_count_hypothesis_labels`)
    -- never a second LLM judgment. If the graph exhausts its real transition
    budget without ever reaching ``causal_closure``, this backend refuses
    (:class:`~autofde_lab.powl.refusals.PowlError`) rather than guessing a
    diagnosis from incomplete evidence.
    """

    def __init__(
        self,
        *,
        pipeline: SreTroubleshootingPipeline | None = None,
        probe_rounds: int = 2,
    ) -> None:
        self._pipeline = pipeline or SreTroubleshootingPipeline()
        self._probe_rounds = max(0, probe_rounds)

    def _build_investigation_graph(self) -> ChoiceGraph:
        """The real, admitted process shape: Start -> normalize -> hypothesize
        -> decide -> {commit_diagnosis | construct_discriminator (loops back
        to normalize) | regenerate_hypotheses (loops back to hypothesize)}
        -> ... -> End. Neither loop-back edge targets index 0 (``Start``),
        which POWL 2.0 forbids having any incoming edge -- see
        ``ChoiceGraph``'s own construction-time check."""
        return ChoiceGraph(
            children=(
                Start(),  # 0
                End(),  # 1
                PowlAtom(label="normalize", consequence="PURE"),  # 2
                PowlAtom(label="hypothesize", consequence="PURE"),  # 3
                Silent(),  # 4 -- "decide" (guard evaluation point)
                PowlAtom(label="commit_diagnosis", consequence="PURE"),  # 5
                PowlAtom(label="construct_discriminator", consequence="READ"),  # 6
                PowlAtom(label="regenerate_hypotheses", consequence="PURE"),  # 7
            ),
            edges=frozenset(
                [
                    ChoiceGraphEdge(NodeId(0), NodeId(2)),
                    ChoiceGraphEdge(NodeId(2), NodeId(3)),
                    ChoiceGraphEdge(NodeId(3), NodeId(4)),
                    ChoiceGraphEdge(NodeId(4), NodeId(5), guard=Guard("causal_closure")),
                    ChoiceGraphEdge(NodeId(4), NodeId(6), guard=Guard("overdetermined")),
                    ChoiceGraphEdge(NodeId(4), NodeId(6), guard=Guard("underdetermined")),
                    ChoiceGraphEdge(NodeId(4), NodeId(7), guard=Guard("exhausted")),
                    ChoiceGraphEdge(NodeId(5), NodeId(1)),
                    ChoiceGraphEdge(NodeId(6), NodeId(2)),  # loop back to normalize, not Start
                    ChoiceGraphEdge(NodeId(7), NodeId(3)),  # loop back to hypothesize, not Start
                ]
            ),
            start=0,
            end=1,
        )

    def _wasm4pm_ensemble_confirms_closure(self, state: dict[str, Any], trajectory: dict[str, Any]) -> bool:
        """Real, additive cross-check on the ``causal_closure`` guard, via
        a real, multi-breed ``~/wasm4pm`` ensemble
        (``breed_ensemble.run_breed_ensemble``: real concurrent Hearsay-II +
        Abductive-IBE invocation, real ``meta_reasoning``-arbitrated
        verdict) -- generalized from an earlier single-breed (Hearsay-only)
        version of this method (see ``hearsay_cross_check.py``'s own module
        docstring for why any independent, non-LLM cross-check exists at
        all here: this session and a separate, independently-developed rail
        (``agent/sregym-signature-sota``) both hit the same real failure --
        a closure guard whose only signal is the same LLM's own
        self-labeling anchors and never disagrees with itself). Two
        structurally different reasoning engines checking the same evidence
        is a strictly stronger independent signal than one.

        Called only once the DSPy-only condition (``supported == 1``) is
        already true. Compares against ``state["hypothesis_portfolio"]``'s
        real text, not a not-yet-produced ``commit_pred.root_cause`` --
        structurally, this guard fires *before* the ``commit_diagnosis``
        atom runs, so there is no committed root cause yet to compare
        against; the supported hypothesis's own portfolio text is the real,
        available signal at this point in the walk.

        Every outcome (checked-and-resolved, checked-and-unresolved,
        unavailable, insufficient-evidence) is honestly recorded in the real
        trajectory -- never silently indistinguishable from agreement.
        """
        hearsay_input = hypotheses_to_breed_input(
            admitted_facts=state["admitted_facts"], hypothesis_portfolio=state["hypothesis_portfolio"]
        )
        ibe_input = _hypotheses_to_abductive_ibe_input(
            admitted_facts=state["admitted_facts"], hypothesis_portfolio=state["hypothesis_portfolio"]
        )
        members = [
            BreedEnsembleMember(breed="hearsay", build_input=lambda hi=hearsay_input: hi),
            BreedEnsembleMember(breed="abductive_ibe", build_input=lambda ii=ibe_input: ii),
        ]
        result = run_breed_ensemble(members, resolution_threshold=0.5, timeout_s=15.0)

        if not result.member_evidence:
            # Both breeds genuinely unavailable in this environment (e.g.
            # the wasm4pm CLI isn't built) -- a real, named "not attempted
            # here" outcome, same fallback semantics the single-breed
            # version already had: DSPy's own supported==1 condition is
            # already satisfied, so closure is not withheld on the strength
            # of an environment gap.
            trajectory["stages"].append(
                {"stage": "wasm4pm_ensemble_cross_check", "outcome": Wasm4pmEnsembleCrossCheckOutcome.UNAVAILABLE}
            )
            return True

        if len(result.member_evidence) < 2 or result.arbitrated is None:
            # At most one real breed produced usable evidence -- genuinely
            # insufficient to arbitrate (arbitration needs >=2 real
            # opinions, per run_breed_ensemble's own documented law). This
            # is real, honest insufficiency, never coerced into agreement.
            trajectory["stages"].append(
                {
                    "stage": "wasm4pm_ensemble_cross_check",
                    "outcome": Wasm4pmEnsembleCrossCheckOutcome.NO_EVIDENCE,
                    "detail": f"only {len(result.member_evidence)} member(s) produced usable evidence; cannot arbitrate",
                }
            )
            return False

        trajectory["stages"].append(
            {
                "stage": "wasm4pm_ensemble_cross_check",
                "outcome": Wasm4pmEnsembleCrossCheckOutcome.CHECKED,
                "resolved": result.resolved,
                "resolution_weight": result.resolution_weight,
                "arbitrated_selected": result.arbitrated.selected,
            }
        )
        return result.resolved

    def decide(
        self,
        *,
        namespace: str,
        symptom_description: str,
        observed_resource_state: str,
        tools: list[Callable[..., str]],
        max_iters: int,
        recorder: OcelExecutionRecorder | None = None,
    ) -> DecisionOutcome:
        capability_catalog = _capability_catalog_text(tools)
        observe_tool = next((t for t in tools if getattr(t, "__name__", "") == "observe_cluster_state"), None)

        trajectory: dict[str, Any] = {"stages": []}

        orient_pred = self._pipeline.orient(
            episode_goal=symptom_description,
            system_context=f"namespace={namespace}; {observed_resource_state}",
            capability_catalog=capability_catalog,
        )
        trajectory["stages"].append({"stage": "orient", "system_boundary": orient_pred.system_boundary})

        state: dict[str, Any] = {
            "raw_evidence": observed_resource_state,
            "admitted_facts": "none",
            "hypothesis_portfolio": "none",
            "commit_pred": None,
        }

        def guard_evaluator(predicate_name: str, _predicate_args: Mapping[str, Any]) -> bool:
            counts = _count_hypothesis_labels(state["hypothesis_portfolio"])
            supported, unknown = counts["supported"], counts["unknown"]
            # causal_closure does NOT require unknown == 0. A real, honest
            # model can genuinely support exactly one hypothesis while
            # leaving OTHER hypotheses labeled "unknown" rather than
            # "refuted" -- it never actively disproved them, and refusing to
            # commit until every alternative is refuted is not how real SRE
            # diagnosis works (nor how HypothesizeSreCauses's own signature
            # is written: "unknown" is explicitly not "refuted"). This
            # session's own live trial confirmed the earlier, stricter
            # `unknown == 0` requirement never closes against a real model's
            # honestly-cautious hedging -- residual unknowns are exactly what
            # `commit_diagnosis`'s own `confidence` output field exists to
            # express, not a reason to withhold commitment indefinitely.
            if predicate_name == "causal_closure":
                if supported != 1:
                    return False
                return self._wasm4pm_ensemble_confirms_closure(state, trajectory)
            if predicate_name == "overdetermined":
                return supported > 1
            if predicate_name == "underdetermined":
                return supported == 0 and unknown > 0
            if predicate_name == "exhausted":
                return supported == 0 and unknown == 0
            return False

        def atom_invoker(atom: PowlAtom) -> Any:
            if atom.label == "normalize":
                pred = self._pipeline.normalize(
                    raw_evidence=state["raw_evidence"], prior_facts=state["admitted_facts"]
                )
                state["admitted_facts"] = pred.admitted_facts
                trajectory["stages"].append({"stage": "normalize", "admitted_facts": pred.admitted_facts})
                return pred
            if atom.label == "hypothesize":
                pred = self._pipeline.hypothesize(
                    admitted_facts=state["admitted_facts"], prior_hypotheses=state["hypothesis_portfolio"]
                )
                state["hypothesis_portfolio"] = pred.hypothesis_portfolio
                trajectory["stages"].append(
                    {"stage": "hypothesize", "hypothesis_portfolio": pred.hypothesis_portfolio}
                )
                return pred
            if atom.label == "commit_diagnosis":
                pred = self._pipeline.commit_diagnosis(
                    admitted_facts=state["admitted_facts"], hypothesis_portfolio=state["hypothesis_portfolio"]
                )
                state["commit_pred"] = pred
                trajectory["stages"].append({"stage": "commit_diagnosis", "root_cause": pred.root_cause})
                return pred
            if atom.label == "construct_discriminator":
                probe_pred = self._pipeline.select_probe(
                    admitted_facts=state["admitted_facts"],
                    hypothesis_portfolio=state["hypothesis_portfolio"],
                    capability_catalog=capability_catalog,
                )
                executed = False
                if observe_tool is not None:
                    state["raw_evidence"] = str(observe_tool())
                    executed = True
                trajectory["stages"].append(
                    {"stage": "probe", "probe_intent": probe_pred.probe_intent, "executed": executed}
                )
                return probe_pred
            if atom.label == "regenerate_hypotheses":
                trajectory["stages"].append({"stage": "regenerate_hypotheses"})
                return None
            raise AssertionError(f"unreachable: unknown atom label {atom.label!r}")  # pragma: no cover

        graph = self._build_investigation_graph()
        # The straight-line happy path alone (Start->normalize->hypothesize
        # ->decide->commit_diagnosis->End) is 5 real ChoiceGraphEdge
        # traversals -- every edge counts against the budget, not just
        # loop-back ones. Each additional probe/regenerate round adds 4 more
        # (decide->branch, branch->loop-back-target, then re-traversing
        # normalize->hypothesize->decide again). This is the honest minimum
        # for `self._probe_rounds` rounds of real investigation to even be
        # reachable; `max_iters` further caps it when the caller wants a
        # tighter real bound than `probe_rounds` alone would allow.
        max_choice_transitions = 5 + max(0, self._probe_rounds) * 4
        max_choice_transitions = min(max_choice_transitions, 5 + max(0, max_iters) * 4)
        if recorder is not None:
            execute_with_ocel(
                graph,
                guard_evaluator=guard_evaluator,
                atom_invoker=atom_invoker,
                max_choice_transitions=max_choice_transitions,
                recorder=recorder,
            )
        else:
            execute_powl(
                graph,
                guard_evaluator=guard_evaluator,
                atom_invoker=atom_invoker,
                max_choice_transitions=max_choice_transitions,
            )

        commit_pred = state["commit_pred"]
        assert commit_pred is not None, "unreachable: End only reached via commit_diagnosis"

        try:
            confidence_pct = float(getattr(commit_pred, "confidence", 0))
        except (TypeError, ValueError):
            confidence_pct = 0.0
        confidence = max(0.0, min(1.0, confidence_pct / 100.0))

        mitigation_pred = self._pipeline.select_mitigation(
            root_cause=commit_pred.root_cause,
            relevant_resource_spec=state["raw_evidence"],
            capability_catalog=capability_catalog,
        )
        trajectory["stages"].append(
            {"stage": "select_mitigation", "safe_to_actuate": mitigation_pred.safe_to_actuate}
        )

        return DecisionOutcome(
            root_cause=commit_pred.root_cause,
            confidence=confidence,
            supporting_evidence=commit_pred.evidence_refs,
            trajectory=trajectory,
            mitigation_intent=mitigation_pred.mitigation_intent,
            safe_to_actuate=bool(mitigation_pred.safe_to_actuate),
            rollback_plan=mitigation_pred.rollback_plan,
        )


class GymActReActDiagnoser(dspy.Module):
    """One real diagnosis run over the gated sregym tool surface, delegated
    to a swappable :class:`DiagnosisDecisionBackend` (DSPy today).

    Kept intentionally thin: this class owns no environment-materialization
    or teardown logic (that stays in :func:`run_dspy_diagnosis`, matching
    ``gymact_diagnosis_driver.py``'s own separation of "build real
    collaborators" from "reason over them"), and owns no decision logic of
    its own -- it only builds the gated tools and the symptom-description
    text, then hands both to whichever real backend it was given.
    """

    def __init__(
        self,
        *,
        environment: Any,
        gate: CapabilityGate,
        capabilities: Any,
        namespace: str,
        max_iters: int = 6,
        decision_backend: DiagnosisDecisionBackend | None = None,
    ) -> None:
        super().__init__()
        self._tools = build_gated_react_tools(environment, gate, capabilities, namespace=namespace)
        self._max_iters = max_iters
        self._decision_backend: DiagnosisDecisionBackend = decision_backend or DspyReActDecisionBackend()

    def forward(self, problem_id: str, namespace: str) -> DecisionOutcome:
        symptom_description = (
            f"Diagnose the live Kubernetes cluster fault for sregym benchmark "
            f"problem {problem_id!r}. Use the provided tools to inspect real "
            "live cluster state before concluding -- never guess a root cause "
            "the tools have not evidenced."
        )
        return self._decision_backend.decide(
            namespace=namespace,
            symptom_description=symptom_description,
            observed_resource_state="not yet observed -- use the provided tools to inspect real state",
            tools=self._tools,
            max_iters=self._max_iters,
        )


@dataclass(frozen=True, slots=True)
class DiagnosisResult:
    """Real, typed result of one basic decision-backend-mediated diagnosis
    run."""

    problem_id: str
    namespace: str
    diagnosis: str
    confidence: float
    trajectory: dict[str, Any]
    submit_diagnosis_response: Any
    mitigation_attempted: bool
    submit_mitigation_response: Any | None


async def run_dspy_diagnosis(
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
    max_iters: int = 6,
    attempt_mitigation: bool = False,
    lm: Any | None = None,
    decision_backend: DiagnosisDecisionBackend | None = None,
    _environment_factory: Callable[[], Any] | None = None,
    _capabilities: Any = None,
) -> DiagnosisResult:
    """Materialize a real ``SregymEnvironment``, run one real diagnosis via
    a swappable :class:`DiagnosisDecisionBackend` (DSPy by default) over the
    gated tool surface, and submit a real ``submit_diagnosis`` capability
    call.

    ``lm``, when given, is used as-is (a real, already-constructed
    ``dspy.LM``) -- useful for tests/callers that want to reuse one LM
    instance across calls. When omitted, a real ``dspy.LM(judge_model_id)``
    is constructed and used via ``dspy.context(lm=...)`` (DSPy's own
    thread/call-scoped LM override) so this function never mutates any
    caller's global ``dspy.settings`` -- reusing ``judge_model_id``/
    ``judge_api_base`` unmodified from ``gymact_diagnosis_driver.py``'s
    identical defaults, per this task's instruction to match the existing
    driver's confirmed-working Groq routing (litellm resolves the
    ``"groq/"``-prefixed model string against the real ``GROQ_API_KEY``
    environment variable; ``judge_api_base`` is accepted for parity with
    the existing driver's signature but litellm's groq provider does not
    require an explicit ``api_base`` override for the default
    ``api.groq.com`` endpoint). ``lm`` is only meaningful when
    ``decision_backend`` is DSPy-backed (the default); a future
    planner-backed decision backend would ignore it.

    ``decision_backend``, when given, replaces the default
    :class:`DspyReActDecisionBackend` -- the seam a future
    planner-backed implementation swaps through.

    ``_environment_factory``/``_capabilities`` are test-only injection
    points (leading underscore), same contract as
    ``gymact_diagnosis_driver.run_gymact_mediated_diagnosis``: a test
    supplies a real, hand-written fake ``SregymEnvironment``-shaped object
    instead of materializing a real cluster.
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

    resolved_lm = lm if lm is not None else dspy.LM(judge_model_id, max_tokens=16000)

    try:
        # Wait for the real conductor's own stage machine to leave "setup"
        # before diagnosing -- otherwise the ReAct loop observes an
        # empty/not-yet-deployed namespace, correctly (honestly) reports
        # that nothing exists yet, and the real conductor then rejects the
        # submission with "Cannot submit at stage: 'setup'". A live trial
        # this session hit exactly this race (a real 22.8s round trip that
        # finished before the app finished deploying). `env.verify(...)` is
        # the same real, bounded stage-poll `gymact_diagnosis_driver.py`'s
        # own `_wait_for_deploy()` already trusts for this exact purpose --
        # reused here rather than inventing a second, parallel readiness
        # mechanism. Honest best-effort: if the conductor never leaves
        # "setup" within `verify_timeout_seconds`, this proceeds anyway (the
        # ReAct loop, and then the real conductor's own real rejection if the
        # deploy genuinely never completed, still surface the true state
        # honestly -- never silently skipped).
        await env.verify({"stage": "diagnosis"})

        diagnoser = GymActReActDiagnoser(
            environment=env,
            gate=gate,
            capabilities=capabilities,
            namespace=namespace,
            max_iters=max_iters,
            decision_backend=decision_backend,
        )
        with dspy.context(lm=resolved_lm):
            outcome = diagnoser(problem_id=problem_id, namespace=namespace)

        diagnosis_text = outcome.root_cause
        confidence = outcome.confidence
        trajectory = outcome.trajectory

        submit_cap = _capability(capabilities, "submit_diagnosis")
        gate.guard_capability(submit_cap)
        submit_response = await env.actuate(
            submit_cap, {"diagnosis": diagnosis_text, "confidence": confidence}
        )

        mitigation_response: Any | None = None
        if attempt_mitigation:
            from autofde_lab.reasoning.gymact_mitigation_actuation import execute_and_submit_mitigation

            # A fresh, real observe_cluster_state read -- the diagnosis
            # ReAct loop's own observations live inside its internal
            # dspy.ReAct trajectory dict (per-step, not one clean string),
            # so this re-observes real, current state rather than guessing
            # at a trajectory key that doesn't hold it.
            observe_cap = _capability(capabilities, "observe_cluster_state")
            gate.guard_capability(observe_cap)
            observed_state = await env.actuate(observe_cap, {})

            # Real mitigation actuation (closes the gap named in this
            # module's own earlier docstring: every prior call site here
            # submitted a literal "not_attempted" placeholder). Uses the
            # real, committed diagnosis text as root_cause.
            mitigation_result = await execute_and_submit_mitigation(
                env,
                gate,
                capabilities,
                root_cause=diagnosis_text,
                relevant_resource_spec=str(observed_state),
                capability_catalog="\n".join(f"- {cap.binding}" for cap in capabilities),
                namespace=namespace,
            )
            mitigation_response = mitigation_result.submit_mitigation_response
            trajectory = dict(trajectory) if isinstance(trajectory, dict) else {"trajectory": trajectory}
            trajectory["mitigation_execution"] = {
                "attempted": mitigation_result.attempted,
                "reason": mitigation_result.reason,
                "executed_commands": mitigation_result.executed_commands,
            }

        return DiagnosisResult(
            problem_id=problem_id,
            namespace=namespace,
            diagnosis=diagnosis_text,
            confidence=confidence,
            trajectory=trajectory,
            submit_diagnosis_response=submit_response,
            mitigation_attempted=attempt_mitigation,
            submit_mitigation_response=mitigation_response,
        )
    finally:
        try:
            await env.teardown()
        except Exception as teardown_exc:  # noqa: BLE001 -- teardown failure must not mask a real result
            import logging

            logging.getLogger(__name__).warning(
                "gymact_dspy_react: env.teardown() raised %r", teardown_exc
            )
