# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Property-based and additional adversarial Chicago-style tests for
`autofde_lab.powl.conformance`, expanding well beyond
`tests/powl/test_conformance_chicago.py`'s one positive control and two
hand-picked negative controls (drop, swap).

Real collaborators throughout, zero mocks:

- Real, randomly-generated (fixed-seed `random.Random`, a real reproducible
  PRNG -- not banned nondeterminism) small POWL 2.0 structures, built
  directly from `powl.algebra`'s real dataclasses.
- Each real structure is driven to completion by the real
  `ocel.powl_replay.replay_structural_fires` driver, which itself calls only
  the real `powl.executor.enabled()`/`fire()` functions -- never a
  hand-simulated trace.
- `check_ocel_conformance` is the one function under test, called only
  against real `OcelEvent` tuples a real driver actually produced (or a
  real, deliberate mutation of one).
- The real production model (`build_pipeline_powl_node()`), driven by BOTH
  real log-producing code paths this repo has (`replay_structural_fires`'s
  structural-only driver, and `runner.run_pipeline`'s concurrent-batch
  executor loop), including one run with real, deliberately staggered
  `time.sleep` durations to exercise genuinely-concurrent real recording
  order.

No `unittest.mock` / `Mock` / `patch` / `monkeypatch` anywhere in this file.

