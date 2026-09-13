# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Adversarial, mutation-testing-style checks for the POWL v2 concurrent-runner
design described in the approved plan (see
``/Users/sac/.claude/plans/what-are-the-current-shimmying-bear.md``).

This file is deliberately ORTHOGONAL to the runner/driver implementation work
happening concurrently in ``src/autofde_lab/powl/runner.py``,
``src/autofde_lab/reasoning/gymact_diagnosis_driver.py``,
``tests/powl/test_runner_pipeline_chicago.py``, ``tests/powl/test_executor.py``,
and ``tests/reasoning/test_gymact_diagnosis_driver_chicago.py`` — none of those
five files are touched here. Instead, this file exercises only the stable,
read-only primitives in ``executor.py``/``algebra.py`` directly, constructing
BROKEN variants of the intended tree shape (a spurious order edge, leaking
closure state across sibling blocks, a partial AND-join, a double-fire) and
proving each broken variant is caught by real, state-based assertions on real
``Marking``/``enabled()``/``fire()`` output — not that the good design works
(sibling tests already cover that), but that a plausible implementation
mistake in building this design would be caught, not silently pass.

All real collaborators. Zero mocks/monkeypatches — see the module's own
zero-mock grep requirement in ``.claude/rules/testing-chicago-style.md``.
"""

from __future__ import annotations

import pytest

from autofde_lab.powl.algebra import Atom, NodeId, OrderEdge, PartialOrder
from autofde_lab.powl.executor import (
    INITIAL_MARKING,
    Marking,
    enabled,
    fire,
)
from autofde_lab.powl.refusals import PowlError, PowlRefusal


def _oe(a: int, b: int) -> OrderEdge:
    return OrderEdge(NodeId(a), NodeId(b))


def _labels(n: int, prefix: str) -> tuple[Atom, ...]:
    return tuple(Atom(label=f"{prefix}_{i}") for i in range(n))


# ── 1. spurious order edge between two "unordered" checks ───────────────────


def test_a_spurious_order_edge_between_two_checks_provably_serializes_them() -> None:
    """A realistic hand-building slip: passing ``order={OrderEdge(0, 1)}``
    instead of ``order=frozenset()`` when constructing a block meant to be
    fully concurrent (the exact shape ``build_pipeline_powl_node()`` builds
    for the observe/remediate blocks per the plan).

    If this test ever fails because someone "fixed" it to expect all 5 paths
    enabled at the start, that IS the point: it means the mistake this test
    targets was actually made in the real tree-construction code, and the
    real regression this test exists to catch has happened.
    """
    children = _labels(5, "check")
    # Deliberately broken: children 0 and 1 are (by mistake) ordered.
    broken = PartialOrder(children=children, order=frozenset({_oe(0, 1)}))

    live = enabled(broken, INITIAL_MARKING)

    # Only 4 of the 5 leaves are enabled at the initial marking: child 1 is
    # blocked behind child 0's completion. A correctly-unordered block would
    # enable all 5 simultaneously.
    assert len(live) == 4
    assert (0,) in live
    assert (1,) not in live  # the ordered pair's second member is NOT enabled yet
    assert (2,) in live
    assert (3,) in live
    assert (4,) in live

    # Firing child 0 is what unblocks child 1 — proving the order edge, not
    # some unrelated cause, is what withheld it.
    after = fire(broken, INITIAL_MARKING, (0,))
    live_after = enabled(broken, after)
    assert (1,) in live_after
    assert len(live_after) == 4  # {1,2,3,4} — 0 is now complete, not enabled


# ── 2. two independent partial-order blocks must not share closure state ───


def test_two_genuinely_independent_partial_order_blocks_do_not_share_closure_state() -> None:
    """Mimics the plan's ``observe_block -> aggregation -> remediate_block ->
    aggregation`` shape: block1 (5 unordered children), an aggregation atom,
    block2 (3 unordered children), a second aggregation atom, all chained
    sequentially at the top level.

    Proves firing all of block1's children and its aggregation atom does NOT
    spuriously affect block2's own ``enabled()``-returned set: block2 must
    show 0 enabled paths until reached, then all 3 simultaneously once
    reached. A closure-computation bug that accidentally leaked state across
    sibling blocks (e.g. reusing one cached ``_closure`` object, or indexing
    block2's children against block1's edge set) would be caught here.
    """
    block1 = PartialOrder(children=_labels(5, "observe"), order=frozenset())
    agg1 = Atom(label="scan_anomalies")
    block2 = PartialOrder(children=_labels(3, "recheck"), order=frozenset())
    agg2 = Atom(label="recheck_scan")

    top = PartialOrder(
        children=(block1, agg1, block2, agg2),
        order=frozenset({_oe(0, 1), _oe(1, 2), _oe(2, 3)}),
    )

    marking = INITIAL_MARKING

    # Before anything fires: block2's 3 leaves must show 0 enabled paths —
    # only block1's 5 leaves are live.
    live0 = enabled(top, marking)
    block2_paths_live0 = {p for p in live0 if p[:1] == (2,)}
    assert block2_paths_live0 == set()
    block1_paths_live0 = {p for p in live0 if p[:1] == (0,)}
    assert len(block1_paths_live0) == 5

    # Fire all 5 of block1's children, in a fixed order.
    for i in range(5):
        marking = fire(top, marking, (0, i))

    # block1 complete but agg1 not yet fired: block2 must STILL show 0.
    live_mid = enabled(top, marking)
    assert {p for p in live_mid if p[:1] == (2,)} == set()
    assert live_mid == {(1,)}  # only the aggregation atom is live

    # Fire agg1 — now block2 must become live, and precisely all 3 at once
    # (not leaked partial state from block1's own closure/order edges).
    marking = fire(top, marking, (1,))
    live_after_agg1 = enabled(top, marking)
    block2_paths = {p for p in live_after_agg1 if p[:1] == (2,)}
    assert block2_paths == {(2, 0), (2, 1), (2, 2)}
    assert len(live_after_agg1) == 3  # exactly block2's 3 leaves, nothing else


# ── 3. AND-join atom must never be enabled on a strict subset ──────────────


def test_an_and_join_atom_is_never_enabled_with_only_a_strict_subset_of_its_block_complete() -> None:
    """A 4-child unordered PartialOrder followed by one AND-join Atom. Fires
    children 0, 1, 2 (deliberately withholding 3) and asserts the AND-join
    atom is NOT enabled after each of the first 3 fires — checking all 3
    intermediate states, not just the final one, so a partial-join bug (an
    OR-join accidentally implemented where an AND-join was intended) would be
    caught at the very first premature enablement, not only at the end.
    """
    block = PartialOrder(children=_labels(4, "check"), order=frozenset())
    and_join = Atom(label="scan_anomalies")
    top = PartialOrder(children=(block, and_join), order=frozenset({_oe(0, 1)}))

    marking = INITIAL_MARKING
    fire_order = [0, 1, 2]  # deliberately not 3

    for step, child_idx in enumerate(fire_order):
        marking = fire(top, marking, (0, child_idx))
        live = enabled(top, marking)
        # The AND-join atom's own path is (1,) — must never appear while any
        # of block's 4 children remains unfired.
        assert (1,) not in live, (
            f"AND-join atom enabled after only {step + 1}/4 children fired "
            f"(fired={fire_order[: step + 1]}) -- this is exactly the "
            f"OR-join-instead-of-AND-join mistake this test targets"
        )
        # The still-unfired children (excluding the withheld child 3) remain
        # enabled, confirming the join withholding is specifically about the
        # aggregation atom and not a broader stall.
        remaining = {(0, i) for i in range(4)} - {(0, i) for i in fire_order[: step + 1]}
        assert remaining <= live

    # Now fire the last withheld child (3) — only then must the AND-join
    # become enabled.
    marking = fire(top, marking, (0, 3))
    live_final = enabled(top, marking)
    assert (1,) in live_final
    assert live_final == {(1,)}


# ── 4. firing the same path twice is refused, not silently idempotent ──────


def test_firing_the_same_path_twice_is_refused_not_silently_idempotent() -> None:
    """A real safety-net test: a buggy concurrent-batch implementation that
    accidentally fires the same ``NodePath`` twice (e.g. a set/list confusion
    when building the batch) must fail loudly, not silently double-count.
    Proves the real refusal mechanism read from ``executor.py``: ``fire()``
    computes ``enabled()`` fresh each call, and a path already in
    ``completed_paths`` is never re-offered, so the second ``fire()`` raises
    a real ``PowlError`` with ``PowlRefusal.LANGUAGE_MISMATCH``.
    """
    children = _labels(5, "check")
    model = PartialOrder(children=children, order=frozenset())

    marking = fire(model, INITIAL_MARKING, (2,))

    # The same leaf path is no longer enabled once fired.
    assert (2,) not in enabled(model, marking)

    with pytest.raises(PowlError) as excinfo:
        fire(model, marking, (2,))

    assert excinfo.value.refusal is PowlRefusal.LANGUAGE_MISMATCH

    # Refused, not silently accepted: the marking's fire count and completed
    # set must be exactly what one real fire produced — no double-counting
    # leaked through even though the call was attempted twice.
    assert marking.fires == 1
    assert (2,) in marking.completed_paths
    assert len(marking.completed_paths) == 1
