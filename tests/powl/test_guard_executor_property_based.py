# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Property-based generative tests for `guard_executor.py`'s five
capabilities, mirroring `test_runner_concurrency_property_based.py`'s idiom:
`random.Random(<fixed literal seed>)` exclusively (never the unseeded global
`random` module), 30+ structures per test, real collaborators throughout.

No mocks/monkeypatches anywhere in this file.
"""

from __future__ import annotations

import random
import threading
import time

from autofde_lab.powl.algebra import Atom, NodeId, OrderEdge, PartialOrder
from autofde_lab.powl.frequency import Frequency
from autofde_lab.powl.guard_executor import ExecutionContext, execute
from autofde_lab.powl.refusals import PowlError

_NUM_STRUCTURES = 30


# ---------------------------------------------------------------------------
# 1. Frequency: min always honored, max never exceeded, oracle = Frequency.allows
# ---------------------------------------------------------------------------


def test_frequency_repetition_count_always_satisfies_frequency_allows() -> None:
    rng = random.Random(20260810001)
    failures: list[str] = []

    for i in range(_NUM_STRUCTURES):
        freq_min = rng.randint(0, 3)
        freq_max = freq_min + rng.randint(0, 3)
        freq = Frequency(min=freq_min, max=freq_max)
        target_reps = rng.randint(0, freq_max + 2)  # may exceed max -- evaluator must be capped by the runner

        node = PartialOrder(
            children=(Atom(label=f"s{i}_a"), Atom(label=f"s{i}_b")),
            order=frozenset([OrderEdge(NodeId(0), NodeId(1))]),
            frequency=freq,
        )

        def repeat_evaluator(_composite_id, completed: int, target=target_reps) -> bool:
            return completed < target

        calls: list[str] = []

        def invoker(atom: Atom) -> str:
            calls.append(atom.label)
            return "ok"

        execute(node, guard_evaluator=lambda n, a: True, atom_invoker=invoker, max_choice_transitions=10, repeat_evaluator=repeat_evaluator)

        real_reps = len(calls) // 2
        if not freq.allows(real_reps):
            failures.append(f"structure {i}: freq={freq} real_reps={real_reps} target={target_reps} -- Frequency.allows() rejects the real repetition count")
        if real_reps < freq_min:
            failures.append(f"structure {i}: real_reps={real_reps} < min={freq_min}")
        if real_reps > freq_max:
            failures.append(f"structure {i}: real_reps={real_reps} > max={freq_max}")

    assert not failures, "\n".join(failures)


# ---------------------------------------------------------------------------
# 2. Concurrency: trace order always deterministic sorted-index order,
#    regardless of max_workers; real distinct thread ids when width>1
# ---------------------------------------------------------------------------


def test_concurrent_trace_order_is_always_deterministic_regardless_of_max_workers() -> None:
    rng = random.Random(20260810002)
    failures: list[str] = []

    for i in range(_NUM_STRUCTURES):
        width = rng.randint(2, 6)
        max_workers = rng.choice([1, 2, 4, width, width * 2])
        children = tuple(Atom(label=f"s{i}_a{j}") for j in range(width))
        node = PartialOrder(children=children)  # no order edges -- one full ready set

        thread_ids: set[int] = set()
        lock = threading.Lock()

        def invoker(atom: Atom) -> str:
            time.sleep(0.005)  # widen the concurrency window -- instant no-delay
            # invocations can all land on one pool worker before the others
            # wake, which is a real scheduling artifact, not a guard_executor
            # bug (see test_guard_executor_chicago.py's identical technique).
            with lock:
                thread_ids.add(threading.get_ident())
            return atom.label

        trace = execute(node, guard_evaluator=lambda n, a: True, atom_invoker=invoker, max_choice_transitions=10, max_workers=max_workers)

        labels = [s.label for s in trace.steps if s.kind == "Atom"]
        expected = [f"s{i}_a{j}" for j in range(width)]
        if labels != expected:
            failures.append(f"structure {i}: max_workers={max_workers} width={width} trace order {labels} != expected {expected}")

        if max_workers > 1 and width > 1 and len(thread_ids) < 2:
            failures.append(f"structure {i}: max_workers={max_workers} width={width} but only {len(thread_ids)} distinct thread(s) observed")

    assert not failures, "\n".join(failures)


# ---------------------------------------------------------------------------
# 3. Failure: partial_trace always contains exactly the atoms genuinely
#    invoked before the failure, real order, failing one marked failed=True
# ---------------------------------------------------------------------------


def test_partial_trace_on_failure_always_matches_the_real_atoms_invoked_before_it() -> None:
    rng = random.Random(20260810003)
    failures: list[str] = []

    for i in range(_NUM_STRUCTURES):
        n = rng.randint(2, 8)
        fail_at = rng.randint(0, n - 1)
        children = tuple(Atom(label=f"s{i}_a{j}") for j in range(n))
        edges = frozenset(OrderEdge(NodeId(j), NodeId(j + 1)) for j in range(n - 1))
        node = PartialOrder(children=children, order=edges)

        invoked_before_failure: list[str] = []

        def invoker(atom: Atom, fail_label=f"s{i}_a{fail_at}") -> str:
            if atom.label == fail_label:
                raise RuntimeError("real seeded failure")
            invoked_before_failure.append(atom.label)
            return "ok"

        try:
            execute(node, guard_evaluator=lambda n, a: True, atom_invoker=invoker, max_choice_transitions=10)
            failures.append(f"structure {i}: expected PowlError, none raised")
            continue
        except PowlError as exc:
            partial = exc.partial_trace

        if partial is None:
            failures.append(f"structure {i}: partial_trace is None")
            continue

        atom_steps = [s for s in partial.steps if s.kind == "Atom"]
        expected_labels = [f"s{i}_a{j}" for j in range(fail_at)] + [f"s{i}_a{fail_at}"]
        real_labels = [s.label for s in atom_steps]
        if real_labels != expected_labels:
            failures.append(f"structure {i}: partial_trace labels {real_labels} != expected {expected_labels}")
        if atom_steps and not atom_steps[-1].failed:
            failures.append(f"structure {i}: last step {atom_steps[-1].label!r} not marked failed=True")
        if any(s.failed for s in atom_steps[:-1]):
            failures.append(f"structure {i}: an earlier, genuinely-succeeded step is incorrectly marked failed=True")

    assert not failures, "\n".join(failures)


# ---------------------------------------------------------------------------
# 4. Checkpoint/resume: resuming from ANY on_step checkpoint never re-invokes
#    an atom the cursor already marked completed
# ---------------------------------------------------------------------------


def test_resume_from_any_captured_checkpoint_never_reinvokes_already_completed_atoms() -> None:
    rng = random.Random(20260810004)
    failures: list[str] = []

    for i in range(_NUM_STRUCTURES):
        n = rng.randint(3, 6)
        children = tuple(Atom(label=f"s{i}_a{j}") for j in range(n))
        edges = frozenset(OrderEdge(NodeId(j), NodeId(j + 1)) for j in range(n - 1))
        node = PartialOrder(children=children, order=edges)

        checkpoints = []

        def invoker(atom: Atom) -> str:
            return "ok"

        execute(node, guard_evaluator=lambda n, a: True, atom_invoker=invoker, max_choice_transitions=10, on_step=checkpoints.append)

        # Resume from a random mid-walk checkpoint (not the last one, which
        # would have nothing left to resume).
        if len(checkpoints) < 2:
            continue
        pick = rng.randint(0, len(checkpoints) - 2)
        checkpoint = checkpoints[pick]

        if checkpoint.cursor[0] != "partial_order":
            continue  # only meaningful for this fixture's top-level kind
        already_completed = checkpoint.cursor[1]

        second_calls: list[str] = []

        def real_invoker(atom: Atom, calls=second_calls) -> str:
            calls.append(atom.label)
            return "ok"

        execute(node, guard_evaluator=lambda n, a: True, atom_invoker=real_invoker, max_choice_transitions=10, resume_from=checkpoint)

        reinvoked = {children[idx].label for idx in already_completed} & set(second_calls)
        if reinvoked:
            failures.append(f"structure {i}: resume re-invoked already-completed atoms {reinvoked}")

    assert not failures, "\n".join(failures)


# ---------------------------------------------------------------------------
# 5. ExecutionContext.history is always exactly trace.steps component-wise
# ---------------------------------------------------------------------------


def test_execution_context_history_always_mirrors_trace_steps() -> None:
    rng = random.Random(20260810005)
    failures: list[str] = []

    for i in range(_NUM_STRUCTURES):
        n = rng.randint(2, 6)
        children = tuple(Atom(label=f"s{i}_a{j}") for j in range(n))
        node = PartialOrder(children=children)
        context = ExecutionContext()

        def invoker(atom: Atom) -> str:
            return "ok"

        trace = execute(node, guard_evaluator=lambda n, a: True, atom_invoker=invoker, max_choice_transitions=10, context=context)

        if list(context.history) != list(trace.steps):
            failures.append(f"structure {i}: context.history != trace.steps")

    assert not failures, "\n".join(failures)