Why drop/duplicate/swap mutations are restricted to a *totally-ordered*
generator for the negative control
-------------------------------------------------------------------------
A naive property-based negative control ("mutate any real log, assert
`conforms=False`") is unsound in general: if two adjacent events are
genuinely concurrent siblings of a `PartialOrder` with no `OrderEdge`
between them, swapping them is NOT a violation -- both orders are legal by
construction (`_enabled()`'s own law: "Two mutually unordered children of a
partial order are both in the result; concurrency is preserved, not
serialized."). Rather than trying to classify, post hoc, which adjacent
pairs in an arbitrary generated log happen to be concurrent, the negative
control below uses a *second*, dedicated generator that only ever produces
`PartialOrder` nodes with the *full* transitive closure as their `order`
(a strict total order at every level of nesting) and `ChoiceGraph` nodes
that are simple, unbranched chains (also a strict total order). The
resulting structure has a single, total firing order end to end, so
dropping, duplicating, or swapping *any* real fired event is provably always
a real violation -- verified by hand first in
`test_negative_control_hand_traced_two_atom_sequence` below before trusting
the generator-driven version at scale.
"""

from __future__ import annotations

import random
import time

from autofde_lab.fabric.gymact_capability_gate import DEFAULT_MANIFEST_PATH, CapabilityGate
from autofde_lab.ocel.powl_replay import replay_structural_fires
from autofde_lab.powl.algebra import (
    Atom,
    ChoiceGraph,
    ChoiceGraphEdge,
    NodeId,
    OrderEdge,
    PartialOrder,
    PowlNode,
    Silent,
)
from autofde_lab.powl.conformance import check_ocel_conformance, observed_labels_from_events
from autofde_lab.powl.runner import (
    GYMACT_CHECK_DEPLOYMENTS_LABEL,
    GYMACT_CHECK_NAMESPACE_LABEL,
    GYMACT_CHECK_PODS_LABEL,
    GYMACT_CHECK_SERVICES_LABEL,
    GYMACT_CHECK_STATUS_LABEL,
    GatedCapabilityBinding,
    build_pipeline_powl_node,
    run_pipeline,
)

#: Real, fixed literal seed -- a real reproducible PRNG, not the
#: `Date.now()`/`random.random()`-without-a-seed nondeterminism this repo's
#: testing law bans elsewhere.
_SEED = 20260810


def _full_order(n: int) -> frozenset[OrderEdge]:
    """Every `i -> j` pair for `i < j` -- the full transitive closure over
    `n` children, i.e. a strict total order (`PartialOrder.__post_init__`
    normalizes this down to its transitive reduction, the `i -> i+1` chain,
    but the input relation is equivalent either way)."""
    return frozenset(OrderEdge(NodeId(i), NodeId(j)) for i in range(n) for j in range(n) if i < j)


class _LabelCounter:
    """Real, simple monotone label generator -- guarantees every real Atom
    in one generated tree gets a distinct label, so no two real fires in the
    same log can ever coincidentally share a `detail` string."""

    def __init__(self, prefix: str) -> None:
        self._prefix = prefix
        self._n = 0

    def next(self) -> str:
        label = f"{self._prefix}_{self._n}"
        self._n += 1
        return label


# ── generator 1: wide structural variety, for the positive control ─────────


def _random_variety_node(rng: random.Random, counter: _LabelCounter, depth: int) -> PowlNode:
    """A real, randomly-shaped POWL node: `Atom`, `Silent`, `PartialOrder`
    (randomly either genuinely concurrent -- no order edges -- or totally
    ordered), or an acyclic, unbranched `ChoiceGraph` chain. `depth` bounds
    recursion well under `MAX_POWL_DEPTH` so construction never refuses."""
    if depth <= 0 or rng.random() < 0.4:
        return Silent() if rng.random() < 0.2 else Atom(label=counter.next())

    kind = rng.choice(["partial_order", "partial_order", "choice_graph"])
    n = rng.randint(2, 3)
    children = tuple(_random_variety_node(rng, counter, depth - 1) for _ in range(n))

    if kind == "partial_order":
        order = _full_order(n) if rng.random() < 0.5 else frozenset()
        return PartialOrder(children=children, order=order)

    edges = frozenset(ChoiceGraphEdge(NodeId(i), NodeId(i + 1)) for i in range(n - 1))
    return ChoiceGraph(children=children, edges=edges, start=0, end=n - 1)


def _random_variety_root(rng: random.Random, counter: _LabelCounter) -> PowlNode:
    n = rng.randint(2, 4)
    children = tuple(_random_variety_node(rng, counter, depth=2) for _ in range(n))
    order = _full_order(n) if rng.random() < 0.5 else frozenset()
    return PartialOrder(children=children, order=order)


# ── generator 2: strictly totally ordered, for the negative control ────────


def _random_totally_ordered_node(rng: random.Random, counter: _LabelCounter, depth: int) -> PowlNode:
    """Same shape space as `_random_variety_node`, but every `PartialOrder`
    is forced to the full total order and every `ChoiceGraph` is a simple,
    unbranched chain -- so the generated tree has exactly one legal firing
    order end to end, with no genuinely-concurrent pair anywhere."""
    if depth <= 0 or rng.random() < 0.4:
        return Silent() if rng.random() < 0.2 else Atom(label=counter.next())

    kind = rng.choice(["partial_order", "choice_graph"])
    n = rng.randint(2, 3)
    children = tuple(_random_totally_ordered_node(rng, counter, depth - 1) for _ in range(n))

    if kind == "partial_order":
        return PartialOrder(children=children, order=_full_order(n))

    edges = frozenset(ChoiceGraphEdge(NodeId(i), NodeId(i + 1)) for i in range(n - 1))
    return ChoiceGraph(children=children, edges=edges, start=0, end=n - 1)


def _random_totally_ordered_root(rng: random.Random, counter: _LabelCounter) -> PowlNode:
    n = rng.randint(2, 4)
    children = tuple(_random_totally_ordered_node(rng, counter, depth=2) for _ in range(n))
    return PartialOrder(children=children, order=_full_order(n))


def _mutate(rng: random.Random, events: tuple, kind: str) -> tuple:
    out = list(events)
    if kind == "drop":
        idx = rng.randrange(len(out))
        del out[idx]
    elif kind == "duplicate":
        idx = rng.randrange(len(out))
        out.insert(idx + 1, out[idx])
    elif kind == "swap":
        idx = rng.randrange(len(out) - 1)
        out[idx], out[idx + 1] = out[idx + 1], out[idx]
    else:  # pragma: no cover - test bug, not a runtime path
        raise ValueError(f"unknown mutation kind {kind!r}")
    return tuple(out)


# ── (1) hand-traced base case, verified before trusting the generator ──────


def test_negative_control_hand_traced_two_atom_sequence():
    """Hand-traced base case for the property-based negative control below:
    a bare 2-Atom, strictly-ordered `PartialOrder` (`a -> b`). Each of drop,
    duplicate, and swap is traced explicitly here, before the
    generator-driven version at scale is trusted."""
    model = PartialOrder(
        children=(Atom(label="a"), Atom(label="b")),
        order=frozenset({OrderEdge(NodeId(0), NodeId(1))}),
    )
    log = replay_structural_fires(model, session_id="conformance-hand-traced")
    labels = observed_labels_from_events(log.events)
    assert labels == ("a", "b")

    baseline = check_ocel_conformance(model, log.events)
    assert baseline.conforms is True

    # Drop "a": "b" is not enabled until "a" has fired -- diverges at index 0.
    dropped = tuple(e for e in log.events if e is not log.events[0])
    result = check_ocel_conformance(model, dropped)
    assert result.conforms is False
    assert result.divergence_index == 0
    assert result.divergence_label == "b"

    # Duplicate "a": the second "a" has already completed and is no longer
    # enabled -- diverges at index 1 (the re-inserted "a").
    duplicated = (log.events[0],) + log.events
    result = check_ocel_conformance(model, duplicated)
    assert result.conforms is False
    assert result.divergence_index == 1
    assert result.divergence_label == "a"

    # Swap: "b" observed first is not enabled before "a" has fired --
    # diverges at index 0.
    swapped = (log.events[1], log.events[0])
    result = check_ocel_conformance(model, swapped)
    assert result.conforms is False
    assert result.divergence_index == 0
    assert result.divergence_label == "b"


# ── (2) property-based positive control ─────────────────────────────────


def test_property_based_positive_control_never_false_negatives_across_wide_variety():
    """30 real, randomly-generated small POWL structures (mixing `Atom`,
    `Silent`, concurrent and ordered `PartialOrder`, and `ChoiceGraph`), each
    driven to real completion by the real `replay_structural_fires` driver.
    Every one of the resulting real logs must conform to the model that
    produced it -- proving the checker never has a false negative on a
    genuinely valid trace across wide structural variety, not just the one
    production pipeline shape the existing hand-written test covers."""
    rng = random.Random(_SEED)
    failures = []
    for i in range(30):
        counter = _LabelCounter(f"pos{i}")
        model = _random_variety_root(rng, counter)
        log = replay_structural_fires(model, session_id=f"conformance-property-positive-{i}")
        assert len(log.events) >= 2, f"iteration {i}: generator produced a degenerate 0/1-fire model"

        result = check_ocel_conformance(model, log.events)
        if not result.conforms:
            failures.append((i, result))

    assert not failures, (
        f"conformance false negative(s) on genuinely valid real traces: {failures!r}"
    )


# ── (3) property-based negative control ─────────────────────────────────


def test_property_based_negative_control_totally_ordered_mutations_always_diverge():
    """30 real, randomly-generated, strictly totally-ordered POWL
    structures, each driven to real completion, then each real log mutated
    exactly once (drop / duplicate / swap, cycled across iterations) via the
    same fixed-seed RNG. Because the generator forces a full total order at
    every level of nesting (see module docstring), every one of these
    mutations is a real, provable violation -- never a same-result case that
    would need to be handled as "both outcomes are legal"."""
    rng = random.Random(_SEED + 1)
    kinds = ["drop", "duplicate", "swap"]
    failures = []
    for i in range(30):
        counter = _LabelCounter(f"neg{i}")
        model = _random_totally_ordered_root(rng, counter)
        log = replay_structural_fires(model, session_id=f"conformance-property-negative-{i}")
        assert len(log.events) >= 2, f"iteration {i}: generator produced a degenerate 0/1-fire model"

        baseline = check_ocel_conformance(model, log.events)
        assert baseline.conforms is True, (
            f"iteration {i}: the real, unmutated totally-ordered trace must itself conform "
            f"(sanity check before mutating) -- got {baseline!r}"
        )

        kind = kinds[i % len(kinds)]
        mutated = _mutate(rng, log.events, kind)
        result = check_ocel_conformance(model, mutated)
        if result.conforms:
            failures.append((i, kind, result))

    assert not failures, (
        f"mutation(s) of a strictly totally-ordered real trace failed to diverge "
        f"(model has no concurrency at any level, so a same-result outcome here would be "
        f"a real checker defect, never a legitimate 'swapped concurrent siblings' case): "
        f"{failures!r}"
    )


# ── (4) the real run_pipeline concurrent-batch executor log path ──────────


def test_run_pipeline_produced_log_conforms_via_the_concurrent_batch_executor_path():
    """The real production model, driven by the OTHER real log-producing
    code path this repo has -- `runner.run_pipeline`'s own executor loop
    (single-fire AND concurrent-batch-fire, `ThreadPoolExecutor`-backed) --
    rather than `replay_structural_fires`'s simpler structural-only driver.
    Proves `check_ocel_conformance` works for both real log producers, not
    just the one the existing hand-written test exercises."""
    node = build_pipeline_powl_node()
    log, result = run_pipeline(node, session_id="conformance-run-pipeline-log")

    assert result.final is True
    assert len(log.events) == 22

    conf = check_ocel_conformance(node, log.events)
    assert conf.conforms is True
    assert conf.final is True
    assert conf.fired_count == conf.observed_count == 22
    assert conf.divergence_index is None
    assert conf.divergence_label is None


# ── (5) genuine concurrency does not cause a false divergence ─────────────


def _staggered_binding(gate: CapabilityGate, capability_name: str, sleep_s: float) -> GatedCapabilityBinding:
    """A real `GatedCapabilityBinding` around a real, simple callable that
    really sleeps a real, deterministic (but distinct per-label) duration --
    the repo's established real-degraded-alternative pattern, so the 5
    concurrent checks really finish, and really get recorded by Step C, in a
    different relative order than their declared structural order."""

    def _target(atom_attrs: dict) -> dict:
        time.sleep(sleep_s)
        return {"label": atom_attrs["label"]}

    return GatedCapabilityBinding(capability_name=capability_name, callable_=_target, gate=gate)


def test_concurrent_observe_block_staggered_real_completion_order_still_conforms():
    """The real production model's 5-way concurrent observe block, driven
    through `run_pipeline` with real bindings whose real, deliberately
    staggered `time.sleep` durations make Step C record the 5 checks in a
    real completion order that is NOT their declared structural order
    (`status < namespace < deployments < pods < services`) -- proving
    `check_ocel_conformance`'s "lexicographically-smallest matching path
    first" tie-break correctly accepts whichever legal relative order the
    real concurrent dispatch actually produced, not one hardcoded order."""
    gate = CapabilityGate.from_toml(DEFAULT_MANIFEST_PATH)
    # Deliberately NOT declaration order: services (fastest) finishes well
    # before status (slowest), inverting the structural declaration order
    # for at least that pair.
    action_bindings = {
        GYMACT_CHECK_STATUS_LABEL: _staggered_binding(gate, "observe_cluster_state", 0.09),
        GYMACT_CHECK_NAMESPACE_LABEL: _staggered_binding(gate, "run_kubectl", 0.07),
        GYMACT_CHECK_DEPLOYMENTS_LABEL: _staggered_binding(gate, "run_kubectl", 0.05),
        GYMACT_CHECK_PODS_LABEL: _staggered_binding(gate, "run_kubectl", 0.03),
        GYMACT_CHECK_SERVICES_LABEL: _staggered_binding(gate, "run_kubectl", 0.01),
    }

    node = build_pipeline_powl_node()
    log, result = run_pipeline(
        node,
        session_id="conformance-staggered-concurrent",
        action_bindings=action_bindings,
        allow_partial_bindings=True,
    )
    assert result.final is True

    check_labels = {
        GYMACT_CHECK_STATUS_LABEL,
        GYMACT_CHECK_NAMESPACE_LABEL,
        GYMACT_CHECK_DEPLOYMENTS_LABEL,
        GYMACT_CHECK_PODS_LABEL,
        GYMACT_CHECK_SERVICES_LABEL,
    }
    observed_labels = observed_labels_from_events(log.events)
    observed_check_order = [label for label in observed_labels if label in check_labels]
    assert set(observed_check_order) == check_labels, "all 5 real checks must have really fired"

    result = check_ocel_conformance(node, log.events)
    assert result.conforms is True
    assert result.final is True
    assert result.divergence_index is None
    assert result.divergence_label is None
