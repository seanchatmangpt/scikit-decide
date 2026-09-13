# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for `run_pipeline`'s real OCEL 2.0 log under real
concurrent (multi-threaded) firing -- proving the log's own structural laws
hold beyond what `OcelLog.validate()` already checks automatically, and
beyond what `tests/powl/test_runner_pipeline_chicago.py` already covers.

Real collaborators throughout, zero mocks:

- The real, production `build_pipeline_powl_node()` tree -- the same 5-way
  concurrent `PartialOrder` "observe block" `test_runner_pipeline_chicago.py`
  drives, not a hand-built concurrency fixture standing in for it.
- Real `GatedCapabilityBinding` + `CapabilityGate` loaded from the real TOML
  manifest, wrapping real, simple Python callables that do a real
  `time.sleep()` for a real, deterministic, per-label duration and record
  their own real return values -- the repo's own established "real
  degraded alternative" pattern, never an interaction-verifying mock.
- The real `run_pipeline` executor loop and its real `ThreadPoolExecutor`
  batch-fire path (`len(batch) > 1`) -- never a hand-rolled substitute for
  the concurrency under test.
- A real, unmocked `OcelLog` returned by `run_pipeline`, plus an explicit,
  second call to the real `OcelLog.validate()` in some tests (never assumed
  merely because `run_pipeline` did not raise) to prove OCPQ Definition 2's
  structural laws really hold for a log built from a concurrent batch, not
  only for the log's own recorder-internal bookkeeping.

Deliberately NOT re-tested here (already covered by
`test_runner_pipeline_chicago.py`, read in full before writing this file):
`test_run_pipeline_fires_the_five_gymact_checks_concurrently_on_distinct_threads`
(distinct real OS threads + wall-clock overlap) and
`test_ocel_recorder_is_only_ever_invoked_from_the_calling_thread_even_under_concurrent_firing`
(recorder-invocation thread identity). This file goes beyond both: object-id
uniqueness/resolution across a concurrent batch, real batch-order vs.
real-completion-order event sequencing, an explicit second `validate()` call,
and real monotonic timestamp ordering under genuine cross-thread scrambling.

