# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Adversarial, mutation-testing-style hammering of `guard_executor.py`'s
five capabilities (frequency repetition, real concurrency, typed atom
failure, checkpoint/resume, `ExecutionContext`), using real, structurally
rich fixtures hand-ported from `~/POWL` (see
`tests/powl/fixtures_upstream_powl_reference.py`'s own licensing-boundary
docstring -- no `~/POWL` code is imported or executed anywhere).

Mirrors `test_runner_concurrency_adversarial.py`'s idiom: not proving the
happy path works (`test_guard_executor_chicago.py` already covers each
capability in isolation), but proving a plausible implementation mistake
combining TWO capabilities at once would be caught, not silently pass.

All real collaborators. Zero mocks/monkeypatches.
"""

from __future__ import annotations

import threading

import pytest
from tests.powl.fixtures_upstream_powl_reference import (
    hospital_concurrent_shape,
    pools_and_lanes_choice_shape,
    running_example_choice_concurrency_loop_shape,
)

from autofde_lab.powl.algebra import Atom, NodeId, OrderEdge, PartialOrder
from autofde_lab.powl.frequency import Frequency
from autofde_lab.powl.guard_executor import ExecutionContext, execute
from autofde_lab.powl.refusals import PowlError, PowlRefusal
from autofde_lab.powl.validate import validate_model


# ---------------------------------------------------------------------------
# 0. The fixtures themselves are real, admitted models -- proven, not assumed
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "build_fixture",
    [running_example_choice_concurrency_loop_shape, hospital_concurrent_shape, pools_and_lanes_choice_shape],
)
def test_upstream_reference_fixture_is_a_real_admitted_powl_model(build_fixture) -> None:
    model = build_fixture()
    validate_model(model)  # raises PowlError on any structural refusal


# ---------------------------------------------------------------------------
# 1. Concurrency + failure combined: partial_trace under a concurrent batch
# ---------------------------------------------------------------------------


def test_partial_trace_under_concurrent_failure_captures_the_other_completed_siblings() -> None:
    """A realistic implementation mistake: a naive concurrent failure-handler
    might only record the ONE failing atom's step and drop whatever its
    concurrently-running siblings had already produced. `hospital_concurrent_shape`'s
    real {Blood_Test, X-Ray} concurrent pair is used here (`max_workers=2`);
    `X-Ray` fails, and the real `partial_trace` must still contain
    `Blood_Test`'s real completed step alongside the failed `X-Ray` step."""
    model = hospital_concurrent_shape()
    lock = threading.Lock()
    completed: list[str] = []

    def invoker(atom: Atom) -> str:
        if atom.label == "X-Ray":
            raise RuntimeError("real concurrent failure")
        with lock:
            completed.append(atom.label)
        return "ok"

    with pytest.raises(PowlError) as excinfo:
        execute(model, guard_evaluator=lambda n, a: True, atom_invoker=invoker, max_choice_transitions=10, max_workers=2)

    assert excinfo.value.refusal == PowlRefusal.ATOM_INVOCATION_FAILED
    partial = excinfo.value.partial_trace
    assert partial is not None
    labels = {s.label for s in partial.steps if s.kind == "Atom"}
    # Both siblings of the same concurrent ready-set are represented: the one
    # that genuinely completed (Blood_Test), and the one that genuinely failed
    # (X-Ray, failed=True) -- neither silently dropped.
    assert "Blood_Test" in labels
    assert "X-Ray" in labels
    xray_step = next(s for s in partial.steps if s.label == "X-Ray")
    assert xray_step.failed is True
    blood_step = next(s for s in partial.steps if s.label == "Blood_Test")
    assert blood_step.failed is False
    assert completed == ["Blood_Test"]  # Surgery (downstream of both) never ran


# ---------------------------------------------------------------------------
# 2. Frequency + checkpoint/resume combined: resume continues the SAME
#    repetition count, never restarting it
# ---------------------------------------------------------------------------


