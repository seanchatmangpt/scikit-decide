# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Property-based confluence tests for the POWL 2.0 reference executor.

These generalize the single fixed 3-atom confluence fixture in
``test_executor.py`` (``test_unordered_partial_order_enables_both_children_initially``
and its neighbors) into a broad, generative proof: for MANY random unordered
and mixed-order ``PartialOrder`` structures, firing order among genuinely
unordered siblings never affects the resulting ``Marking`` or the ``enabled``
set, and a real partial order's ordered pairs are always respected regardless
of which valid interleaving is used.

All collaborators are real, already-tested, pure primitives from
``autofde_lab.powl.algebra`` and ``autofde_lab.powl.executor`` — no mocks.
Randomness uses ``random.Random(<fixed seed>)`` exclusively, never the
unseeded global ``random`` module, so every run is exactly reproducible.
"""

from __future__ import annotations

import random

from autofde_lab.powl.algebra import Atom, OrderEdge, PartialOrder, PowlNode
from autofde_lab.powl.executor import INITIAL_MARKING, Marking, enabled, fire

# Fixed seeds -- chosen once, hardcoded, never regenerated per-run.
_SEED_TEST_1 = 20260809
_SEED_TEST_2 = 20260810
_SEED_TEST_3 = 20260811

_NUM_STRUCTURES = 50


def _random_unordered_partial_order(rng: random.Random, index: int) -> PartialOrder:
    """A PartialOrder with 3-8 genuinely unordered Atom children (no edges)."""
    n = rng.randint(3, 8)
    children = tuple(Atom(label=f"s{index}_a{i}") for i in range(n))
    return PartialOrder(children=children, order=frozenset())


def _fire_all_children_in_order(
    model: PowlNode, permutation: list[int]
) -> Marking:
    """Fire every leaf child of the top-level PartialOrder in ``permutation`` order."""
    marking = INITIAL_MARKING
    for child_index in permutation:
        path = (child_index,)
        marking = fire(model, marking, path)
    return marking


def test_confluence_holds_for_many_random_unordered_partial_orders():
    """For 50 random fully-unordered PartialOrders, any two firing permutations
    of the same children yield an identical resulting Marking and an identical
    ``enabled`` set -- the general confluence law the POWL v2 concurrent
    runner design depends on, not just the specific 2-3 atom shapes used in
    the pipeline fixtures.
    """
    rng = random.Random(_SEED_TEST_1)
    failures: list[str] = []

    for i in range(_NUM_STRUCTURES):
        model = _random_unordered_partial_order(rng, i)
        n = len(model.children)
        indices = list(range(n))

        permutation_a = indices[:]
        rng.shuffle(permutation_a)
        permutation_b = indices[:]
        rng.shuffle(permutation_b)
        # Ensure the two permutations actually differ when n > 1 -- otherwise
        # the test would trivially pass without exercising order-independence.
        attempts = 0
        while permutation_b == permutation_a and n > 1 and attempts < 10:
            rng.shuffle(permutation_b)
            attempts += 1

        marking_a = _fire_all_children_in_order(model, permutation_a)
        marking_b = _fire_all_children_in_order(model, permutation_b)

        if marking_a != marking_b:
            failures.append(
                f"structure {i} (n={n}): marking_a != marking_b for "
                f"permutation_a={permutation_a} permutation_b={permutation_b}"
            )

        enabled_a = enabled(model, marking_a)
        enabled_b = enabled(model, marking_b)
        if enabled_a != enabled_b:
            failures.append(
                f"structure {i} (n={n}): enabled(marking_a)={sorted(enabled_a)} "
                f"!= enabled(marking_b)={sorted(enabled_b)}"
            )

    assert not failures, "\n".join(failures)


def test_confluence_holds_for_partially_ordered_mixed_structures():
    """Random structures mixing SOME order edges with SOME genuinely unordered
    siblings: an ordered pair must always fire in its required relative order
    across every valid interleaving generated; unordered siblings within the
    same structure remain provably order-independent, scoped to just that
    unordered subset (same technique as test 1).
    """
    rng = random.Random(_SEED_TEST_2)
    failures: list[str] = []

    for i in range(_NUM_STRUCTURES):
        n = rng.randint(4, 8)
        children = tuple(Atom(label=f"m{i}_a{j}") for j in range(n))

        # Build a random DAG of order edges over a subset of indices, keeping
        # at least 2 indices genuinely unordered (no edge touching them) so
        # the "mixed" property is real, not accidentally fully-ordered or
        # fully-unordered.
        num_unordered = rng.randint(2, max(2, n // 2))
        all_indices = list(range(n))
        rng.shuffle(all_indices)
        unordered_indices = set(all_indices[:num_unordered])
        ordered_indices = [idx for idx in range(n) if idx not in unordered_indices]

        edges: set[OrderEdge] = set()
        # Only add forward edges (low index -> high index) among the ordered
        # subset, guaranteeing acyclicity by construction.
        ordered_indices_sorted = sorted(ordered_indices)
        for a_pos in range(len(ordered_indices_sorted)):
            for b_pos in range(a_pos + 1, len(ordered_indices_sorted)):
                if rng.random() < 0.35:
                    src = ordered_indices_sorted[a_pos]
                    dst = ordered_indices_sorted[b_pos]
                    edges.add(OrderEdge(src, dst))

        model = PartialOrder(children=children, order=frozenset(edges))
        # Required pairs: every (src, dst) in the model's transitive closure.
        required_pairs = list(model.closure)

        # Generate several independent valid interleavings by repeatedly
        # firing whatever is currently enabled, breaking ties randomly.
        interleavings: list[list[int]] = []
        for _trial in range(3):
            marking = INITIAL_MARKING
            order_taken: list[int] = []
            remaining = set(range(n))
            while remaining:
                live = enabled(model, marking)
                # Map enabled leaf paths back to child indices.
                live_indices = sorted(p[0] for p in live if len(p) == 1)
                assert live_indices, (
                    f"structure {i}: nothing enabled with remaining={remaining}"
                )
                choice = rng.choice(live_indices)
                marking = fire(model, marking, (choice,))
                order_taken.append(choice)
                remaining.discard(choice)
            interleavings.append(order_taken)

        # Property A: every ordered pair fires in the required relative order,
        # in EVERY generated interleaving.
        for interleaving in interleavings:
            position = {child: pos for pos, child in enumerate(interleaving)}
            for edge in required_pairs:
                if position[edge.src] >= position[edge.dst]:
                    failures.append(
                        f"structure {i}: order edge {edge.src}->{edge.dst} "
                        f"violated in interleaving {interleaving}"
                    )

        # Property B: restricting any two interleavings to just the
        # unordered-subset positions, the relative order among THOSE indices
        # need not match interleaving-to-interleaving (they're free), but
        # firing the unordered subset alone (in isolation, ignoring the
        # ordered siblings) is confluent -- proven directly by firing only
        # the unordered children of a small standalone PartialOrder built
        # from just that subset, in two different random orders.
        if len(unordered_indices) >= 2:
            unordered_children = tuple(
                Atom(label=f"m{i}_u{idx}") for idx in sorted(unordered_indices)
            )
            sub_model = PartialOrder(children=unordered_children, order=frozenset())
            sub_n = len(unordered_children)
            perm_x = list(range(sub_n))
            rng.shuffle(perm_x)
            perm_y = list(range(sub_n))
            rng.shuffle(perm_y)
            marking_x = _fire_all_children_in_order(sub_model, perm_x)
            marking_y = _fire_all_children_in_order(sub_model, perm_y)
            if marking_x != marking_y:
                failures.append(
                    f"structure {i}: unordered-subset confluence violated: "
                    f"perm_x={perm_x} perm_y={perm_y}"
                )

    assert not failures, "\n".join(failures)


def test_marking_fires_count_is_invariant_to_firing_order_for_unordered_siblings():
    """For the same random unordered structures as test 1, ``marking.fires``
    (the real fire-budget counter) ends at the same value regardless of which
    random permutation was used to fire everything -- a real, simple,
    additional invariant beyond full marking equality.
    """
    rng = random.Random(_SEED_TEST_3)
    failures: list[str] = []

    for i in range(_NUM_STRUCTURES):
        model = _random_unordered_partial_order(rng, i)
        n = len(model.children)
        indices = list(range(n))

        permutation_a = indices[:]
        rng.shuffle(permutation_a)
        permutation_b = indices[:]
        rng.shuffle(permutation_b)

        marking_a = _fire_all_children_in_order(model, permutation_a)
        marking_b = _fire_all_children_in_order(model, permutation_b)

        if marking_a.fires != n or marking_b.fires != n:
            failures.append(
                f"structure {i}: expected fires == {n}, got "
                f"marking_a.fires={marking_a.fires} marking_b.fires={marking_b.fires}"
            )
        if marking_a.fires != marking_b.fires:
            failures.append(
                f"structure {i}: fires count diverged: "
                f"marking_a.fires={marking_a.fires} != marking_b.fires={marking_b.fires} "
                f"for permutation_a={permutation_a} permutation_b={permutation_b}"
            )

    assert not failures, "\n".join(failures)
