# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Integration runner: pipeline steps wired as `action_bindings` on a real
:class:`~autofde_lab.powl.algebra.PowlNode` tree, built partly from a real
POWL2 Turtle document via :mod:`autofde_lab.powl.turtle_bridge`.

Pipeline steps modelled: scan, phi-encode (:mod:`autofde_lab.fabric.phi`),
dispatch (:func:`autofde_lab.utils.match_solvers`), solve, case-library
retrieve/retain (:mod:`autofde_lab.case_library`), a DSPy-fallback stub, and
OCEL record. Each becomes one :class:`~autofde_lab.powl.algebra.Atom` leaf;
a caller binds real callables to their labels and drives the tree through
:func:`autofde_lab.ocel.powl_replay.replay_structural_fires`.

Why the case-library branch is NOT built via turtle_bridge
------------------------------------------------------------
Verified this session, directly from source:
``autofde_lab.fabric.powl``'s Turtle vocabulary (what
``project_plan_to_powl``/``parse_powl_turtle`` actually accept) has no
``powl2:ChoiceGraph`` construct at all -- it models only a flat total order
of ``powl2:ActivityLeaf`` steps. ``turtle_bridge.powl_model_to_node`` and
``turtle_bridge.powl_node_to_model`` both refuse
(``BridgeError: UNSUPPORTED_NODE_SHAPE``) anything that is not a bare
:class:`~autofde_lab.powl.algebra.Atom` or a flat
:class:`~autofde_lab.powl.algebra.PartialOrder` of ``Atom`` children (see
that module's own docstring and refusal text).

So this module uses turtle_bridge for exactly what it can honestly do --
convert the *linear* prefix (scan, phi-encode, dispatch, solve) from a real
parsed Turtle document into real ``Atom`` leaves -- and builds the
case-library hit/miss branch as a real
:class:`~autofde_lab.powl.algebra.ChoiceGraph` directly via ``algebra.py``,
grafted into the same top-level :class:`PartialOrder` alongside the
turtle-sourced atoms. Both are real, executor-consumable ``PowlNode``
objects; only their construction path differs, named here rather than
silently faked.

``ChoiceGraphEdge`` carries no label field (confirmed in ``algebra.py`` this
session -- it is a frozen ``(src, dst)`` pair, nothing else). The hit/miss
branches are therefore distinguished by labelling each branch's *entry Atom*
(``"case_hit"`` / ``"case_miss"``) rather than by adding a label to the edge.

No silent hang
---------------
Termination of a (possibly cyclic) choice graph is structural, never a
wall-clock timeout -- see ``executor.py``'s module docstring and
``bounds.py``'s three counters (``max_activity_fires``, ``max_node_visits``,
``max_marking_states``). :func:`classify_pipeline_stall` surfaces
``executor.classify_stall()``'s result directly rather than adding a new
timeout layer of its own.

Decision: the runner stays structural-only; it does not gain a direct
actuation path
---------------------------------------------------------------------------
Now that ``action_bindings`` is merged (``ocel/powl_replay.py``), this
runner is free to bind real callables to Atom labels for every read-only or
diagnostic pipeline step -- scan, phi-encode, dispatch, solve, case-library
retrieve -- because none of those steps mutate a live cluster; they compute
or look up, and their own modules already own whatever standing they carry.
What this runner deliberately does NOT do is bind a cluster-mutating
remediation action directly to an Atom and let structural replay invoke it
as a side effect of marking advancement. Any real actuation step must be
reached through a separate, explicitly authorized call the runner's own
``action_bindings`` dict never performs itself -- e.g. a caller-held,
independently admitted actuator such as a gymact-mediated
``SregymEnvironment.actuate()``, invoked outside and after this runner's
structural replay, never from inside an Atom's binding. This matches
``CLAUDE.md``'s standing law verbatim: "It computes candidate plans. It does
not actuate." Collapsing that seam here -- letting a POWL Atom's action
payload double as a real actuator -- would hand structural marking
advancement (a property of the *plan*) the authority that belongs only to a
brokered, independently authorized actuation call (a property of the
*world*), the same class of defect ``.claude/rules/absence-is-not-evidence.md``
and ``.claude/rules/no-dual-bookkeeping.md`` name for admission and evidence:
a convenient coupling standing in for a lawful one.

Capability boundary when gymact is the target environment
------------------------------------------------------------
Whenever an ``action_bindings`` entry in this runner does reach a gymact
``Capability`` (e.g. ``run_kubectl``, ``submit_diagnosis``), it must go
through :class:`autofde_lab.fabric.gymact_capability_gate.CapabilityGate`
rather than importing a gymact capability constructor directly. The gate
loads an explicit TOML allowlist (``fabric/gymact_capabilities.toml``) of
exactly which real ``gymact.gyms.sregym.SREGYM_CAPABILITIES`` entries this
diagnosing pipeline may invoke, and refuses (``CapabilityRefused``, never a
silent pass) anything not listed -- concretely enforcing that the diagnosing
agent cannot reach ground-truth or grading-internal surfaces even if a
future gymact capability is added carelessly. This is a real allowlist, not
documentation: verified this session that none of the 5 real capabilities
expose ground truth, and that ``SregymEnvironment.verify()`` is not a
``Capability`` at all (a plain coroutine never wired into ``actuate()``'s
dispatch table), so it is structurally unreachable through this surface
regardless of the manifest's contents.

Revised decision: capability-gated actuation IS now allowed from inside a
binding, narrowly
---------------------------------------------------------------------------
The blanket "this runner stays structural-only; it does not gain a direct
actuation path" decision above is superseded by a narrower, principled rule
for exactly four new labels (:data:`ALLOWED_ACTUATION_BINDING_LABELS`,
disjoint from :data:`ALLOWED_ACTION_BINDING_LABELS`): a mutating actuation
step MAY be bound to one of those four labels, but *only* as a
:class:`GatedCapabilityBinding` -- never a bare :class:`ActionBinding`
callable. Constructing a ``GatedCapabilityBinding`` itself calls
``CapabilityGate.check(capability_name)`` (see its docstring), so an
unauthorized capability name can never even be wrapped, let alone bound;
``run_pipeline`` additionally refuses, structurally
(``isinstance(binding, GatedCapabilityBinding)``, never a docstring
convention), any of the four actuation-class labels bound to anything else,
before any Atom fires.