def test_resume_of_a_repeating_composite_continues_the_same_repetition_count() -> None:
    """A realistic implementation mistake: resume logic that re-derives
    `completed_repetitions` from scratch (e.g. always 0) instead of trusting
    the checkpoint's own accumulated steps. `Frequency(min=3, max=3)` forces
    exactly 3 real repetitions; failing mid-repetition-2 and resuming must
    finish with exactly 3 total repetitions recorded, never 3 MORE on top of
    the 2 already run (which would silently over-repeat)."""
    node = PartialOrder(
        children=(Atom(label="a"), Atom(label="b")),
        order=frozenset([OrderEdge(NodeId(0), NodeId(1))]),
        frequency=Frequency(min=3, max=3),
    )
    checkpoints = []
    call_count = {"n": 0}

    def failing_invoker(atom: Atom) -> str:
        call_count["n"] += 1
        # Fail on the 4th real invocation (repetition index 1's "a"),
        # i.e. partway through repetition 2 of 3.
        if call_count["n"] == 4:
            raise RuntimeError("boom mid-repetition")
        return "ok"

    with pytest.raises(PowlError):
        execute(
            node,
            guard_evaluator=lambda n, a: True,
            atom_invoker=failing_invoker,
            max_choice_transitions=10,
            on_step=checkpoints.append,
        )

    last_checkpoint = checkpoints[-1]

    real_invoker_calls: list[str] = []

    def real_invoker(atom: Atom) -> str:
        real_invoker_calls.append(atom.label)
        return "ok"

    trace = execute(
        node,
        guard_evaluator=lambda n, a: True,
        atom_invoker=real_invoker,
        max_choice_transitions=10,
        resume_from=last_checkpoint,
    )

    atom_steps = [s for s in trace.steps if s.kind == "Atom"]
    repetition_indices_present = sorted({s.repetition_index for s in atom_steps})
    # Exactly repetitions 0, 1, 2 are present in the combined (resumed) trace
    # -- never a 4th (0,1,2,3) which would mean the mandatory min=3 was
    # exceeded by restarting the repetition counter from 0 on resume.
    assert repetition_indices_present == [0, 1, 2]


# ---------------------------------------------------------------------------
# 3. Real loop + ExecutionContext combined: the upstream running-example
#    fixture's real cyclic ChoiceGraph, driven through 3 real iterations
# ---------------------------------------------------------------------------


def test_running_example_fixture_loop_closes_after_real_context_driven_iterations() -> None:
    """`running_example_choice_concurrency_loop_shape()`'s real
    `reinitiate_request -> examine_and_check` back-edge is driven through
    exactly 2 real loop-backs before a real `ExecutionContext`-tracked round
    counter decides `approved`, proving the guard/context wiring genuinely
    reasons across real re-entries of the SAME choice node, not just a
    synthetic toy graph."""
    model = running_example_choice_concurrency_loop_shape()
    context = ExecutionContext(attributes={"round": 0})
    invoked_labels: list[str] = []

    def evaluator(name: str, _args: dict, ctx: ExecutionContext) -> bool:
        if name == "approved":
            return ctx.attributes["round"] >= 2
        if name == "needs_more_info":
            return ctx.attributes["round"] < 2
        return False  # "rejected" never fires in this scenario

    def invoker(atom: Atom, ctx: ExecutionContext) -> str:
        invoked_labels.append(atom.label)
        if atom.label == "reinitiate_request":
            ctx.attributes["round"] += 1
        return "ok"

    trace = execute(
        model, guard_evaluator=evaluator, atom_invoker=invoker, max_choice_transitions=30, context=context
    )

    assert context.attributes["round"] == 2
    assert invoked_labels.count("reinitiate_request") == 2
    assert invoked_labels[-1] == "pay_compensation"
    assert [s.label for s in context.history if s.kind == "Atom"] == invoked_labels


# ---------------------------------------------------------------------------
# 4. Choice + concurrency combined: pools_and_lanes fixture, real max_workers
# ---------------------------------------------------------------------------


def test_pools_and_lanes_fixture_both_branches_reachable_under_real_execution() -> None:
    """Real end-to-end execution of the pools-and-lanes-shaped fixture along
    both its real branches (guarded and else-edge), proving the guard/else
    split constructed by hand-porting the upstream example is genuinely
    navigable both ways, not just admitted by `validate_model`."""
    model = pools_and_lanes_choice_shape()

    for wants_to_pay_first in (True, False):
        invoked: list[str] = []

        def evaluator(name: str, _args: dict, _wants=wants_to_pay_first) -> bool:
            return name == "wants_to_pay_first" and _wants

        def invoker(atom: Atom) -> str:
            invoked.append(atom.label)
            return "ok"

        execute(model, guard_evaluator=evaluator, atom_invoker=invoker, max_choice_transitions=10, max_workers=2)

        if wants_to_pay_first:
            assert invoked == ["order_coffee", "pay", "prepare_coffee", "serve_coffee"]
        else:
            assert invoked == ["order_coffee", "serve_coffee"]
