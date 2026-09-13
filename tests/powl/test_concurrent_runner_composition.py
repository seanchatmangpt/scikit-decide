"""Current-master composition court for the preserved POWL v2 concurrent runner.

The runner was imported from the exact-head-qualified PR #48 artifact rather
than overwriting the newer pipeline runner.  These Chicago-style tests prove
that artifact still composes with the current POWL algebra/executor surface.
"""

from __future__ import annotations

from threading import Barrier, Lock, current_thread

from autofde_lab.powl.algebra import (
    Atom,
    ChoiceGraph,
    ChoiceGraphEdge,
    NodeId,
    OrderEdge,
    PartialOrder,
    Silent,
)
from autofde_lab.powl.concurrent_runner import (
    ActivityIntent,
    ActivityOutcome,
    ChoiceDecision,
    PowlV2Runner,
    RunnerRefusal,
    RunStatus,
)
from autofde_lab.powl.executor import is_final, replay


def _order(src: int, dst: int) -> OrderEdge:
    return OrderEdge(NodeId(src), NodeId(dst))


def _choice(src: int, dst: int) -> ChoiceGraphEdge:
    return ChoiceGraphEdge(NodeId(src), NodeId(dst))


class ReceiptDriver:
    def __init__(self) -> None:
        self.labels: list[str] = []
        self._lock = Lock()

    def execute(self, intent: ActivityIntent) -> ActivityOutcome:
        with self._lock:
            self.labels.append(intent.label)
        return ActivityOutcome(
            authority_receipt=f"bounded-test-receipt:{intent.run_id}:{intent.label}"
        )


class Pick:
    def __init__(self, index: int) -> None:
        self.index = index
        self.decisions: list[ChoiceDecision] = []

    def choose(self, decision: ChoiceDecision) -> int:
        self.decisions.append(decision)
        return self.index


def test_current_master_composes_with_eight_way_physical_concurrency() -> None:
    barrier = Barrier(8, timeout=10)
    workers: set[str] = set()
    lock = Lock()

    class BarrierDriver:
        def execute(self, intent: ActivityIntent) -> ActivityOutcome:
            with lock:
                workers.add(current_thread().name)
            barrier.wait()
            return ActivityOutcome(
                authority_receipt=f"bounded-test-receipt:{intent.label}"
            )

    model = PartialOrder(tuple(Atom(f"sony-rail-{index}") for index in range(8)))
    with PowlV2Runner() as runner:
        evidence = runner.run(model, BarrierDriver(), run_id="composition-eight-wide")

    assert evidence.status is RunStatus.COMPLETED
    assert evidence.peak_concurrency == 8
    assert len(workers) == 8
    assert len(evidence.worker_threads) == 8
    assert len(evidence.activity_records) == 8
    assert all(record.authority_receipt for record in evidence.activity_records)
    assert is_final(model, evidence.final_marking)
    assert replay(model, evidence.structural_records) == evidence.final_marking


def test_current_master_preserves_precedence_and_receipts() -> None:
    driver = ReceiptDriver()
    model = PartialOrder(
        (Atom("discover"), Atom("construct"), Atom("verify")),
        frozenset({_order(0, 1), _order(1, 2)}),
    )

    with PowlV2Runner() as runner:
        evidence = runner.run(model, driver, run_id="composition-precedence")

    assert evidence.status is RunStatus.COMPLETED
    assert evidence.peak_concurrency == 1
    assert driver.labels == ["discover", "construct", "verify"]
    assert all(record.authority_receipt for record in evidence.activity_records)
    assert replay(model, evidence.structural_records) == evidence.final_marking


def test_current_master_refuses_ambient_choice_authority() -> None:
    model = ChoiceGraph(
        (Silent(), Silent(), Atom("left"), Atom("right")),
        frozenset(
            {
                _choice(0, 2),
                _choice(0, 3),
                _choice(2, 1),
                _choice(3, 1),
            }
        ),
        start=0,
        end=1,
    )

    with PowlV2Runner() as runner:
        refused = runner.run(model, ReceiptDriver(), run_id="composition-refusal")

    assert refused.status is RunStatus.REFUSED
    assert refused.refusal is RunnerRefusal.CHOICE_POLICY_REQUIRED
    assert refused.activity_records == ()

    driver = ReceiptDriver()
    policy = Pick(3)
    with PowlV2Runner() as runner:
        admitted = runner.run(
            model,
            driver,
            choice_policy=policy,
            run_id="composition-explicit-select",
        )

    assert admitted.status is RunStatus.COMPLETED
    assert driver.labels == ["right"]
    assert policy.decisions[0].candidates == (2, 3)
    assert admitted.policy_records[0].chosen == 3
    assert replay(model, admitted.structural_records) == admitted.final_marking
