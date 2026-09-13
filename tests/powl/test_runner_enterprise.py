# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Enterprise failure/iteration courts for the concurrent POWL runner."""

from __future__ import annotations

from threading import Barrier

from autofde_lab.powl.algebra import (
    Atom,
    ChoiceGraph,
    ChoiceGraphEdge,
    NodeId,
    PartialOrder,
    Silent,
)
from autofde_lab.powl.executor import replay
from autofde_lab.powl.runner import (
    ActivityIntent,
    ActivityOutcome,
    ChoiceDecision,
    PowlV2Runner,
    RunnerRefusal,
    RunStatus,
)


def _ce(a: int, b: int) -> ChoiceGraphEdge:
    return ChoiceGraphEdge(NodeId(a), NodeId(b))


def test_fail_fast_drains_every_already_dispatched_activity_into_evidence():
    barrier = Barrier(2, timeout=10)

    class OneFailsOneSucceeds:
        def execute(self, intent: ActivityIntent) -> ActivityOutcome:
            barrier.wait()
            if intent.label == "fail":
                raise RuntimeError("boom")
            return ActivityOutcome(
                authority_receipt="test:success",
                metadata={"observed": True},
            )

    model = PartialOrder((Atom("fail"), Atom("succeed")))
    with PowlV2Runner() as runner:
        evidence = runner.run(model, OneFailsOneSucceeds(), run_id="fail-fast-drain")

    assert evidence.status is RunStatus.FAILED
    assert evidence.peak_concurrency == 2
    assert len(evidence.activity_records) == 2
    by_label = {record.label: record for record in evidence.activity_records}
    assert by_label["fail"].success is False
    assert by_label["fail"].committed is False
    assert by_label["succeed"].success is True
    assert by_label["succeed"].committed is True
    assert by_label["succeed"].authority_receipt == "test:success"
    assert by_label["succeed"].metadata == {"observed": True}
    assert evidence.committed_activities == 1
    assert replay(model, evidence.structural_records) == evidence.final_marking


def test_cyclic_choice_graph_runs_iteration_then_exits_by_explicit_policy():
    class Driver:
        def __init__(self) -> None:
            self.labels: list[str] = []

        def execute(self, intent: ActivityIntent) -> ActivityOutcome:
            self.labels.append(intent.label)
            return ActivityOutcome()

    class LoopOnceThenExit:
        def __init__(self) -> None:
            self.choices: list[int] = []

        def choose(self, decision: ChoiceDecision) -> int:
            visits_to_body = decision.marking.visits.get(((), 2), 0)
            chosen = 3 if visits_to_body < 2 else 1
            self.choices.append(chosen)
            return chosen

    model = ChoiceGraph(
        (Silent(), Silent(), Atom("a"), Atom("b")),
        frozenset({_ce(0, 2), _ce(2, 3), _ce(3, 2), _ce(2, 1)}),
        start=0,
        end=1,
    )
    driver = Driver()
    policy = LoopOnceThenExit()
    with PowlV2Runner() as runner:
        evidence = runner.run(model, driver, choice_policy=policy, run_id="cycle")

    assert evidence.status is RunStatus.COMPLETED
    assert driver.labels == ["a", "b", "a"]
    assert policy.choices == [3, 1]
    assert replay(model, evidence.structural_records) == evidence.final_marking


def test_choice_policy_exception_becomes_typed_refusal():
    class ExplodingPolicy:
        def choose(self, decision: ChoiceDecision) -> int:
            raise ValueError("policy unavailable")

    class Driver:
        def execute(self, intent: ActivityIntent) -> ActivityOutcome:
            return ActivityOutcome()

    model = ChoiceGraph(
        (Silent(), Silent(), Atom("left"), Atom("right")),
        frozenset({_ce(0, 2), _ce(0, 3), _ce(2, 1), _ce(3, 1)}),
        start=0,
        end=1,
    )
    with PowlV2Runner() as runner:
        evidence = runner.run(model, Driver(), choice_policy=ExplodingPolicy())

    assert evidence.status is RunStatus.REFUSED
    assert evidence.refusal is RunnerRefusal.POLICY_FAILED
    assert "ValueError" in evidence.detail