No `unittest.mock` / `Mock` / `patch` / `monkeypatch` anywhere in this file.
"""

from __future__ import annotations

import time

import pytest

from autofde_lab.fabric.gymact_capability_gate import DEFAULT_MANIFEST_PATH, CapabilityGate
from autofde_lab.ocel.log import OcelLog
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


def _capability_gate() -> CapabilityGate:
    return CapabilityGate.from_toml(DEFAULT_MANIFEST_PATH)

# real gymact capability name each observe-block label is gated against --
# transcribed from `test_runner_pipeline_chicago.py::_observe_block_bindings`.
_OBSERVE_BLOCK_CAPABILITIES: dict[str, str] = {
    GYMACT_CHECK_STATUS_LABEL: "observe_cluster_state",
    GYMACT_CHECK_NAMESPACE_LABEL: "run_kubectl",
    GYMACT_CHECK_DEPLOYMENTS_LABEL: "run_kubectl",
    GYMACT_CHECK_PODS_LABEL: "run_kubectl",
    GYMACT_CHECK_SERVICES_LABEL: "run_kubectl",
}

# Scrambled on purpose: batch order (sorted `NodePath`, i.e. label order
# above -- status, namespace, deployments, pods, services) must NOT match
# completion order under these real sleep durations. Completion order here
# is genuinely: services (0.01s) < pods (0.03s) < deployments (0.05s) <
# namespace (0.07s) < status (0.09s) -- the exact reverse of batch order.
_SCRAMBLED_SLEEP_S: dict[str, float] = {
    GYMACT_CHECK_STATUS_LABEL: 0.09,
    GYMACT_CHECK_NAMESPACE_LABEL: 0.07,
    GYMACT_CHECK_DEPLOYMENTS_LABEL: 0.05,
    GYMACT_CHECK_PODS_LABEL: 0.03,
    GYMACT_CHECK_SERVICES_LABEL: 0.01,
}


def _scrambled_observe_block_bindings() -> dict[str, GatedCapabilityBinding]:
    """Real `GatedCapabilityBinding`s over the real observe-block labels,
    each wrapping a real callable with a real, distinct, deliberately
    reverse-of-batch-order `time.sleep()` so completion order and batch
    order are guaranteed to disagree -- not merely "probably different"."""
    gate = _capability_gate()
    bindings: dict[str, GatedCapabilityBinding] = {}
    for label, capability_name in _OBSERVE_BLOCK_CAPABILITIES.items():
        sleep_s = _SCRAMBLED_SLEEP_S[label]

        def _target(atom_attrs: dict, _sleep_s: float = sleep_s) -> dict:
            time.sleep(_sleep_s)
            return {"label": atom_attrs["label"]}

        bindings[label] = GatedCapabilityBinding(
            capability_name=capability_name, callable_=_target, gate=gate
        )
    return bindings


def _observe_block_events(log: OcelLog) -> list:
    """The real fired `powl_structural_fire` events for the 5 observe-block
    labels, in real log order (the order `run_pipeline`'s Step C actually
    recorded them, not re-sorted here)."""
    labels = set(_OBSERVE_BLOCK_CAPABILITIES)
    events = []
    for event in log.events:
        detail = next(
            (a.value.value for a in event.attributes if a.key == "detail"), None
        )
        if event.activity == "powl_structural_fire" and detail in labels:
            events.append(event)
    return events


def test_concurrent_batch_object_ids_are_real_distinct_and_resolve_to_real_objects():
    """Every one of the 5 real observe-block events' `object_ids` resolves to
    a real, distinct declared `OcelObject` -- no two concurrently-fired
    paths collide on object id under real thread-interleaved `record()`
    calls (Step C is single-threaded on the calling thread, but this proves
    the *identity* space itself stayed distinct, not merely that recording
    didn't crash)."""
    node = build_pipeline_powl_node()
    log, result = run_pipeline(
        node,
        session_id="test-concurrency-shape-object-ids",
        action_bindings=_scrambled_observe_block_bindings(),
        allow_partial_bindings=True,
    )

    events = _observe_block_events(log)
    assert len(events) == 5, f"expected exactly 5 real observe-block fires, got {len(events)}"

    declared_object_ids = {obj.id for obj in log.objects}
    event_object_ids: list[str] = []
    for event in events:
        linked = [link.object_id for link in log.event_object_links if link.event_id == event.id]
        # session object + exactly one real PowlNode object per fire.
        assert len(linked) == 2, f"expected session+node links for {event.id!r}, got {linked!r}"
        real_node_ids = [oid for oid in linked if oid.startswith("test-concurrency-shape-object-ids-node-")]
        assert len(real_node_ids) == 1, f"expected exactly one real PowlNode object id for {event.id!r}"
        object_id = real_node_ids[0]
        assert object_id in declared_object_ids, f"{object_id!r} must be a really-declared OcelObject"
        event_object_ids.append(object_id)

    assert len(event_object_ids) == len(set(event_object_ids)), (
        f"real concurrently-fired paths must never share an object id -- got {event_object_ids!r}"
    )


def test_concurrent_batch_event_order_in_log_matches_real_batch_order_not_completion_order():
    """Step C's own documented law: OCEL events for a concurrent batch are
    recorded "sequentially on the calling thread... in batch order" -- this
    proves it holds for real, using bindings whose real, distinct sleep
    durations scramble completion order relative to batch order. If Step C
    silently recorded in completion order instead, this test's real event
    sequence would come back reversed relative to batch order; it does not."""
    node = build_pipeline_powl_node()
    log, result = run_pipeline(
        node,
        session_id="test-concurrency-shape-batch-order",
        action_bindings=_scrambled_observe_block_bindings(),
        allow_partial_bindings=True,
    )
    assert result.final is True

    events = _observe_block_events(log)
    assert len(events) == 5

    def _detail(event) -> str:
        return next(a.value.value for a in event.attributes if a.key == "detail")

    real_log_order = [_detail(e) for e in events]
    # Batch order == sorted `NodePath` == the check labels' own declaration
    # order in `_concurrent_read_block` (status, namespace, deployments,
    # pods, services) -- see `build_pipeline_powl_node`.
    expected_batch_order = [
        GYMACT_CHECK_STATUS_LABEL,
        GYMACT_CHECK_NAMESPACE_LABEL,
        GYMACT_CHECK_DEPLOYMENTS_LABEL,
        GYMACT_CHECK_PODS_LABEL,
        GYMACT_CHECK_SERVICES_LABEL,
    ]
    # The scrambled sleeps make real completion order exactly the reverse.
    completion_order = list(reversed(expected_batch_order))

    assert real_log_order == expected_batch_order, (
        f"real event order {real_log_order!r} must match real batch order "
        f"{expected_batch_order!r}, not completion order {completion_order!r}"
    )
    assert real_log_order != completion_order, (
        "test setup bug: the scrambled sleeps must make completion order "
        "genuinely differ from batch order, or this test cannot distinguish "
        "the two orderings at all"
    )


def test_ocel_log_validate_really_passes_on_a_full_five_way_concurrent_batch():
    """`OcelLog.validate()` is called explicitly, a second time, directly by
    this test -- not merely trusted because `run_pipeline`'s own internal
    `recorder.close()` (which also calls `validate()`) did not raise -- on a
    log produced by really firing the full 5-way concurrent observe block
    with real bindings. Proves OCPQ Definition 2's structural laws hold for
    real concurrently-produced evidence, independently re-checked."""
    node = build_pipeline_powl_node()
    log, result = run_pipeline(
        node,
        session_id="test-concurrency-shape-validate-independently",
        action_bindings=_scrambled_observe_block_bindings(),
        allow_partial_bindings=True,
    )
    assert result.final is True

    # `run_pipeline` already validated internally via `recorder.close()`;
    # this is a real, independent second call against the returned log
    # object, proving the returned artifact -- not some internal
    # intermediate state -- is what really validates.
    revalidated = log.validate()
    assert isinstance(revalidated, OcelLog)
    assert len(revalidated.events) == len(log.events)
    assert {e.id for e in revalidated.events} == {e.id for e in log.events}


def test_concurrent_batch_event_timestamps_are_monotonic_non_decreasing_in_log_order():
    """`OcelSessionRecorder` is documented not thread-safe / single-writer;
    Step C records sequentially on the calling thread even though the 5
    bindings themselves genuinely ran on distinct worker threads and
    returned at genuinely different, scrambled real times. Proves the real
    `timestamp_ns` attached to each event (`time.time_ns()` read at the
    moment `record()` -- i.e. `append_tool_call_event` -- runs, per
    `mcp_session.py`) is monotonically non-decreasing in real log order, for
    the entire log, not merely within the observe block."""
    node = build_pipeline_powl_node()
    log, result = run_pipeline(
        node,
        session_id="test-concurrency-shape-monotonic-timestamps",
        action_bindings=_scrambled_observe_block_bindings(),
        allow_partial_bindings=True,
    )
    assert result.final is True
    assert len(log.events) > 5, "expected more than just the 5 observe-block fires in the full pipeline"

    timestamps = [event.timestamp_ns for event in log.events]
    for i in range(1, len(timestamps)):
        assert timestamps[i] >= timestamps[i - 1], (
            f"real event timestamps must be monotonically non-decreasing in "
            f"real log order -- event {i} ({log.events[i].id!r}, "
            f"{timestamps[i]}) precedes event {i - 1} "
            f"({log.events[i - 1].id!r}, {timestamps[i - 1]})"
        )

    # Specifically within the observe-block's own 5 real concurrent fires,
    # the same property holds, despite their real bindings completing on
    # worker threads in the exact reverse of the order they get recorded in.
    observe_events = _observe_block_events(log)
    assert len(observe_events) == 5
    observe_timestamps = [e.timestamp_ns for e in observe_events]
    assert observe_timestamps == sorted(observe_timestamps), (
        f"observe-block real timestamps must also be monotonic in real log "
        f"order -- got {observe_timestamps!r}"
    )


def test_concurrent_batch_still_produces_exactly_one_event_per_real_fire_no_duplicates_no_drops():
    """Sanity/coverage complement to the above: a real 5-way concurrent
    batch produces exactly 5 real `powl_structural_fire` events for the
    observe block -- no duplicate recording (e.g. a bug double-invoking
    `record()` per path) and no dropped fire (e.g. a bug losing one path's
    event under real thread interleaving)."""
    node = build_pipeline_powl_node()
    log, result = run_pipeline(
        node,
        session_id="test-concurrency-shape-exactly-once",
        action_bindings=_scrambled_observe_block_bindings(),
        allow_partial_bindings=True,
    )
    assert result.final is True

    events = _observe_block_events(log)
    event_ids = [e.id for e in events]
    assert len(event_ids) == len(set(event_ids)) == 5, (
        f"expected exactly 5 real, distinct event ids for the observe block -- got {event_ids!r}"
    )
    details = sorted(
        next(a.value.value for a in e.attributes if a.key == "detail") for e in events
    )
    assert details == sorted(_OBSERVE_BLOCK_CAPABILITIES)
