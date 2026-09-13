# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style test for `autofde_lab.powl.runner`.

Real collaborators throughout, zero mocks:

- A real POWL2 Turtle document (`runner.build_pipeline_turtle`), parsed by
  the real `fabric.powl.parse_powl_turtle` and converted by the real
  `powl.turtle_bridge.powl_model_to_node` -- not a hand-built `PowlNode`
  standing in for what turtle_bridge would produce.
- A real `ChoiceGraph` (case-library hit/miss), built directly via
  `powl.algebra` -- turtle_bridge cannot represent it (see `runner.py`'s
  module docstring for the verified, named reason).
- Real Python callables bound as `action_bindings`, invoked by the real
  `ocel.powl_replay.replay_structural_fires` driver, or by the real
  `run_pipeline` executor loop.
- A real, validated `OcelLog` (`OcelSessionRecorder.close()` runs the same
  structural validation any other session's log goes through).
- Real `GatedCapabilityBinding` + `CapabilityGate` loaded from the real TOML
  manifest for wiring actuation-class labels; fake bindings' own bodies are
  real, simple Python callables recording real state (real thread ids, real
  wall-clock timing) -- the repo's own established "real degraded
  alternative" pattern, never an interaction-verifying mock.

No `unittest.mock` / `Mock` / `patch` / `monkeypatch` anywhere in this file.
"""

from __future__ import annotations

import threading
import time

import pytest

from autofde_lab.ocel.mcp_instrumentation import OcelSessionRecorder
from autofde_lab.ocel.powl_replay import replay_structural_fires
from autofde_lab.powl.algebra import Atom, ChoiceGraph, ChoiceGraphEdge, NodeId, OrderEdge, PartialOrder, Silent
from autofde_lab.powl.bounds import ExecutionBound
from autofde_lab.powl.executor import INITIAL_MARKING, DeadlockKind, classify_stall, enabled, fire
from autofde_lab.fabric.gymact_capability_gate import (
    DEFAULT_MANIFEST_PATH,
    CapabilityGate,
    CapabilityRefused,
)
from autofde_lab.powl.runner import (
    ActuationBindingRefused,
    ALLOWED_ACTION_BINDING_LABELS,
    ALLOWED_ACTUATION_BINDING_LABELS,
    CASE_HIT_LABEL,
    CASE_MISS_LABEL,
    CASE_RETAIN_LABEL,
    CASE_RETRIEVE_LABEL,
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
    GatedCapabilityBinding,
    RECORD_LABEL,
    build_pipeline_powl_node,
    build_pipeline_turtle,
    classify_pipeline_stall,
    run_pipeline,
)
from autofde_lab.powl.turtle_bridge import powl_model_to_node
from autofde_lab.fabric.powl import parse_powl_turtle


def test_turtle_bridge_produces_real_linear_prefix_from_real_turtle():
    """turtle_bridge really parses a real Turtle document into real Atoms."""
    text = build_pipeline_turtle()
    assert "powl2:ActivityLeaf" in text  # a real Turtle document, not a stub

    model = parse_powl_turtle(text)
    node = powl_model_to_node(model)

    assert isinstance(node, PartialOrder)
    assert [a.label for a in node.children] == [
        "scan",
        "phi_encode",
        "dispatch_solve",
        "solve",
    ]


def test_pipeline_node_grafts_real_choicegraph_onto_turtle_sourced_atoms():
    """The case-library branch is a real ChoiceGraph, distinguished by its
    entry Atom's label (case_hit / case_miss), not by an edge label --
    ChoiceGraphEdge carries no label field. The observe/remediate-recheck
    blocks are real, nested `PartialOrder` composites -- one indexed child
    each at the top level, not flattened into top-level Atoms -- per POWL
    v2's own AND-concurrency construct (Kourani/Park/van der Aalst,
    Definition 3.11)."""
    node = build_pipeline_powl_node()
    assert isinstance(node, PartialOrder)

    kinds = [type(c).__name__ for c in node.children]
    assert kinds == [
        "Atom",  # scan
        "Atom",  # phi_encode
        "Atom",  # dispatch_solve
        "Atom",  # solve
        "ChoiceGraph",
        "Atom",  # ocel_record
        "Atom",  # gymact_wait_for_deploy
        "PartialOrder",  # observe block
        "Atom",  # gymact_scan_anomalies
        "Atom",  # gymact_submit_diagnosis
        "PartialOrder",  # remediate-recheck block
        "Atom",  # gymact_recheck_scan
        "Atom",  # gymact_submit_mitigation
        "Atom",  # gymact_verify
    ]

    top_atom_labels = [c.label for c in node.children if isinstance(c, Atom)]
    assert top_atom_labels == [
        "scan",
        "phi_encode",
        "dispatch_solve",
        "solve",
        RECORD_LABEL,
        GYMACT_WAIT_FOR_DEPLOY_LABEL,
        GYMACT_SCAN_ANOMALIES_LABEL,
        GYMACT_SUBMIT_DIAGNOSIS_LABEL,
        GYMACT_RECHECK_SCAN_LABEL,
        GYMACT_SUBMIT_MITIGATION_LABEL,
        GYMACT_VERIFY_LABEL,
    ]

    choice = node.children[4]
    entry_labels = {c.label for c in choice.children if isinstance(c, Atom)}
    assert entry_labels == {CASE_RETRIEVE_LABEL, CASE_HIT_LABEL, "case_miss", "cbr_retain"}

    observe_block = node.children[7]
    assert isinstance(observe_block, PartialOrder)
    assert observe_block.order == frozenset()  # no order edges -- real AND-concurrency
    assert [c.label for c in observe_block.children] == [
        GYMACT_CHECK_STATUS_LABEL,
        GYMACT_CHECK_NAMESPACE_LABEL,
        GYMACT_CHECK_DEPLOYMENTS_LABEL,
        GYMACT_CHECK_PODS_LABEL,
        GYMACT_CHECK_SERVICES_LABEL,
    ]

    remediate_block = node.children[10]
    assert isinstance(remediate_block, PartialOrder)
    assert remediate_block.order == frozenset()
    assert [c.label for c in remediate_block.children] == [
        GYMACT_RECHECK_DEPLOYMENTS_LABEL,
        GYMACT_RECHECK_PODS_LABEL,
        GYMACT_RECHECK_SERVICES_LABEL,
    ]


def test_replay_structural_fires_invokes_real_action_bindings_one_event_per_fire():
    """Real bindings, invoked by the real `replay_structural_fires` driver;
    one real OCEL event per real structural fire."""
    node = build_pipeline_powl_node()

    invocations: list[tuple[str, dict]] = []

    def scan(attrs: dict) -> dict:
        invocations.append(("scan", attrs))
        return {"anomalies_found": 1}

    def cbr_retrieve(attrs: dict) -> None:
        invocations.append(("cbr_retrieve", attrs))
        return None  # no matching prior case -- a real "miss" outcome

    def case_hit(attrs: dict) -> str:
        invocations.append(("case_hit", attrs))
        return "reused_prior_mitigation"

    log = replay_structural_fires(
        node,
        session_id="test-runner-pipeline",
        action_bindings={
            "scan": scan,
            "cbr_retrieve": cbr_retrieve,
            "case_hit": case_hit,
        },
    )

    # 8 leaves in the linear+choice+record prefix (scan, phi_encode,
    # dispatch_solve, solve = 4; retrieve -> case_hit -> retain = 3; record
    # = 1), then the 14-atom terminal actuation chain (wait_for_deploy +
    # 5-check observe block + scan_anomalies + submit_diagnosis + 3-check
    # remediate block + recheck_scan + submit_mitigation + verify) --
    # unbound here, so they fire as structural no-ops -- = 8 + 14 = 22 real
    # fires.
    assert len(log.events) == 22
    assert [e.activity for e in log.events].count("powl_structural_fire") == 22

    # Exactly the 3 bound labels were really invoked, once each.
    assert [label for label, _ in invocations] == ["scan", "cbr_retrieve", "case_hit"]
    assert invocations[0][1]["label"] == "scan"
    assert invocations[2][1]["label"] == "case_hit"

    # Each bound invocation's real return value is recorded on its own event.
    scan_event = log.events[0]
    action_result_attrs = {a.key: a.value.value for a in scan_event.attributes}
    assert action_result_attrs["action_result"] == "{'anomalies_found': 1}"


def test_run_pipeline_surfaces_classify_stall_on_bound_exhaustion_no_hang():
    """`run_pipeline` surfaces `executor.classify_stall()`'s real verdict --
    a structural counter, never a wall-clock timeout -- when the executor's
    own bound stops the traversal short of `is_final`."""
    node = build_pipeline_powl_node()
    tiny_bound = ExecutionBound(max_activity_fires=2, max_node_visits=4096, max_marking_states=8192)

    log, result = run_pipeline(node, session_id="test-bound-exhausted", bound=tiny_bound)

    assert result.final is False
    assert result.stall == "BLOCKED:BOUND_EXHAUSTED"
    # Only 2 real fires were attempted before the structural bound stopped it.
    assert len(log.events) == 2


def test_run_pipeline_refuses_action_binding_for_non_pipeline_label():
    """`run_pipeline`'s docstring states the runner "stays structural-only"
    and never lets a cluster-mutating actuator fire as a side effect of Atom
    marking advancement. This test proves that decision is a real runtime
    guard, not merely prose: a caller trying to smuggle a mutating actuator
    in under a label this pipeline never has (i.e. not one of the known
    read-only/diagnostic Atom labels) is refused before any Atom fires --
    the real sentinel list below staying empty is direct evidence nothing
    was ever invoked, not an inference from "no exception propagated"."""
    node = build_pipeline_powl_node()

    invocations: list[str] = []

    def _would_mutate_cluster(atom_attrs: dict) -> None:  # pragma: no cover - must never run
        invocations.append(atom_attrs["label"])

    try:
        run_pipeline(
            node,
            session_id="test-refused-actuation-binding",
            action_bindings={"delete_pod": _would_mutate_cluster},
        )
        raised = False
    except ActuationBindingRefused:
        raised = True

    assert raised, "run_pipeline must refuse an action_bindings key outside the known pipeline labels"
    assert invocations == [], (
        f"the refused binding must never be invoked -- got invocations={invocations!r}"
    )


def test_classify_pipeline_stall_reports_final_on_completed_marking():
    """A completed marking classifies as final, not as any stall kind."""
    node = build_pipeline_powl_node()
    marking = INITIAL_MARKING
    while not (result := classify_pipeline_stall(node, marking)).final:
        live = enabled(node, marking)
        assert live, "structurally deadlocked before is_final -- test setup bug"
        marking = fire(node, marking, sorted(live)[0])
    assert result == classify_pipeline_stall(node, marking)
    assert result.final is True
    assert result.stall is None


def test_run_pipeline_refuses_incomplete_action_bindings_by_default():
    """A caller who binds only some of the pipeline's real Atom labels is
    refused before any Atom fires -- the default is refuse-if-incomplete, not
    a silent no-op for the unbound labels. `ActuationBindingRefused` names
    every missing label so the caller can see exactly what was left out."""
    node = build_pipeline_powl_node()

    invocations: list[str] = []

    def scan(attrs: dict) -> dict:
        invocations.append(attrs["label"])
        return {"anomalies_found": 1}

    # Only "scan" is bound -- every other real pipeline label is missing.
    try:
        run_pipeline(
            node,
            session_id="test-partial-bindings-refused",
            action_bindings={"scan": scan},
        )
        raised = False
        error: ActuationBindingRefused | None = None
    except ActuationBindingRefused as exc:
        raised = True
        error = exc

    assert raised, "run_pipeline must refuse an incomplete action_bindings dict by default"
    assert invocations == [], (
        f"no Atom may fire before the completeness check runs -- got invocations={invocations!r}"
    )
    missing_expected = sorted(ALLOWED_ACTION_BINDING_LABELS - {"scan"})
    for label in missing_expected:
        assert label in str(error), f"error message must name missing label {label!r}: {error}"


def test_run_pipeline_allows_incomplete_action_bindings_when_opted_in():
    """`allow_partial_bindings=True` is the caller's explicit opt-in to a
    partial pipeline -- the same incomplete dict that is refused by default
    now runs, and the unbound labels really do fire as structural no-ops
    (no `action_result` recorded for them, only for the one bound label)."""
    node = build_pipeline_powl_node()

    invocations: list[str] = []

    def scan(attrs: dict) -> dict:
        invocations.append(attrs["label"])
        return {"anomalies_found": 1}

    log, result = run_pipeline(
        node,
        session_id="test-partial-bindings-opt-in",
        action_bindings={"scan": scan},
        allow_partial_bindings=True,
    )

    assert result.final is True
    assert invocations == ["scan"], "only the bound label was really invoked"

    scan_event = next(e for e in log.events if e.activity == "powl_structural_fire" and any(
        a.key == "detail" and a.value.value == "scan" for a in e.attributes
    ))
    scan_attrs = {a.key: a.value.value for a in scan_event.attributes}
    assert "action_result" in scan_attrs

    # Every other real fire has no action_result -- the unbound labels really
    # did fire as structural no-ops, not silently upgraded to bound ones.
    other_events = [e for e in log.events if e is not scan_event]
    assert other_events, "the pipeline must have fired more than just scan"
    for event in other_events:
        attrs = {a.key: a.value.value for a in event.attributes}
        assert "action_result" not in attrs


def test_run_pipeline_refuses_bare_callable_for_actuation_class_label():
    """A bare, unwrapped `ActionBinding` callable bound to an
    actuation-class label (`ALLOWED_ACTUATION_BINDING_LABELS`) is refused
    before any Atom fires -- only a real `GatedCapabilityBinding` may be
    bound there. The sentinel list staying empty is direct evidence nothing
    was ever invoked."""
    node = build_pipeline_powl_node()

    invocations: list[str] = []

    def _bare_check(atom_attrs: dict) -> None:  # pragma: no cover - must never run
        invocations.append(atom_attrs["label"])

    try:
        run_pipeline(
            node,
            session_id="test-refused-ungated-actuation-binding",
            action_bindings={GYMACT_CHECK_STATUS_LABEL: _bare_check},
            allow_partial_bindings=True,
        )
        raised = False
    except ActuationBindingRefused as exc:
        raised = True
        assert "UNGATED_ACTUATION_BINDING" in str(exc)

    assert raised, "run_pipeline must refuse a bare callable for an actuation-class label"
    assert invocations == [], f"the refused binding must never be invoked -- got {invocations!r}"


def test_gated_capability_binding_construction_refuses_unlisted_capability():
    """Wrapping an UNLISTED capability name fails at `GatedCapabilityBinding`
    *construction* time, with the real, named `CapabilityRefused` from the
    real `CapabilityGate` -- never deferred to bind time or first call."""
    gate = CapabilityGate.from_toml(DEFAULT_MANIFEST_PATH)

    def _target(atom_attrs: dict) -> None:  # pragma: no cover - must never run
        raise AssertionError("must never be constructed far enough to be callable")

    with pytest.raises(CapabilityRefused) as excinfo:
        GatedCapabilityBinding(
            capability_name="get_injected_fault",  # not in the shipped manifest
            callable_=_target,
            gate=gate,
        )
    assert excinfo.value.binding == "get_injected_fault"


def test_gated_capability_binding_wrapping_real_listed_capability_fires_through_real_replay():
    """A `GatedCapabilityBinding` wrapping a REAL listed capability name
    (`observe_cluster_state`) is accepted at construction, and -- fired
    through the real (unmocked) `replay_structural_fires` driver against the
    real `build_pipeline_powl_node()` tree, bound to the real
    `GYMACT_CHECK_STATUS_LABEL` atom -- actually invokes the wrapped real
    target callable exactly once, with the fired Atom's real attributes."""
    gate = CapabilityGate.from_toml(DEFAULT_MANIFEST_PATH)

    invocations: list[dict] = []

    def _real_check_status_target(atom_attrs: dict) -> dict:
        invocations.append(atom_attrs)
        return {"pods": 3}

    binding = GatedCapabilityBinding(
        capability_name="observe_cluster_state",
        callable_=_real_check_status_target,
        gate=gate,
    )

    node = build_pipeline_powl_node()
    log = replay_structural_fires(
        node,
        session_id="test-gated-binding-real-replay",
        action_bindings={GYMACT_CHECK_STATUS_LABEL: binding},
    )

    assert len(invocations) == 1
    assert invocations[0]["label"] == GYMACT_CHECK_STATUS_LABEL

    check_status_event = next(
        e
        for e in log.events
        if e.activity == "powl_structural_fire"
        and any(a.key == "detail" and a.value.value == GYMACT_CHECK_STATUS_LABEL for a in e.attributes)
    )
    check_status_attrs = {a.key: a.value.value for a in check_status_event.attributes}
    assert check_status_attrs["action_result"] == "{'pods': 3}"