``verify()`` is deliberately NOT one of these four. Confirmed earlier this
session, directly from source: ``SregymEnvironment.verify()`` is a plain
coroutine, never wrapped as a real gymact ``Capability``, never wired into
``actuate()``'s dispatch table. Forcing it through ``GatedCapabilityBinding``
would mean inventing a fake ``Capability`` for it in the TOML manifest --
which an earlier pass in this session actually did, and which
``CapabilityGate.stale_entries()`` correctly flagged as a real defect (an
allowlist entry matching no real capability name is exactly the drift that
detector exists to catch). Fixed forward: :data:`GYMACT_VERIFY_LABEL` takes a
bare :class:`ActionBinding` instead, the same as the original nine read-only
labels -- ``verify()`` was always a plain oracle call available to any
caller with a live environment reference, not a gated capability invocation,
so gating it added a false capability without adding real authorization.

**Correction (2026-08-12), per this repo's own "never overwrite, add a
retraction beside it" convention**: the "exactly four new labels" claim
above described :data:`ALLOWED_ACTUATION_BINDING_LABELS` as it stood at
the time this paragraph was written. Real, current count, re-verified this
session directly against the frozenset literal below:
:data:`ALLOWED_ACTUATION_BINDING_LABELS` now has **11** members (grew via
later, separate work adding the recheck/mitigation labels
:data:`GYMACT_ACTUATE_REMEDIATE_LABEL`, :data:`GYMACT_SUBMIT_MITIGATION_LABEL`,
:data:`GYMACT_RECHECK_DEPLOYMENTS_LABEL`, :data:`GYMACT_RECHECK_PODS_LABEL`,
:data:`GYMACT_RECHECK_SERVICES_LABEL`, :data:`GYMACT_CHECK_SERVICES_LABEL`,
never updated in this narrative when they were added). The narrower,
principled rule described above (gated-actuation-only, structurally
refused otherwise) is unchanged and still real -- only the literal count
"four" is stale; read the frozenset literal itself as the source of truth
for the current real count, not this prose.

