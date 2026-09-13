# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Offline GEPA optimization for :class:`DspyReActDecisionBackend`
(`gymact_dspy_react.py`) -- the swappable, DSPy-backed implementation of the
`DiagnosisDecisionBackend` seam that is meant to be replaced by a real
O*/scikit-decide planner call later.

Why offline, and why this is NOT a SOTA claim
------------------------------------------------
A real GEPA pass against live sregym clusters is genuinely expensive (each
reflection round is one full cluster episode, 90-900s, per
`.claude/plans/.../wombat.md`'s Part 2) and this module does not attempt
that here. Instead it optimizes `DiagnoseKubernetesFault`'s prompt against a
real, offline, fault-shaped trainset (see below) -- an honest curriculum
step, not a `gymact.sota.sota_claim`-eligible result. Per
`.claude/rules/standing-law.md`, a claim about live diagnostic performance
against real sregym requires real receipt/verifier/replay bindings this
module never produces; nothing here should be cited as SOTA evidence. What
it produces is a better-initialized prompt for the same swappable seam a
later live-episode GEPA pass (or a future planner backend) can start from.

Reference-only vendored reading, never import or actuation
------------------------------------------------------------
Per `.claude/rules/gym-actuation-boundary.md`, `vendor/gyms/sregym/` is read
for reference only. The four fault templates below were read directly from
four real sregym `Problem` subclasses (component, namespace, and the
natural-language `description` each problem's own
`build_structured_root_cause(...)` call constructs, the exact text sregym's
own `LLMAsAJudgeOracle` grades a real diagnosis against) -- cited per-template
below, matching `PROBLEM_ID_NAMESPACE`'s own citation convention in
`gymact_diagnosis_driver.py`. This module never imports anything under
`vendor/gyms/` at runtime; the templates are hand-transcribed constants.

Faker substitution -- the anti-memorization mechanism
---------------------------------------------------------
A GEPA reflection LM (or a downstream judge) may have seen sregym's real,
public problem descriptions during its own pretraining -- optimizing
directly against "the `geo` deployment has a CPU limit set too low" risks
rewarding memorized recall of that specific, public sentence rather than the
general causal PATTERN (a low CPU limit throttling a container, invisible to
`kubectl top`, visible in cgroup `nr_throttled` stats). `build_trainset()`
uses a seeded `faker.Faker` instance to substitute a fresh, fake service
name, namespace, and app name into every template on every call, so the
concrete strings a compiled program is scored against are never the real
vendored ones -- a program that only pattern-matches "geo"/"hotel-reservation"
literally cannot get credit; it must generalize the fault SHAPE to whatever
fake name appears.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import dspy
from faker import Faker

from autofde_lab.reasoning.k8s_signatures import DiagnoseKubernetesFault
from autofde_lab.reasoning.sre_troubleshooting_pipeline import SreTroubleshootingPipeline

__all__ = [
    "FaultTemplate",
    "FAULT_TEMPLATES",
    "SreTroubleshootingReasoningOnly",
    "build_trainset",
    "metric_with_feedback",
    "run_gepa_optimization",
    "run_gepa_optimization_for_troubleshooting_pipeline",
]


@dataclass(frozen=True, slots=True)
class FaultTemplate:
    """One real sregym fault shape, transcribed from a real vendored
    `Problem` subclass's own `root_cause` description -- see each
    instance's `source` for the exact cited file."""

    fault_id: str
    component_template: str
    description_template: str
    diagnostic_keywords: tuple[str, ...]
    """Real, fault-specific vocabulary from the template's own description
    that a correct diagnosis must mention regardless of which faked names
    were substituted -- this is what `metric_with_feedback` scores against,
    never the faked names themselves."""
    source: str


FAULT_TEMPLATES: tuple[FaultTemplate, ...] = (
    FaultTemplate(
        fault_id="cpu_throttling",
        component_template="deployment/{service}",
        description_template=(
            "The `{service}` deployment has a CPU limit set too low for its normal operation. "
            "The Linux CFS scheduler throttles the container whenever it exceeds its quota within a "
            "100ms scheduling window, delaying bursts and causing intermittent tail latency on request "
            "paths that depend on this service. Crucially, `kubectl top pods` shows CPU usage well below "
            "the limit -- the throttling is silent at the kubectl level but visible in the container's "
            "cgroup stats (`cpu.stat`: high `nr_throttled`) and in the Prometheus `ContainerCPUThrottling` "
            "alert. The fix is to raise the CPU limit to a value that accommodates burst traffic, or "
            "remove it entirely."
        ),
        diagnostic_keywords=("cpu limit", "throttl", "cgroup", "nr_throttled", "cfs"),
        source="vendor/gyms/sregym/sregym/conductor/problems/cpu_throttling.py",
    ),
    FaultTemplate(
        fault_id="missing_configmap",
        component_template="{service}",
        description_template=(
            "A required ConfigMap for deployment `{service}` has been deleted, so pods lose required "
            "runtime configuration during startup and reload. Affected pods fail to initialize correctly "
            "or run with invalid defaults, leading to NotReady/CrashLoop behavior and unstable service "
            "operation. Users observe request failures and degraded functionality for features backed by "
            "this component."
        ),
        diagnostic_keywords=("configmap", "deleted", "crashloop", "notready"),
        source="vendor/gyms/sregym/sregym/conductor/problems/missing_configmap.py",
    ),
    FaultTemplate(
        fault_id="service_dns_resolution_failure",
        component_template="{service}",
        description_template=(
            "CoreDNS is configured with an NXDOMAIN template for `{service}.{namespace}.svc.cluster.local`, "
            "so in-cluster lookups for this service name fail at DNS resolution time. Dependent services "
            "cannot resolve or connect to the target even though pods may be healthy and listening. Users "
            "observe request timeouts and cascading failures on flows that depend on this service endpoint."
        ),
        diagnostic_keywords=("coredns", "dns", "nxdomain", "resolution", "resolve"),
        source="vendor/gyms/sregym/sregym/conductor/problems/service_dns_resolution_failure.py",
    ),
    FaultTemplate(
        fault_id="incorrect_image",
        component_template="deployment/{service}",
        description_template=(
            "The {service} deployment is configured to pull a non-existent image tag "
            "(app-image:latest), so pods fail with image pull errors and the {service} path becomes "
            "unavailable. Symptoms typically include ImagePullBackOff events and upstream calls timing "
            "out or failing."
        ),
        diagnostic_keywords=("image", "imagepullbackoff", "pull", "non-existent"),
        source="vendor/gyms/sregym/sregym/conductor/problems/incorrect_image.py",
    ),
)


def _fake_names(faker: Faker) -> dict[str, str]:
    """Real, deterministic (given a seeded `faker.Faker`) substitution set --
    never a real sregym service/namespace/app name."""
    return {
        "service": faker.unique.word() + "-svc",
        "namespace": faker.unique.word() + "-ns",
        "app": faker.unique.company().lower().replace(" ", "-").replace(",", ""),
    }


def build_trainset(*, seed: int = 0, n_per_template: int = 3) -> list[dspy.Example]:
    """Build a real, deterministic (seeded) offline trainset: every
    `FaultTemplate` instantiated `n_per_template` times with fresh faked
    names, formatted as real `dspy.Example`s matching
    `DiagnoseKubernetesFault`'s input/output contract.

    `observed_resource_state` is deliberately the templated description
    itself, framed as though tools had already gathered it -- this trains
    the "diagnose from given evidence" reasoning
    `DspyReActDecisionBackend`'s final answer synthesis does, not the
    tool-selection loop (which requires a live cluster this module does not
    have; see the module docstring).
    """
    faker = Faker()
    faker.seed_instance(seed)
    examples: list[dspy.Example] = []
    for template in FAULT_TEMPLATES:
        for _ in range(n_per_template):
            names = _fake_names(faker)
            component = template.component_template.format(**names)
            description = template.description_template.format(**names)
            example = dspy.Example(
                namespace=names["namespace"],
                symptom_description=(
                    f"Intermittent failures reported for requests touching {component} "
                    f"in namespace {names['namespace']}."
                ),
                observed_resource_state=description,
                root_cause=description,
                fault_id=template.fault_id,
                diagnostic_keywords=template.diagnostic_keywords,
                faked_component=component,
            ).with_inputs("namespace", "symptom_description", "observed_resource_state")
            examples.append(example)
    return examples


def _keyword_overlap_score(text: str, keywords: tuple[str, ...]) -> float:
    lowered = text.lower()
    hits = sum(1 for kw in keywords if kw in lowered)
    return hits / len(keywords) if keywords else 0.0


def metric_with_feedback(
    example: dspy.Example,
    prediction: dspy.Prediction,
    trace: object | None = None,
    pred_name: str | None = None,
    pred_trace: object | None = None,
) -> dspy.Prediction:
    """Real, deterministic metric: score a predicted `root_cause` against
    the example's own real diagnostic keywords (never literal-string
    equality against the templated description, and never the faked
    component name -- scoring on the faked name would reward copying it
    back rather than diagnosing the fault). Returns a real
    `dspy.Prediction(score=..., feedback=...)`, the shape `dspy.GEPA`'s
    reflection step consumes.

    `pred_name`/`pred_trace` are accepted (unused) because the installed
    `dspy.GEPA` requires a metric that binds all five positional arguments
    `(gold, pred, trace, pred_name, pred_trace)` -- confirmed against a real
    `inspect.signature(metric).bind(...)` check `dspy.GEPA.__init__` itself
    performs; this repo's own metric had never actually been exercised
    against a real GEPA compile until a live trial this session ran it for
    the first time (previously always named-skip on missing
    `GROQ_API_KEY`), which is what surfaced this real, pre-existing
    signature mismatch.
    """
    predicted_root_cause = str(getattr(prediction, "root_cause", ""))
    keywords: tuple[str, ...] = example.diagnostic_keywords
    score = _keyword_overlap_score(predicted_root_cause, keywords)

    missing = tuple(kw for kw in keywords if kw not in predicted_root_cause.lower())
    if missing:
        feedback = (
            f"Diagnosis for fault_id={example.fault_id!r} scored {score:.2f}: "
            f"missing the real diagnostic signature terms {missing!r}. "
            "A correct diagnosis for this fault shape must name the underlying "
            "mechanism (not just symptoms), grounded in the given observed_resource_state."
        )
    else:
        feedback = (
            f"Diagnosis for fault_id={example.fault_id!r} scored {score:.2f}: "
            "all real diagnostic signature terms present."
        )

    return dspy.Prediction(score=score, feedback=feedback)


def run_gepa_optimization(
    *,
    seed: int = 0,
    n_per_template: int = 3,
    reflection_lm: dspy.LM,
    task_lm: dspy.LM | None = None,
    auto: Literal["light", "medium", "heavy"] = "light",
    num_threads: int = 4,
) -> dspy.Module:
    """Compile a real `dspy.ReAct(DiagnoseKubernetesFault, tools=[])`
    program (no live tools -- see module docstring) via a real
    `dspy.GEPA` pass over the offline, faker-substituted trainset.

    Returns the real compiled `dspy.Module` -- pass it as
    `DspyReActDecisionBackend(program=...)` to use it. This function makes
    real LM calls (both `task_lm` and `reflection_lm`); callers are
    responsible for supplying real, already-authenticated `dspy.LM`
    instances (no default is constructed here, so this module never
    silently reaches for network credentials).
    """
    examples = build_trainset(seed=seed, n_per_template=n_per_template)
    split = max(1, len(examples) * 2 // 3)
    trainset, valset = examples[:split], examples[split:] or examples[:1]

    program = dspy.ReAct(DiagnoseKubernetesFault, tools=[], max_iters=1)
    if task_lm is not None:
        program.set_lm(task_lm)

    optimizer = dspy.GEPA(
        metric=metric_with_feedback,
        auto=auto,
        num_threads=num_threads,
        reflection_lm=reflection_lm,
        track_stats=True,
    )
    return optimizer.compile(program, trainset=trainset, valset=valset)


class SreTroubleshootingReasoningOnly(dspy.Module):
    """Real `dspy.Module` wrapping `SreTroubleshootingPipeline`'s
    orient -> normalize -> hypothesize -> commit_diagnosis chain as ONE
    compilable program, for offline GEPA optimization only.

    Deliberately excludes `select_probe`/`select_mitigation` -- per this
    session's established scoping rule ("optimize the reasoning stages
    jointly; do not include the actuation stage inside the compiled
    program"), those two stages either require a real environment
    (`select_probe`'s real observation) or produce a candidate that gets
    real-actuation-gated downstream (`select_mitigation`), neither of which
    this offline trainset can honestly exercise. `forward()`'s single
    real evidence input stands in for what a real probe loop would have
    gathered -- an honest simplification for offline optimization, not a
    claim that probing/discrimination themselves are optimized here.
    """

    def __init__(self, *, pipeline: SreTroubleshootingPipeline | None = None) -> None:
        super().__init__()
        self._pipeline = pipeline or SreTroubleshootingPipeline()

    def forward(
        self, *, namespace: str, symptom_description: str, observed_resource_state: str
    ) -> dspy.Prediction:
        capability_catalog = "- run_kubectl: read-only kubectl commands\n- observe_cluster_state: benchmark status"
        self._pipeline.orient(
            episode_goal=symptom_description,
            system_context=f"namespace={namespace}",
            capability_catalog=capability_catalog,
        )
        normalize_pred = self._pipeline.normalize(raw_evidence=observed_resource_state, prior_facts="none")
        hypothesize_pred = self._pipeline.hypothesize(
            admitted_facts=normalize_pred.admitted_facts, prior_hypotheses="none"
        )
        commit_pred = self._pipeline.commit_diagnosis(
            admitted_facts=normalize_pred.admitted_facts,
            hypothesis_portfolio=hypothesize_pred.hypothesis_portfolio,
        )
        return dspy.Prediction(
            root_cause=commit_pred.root_cause,
            confidence=commit_pred.confidence,
            supporting_evidence=commit_pred.evidence_refs,
        )


def run_gepa_optimization_for_troubleshooting_pipeline(
    *,
    seed: int = 0,
    n_per_template: int = 3,
    reflection_lm: dspy.LM,
    task_lm: dspy.LM | None = None,
    auto: Literal["light", "medium", "heavy"] = "light",
    num_threads: int = 4,
) -> dspy.Module:
    """Same offline trainset/metric as :func:`run_gepa_optimization`, but
    compiles :class:`SreTroubleshootingReasoningOnly` (the multi-stage
    orient/normalize/hypothesize/commit_diagnosis chain) instead of a
    single-signature `dspy.ReAct`. `metric_with_feedback` is reused as-is --
    it only inspects `prediction.root_cause` and the example's own
    `diagnostic_keywords`/`fault_id`, so it is agnostic to which real
    program produced the prediction.
    """
    examples = build_trainset(seed=seed, n_per_template=n_per_template)
    split = max(1, len(examples) * 2 // 3)
    trainset, valset = examples[:split], examples[split:] or examples[:1]

    program = SreTroubleshootingReasoningOnly()
    if task_lm is not None:
        program.set_lm(task_lm)

    optimizer = dspy.GEPA(
        metric=metric_with_feedback,
        auto=auto,
        num_threads=num_threads,
        reflection_lm=reflection_lm,
        track_stats=True,
    )
    return optimizer.compile(program, trainset=trainset, valset=valset)