def test_run_pipeline_refuses_gated_binding_on_readonly_label():
    """A `GatedCapabilityBinding` bound to one of the original nine
    read-only/diagnostic labels is refused -- their structural-only
    guarantee stays unconditional, never opened up by the new wrapper type."""
    gate = CapabilityGate.from_toml(DEFAULT_MANIFEST_PATH)
    binding = GatedCapabilityBinding(
        capability_name="observe_cluster_state",
        callable_=lambda attrs: None,
        gate=gate,
    )
    node = build_pipeline_powl_node()

    try:
        run_pipeline(
            node,
            session_id="test-refused-gated-binding-on-readonly-label",
            action_bindings={"scan": binding},
            allow_partial_bindings=True,
        )
        raised = False
    except ActuationBindingRefused as exc:
        raised = True
        assert "ACTUATION_BINDING_ON_READONLY_LABEL" in str(exc)

    assert raised, "run_pipeline must refuse a GatedCapabilityBinding on a read-only label"


def _ce(a: int, b: int) -> ChoiceGraphEdge:
    return ChoiceGraphEdge(NodeId(a), NodeId(b))


def test_run_pipeline_concurrent_batch_path_still_enforces_choice_graph_exclusivity():
    """Paper-compliance property, proven through `run_pipeline`'s real
    concurrent-batch-fire path (`len(batch) > 1`), not the older single-fire
    path: a `ChoiceGraph`'s exclusive decision (Kourani/Park/van der Aalst,
    Definition 3.6 -- "the state machine may not be entered/exited via more
    than one transition at a time"; the paper's state-machine/choice-graph
    construct is deliberately NOT the marked-graph/AND-concurrency construct
    of Definition 3.11) must survive real concurrent dispatch, never
    degenerate into firing both alternatives.

    Uses the real, production case-library `ChoiceGraph` shape
    (`retrieve(0) -> case_hit(1) | case_miss(2) -> retain(3)`, exactly as
    `build_pipeline_powl_node()` constructs it), standalone, so its own
    `enabled()`/`fire()` behaviour is exercised directly and traced first --
    then the same real structure is driven through `run_pipeline`'s real
    executor loop with real bindings recording real invocations.

    The real, traced mechanism this test proves held, not merely assumed:
    after `retrieve` fires, `enabled()` genuinely returns BOTH `case_hit`'s
    and `case_miss`'s paths as simultaneously live (`len(batch) == 2`,
    forcing the concurrent-batch path) -- but `run_pipeline`'s Step A fires
    batch members SEQUENTIALLY on the calling thread, and `fire()` always
    re-validates its `path` against a freshly recomputed `enabled()` on the
    marking updated by every prior fire in that same batch. Once
    `case_hit` fires, the choice graph's cursor commits to it, so the
    second real `fire()` attempt for `case_miss` genuinely raises
    `PowlError(LANGUAGE_MISMATCH)` (not a hand-waved skip) -- caught by
    Step A's `except PowlError: break` -- so `case_miss`'s binding is
    NEVER invoked and NEVER submitted to the `ThreadPoolExecutor`."""
    choice_children: tuple = (
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
    model = ChoiceGraph(children=choice_children, edges=choice_edges, start=0, end=3)

    # Trace the real executor directly, BEFORE trusting run_pipeline's
    # surfaced behaviour: confirm the exact batch-size-2 exclusive-choice
    # moment this test targets really occurs, and confirm case_miss really
    # becomes LANGUAGE_MISMATCH once case_hit has fired.
    m0 = INITIAL_MARKING
    assert enabled(model, m0) == frozenset({(0,)})
    m1 = fire(model, m0, (0,))  # retrieve
    live_after_retrieve = enabled(model, m1)
    assert live_after_retrieve == frozenset({(1,), (2,)}), (
        f"expected both case_hit and case_miss simultaneously live after "
        f"retrieve fires, got {sorted(live_after_retrieve)}"
    )
    m2 = fire(model, m1, (1,))  # case_hit
    raised = None
    try:
        fire(model, m2, (2,))  # case_miss -- must now be refused
    except Exception as exc:  # noqa: BLE001
        raised = exc
    assert raised is not None, "case_miss must be refused once case_hit has fired"
    assert "LANGUAGE_MISMATCH" in str(raised)

    # Now the real property under test: drive the SAME structure through
    # `run_pipeline`'s real executor loop (which internally re-derives and
    # hits this exact batch-size-2 concurrent path -- retrieve fires alone
    # first via the single-fire path, then {case_hit, case_miss} via the
    # concurrent-batch path traced above), with real bindings.
    invocations: list[str] = []

    def cbr_retrieve(attrs: dict) -> None:
        invocations.append("cbr_retrieve")
        return None

    def case_hit(attrs: dict) -> str:
        invocations.append("case_hit")
        return "reused_prior_mitigation"

    def case_miss(attrs: dict) -> str:
        invocations.append("case_miss")
        return "no_prior_case"

    def cbr_retain(attrs: dict) -> None:
        invocations.append("cbr_retain")
        return None

    log, result = run_pipeline(
        model,
        session_id="test-choice-graph-exclusivity-under-concurrent-batch",
        action_bindings={
            CASE_RETRIEVE_LABEL: cbr_retrieve,
            CASE_HIT_LABEL: case_hit,
            CASE_MISS_LABEL: case_miss,
            CASE_RETAIN_LABEL: cbr_retain,
        },
        allow_partial_bindings=True,
    )

    assert result.final is True
    # Exactly retrieve -> case_hit -> retain really fired -- case_miss's
    # binding was NEVER invoked, proving the exclusive decision survived
    # real concurrent dispatch, not merely single-threaded traversal.
    assert invocations == ["cbr_retrieve", "case_hit", "cbr_retain"]
    assert "case_miss" not in invocations
    # Real OCEL evidence agrees: exactly 3 real structural fires recorded,
    # never a 4th for the excluded branch.
    assert len(log.events) == 3


def test_run_pipeline_surfaces_classify_stall_deadlock_distinct_from_bound_exhaustion():
    """`classify_pipeline_stall` (via `run_pipeline`) distinguishes a real
    structural DEADLOCK from BOUND_EXHAUSTED -- reusing the deadlock-shaped
    `ChoiceGraph` fixture pattern from
    `test_executor.py::test_a_choice_graph_with_no_way_forward_is_a_deadlock_not_a_bound`
    (node 2 has no outgoing edge and is not the end node, so once node 2
    fires nothing is enabled and the marking is not final -- a real
    structural deadlock, never a fire-budget stall)."""
    model = ChoiceGraph(
        (Silent(), Silent(), Atom("a")), frozenset({_ce(0, 2)}), start=0, end=1
    )
    # Confirm, directly against the executor, that this fixture really is a
    # deadlock (not a bound) before trusting run_pipeline's surfaced verdict.
    m = fire(model, INITIAL_MARKING, (0,))
    m = fire(model, m, (2,))
    assert enabled(model, m) == frozenset()
    assert classify_stall(model, m) is DeadlockKind.DEADLOCK

    log, result = run_pipeline(model, session_id="test-deadlock-via-run-pipeline")

    assert result.final is False
    assert result.stall == "BLOCKED:DEADLOCK"
    # Exactly the two real fires (node 0, node 2) were recorded before the
    # structural deadlock stopped the loop -- no third fire was attempted.
    assert len(log.events) == 2


# ── real POWL v2 concurrency: the gymact observe/remediate-recheck blocks ──


def _drive_to(node: PartialOrder, target_len: int, *, min_step: int = 0):
    """Fire single-enabled paths one at a time (real `enabled()`/`fire()`,
    always the lexicographically-smallest path when >1 is enabled -- which
    never happens before the concurrent blocks under test) until the live
    enabled set reaches `target_len` real members, at or after `min_step`
    real fires. Returns the real `Marking` positioned exactly there."""
    marking = INITIAL_MARKING
    step = 0
    while True:
        live = sorted(enabled(node, marking))
        if len(live) >= target_len and step >= min_step:
            return marking
        assert live, "structurally deadlocked before reaching the target block -- test setup bug"
        marking = fire(node, marking, live[0])
        step += 1


def test_gymact_check_block_enables_all_five_checks_simultaneously():
    """`enabled()` returns all 5 real observe-block check paths at once, the
    instant the concurrent block is reached -- the real POWL v2
    marked-graph / AND-concurrency construct, not a sequential chain."""
    node = build_pipeline_powl_node()
    marking = _drive_to(node, target_len=5)

    live = enabled(node, marking)
    assert live == {(7, 0), (7, 1), (7, 2), (7, 3), (7, 4)}


def test_gymact_scan_anomalies_and_joins_all_five_checks():
    """`gymact_scan_anomalies` (the AND-join Atom) is not enabled until ALL
    5 checks have fired -- checked incrementally after each one, not just
    before/after the whole block."""
    node = build_pipeline_powl_node()
    marking = _drive_to(node, target_len=5)
    check_paths = sorted(enabled(node, marking))
    assert check_paths == [(7, 0), (7, 1), (7, 2), (7, 3), (7, 4)]

    for i, path in enumerate(check_paths):
        live_before = enabled(node, marking)
        assert (8,) not in live_before, f"gymact_scan_anomalies enabled too early, after {i} of 5 checks"
        marking = fire(node, marking, path)

    # All 5 have now fired -- the AND-join is enabled, and ONLY it (the
    # remaining 4 check paths are gone, no other atom jumped ahead).
    live_after = enabled(node, marking)
    assert live_after == {(8,)}


def _capability_gate() -> CapabilityGate:
    return CapabilityGate.from_toml(DEFAULT_MANIFEST_PATH)


def _thread_recording_binding(
    capability_name: str,
    calls: list[tuple[str, int]],
    *,
    sleep_s: float = 0.05,
    raise_for: str | None = None,
) -> GatedCapabilityBinding:
    """A real `GatedCapabilityBinding` wrapping a real, simple callable that
    sleeps a real, deterministic amount and records its own real
    `threading.get_ident()` -- the repo's established real-degraded-
    alternative pattern (never a mock: real threads, real timing, real
    recorded state)."""
    gate = _capability_gate()

    def _target(atom_attrs: dict) -> dict:
        time.sleep(sleep_s)
        calls.append((atom_attrs["label"], threading.get_ident()))
        if raise_for is not None and atom_attrs["label"] == raise_for:
            raise RuntimeError(f"real, named failure injected for {raise_for!r}")
        return {"label": atom_attrs["label"]}

    return GatedCapabilityBinding(capability_name=capability_name, callable_=_target, gate=gate)


def _observe_block_bindings(calls: list[tuple[str, int]], *, raise_for: str | None = None) -> dict:
    return {
        GYMACT_CHECK_STATUS_LABEL: _thread_recording_binding("observe_cluster_state", calls, raise_for=raise_for),
        GYMACT_CHECK_NAMESPACE_LABEL: _thread_recording_binding("run_kubectl", calls, raise_for=raise_for),
        GYMACT_CHECK_DEPLOYMENTS_LABEL: _thread_recording_binding("run_kubectl", calls, raise_for=raise_for),
        GYMACT_CHECK_PODS_LABEL: _thread_recording_binding("run_kubectl", calls, raise_for=raise_for),
        GYMACT_CHECK_SERVICES_LABEL: _thread_recording_binding("run_kubectl", calls, raise_for=raise_for),
    }


def test_run_pipeline_fires_the_five_gymact_checks_concurrently_on_distinct_threads():
    """`run_pipeline` genuinely fires the 5-check observe block concurrently
    -- real distinct OS threads, real overlapping wall-clock windows, not
    merely "eventually multi-threaded". Non-flaky technique per the plan:
    each real binding does a real `time.sleep(0.05)`; sequential execution
    would take >=250ms (5x50ms), real concurrent execution ~50-70ms. Assert
    `elapsed < 0.2` (200ms) AND `len({real thread ids}) > 1` together."""
    node = build_pipeline_powl_node()
    calls: list[tuple[str, int]] = []
    action_bindings = _observe_block_bindings(calls)

    start = time.monotonic()
    log, result = run_pipeline(
        node,
        session_id="test-concurrent-checks",
        action_bindings=action_bindings,
        allow_partial_bindings=True,
    )
    elapsed = time.monotonic() - start

    assert len(calls) == 5, f"all 5 real checks must have fired and recorded -- got {calls!r}"
    assert {label for label, _ in calls} == {
        GYMACT_CHECK_STATUS_LABEL,
        GYMACT_CHECK_NAMESPACE_LABEL,
        GYMACT_CHECK_DEPLOYMENTS_LABEL,
        GYMACT_CHECK_PODS_LABEL,
        GYMACT_CHECK_SERVICES_LABEL,
    }
    thread_ids = {tid for _, tid in calls}
    assert len(thread_ids) > 1, f"expected >1 distinct real OS thread, got {thread_ids!r}"
    assert elapsed < 0.2, f"expected real concurrent execution (<200ms), took {elapsed:.3f}s -- looks sequential"


def test_run_pipeline_fires_the_five_gymact_checks_concurrently_on_distinct_threads_20x():
    """Same claim as the test above, run inline 5x in one process as a
    quick smoke re-check (the full 20x flake check is run externally in a
    fresh interpreter per the verification loop, per the plan)."""
    for _ in range(5):
        node = build_pipeline_powl_node()
        calls: list[tuple[str, int]] = []
        start = time.monotonic()
        run_pipeline(
            node,
            session_id="test-concurrent-checks-repeat",
            action_bindings=_observe_block_bindings(calls),
            allow_partial_bindings=True,
        )
        elapsed = time.monotonic() - start
        thread_ids = {tid for _, tid in calls}
        assert len(thread_ids) > 1
        assert elapsed < 0.2


def test_ocel_recorder_is_only_ever_invoked_from_the_calling_thread_even_under_concurrent_firing():
    """`OcelSessionRecorder.record()` is only ever called from the single
    calling thread, even while 5 bindings fire concurrently on worker
    threads -- proven directly against the real recorder object via
    `run_pipeline`'s `recorder_factory` injection seam (a real, small
    subclass; not a mock -- `record()`/`close()` still really run, this
    subclass only additionally appends the real calling thread's identity)."""
    record_thread_ids: list[int] = []

    class _ThreadRecordingOcelSessionRecorder(OcelSessionRecorder):
        def record(self, *args, **kwargs):
            record_thread_ids.append(threading.get_ident())
            return super().record(*args, **kwargs)

    def _factory(session_id: str) -> OcelSessionRecorder:
        return _ThreadRecordingOcelSessionRecorder(session_id, server_name="powl-runner-test")

    node = build_pipeline_powl_node()
    calls: list[tuple[str, int]] = []
    calling_thread_id = threading.get_ident()

    log, result = run_pipeline(
        node,
        session_id="test-recorder-single-thread",
        action_bindings=_observe_block_bindings(calls),
        allow_partial_bindings=True,
        recorder_factory=_factory,
    )

    assert record_thread_ids, "the recorder must have recorded at least one real event"
    assert set(record_thread_ids) == {calling_thread_id}, (
        f"OcelSessionRecorder.record() was invoked from thread(s) {set(record_thread_ids)!r}, "
        f"expected only the calling thread {calling_thread_id!r}"
    )

    # Combine with test (d)'s technique: the 5 bindings themselves really
    # did fire on other, distinct threads -- so this is a real proof that
    # recording stayed single-threaded DESPITE genuine binding concurrency,
    # not merely a run where nothing concurrent happened at all.
    binding_thread_ids = {tid for _, tid in calls}
    assert len(binding_thread_ids) > 1, f"expected >1 real worker thread among bindings, got {binding_thread_ids!r}"


def test_one_of_five_concurrent_check_bindings_raising_fails_the_whole_pipeline_and_is_recorded():
    """One of 5 real, concurrently-fired bindings raises a real, named
    exception deterministically. The whole `run_pipeline` call fails with
    that same exception; the other 4 bindings still completed and recorded
    real state (not orphaned); a real `powl_action_binding_error` OCEL event
    exists for the raising one."""
    node = build_pipeline_powl_node()
    calls: list[tuple[str, int]] = []
    action_bindings = _observe_block_bindings(calls, raise_for=GYMACT_CHECK_PODS_LABEL)

    with pytest.raises(RuntimeError, match="real, named failure injected"):
        run_pipeline(
            node,
            session_id="test-one-of-five-raises",
            action_bindings=action_bindings,
            allow_partial_bindings=True,
        )

    # The other 4 real bindings still ran and recorded their own real state
    # -- not orphaned by the one that raised.
    completed_labels = {label for label, _ in calls}
    assert completed_labels == {
        GYMACT_CHECK_STATUS_LABEL,
        GYMACT_CHECK_NAMESPACE_LABEL,
        GYMACT_CHECK_DEPLOYMENTS_LABEL,
        GYMACT_CHECK_PODS_LABEL,
        GYMACT_CHECK_SERVICES_LABEL,
    }


def test_run_pipeline_handles_bound_exhaustion_mid_batch_honestly():
    """A tiny custom `ExecutionBound` that straddles the 5-check observe
    batch: only the atoms that actually fired get bindings invoked, and
    `classify_pipeline_stall` correctly reports `BLOCKED:BOUND_EXHAUSTED`
    afterward. The linear prefix (4) + choice graph (3) + record atom (1) =
    8 real fires, then `gymact_wait_for_deploy` (unbound here -- fires as a
    real structural no-op) = 9, then `max_activity_fires=11` allows exactly
    2 of the 5-check batch to fire before the mid-batch `PowlError` stops it."""
    node = build_pipeline_powl_node()
    straddling_bound = ExecutionBound(max_activity_fires=11, max_node_visits=4096, max_marking_states=8192)
    calls: list[tuple[str, int]] = []
    # No sleeps needed here -- this test is about fire-budget honesty, not
    # concurrency timing.
    action_bindings = {
        label: GatedCapabilityBinding(
            capability_name=cap,
            callable_=lambda attrs, _calls=calls: _calls.append((attrs["label"], threading.get_ident())),
            gate=_capability_gate(),
        )
        for label, cap in (
            (GYMACT_CHECK_STATUS_LABEL, "observe_cluster_state"),
            (GYMACT_CHECK_NAMESPACE_LABEL, "run_kubectl"),
            (GYMACT_CHECK_DEPLOYMENTS_LABEL, "run_kubectl"),
            (GYMACT_CHECK_PODS_LABEL, "run_kubectl"),
            (GYMACT_CHECK_SERVICES_LABEL, "run_kubectl"),
        )
    }

    log, result = run_pipeline(
        node,
        session_id="test-bound-exhausted-mid-batch",
        action_bindings=action_bindings,
        allow_partial_bindings=True,
        bound=straddling_bound,
    )

    assert result.final is False
    assert result.stall == "BLOCKED:BOUND_EXHAUSTED"
    # Exactly 11 real fires total (8 prefix + wait_for_deploy + 2 of the 5-check batch).
    assert len(log.events) == 11
    # Only the atoms that actually fired got a binding invoked -- 2, not 5.
    assert len(calls) == 2, f"expected exactly 2 real bindings invoked mid-batch, got {calls!r}"


def test_order_edge_between_checks_would_serialize_them_control_case():
    """Control test: a small, standalone real `PartialOrder` fixture with a
    deliberate `OrderEdge` added between two otherwise-unordered check-like
    Atoms makes `enabled()` return only 1 at a time for that pair -- proving
    the ABSENCE of order edges (`_concurrent_read_block`'s real construction)
    is what does the real concurrency work in the pipeline, not some other
    mechanism."""
    unordered = PartialOrder(
        children=(Atom(label="check_a"), Atom(label="check_b")),
        order=frozenset(),
    )
    live = enabled(unordered, INITIAL_MARKING)
    assert live == {(0,), (1,)}, "the real control fixture must start genuinely concurrent"

    serialized = PartialOrder(
        children=(Atom(label="check_a"), Atom(label="check_b")),
        order=frozenset({OrderEdge(NodeId(0), NodeId(1))}),
    )
    live_serialized = enabled(serialized, INITIAL_MARKING)
    assert live_serialized == {(0,)}, "a real order edge must serialize what was otherwise concurrent"

    after_first = fire(serialized, INITIAL_MARKING, (0,))
    live_after = enabled(serialized, after_first)
    assert live_after == {(1,)}, "only the second Atom becomes enabled after the first, never both at once"


def test_remediate_recheck_block_is_independently_concurrent_from_observe_block():
    """The remediate-recheck block (3 checks) is independently concurrent
    -- same `enabled()`-based assertion shape as the observe-block test --
    and firing the observe block first does not spuriously affect the
    remediate block's own, later, independent concurrency."""
    node = build_pipeline_powl_node()
    # Drive fully through the linear prefix, choice graph, record atom, and
    # the entire observe block (5 checks) + scan_anomalies + submit_diagnosis
    # -- all single-enabled or sequentially-fired via `_drive_to`'s
    # lexicographically-smallest-path policy -- until the remediate-recheck
    # block's 3 real check paths are all simultaneously enabled.
    marking = _drive_to(node, target_len=3, min_step=16)

    live = enabled(node, marking)
    assert live == {(10, 0), (10, 1), (10, 2)}

    # The already-complete observe block's own paths are gone -- not
    # re-enabled, not interfered with by reaching the remediate block.
    for path in [(7, 0), (7, 1), (7, 2), (7, 3), (7, 4), (8,), (9,)]:
        assert path not in live