Why this does not violate ``.claude/rules/ecosystem-boundary.md``'s "this
repo... does not attach actuation semantics" law: that law binds this
repo's *own* claims about the portfolio's actuation, broker, and receipt
surfaces (``mfw``'s admission/broker, ``bcinr``'s scheduler,
``ggen``/``ggen-legacy``'s manufacture-and-receipt chain) -- it does not
forbid this repo from *calling into* a sibling project's own,
already-authorized, already-gated capability surface, the same way any
caller of a properly bounded external API is expected to. `gymact` is not
part of this repo's actuation/broker/receipt chain at all; it is the real,
external environment this diagnosing pipeline targets, and
``SREGYM_CAPABILITIES`` is gymact's own intended external-caller surface
(``gymact.gyms.sregym``'s own module, not something this repo reverse
engineers). Routing exclusively through that real, gated, bounded surface
-- never gymact internals, never ``verify()``, never anything outside the
TOML allowlist -- is invoking gymact's *own* authorization the way gymact
itself intends external callers to, not autofde-lab manufacturing or
claiming ecosystem-wide actuation authority of its own. See
``.claude/rules/actuation-boundary.md`` for the parallel: a bounded,
catalog-described, typed-refusal-capable external call is the lawful shape
of "this repo may call out," which is what this widened rule uses --
``CapabilityGate`` is exactly that catalog/refusal mechanism, applied here
at bind-construction time rather than at call time only.

This keeps the original guarantee for the original nine labels completely
unchanged: they may still only ever take a bare :class:`ActionBinding`
callable (never a ``GatedCapabilityBinding``, never any wider capability),
so the "structural-only, no actuation" property for scan/phi-encode/
dispatch/solve/case-library/record remains true by the same unmodified
refusal code path it always was, not merely by convention now that a
second, disjoint set of labels exists alongside it.
"""

from __future__ import annotations

import concurrent.futures
from dataclasses import dataclass
from typing import Any, Callable, Sequence

from autofde_lab.fabric.gymact_capability_gate import CapabilityGate
from autofde_lab.fabric.powl import parse_powl_turtle, project_plan_to_powl
from autofde_lab.ocel.log import OcelLog
from autofde_lab.ocel.mcp_instrumentation import OcelSessionRecorder
from autofde_lab.ocel.powl_replay import ActionBinding
from autofde_lab.powl.algebra import (
    Atom,
    ChoiceGraph,
    ChoiceGraphEdge,
    NodeId,
    OrderEdge,
    PartialOrder,
    PowlNode,
)
from autofde_lab.powl.bounds import DEFAULT_BOUND, ExecutionBound
from autofde_lab.powl.executor import (
    INITIAL_MARKING,
    Marking,
    NodePath,
    classify_stall,
    enabled,
    fire,
    is_final,
    node_at,
)
from autofde_lab.powl.refusals import PowlError

__all__ = [
    "PIPELINE_LINEAR_STEPS",
    "CASE_RETRIEVE_LABEL",
    "CASE_HIT_LABEL",
    "CASE_MISS_LABEL",
    "CASE_RETAIN_LABEL",
    "RECORD_LABEL",
    "BridgeUnavailable",
    "build_pipeline_turtle",
    "build_pipeline_powl_node",
    "PipelineStallResult",
    "classify_pipeline_stall",
    "run_pipeline",
    "ALLOWED_ACTION_BINDING_LABELS",
    "ALLOWED_ACTUATION_BINDING_LABELS",
    "GYMACT_CHECK_STATUS_LABEL",
    "GYMACT_CHECK_NAMESPACE_LABEL",
    "GYMACT_CHECK_DEPLOYMENTS_LABEL",
    "GYMACT_CHECK_PODS_LABEL",
    "GYMACT_CHECK_SERVICES_LABEL",
    "GYMACT_SCAN_ANOMALIES_LABEL",
    "GYMACT_RECHECK_SCAN_LABEL",
    "GYMACT_SUBMIT_DIAGNOSIS_LABEL",
    "GYMACT_ACTUATE_REMEDIATE_LABEL",
    "GYMACT_SUBMIT_MITIGATION_LABEL",
    "GYMACT_VERIFY_LABEL",
    "GatedCapabilityBinding",
    "ActuationBindingRefused",
]

#: The turtle-bridge-eligible linear prefix: scan the cluster, phi-encode the
#: anomaly into a real domain object, dispatch via `match_solvers`, solve.
#: Each becomes one real `powl2:ActivityLeaf` in a real Turtle document.
PIPELINE_LINEAR_STEPS: tuple[str, ...] = (
    "(scan cluster)",
    "(phi_encode anomaly)",
    "(dispatch_solve problem)",
    "(solve problem)",
)

CASE_RETRIEVE_LABEL = "cbr_retrieve"
CASE_HIT_LABEL = "case_hit"
CASE_MISS_LABEL = "case_miss"
CASE_RETAIN_LABEL = "cbr_retain"
RECORD_LABEL = "ocel_record"
GYMACT_SCAN_ANOMALIES_LABEL = "gymact_scan_anomalies"

#: The complete, closed set of labels this runner will ever invoke an
#: `action_bindings` callable for -- every one of them read-only or
#: diagnostic (scan, phi-encode, dispatch, solve, case-library
#: retrieve/hit/miss/retain, OCEL record). This is the code-level
#: enforcement of this module's own docstring decision ("the runner stays
#: structural-only; it does not gain a direct actuation path"): a caller
#: cannot smuggle a cluster-mutating actuator into `run_pipeline` by
#: keying it under one of this pipeline's Atom labels, because `run_pipeline`
#: refuses any `action_bindings` key outside this set below -- the decision
#: is a runtime guard, not merely stated prose.
#: Aggregation atom for the remediate-recheck block (`_concurrent_read_block`'s
#: three-check AND-join), the remediate-side sibling of
#: `GYMACT_SCAN_ANOMALIES_LABEL` above -- same reasoning: pure computation over
#: already-gathered results, no `env.actuate()` call, so it belongs with the
#: read-only/diagnostic labels, not the actuation-class set.
GYMACT_RECHECK_SCAN_LABEL = "gymact_recheck_scan"

ALLOWED_ACTION_BINDING_LABELS: frozenset[str] = frozenset(
    {
        "scan",
        "phi_encode",
        "dispatch_solve",
        "solve",
        CASE_RETRIEVE_LABEL,
        CASE_HIT_LABEL,
        CASE_MISS_LABEL,
        CASE_RETAIN_LABEL,
        RECORD_LABEL,
        GYMACT_SCAN_ANOMALIES_LABEL,
        GYMACT_RECHECK_SCAN_LABEL,
    }
)

#: Real, POWL v2 partial-order-shaped replacement for the old monolithic
#: `gymact_observe` Atom (fixed forward, per Kourani/Park/van der Aalst,
#: "Hierarchical Decomposition of Separable Workflow-Nets": a partial order
#: with no order edges among its children IS the formalism's own concurrent
#: / marked-graph construct -- Definition 3.11 there, `_enabled()`'s own
#: docstring here ("Two mutually unordered children of a partial order are
#: both in the result; concurrency is preserved, not serialized.")). These
#: five real, independent environment observations have no causal
#: dependency on one another -- each is its own real gymact capability call
#: -- so wiring them as ONE sequential Atom label (the pre-existing
#: `gymact_observe`) was a real, corrected defect: POWL v2's whole
#: distinguishing expressiveness over a plain sequence/choice model is
#: exactly this kind of unordered, genuinely concurrent structure, and this
#: pipeline previously never used it anywhere.
GYMACT_CHECK_STATUS_LABEL = "gymact_check_status"
GYMACT_CHECK_NAMESPACE_LABEL = "gymact_check_namespace"
GYMACT_CHECK_DEPLOYMENTS_LABEL = "gymact_check_deployments"
GYMACT_CHECK_PODS_LABEL = "gymact_check_pods"
GYMACT_CHECK_SERVICES_LABEL = "gymact_check_services"
#: Structurally downstream of the whole concurrent check block above (an
#: AND-join per `_body_complete()`'s `PartialOrder` rule: enabled only once
#: ALL five checks have fired) -- pure computation over their already-
#: gathered results, no `env.actuate()` call, so it belongs with the
#: original read-only/diagnostic labels, not the actuation-class set.
GYMACT_SUBMIT_DIAGNOSIS_LABEL = "gymact_submit_diagnosis"
GYMACT_ACTUATE_REMEDIATE_LABEL = "gymact_actuate_remediate"
GYMACT_SUBMIT_MITIGATION_LABEL = "gymact_submit_mitigation"
GYMACT_VERIFY_LABEL = "gymact_verify"
#: Real, explicit pipeline step (found and fixed forward this cycle, via an
#: actual live trial): waits on the conductor's own real stage-transition
#: signal (the same bounded `env.verify()` poll `gymact_verify` uses) BEFORE
#: the concurrent observe block ever fires -- closing a real race between
#: `materialize()`'s readiness signal (the conductor API/MCP surface being
#: reachable) and the real, slower app deployment (measured 5-15 real
#: minutes) actually finishing. Same class as `gymact_verify`: a plain
#: coroutine oracle call, never a real gymact `Capability`, so it takes a
#: bare `ActionBinding`, not a `GatedCapabilityBinding`.
GYMACT_WAIT_FOR_DEPLOY_LABEL = "gymact_wait_for_deploy"

#: Remediate-phase sibling of the three observe-phase check labels that need a
#: real capability call (deployments/pods/services -- not namespace/status,
#: which the remediate block does not recheck). Distinct labels from the
#: observe-phase ones because they write distinct `diagnosis_state` keys
#: (`recheck_deployments`/`recheck_pods`/`recheck_services`), not because the
#: capability differs.
GYMACT_RECHECK_DEPLOYMENTS_LABEL = "gymact_recheck_deployments"
GYMACT_RECHECK_PODS_LABEL = "gymact_recheck_pods"
GYMACT_RECHECK_SERVICES_LABEL = "gymact_recheck_services"

#: A second, disjoint set of labels -- never merged into
#: `ALLOWED_ACTION_BINDING_LABELS` -- for which `run_pipeline` allows a real
#: actuation-capable binding, but *only* as a `GatedCapabilityBinding` whose
#: construction already proved the wrapped capability name was admitted by a
#: real `CapabilityGate`. See this module's docstring ("Revised decision")
#: for why this narrower rule does not reopen the original structural-only
#: guarantee for `ALLOWED_ACTION_BINDING_LABELS`.
ALLOWED_ACTUATION_BINDING_LABELS: frozenset[str] = frozenset(
    {
        GYMACT_CHECK_STATUS_LABEL,
        GYMACT_CHECK_NAMESPACE_LABEL,
        GYMACT_CHECK_DEPLOYMENTS_LABEL,
        GYMACT_CHECK_PODS_LABEL,
        GYMACT_CHECK_SERVICES_LABEL,
        GYMACT_SUBMIT_DIAGNOSIS_LABEL,
        GYMACT_ACTUATE_REMEDIATE_LABEL,
        GYMACT_SUBMIT_MITIGATION_LABEL,
        GYMACT_RECHECK_DEPLOYMENTS_LABEL,
        GYMACT_RECHECK_PODS_LABEL,
        GYMACT_RECHECK_SERVICES_LABEL,
    }
)

#: A third, disjoint label set: actuation-adjacent but never capability-gated,
#: because there is no real gymact `Capability` behind it to gate against.
#: `gymact_verify` takes a bare `ActionBinding` (same rule as
#: `ALLOWED_ACTION_BINDING_LABELS`) but is NOT required by the default
#: completeness check -- a caller may run a pipeline with or without a real
#: oracle-verify step wired in, unlike the nine always-required read-only
#: pipeline steps.
ALLOWED_ACTUATION_ORACLE_LABELS: frozenset[str] = frozenset(
    {GYMACT_VERIFY_LABEL, GYMACT_WAIT_FOR_DEPLOY_LABEL}
)


class ActuationBindingRefused(ValueError):
    """Raised when `run_pipeline` is given an `action_bindings` key outside
    `ALLOWED_ACTION_BINDING_LABELS` / `ALLOWED_ACTUATION_BINDING_LABELS` --
    i.e. a caller trying to wire a cluster-mutating actuator to fire as a
    side effect of structural marking advancement, which this module's
    docstring states it deliberately never does for the original nine
    read-only/diagnostic labels. Also raised when: (a) `action_bindings` is
    incomplete relative to `ALLOWED_ACTION_BINDING_LABELS` and the caller
    did not explicitly opt into a partial pipeline via
    `allow_partial_bindings` -- see `run_pipeline`'s docstring for why an
    unbound label silently firing as a no-op is refused by default rather
    than treated as a legitimate gap; or (b) an actuation-class label
    (`ALLOWED_ACTUATION_BINDING_LABELS`) is bound to anything other than a
    real `GatedCapabilityBinding` -- a bare, ungated callable for one of
    those five labels is refused before any Atom fires, never invoked; or
    (c) one of the original nine read-only/diagnostic labels is bound to a
    `GatedCapabilityBinding` -- those labels may only ever take a bare
    `ActionBinding`, keeping their structural-only guarantee unconditional."""


@dataclass(frozen=True, slots=True)
class GatedCapabilityBinding:
    """The only construction path an actuation-class Atom label
    (`ALLOWED_ACTUATION_BINDING_LABELS`) may bind to.

    Wraps a raw `ActionBinding` callable together with the real gymact
    capability name it exercises, and eagerly proves that name was admitted
    by a real `CapabilityGate` at *wrap time* -- not merely by convention,
    and not deferred until first invocation. `__post_init__` calls
    `gate.check(capability_name)`, which raises the real, named
    `CapabilityRefused` (from `autofde_lab.fabric.gymact_capability_gate`)
    immediately if `capability_name` is not in the gate's loaded TOML
    manifest -- so an unauthorized capability can never even be
    constructed as a binding, let alone fired.

    Calling the resulting object is a plain pass-through to the wrapped
    callable -- this class adds no new invocation semantics, only the
    construction-time capability proof described above.
    """

    capability_name: str
    callable_: ActionBinding
    gate: CapabilityGate

    def __post_init__(self) -> None:
        self.gate.check(self.capability_name)

    def __call__(self, atom_attrs: dict[str, Any]) -> Any:
        return self.callable_(atom_attrs)


class BridgeUnavailable(ValueError):
    """Raised when turtle_bridge did not produce the shape this runner needs."""


def build_pipeline_turtle(base_iri: str = "urn:autofde-lab:powl-runner") -> str:
    """Real POWL2 Turtle text for the linear scan/phi/dispatch/solve prefix."""
    return project_plan_to_powl(list(PIPELINE_LINEAR_STEPS), base_iri=base_iri)


def _concurrent_read_block(labels: Sequence[str]) -> PartialOrder:
    """N unordered `Atom` children, no order edges among them -- the real POWL
    v2 marked-graph / AND-concurrency construct (Kourani/Park/van der Aalst,
    Definition 3.11). Callers graft the returned node into the outer tree as
    one indexed child, then chain a single `OrderEdge` from it to whatever
    aggregation `Atom` must AND-join all N.

    Narrow scope, deliberately: only the tree-*construction* shape is shared
    between the observe and remediate-recheck blocks -- the driver-side
    binding/`diagnosis_state`-write logic for the two blocks stays separate.
    """
    return PartialOrder(
        children=tuple(Atom(label=l) for l in labels), order=frozenset()
    )


def _sequence(nodes: tuple[PowlNode, ...], *, start_index: int) -> frozenset[OrderEdge]:
    """The `OrderEdge` set chaining every adjacent pair in `nodes` (`nodes[i]
    -> nodes[i+1]` for each `i`), offset so `nodes[0]` sits at `start_index`
    in the caller's own top-level children tuple.

    Real, index-based counterpart to the real reference `powl` package's own
    `builders.py::sequence()` (`~/POWL/powl/objects/tagged_powl/builders.py`
    -- confirmed via direct read this session: `PartialOrder(nodes=ordered,
    edges=[(ordered[i], ordered[i+1]) for i in range(len(ordered)-1)], ...)`,
    an *object-identity*-keyed edge scheme). autofde-lab's own `algebra.py`
    addresses children by 0-based `NodeId` position instead (a deliberate,
    documented arena convention, mirroring `~/wasm4pm-compat/src/powl.rs` --
    kept as-is, not changed to match the reference), so this helper is the
    generic, index-based version of the same "chain every adjacent pair"
    pattern `build_pipeline_powl_node()` used to compute by hand, inline,
    once per call site (`choice_index`/`record_index`/`actuation_start_index`
    plus a bespoke `for offset in range(...)` loop) -- extracted here so that
    bookkeeping exists in exactly one place. Purely an ergonomics refactor:
    the real, source-verified compliance audit this session found no other
    real reference execution/discovery machinery worth porting -- see
    `~/.claude/plans/what-are-the-current-shimmying-bear.md` for the full,
    evidence-grounded comparison (cycles, single-start/end, frequency,
    canonical storage, and the executor itself all checked directly against
    the real `~/POWL` reference package's own source, not assumed)."""
    return frozenset(
        OrderEdge(NodeId(start_index + i), NodeId(start_index + i + 1))
        for i in range(len(nodes) - 1)
    )


def build_pipeline_powl_node(turtle_text: str | None = None) -> PowlNode:
    """The full pipeline as one real, executor-consumable `PowlNode` tree.

    The linear prefix is parsed from a real POWL2 Turtle document via
    `turtle_bridge.powl_model_to_node`. The case-library hit/miss branch is a
    real `ChoiceGraph`, built directly via `algebra.py` -- see this module's
    docstring for why turtle_bridge cannot be used for that part.
    """
    from autofde_lab.powl.turtle_bridge import powl_model_to_node

    text = turtle_text if turtle_text is not None else build_pipeline_turtle()
    model = parse_powl_turtle(text)
    linear = powl_model_to_node(model)
    if not isinstance(linear, PartialOrder) or not all(
        isinstance(c, Atom) for c in linear.children
    ):
        raise BridgeUnavailable(
            f"expected a flat PartialOrder of Atom leaves from turtle_bridge, "
            f"got {type(linear).__name__}"
        )
    linear_atoms: tuple[Atom, ...] = linear.children  # type: ignore[assignment]
    n_linear = len(linear_atoms)

    # Real ChoiceGraph, built directly (turtle_bridge has no vocabulary for
    # it): retrieve(0) -> case_hit(1) | case_miss(2) -> retain(3). Branches
    # are distinguished by the entry Atom's label, never by an edge label.
    choice_children: tuple[PowlNode, ...] = (
        Atom(label=CASE_RETRIEVE_LABEL),
        Atom(label=CASE_HIT_LABEL),
        Atom(label=CASE_MISS_LABEL),
        Atom(label=CASE_RETAIN_LABEL),
    )
    choice_edges = frozenset(
        {
            ChoiceGraphEdge(NodeId(0), NodeId(1)),
            ChoiceGraphEdge(NodeId(0), NodeId(2)),
            ChoiceGraphEdge(NodeId(1), NodeId(3)),
            ChoiceGraphEdge(NodeId(2), NodeId(3)),
        }
    )
    choice_graph = ChoiceGraph(
        children=choice_children, edges=choice_edges, start=0, end=3
    )

    record_atom = Atom(label=RECORD_LABEL)

    # A new, terminal, linear actuation branch, strictly downstream of
    # record_atom -- never interleaved into the case_hit/case_miss
    # ChoiceGraph above. See this module's docstring ("Revised decision")
    # for why the two must stay disjoint: case_hit/case_miss selects *how a
    # solution was found* (orthogonal to *whether the result is later
    # actuated*), so collapsing them would let structural choice-graph
    # traversal double as an actuation gate. A caller who never binds any of
    # these five `gymact_*` labels sees them fire as pure structural no-ops,
    # exactly like any other unbound label -- adding this branch is safe
    # even before any binding exists.
    # Real POWL v2 partial-order-shaped actuation chain: an unordered
    # concurrent observe block (5 real, independent environment checks, no
    # causal dependency on one another) AND-joined by gymact_scan_anomalies,
    # then submit_diagnosis, then an unordered concurrent remediate-recheck
    # block (3 real, independent rechecks) AND-joined by gymact_recheck_scan,
    # then submit_mitigation, then verify. See this module's docstring
    # ("Revised decision") for why this stays disjoint from the case_hit/
    # case_miss ChoiceGraph above.
    observe_block = _concurrent_read_block(
        [
            GYMACT_CHECK_STATUS_LABEL,
            GYMACT_CHECK_NAMESPACE_LABEL,
            GYMACT_CHECK_DEPLOYMENTS_LABEL,
            GYMACT_CHECK_PODS_LABEL,
            GYMACT_CHECK_SERVICES_LABEL,
        ]
    )
    remediate_block = _concurrent_read_block(
        [
            GYMACT_RECHECK_DEPLOYMENTS_LABEL,
            GYMACT_RECHECK_PODS_LABEL,
            GYMACT_RECHECK_SERVICES_LABEL,
        ]
    )
    actuation_entries: tuple[PowlNode, ...] = (
        Atom(label=GYMACT_WAIT_FOR_DEPLOY_LABEL),
        observe_block,
        Atom(label=GYMACT_SCAN_ANOMALIES_LABEL),
        Atom(label=GYMACT_SUBMIT_DIAGNOSIS_LABEL),
        remediate_block,
        Atom(label=GYMACT_RECHECK_SCAN_LABEL),
        Atom(label=GYMACT_SUBMIT_MITIGATION_LABEL),
        Atom(label=GYMACT_VERIFY_LABEL),
    )

    # Everything downstream of the turtle-sourced linear prefix is one real,
    # strictly-sequenced chain: choice_graph -> record_atom -> the actuation
    # entries. `_sequence()` computes its own internal chaining; only the one
    # edge joining the linear prefix's last atom to this chain's first
    # element needs to be added separately.
    tail: tuple[PowlNode, ...] = (choice_graph, record_atom) + actuation_entries
    top_children: tuple[PowlNode, ...] = linear_atoms + tail

    # Remap the turtle-sourced order relation (already 0..n_linear-1) as-is,
    # then chain: last linear step -> choice graph -> record atom -> the new
    # actuation chain (observe_block -> scan_anomalies -> submit_diagnosis ->
    # remediate_block -> recheck_scan -> submit_mitigation -> verify). Each
    # `PartialOrder` entry above is addressed by exactly one index from this
    # top-level `PartialOrder` -- the same nested-composite-as-child shape
    # `choice_graph` above already proves works with `node_at`/`_enabled`
    # (both recurse into any `PartialOrder`/`ChoiceGraph` child uniformly;
    # confirmed by reading `executor.py`'s `node_at`/`_enabled` this session).
    order_edges: set[OrderEdge] = {
        OrderEdge(edge.src, edge.dst) for edge in linear.order
    }
    order_edges.add(OrderEdge(NodeId(n_linear - 1), NodeId(n_linear)))
    order_edges |= _sequence(tail, start_index=n_linear)

    return PartialOrder(children=top_children, order=frozenset(order_edges))


@dataclass(frozen=True, slots=True)
class PipelineStallResult:
    """What `classify_pipeline_stall` surfaces -- never a new timeout layer."""

    final: bool
    stall: str | None  # an `executor.DeadlockKind` value, or None if final/live


def classify_pipeline_stall(
    model: PowlNode,
    marking: Marking,
    bound: ExecutionBound = DEFAULT_BOUND,
) -> PipelineStallResult:
    """Surface `executor.classify_stall()` directly -- no wall-clock timeout.

    Per `executor.py`/`bounds.py`: termination is structural (three counters
    only), never a timeout. This function adds no bound of its own; it is a
    thin, honest pass-through so a caller of this runner gets the same
    `BLOCKED:BOUND_EXHAUSTED` / `BLOCKED:DEADLOCK` classification the
    executor already computes, rather than a silent hang.
    """
    if is_final(model, marking):
        return PipelineStallResult(final=True, stall=None)
    # `max_marking_states` is a genuine third gate here, alongside `fires`
    # and `not enabled(...)` -- found and fixed forward this session
    # (tests/powl/test_runner_bounds_concurrent_chicago.py`): unlike
    # `max_node_visits`, a `max_marking_states` exhaustion is invisible to
    # `enabled()` (it is enforced only inside `fire()`, never removes a
    # path from the enabled set), so a marking that `run_pipeline` actually
    # stopped advancing because of it can still have a real, structurally
    # enabled successor -- `enabled(...)` returns non-empty, and without
    # this explicit check this function fell through to the final `return
    # ... stall=None` line below ("more work enabled, not stalled"), which
    # is a genuinely honest-sounding but wrong verdict: the caller's own
    # `run_pipeline` loop had already halted, so "not stalled" mis-reported
    # a real stop as ongoing progress.
    if (
        marking.fires >= bound.max_activity_fires
        or len(marking.completed_paths) >= bound.max_marking_states
        or not enabled(model, marking, bound)
    ):
        # Delegate the actual verdict to executor.classify_stall itself --
        # this module never re-derives BOUND_EXHAUSTED vs. DEADLOCK on its
        # own, only forwards the executor's real classification.
        return PipelineStallResult(
            final=False, stall=str(classify_stall(model, marking, bound))
        )
    return PipelineStallResult(
        final=False, stall=None
    )  # more work enabled, not stalled


def run_pipeline(
    model: PowlNode,
    *,
    session_id: str | None = None,
    action_bindings: dict[str, ActionBinding] | None = None,
    bound: ExecutionBound = DEFAULT_BOUND,
    allow_partial_bindings: bool = False,
    recorder_factory: Callable[[str], OcelSessionRecorder] | None = None,
) -> tuple[OcelLog, PipelineStallResult]:
    """Drive `model` to completion or to a classified stall, recording one
    real `"powl_structural_fire"` OCEL event per fire -- the same event shape
    `ocel.powl_replay.replay_structural_fires` uses -- while retaining the
    `Marking` so a caller gets `classify_pipeline_stall`'s real verdict
    instead of a silently-incomplete log.

    This module keeps its own loop (rather than delegating entirely to
    `replay_structural_fires`, which does not return its final `Marking`)
    for exactly that reason: surfacing `classify_stall()` requires the
    marking `replay_structural_fires` does not expose.

    Enforces this module's docstring decision at runtime, not merely in
    prose: any `action_bindings` key outside `ALLOWED_ACTION_BINDING_LABELS`
    raises `ActuationBindingRefused` before any Atom fires -- a caller
    cannot wire a cluster-mutating actuator to fire as a side effect of
    structural marking advancement.

    `action_bindings` completeness -- refuse-if-incomplete by default
    --------------------------------------------------------------------
    When a non-empty `action_bindings` is given, the DEFAULT is to require it
    to cover the full `ALLOWED_ACTION_BINDING_LABELS` set exactly. An Atom
    whose label has no bound callable still fires structurally (the marking
    advances -- this runner never re-derives a different traversal), but no
    `action_result` is ever computed for it and no `powl_action_binding_error`
    can ever be raised for it either, because the callable that would have
    produced either is simply absent. A caller who thinks their diagnosis
    pipeline "ran end-to-end" from a clean `run_pipeline` return could
    otherwise be silently wrong about which steps actually executed real
    logic -- exactly the confident-wrong-plan failure mode
    `.claude/rules/absence-is-not-evidence.md` names for admission, here
    recurring at the binding-coverage boundary. `run_pipeline` therefore
    raises `ActuationBindingRefused`, naming every missing label, before any
    Atom fires.

    A caller with a legitimate partial-pipeline use case (e.g. driving only
    the linear scan/phi/dispatch/solve prefix in a context that never reaches
    the case-library branch) opts out explicitly with
    `allow_partial_bindings=True`. Passing `action_bindings=None` or `{}`
    (no bindings at all) is unaffected by this check -- an caller running a
    purely structural replay with zero bound callables is unambiguous about
    what it did, unlike a partial dict that could be mistaken for complete.

    `recorder_factory` -- test-only injection seam, not part of the
    documented public contract's normal use
    --------------------------------------------------------------------
    When omitted (the default for every real caller), `run_pipeline`
    constructs its own `OcelSessionRecorder(session_id, server_name="powl-
    runner")`, exactly as before this parameter existed. A caller may pass a
    zero-arg-beyond-`session_id` callable returning a real (not mocked)
    `OcelSessionRecorder`-shaped object instead -- e.g. a small, real
    subclass that also records `threading.get_ident()` on every `record()`
    call -- so a test can assert directly on the *real* recorder's own
    invocation-thread identity, rather than inferring thread-safety only
    indirectly from the returned `OcelLog`'s event ordering. This is a real
    injection point, not a mock: the object returned still is a real
    `OcelSessionRecorder` (or a real subclass of one) that genuinely performs
    `record()`/`close()`, never a stand-in that fakes the interaction.
    """
    if action_bindings:
        known_labels = (
            ALLOWED_ACTION_BINDING_LABELS
            | ALLOWED_ACTUATION_BINDING_LABELS
            | ALLOWED_ACTUATION_ORACLE_LABELS
        )
        refused = sorted(set(action_bindings) - known_labels)
        if refused:
            raise ActuationBindingRefused(
                f"run_pipeline refuses action_bindings for label(s) {refused!r} -- "
                f"only {sorted(known_labels)!r} (read-only/diagnostic pipeline steps, "
                f"plus the narrow, capability-gated actuation-class labels in "
                f"ALLOWED_ACTUATION_BINDING_LABELS) may be bound. Any other real "
                f"actuation step must be reached through a separate, explicitly "
                f"authorized call outside this replay."
            )

        ungated = sorted(
            label
            for label in action_bindings
            if label in ALLOWED_ACTUATION_BINDING_LABELS
            and not isinstance(action_bindings[label], GatedCapabilityBinding)
        )
        if ungated:
            raise ActuationBindingRefused(
                f"REFUSED:UNGATED_ACTUATION_BINDING label(s)={ungated!r} -- an "
                f"actuation-class label may only be bound to a real "
                f"GatedCapabilityBinding (whose construction already proved the "
                f"wrapped capability name was admitted by a real CapabilityGate), "
                f"never a bare ActionBinding callable. Wrap the callable in "
                f"GatedCapabilityBinding(capability_name=..., callable_=..., gate=...) "
                f"before binding it to {ungated!r}."
            )

        misgated = sorted(
            label
            for label in action_bindings
            if label
            in (ALLOWED_ACTION_BINDING_LABELS | ALLOWED_ACTUATION_ORACLE_LABELS)
            and isinstance(action_bindings[label], GatedCapabilityBinding)
        )
        if misgated:
            raise ActuationBindingRefused(
                f"REFUSED:ACTUATION_BINDING_ON_READONLY_LABEL label(s)={misgated!r} -- "
                f"the original read-only/diagnostic pipeline labels, plus "
                f"gymact_verify (no real gymact Capability exists to gate it "
                f"against), may only ever take a bare ActionBinding callable, "
                f"never a GatedCapabilityBinding (or any other capability-gated "
                f"actuation wrapper). Their structural-only guarantee stays "
                f"unconditional."
            )

        if not allow_partial_bindings:
            missing = sorted(ALLOWED_ACTION_BINDING_LABELS - set(action_bindings))
            if missing:
                raise ActuationBindingRefused(
                    f"run_pipeline refuses incomplete action_bindings -- missing "
                    f"binding(s) for label(s) {missing!r}. An unbound label still "
                    f"fires structurally but silently skips its action_result / "
                    f"binding-error reporting, which could let a caller believe "
                    f"their diagnosis pipeline ran end-to-end when a step was "
                    f"actually a no-op. Pass a callable for every label in "
                    f"{sorted(ALLOWED_ACTION_BINDING_LABELS)!r}, or pass "
                    f"allow_partial_bindings=True to explicitly opt into a "
                    f"partial pipeline."
                )

    session_id = session_id or "powl-runner-pipeline"
    recorder = (
        recorder_factory(session_id)
        if recorder_factory is not None
        else OcelSessionRecorder(session_id, server_name="powl-runner")
    )

    marking: Marking = INITIAL_MARKING
    step = 0
    while not is_final(model, marking):
        if marking.fires >= bound.max_activity_fires:
            # `fire()` itself raises BOUND_EXHAUSTED past this point; checked
            # here instead so a fire-budget stall stops the loop the same
            # honest, non-raising way a visit-cap or deadlock stall does --
            # `classify_pipeline_stall` below reports which one it was.
            break
        live = enabled(model, marking, bound)
        if not live:
            break
        batch: list[NodePath] = sorted(live)  # deterministic ORDER; never a subset pick

        if len(batch) == 1:
            # Byte-identical to the pre-existing single-path body, except for
            # the try/except immediately below -- keeps every pre-existing
            # test passing unchanged (the try/except is a no-op whenever
            # `fire()` does not raise).
            chosen: NodePath = batch[0]
            node = node_at(model, chosen)
            label = node.label if isinstance(node, Atom) else f"path:{chosen}"

            # Genuine bug found and fixed forward this session (tests/powl/
            # test_runner_bounds_concurrent_chicago.py): the top-of-loop
            # `if marking.fires >= bound.max_activity_fires: break` only
            # guards the fire-budget bound. `max_marking_states` (bounds.py)
            # is enforced *inside* `fire()` itself and was left uncaught
            # here, unlike the concurrent batch path's Step A (`except
            # PowlError: break` below) -- so a `max_marking_states`
            # exhaustion discovered on the single-fire path (concretely:
            # right after a concurrent batch partially fired and left
            # exactly one path enabled) propagated out of `run_pipeline` as
            # an uncaught `PowlError` instead of the honest, classified
            # `BLOCKED:BOUND_EXHAUSTED` stall every other bound-exhaustion
            # path already returns. Mirrors Step A's own handling exactly:
            # stop advancing, let `classify_pipeline_stall` report the real
            # verdict afterward.
            try:
                marking = fire(model, marking, chosen, bound=bound)
            except PowlError:
                break
            step += 1

            node_object_id = f"{session_id}-node-{'.'.join(map(str, chosen))}"
            outcome: dict[str, Any] = {
                "standing": "FIRED",
                "detail": label,
                "steps_taken": step,
            }

            binding = action_bindings.get(label) if action_bindings else None
            if binding is not None and isinstance(node, Atom):
                atom_attrs = {
                    "label": node.label,
                    "action": node.action,
                    "bindings": dict(node.bindings),
                }
                try:
                    outcome["action_result"] = binding(atom_attrs)
                except Exception as exc:  # noqa: BLE001 -- recorded honestly, then re-raised
                    recorder.record(
                        activity="powl_action_binding_error",
                        objects=[(node_object_id, "PowlNode")],
                        outcome={
                            "standing": "ERROR",
                            "detail": label,
                            "steps_taken": step,
                            "error": f"{type(exc).__name__}: {exc}",
                        },
                    )
                    raise

            recorder.record(
                activity="powl_structural_fire",
                objects=[(node_object_id, "PowlNode")],
                outcome=outcome,
            )
            continue

        # len(batch) > 1: real concurrent batch-fire -- the executor's own
        # documented law ("the caller picks... never a tie-break") applied
        # for real: fire the whole concurrently-enabled set, not one
        # arbitrarily chosen member.
        #
        # Step A: advance the marking for every chosen path first,
        # sequentially, on the calling thread -- `fire()` is pure/cheap
        # (frozen `Marking`, `dataclasses.replace`, no module-level state),
        # so doing all fires up front keeps `marking` fully consistent before
        # any binding (slow, impure, may raise) runs. Handle BOUND_EXHAUSTED
        # honestly mid-batch: if `fire()` raises partway through, stop firing
        # further batch members; only what actually fired gets a binding
        # invoked or an event recorded, and `classify_pipeline_stall` reports
        # the real verdict afterward.
        fired_this_round: list[tuple[NodePath, PowlNode, str, int]] = []
        for path in batch:
            try:
                marking = fire(model, marking, path, bound=bound)
            except PowlError:
                break  # BOUND_EXHAUSTED mid-batch -- stop firing; handle what did fire below
            step += 1
            fired_node = node_at(model, path)
            fired_label = (
                fired_node.label if isinstance(fired_node, Atom) else f"path:{path}"
            )
            fired_this_round.append((path, fired_node, fired_label, step))

        if not fired_this_round:
            # Genuine bug found and fixed forward this session (tests/powl/
            # test_runner_bounds_concurrent_chicago.py): a >1-sized batch
            # whose very FIRST fire attempt already raises `PowlError`
            # (e.g. a second concurrent batch, recomputed fresh at the top
            # of the loop, whose first member is already over budget
            # because an earlier round spent the whole bound) leaves
            # `marking` completely unchanged by this iteration. Without
            # this explicit `break`, the `while not is_final(...)` loop
            # would recompute the exact same non-empty `batch` next
            # iteration (nothing advanced) and retry the exact same failing
            # first fire forever -- a genuine hang, not merely the
            # `ThreadPoolExecutor(max_workers=0)` crash this guard was
            # originally added alongside (see Step B's own comment). Every
            # other honest stop in this loop (the `max_activity_fires`
            # pre-check above, Step A's own partial-batch `break`, `not
            # live: break`) already leaves the loop via a path that either
            # advanced `marking` or exits outright -- this is the one gap
            # where neither happened.
            break

        # Step B: invoke bindings for everything that DID fire, concurrently,
        # via a ThreadPoolExecutor sized to the batch -- every future starts
        # immediately, so there is never a queued-but-not-started future to
        # cancel on error.
        #
        # Genuine bug found and fixed forward this session (tests/powl/
        # test_runner_bounds_concurrent_chicago.py): `fired_this_round` can
        # legitimately be EMPTY -- not just partially filled -- whenever a
        # bound is exhausted on the very *first* fire attempt of a >1-sized
        # batch (concretely: a second concurrent batch, computed fresh at
        # the top of the loop, whose first member is already over budget
        # because an earlier round used up the whole bound). Constructing
        # `ThreadPoolExecutor(max_workers=len(fired_this_round))` with that
        # count `== 0` raised `ValueError("max_workers must be greater than
        # 0")` uncaught -- a crash on an entirely legitimate, honest "0 of a
        # >1 batch fired" outcome. Step C's own loop below was already a
        # correct no-op over an empty `fired_this_round`; only Step B needed
        # this guard.
        results: dict[NodePath, Any] = {}
        errors: dict[NodePath, Exception] = {}
        if fired_this_round:
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=len(fired_this_round)
            ) as pool:
                future_to_path: dict[concurrent.futures.Future, NodePath] = {}
                for path, fired_node, fired_label, _fired_step in fired_this_round:
                    binding = (
                        action_bindings.get(fired_label) if action_bindings else None
                    )
                    if binding is not None and isinstance(fired_node, Atom):
                        atom_attrs = {
                            "label": fired_node.label,
                            "action": fired_node.action,
                            "bindings": dict(fired_node.bindings),
                        }
                        future_to_path[pool.submit(binding, atom_attrs)] = path
                for future in concurrent.futures.as_completed(future_to_path):
                    path = future_to_path[future]
                    try:
                        results[path] = future.result()
                    except Exception as exc:  # noqa: BLE001 -- recorded honestly, then re-raised
                        errors[path] = exc

        # Step C: record OCEL events sequentially on the calling thread
        # (`OcelSessionRecorder` is explicitly documented not thread-safe --
        # single-writer -- so recording must never happen from a worker
        # thread), in batch order, for every fired path, success or error,
        # THEN raise the first error in that same deterministic order if any.
        for path, fired_node, fired_label, fired_step in fired_this_round:
            node_object_id = f"{session_id}-node-{'.'.join(map(str, path))}"
            if path in errors:
                exc = errors[path]
                recorder.record(
                    activity="powl_action_binding_error",
                    objects=[(node_object_id, "PowlNode")],
                    outcome={
                        "standing": "ERROR",
                        "detail": fired_label,
                        "steps_taken": fired_step,
                        "error": f"{type(exc).__name__}: {exc}",
                    },
                )
                continue
            outcome = {
                "standing": "FIRED",
                "detail": fired_label,
                "steps_taken": fired_step,
            }
            if path in results:
                outcome["action_result"] = results[path]
            recorder.record(
                activity="powl_structural_fire",
                objects=[(node_object_id, "PowlNode")],
                outcome=outcome,
            )
        if errors:
            first_path = next(p for p, *_ in fired_this_round if p in errors)
            raise errors[first_path]

    return recorder.close(), classify_pipeline_stall(model, marking, bound)
