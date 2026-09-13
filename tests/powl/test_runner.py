# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for the concurrent POWL 2.0 runner.

No mocks or monkeypatches: each test runs a real thread pool, real POWL model,
and a small concrete driver implementation. Barriers/events make concurrency
a final-state property rather than an interaction assertion.
"""

from __future__ import annotations

from collections import Counter
from threading import Barrier, Event, Lock, current_thread

from autofde_lab.powl.algebra import (
    Atom,
    ChoiceGraph,
    ChoiceGraphEdge,
    NodeId,
    OrderEdge,
    PartialOrder,
    Silent,
)
from autofde_lab.powl.executor import is_final, replay
from autofde_lab.powl.runner import (
    ActivityIntent,
    ActivityOutcome,
    ChoiceDecision,
    PowlV2Runner,
    RunnerConfig,
    RunnerRefusal,
    RunnerRefused,
    RunStatus,
)


def _oe(a: int, b: int) -> OrderEdge:
    return OrderEdge(NodeId(a), NodeId(b))


def _ce(a: int, b: int) -> ChoiceGraphEdge:
    return ChoiceGraphEdge(NodeId(a), NodeId(b))


class SuccessDriver:
    def __init__(self) -> None:
        self.labels: list[str] = []
        self._lock = Lock()

    def execute(self, intent: ActivityIntent) -> ActivityOutcome:
        with self._lock:
            self.labels.append(intent.label)
        return ActivityOutcome(
            authority_receipt=f"test:{intent.label}:{intent.attempt}"
        )


class Pick:
    def __init__(self, index: int) -> None:
        self.index = index
        self.decisions: list[ChoiceDecision] = []

    def choose(self, decision: ChoiceDecision) -> int:
        self.decisions.append(decision)
        return self.index


def test_runner_eagerly_starts_exactly_eight_workers_by_default():
    with PowlV2Runner() as runner:
        assert runner.config.max_workers == 8
        assert len(runner.worker_threads) == 8
        assert all(name.startswith("powl-v2") for name in runner.worker_threads)


def test_eight_unordered_activities_are_physically_concurrent():
    barrier = Barrier(8, timeout=10)
    names: set[str] = set()
    lock = Lock()

    class BarrierDriver:
        def execute(self, intent: ActivityIntent) -> ActivityOutcome:
            with lock:
                names.add(current_thread().name)
            barrier.wait()
            return ActivityOutcome(authority_receipt=f"test:{intent.label}")

    model = PartialOrder(tuple(Atom(f"a{i}") for i in range(8)))
    with PowlV2Runner() as runner:
        evidence = runner.run(model, BarrierDriver(), run_id="eight-wide")

    assert evidence.status is RunStatus.COMPLETED
    assert is_final(model, evidence.final_marking)
    assert evidence.peak_concurrency == 8
    assert len(names) == 8
    assert len(evidence.worker_threads) == 8
    assert len(evidence.activity_records) == 8
    assert evidence.failed_activities == 0


def test_sixteen_way_fanout_never_exceeds_the_eight_worker_bound():
    first_wave = Barrier(8, timeout=10)
    lock = Lock()
    calls = 0

    class WideDriver:
        def execute(self, intent: ActivityIntent) -> ActivityOutcome:
            nonlocal calls
            with lock:
                calls += 1
                ordinal = calls
            if ordinal <= 8:
                first_wave.wait()
            return ActivityOutcome()

    model = PartialOrder(tuple(Atom(f"a{i}") for i in range(16)))
    with PowlV2Runner() as runner:
        evidence = runner.run(model, WideDriver(), run_id="sixteen-wide")

    assert evidence.status is RunStatus.COMPLETED
    assert evidence.peak_concurrency == 8
    assert len(evidence.activity_records) == 16


def test_scheduler_replenishes_freed_capacity_without_waiting_for_a_wave():
    successor_started = Event()

    class PipelineDriver:
        def execute(self, intent: ActivityIntent) -> ActivityOutcome:
            if intent.label == "slow-independent":
                assert successor_started.wait(10), (
                    "dependent successor did not start while independent work was still "
                    "running; runner regressed to wave/barrier scheduling"
                )
            elif intent.label == "successor":
                successor_started.set()
            return ActivityOutcome()

    chain = PartialOrder(
        (Atom("predecessor"), Atom("successor")),
        frozenset({_oe(0, 1)}),
    )
    model = PartialOrder((chain, Atom("slow-independent")))
    with PowlV2Runner() as runner:
        evidence = runner.run(model, PipelineDriver(), run_id="dynamic-refill")

    assert evidence.status is RunStatus.COMPLETED
    assert successor_started.is_set()
    assert evidence.peak_concurrency >= 2


def test_precedence_is_never_bypassed_for_concurrency():
    driver = SuccessDriver()
    model = PartialOrder(
        (Atom("a"), Atom("b"), Atom("c")),
        frozenset({_oe(0, 1), _oe(1, 2)}),
    )
    with PowlV2Runner() as runner:
        evidence = runner.run(model, driver, run_id="chain")

    assert evidence.status is RunStatus.COMPLETED
    assert driver.labels == ["a", "b", "c"]
    assert evidence.peak_concurrency == 1


def _xor() -> ChoiceGraph:
    return ChoiceGraph(
        (Silent(), Silent(), Atom("left"), Atom("right")),
        frozenset({_ce(0, 2), _ce(0, 3), _ce(2, 1), _ce(3, 1)}),
        start=0,
        end=1,
    )


def test_ambiguous_choice_is_refused_without_a_select_policy():
    driver = SuccessDriver()
    model = _xor()
    with PowlV2Runner() as runner:
        evidence = runner.run(model, driver, run_id="choice-refusal")

    assert evidence.status is RunStatus.REFUSED
    assert evidence.refusal is RunnerRefusal.CHOICE_POLICY_REQUIRED
    assert driver.labels == []


def test_explicit_choice_policy_selects_one_branch_and_replay_closes():
    driver = SuccessDriver()
    policy = Pick(3)
    model = _xor()
    with PowlV2Runner() as runner:
        evidence = runner.run(
            model,
            driver,
            choice_policy=policy,
            run_id="choice-right",
        )

    assert evidence.status is RunStatus.COMPLETED
    assert driver.labels == ["right"]
    assert len(policy.decisions) == 1
    assert policy.decisions[0].candidates == (2, 3)
    assert evidence.policy_records[0].chosen == 3
    assert replay(model, evidence.structural_records) == evidence.final_marking


def test_selected_choice_child_preserves_internal_parallelism():
    barrier = Barrier(2, timeout=10)

    class TwoWideDriver:
        def execute(self, intent: ActivityIntent) -> ActivityOutcome:
            barrier.wait()
            return ActivityOutcome()

    parallel = PartialOrder((Atom("x"), Atom("y")))
    model = ChoiceGraph(
        (Silent(), Silent(), parallel, Atom("other")),
        frozenset({_ce(0, 2), _ce(0, 3), _ce(2, 1), _ce(3, 1)}),
        start=0,
        end=1,
    )
    with PowlV2Runner() as runner:
        evidence = runner.run(model, TwoWideDriver(), choice_policy=Pick(2))

    assert evidence.status is RunStatus.COMPLETED
    assert evidence.peak_concurrency == 2
    assert Counter(r.label for r in evidence.activity_records) == Counter(
        {"x": 1, "y": 1}
    )


def test_runner_never_invokes_atom_action_payload_directly():
    action_calls = 0

    def dangerous_action() -> None:
        nonlocal action_calls
        action_calls += 1
        raise AssertionError("Atom.action must not be invoked by the POWL runner")

    class InspectingDriver:
        def execute(self, intent: ActivityIntent) -> ActivityOutcome:
            assert intent.action is dangerous_action
            return ActivityOutcome()

    model = PartialOrder(
        (
            Atom("a", action=dangerous_action),
            Atom("b", action=dangerous_action),
        )
    )
    with PowlV2Runner() as runner:
        evidence = runner.run(model, InspectingDriver())

    assert evidence.status is RunStatus.COMPLETED
    assert action_calls == 0


def test_retry_reexecutes_same_activity_without_structural_advance():
    attempts: Counter[str] = Counter()

    class FlakyDriver:
        def execute(self, intent: ActivityIntent) -> ActivityOutcome:
            attempts[intent.label] += 1
            if attempts[intent.label] == 1:
                raise RuntimeError("transient")
            return ActivityOutcome()

    model = PartialOrder((Atom("a"), Atom("b")))
    config = RunnerConfig(max_attempts=2, fail_fast=False)
    with PowlV2Runner(config) as runner:
        evidence = runner.run(model, FlakyDriver())

    assert evidence.status is RunStatus.COMPLETED
    assert attempts == Counter({"a": 2, "b": 2})
    assert len(evidence.activity_records) == 4
    assert sum(not item.success for item in evidence.activity_records) == 2
    assert is_final(model, evidence.final_marking)


def test_terminal_activity_failure_blocks_dependents():
    class FailingDriver(SuccessDriver):
        def execute(self, intent: ActivityIntent) -> ActivityOutcome:
            if intent.label == "a":
                raise RuntimeError("permanent")
            return super().execute(intent)

    model = PartialOrder((Atom("a"), Atom("dependent")), frozenset({_oe(0, 1)}))
    with PowlV2Runner(RunnerConfig(fail_fast=False)) as runner:
        evidence = runner.run(model, FailingDriver())

    assert evidence.status is RunStatus.FAILED
    assert evidence.failed_activities == 1
    assert all(record.label != "dependent" for record in evidence.activity_records)
    assert not is_final(model, evidence.final_marking)


def test_atom_requires_an_explicit_external_driver():
    model = PartialOrder((Atom("a"), Atom("b")))
    with PowlV2Runner() as runner:
        evidence = runner.run(model, None)

    assert evidence.status is RunStatus.REFUSED
    assert evidence.refusal is RunnerRefusal.ACTIVITY_DRIVER_REQUIRED


def test_structural_only_model_needs_no_driver():
    model = PartialOrder((Silent(), Silent()))
    with PowlV2Runner() as runner:
        evidence = runner.run(model, None)

    assert evidence.status is RunStatus.COMPLETED
    assert evidence.activity_records == ()
    assert is_final(model, evidence.final_marking)


def test_invalid_policy_choice_is_typed_refusal():
    model = _xor()
    with PowlV2Runner() as runner:
        evidence = runner.run(model, SuccessDriver(), choice_policy=Pick(99))

    assert evidence.status is RunStatus.REFUSED
    assert evidence.refusal is RunnerRefusal.INVALID_CHOICE


def test_closed_runner_refuses_reuse():
    runner = PowlV2Runner()
    runner.close()
    model = PartialOrder((Silent(), Silent()))
    try:
        runner.run(model, None)
    except RunnerRefused as exc:
        assert exc.refusal is RunnerRefusal.RUNNER_CLOSED
    else:
        raise AssertionError("closed runner was reused")
