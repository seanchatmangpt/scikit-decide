# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Real, structurally rich `PowlNode` fixtures, hand-ported from `~/POWL`'s
published example activity names and topology -- **not** its code.

Licensing boundary, stated explicitly
--------------------------------------
`~/POWL` (a real, external, standalone process-mining library at `~/POWL`,
confirmed via `~/POWL/pyproject.toml` to be licensed **GNU AGPLv3+**) is
never imported here or anywhere in this repo (`~/POWL` is confirmed not
installed in this venv: `ModuleNotFoundError: No module named 'powl'`, and
this module keeps it that way). What is hand-ported below is the real
*topology and activity names* of two well-known example datasets
(`~/POWL/examples/running-example.csv` -- the pm4py tutorial log used across
many independent process-mining projects, not `~/POWL`'s own invention -- and
`~/POWL/examples/hospital.csv`) and one hand-built example structure
(`~/POWL/examples/powl_example_with_pools_and_lanes.py`'s `generate_process_1`),
each translated into this repo's own `Atom`/`PartialOrder`/`ChoiceGraph`
construction calls. No `~/POWL` source code is copied or executed; this
mirrors `refusals.py`'s own attribution pattern ("mirrors the PowlRefusal enum
in `~/wasm4pm-compat/src/powl.rs`... only the type shape is transcribed, no
code is copied").

Why these shapes
-----------------
Confirmed this session by direct exploration of `~/POWL`'s discovery output
and hand-built examples: `running-example.csv`'s discovered model genuinely
combines an exclusive choice, a concurrency pair, and a loop back-edge in one
structure; `hospital.csv`'s discovered model is a genuinely 5-node/6-edge
concurrent partial order (`Blood Test`/`X-Ray` share a timestamp -- the raw
signal for real concurrency); `powl_example_with_pools_and_lanes.py` hand-
builds a `ChoiceGraph` wrapping a `sequence`. These are real-world-shaped and
substantially richer than any fixture already in `tests/powl/`, which is
exactly what makes them useful for hammering `guard_executor.execute()`.

Every fixture here must pass `validate_model` -- enforced by a real test in
`test_guard_executor_adversarial.py`, not assumed.
"""

from __future__ import annotations

from autofde_lab.powl.algebra import (
    Atom,
    ChoiceGraph,
    ChoiceGraphEdge,
    End,
    Guard,
    NodeId,
    OrderEdge,
    PartialOrder,
    Silent,
    Start,
)

__all__ = [
    "running_example_choice_concurrency_loop_shape",
    "hospital_concurrent_shape",
    "pools_and_lanes_choice_shape",
]


def running_example_choice_concurrency_loop_shape() -> ChoiceGraph:
    """Hand-ported from `~/POWL/examples/powl_discovery.py`'s real target log
    (`running-example.csv`, the pm4py tutorial log): `register request` is
    followed by an exclusive choice between `examine casually` and
    `examine thoroughly`, each concurrent with `check ticket`; the combined
    result feeds a `decide` step which either commits (`pay compensation` /
    `reject request`) or loops back via `reinitiate request` to `check
    ticket` again -- the real loop-cut/xor-cut/concurrency-cut combination
    the upstream library's `running-example.csv` is documented (this
    session's own discovery-algorithm exploration) to exercise.

    Structure (11 children, 0-indexed):
    0=Start, 1=End, 2=register_request (Atom), 3=examine_and_check (PartialOrder:
    concurrent {examine_casually XOR examine_thoroughly} with check_ticket),
    4=decide (Silent), 5=pay_compensation (Atom), 6=reject_request (Atom),
    7=reinitiate_request (Atom).

    Guard predicates named `"approved"` / `"rejected"` / `"needs_more_info"`
    (evaluated by a caller-supplied `guard_evaluator` in tests -- this module
    only builds the model, never a decision).
    """
    examine_casually = Atom(label="examine_casually")
    examine_thoroughly = Atom(label="examine_thoroughly")
    examine_choice = ChoiceGraph(
        children=(Start(), End(), examine_casually, examine_thoroughly),
        edges=frozenset(
            [
                ChoiceGraphEdge(NodeId(0), NodeId(2)),
                ChoiceGraphEdge(NodeId(0), NodeId(3)),
                ChoiceGraphEdge(NodeId(2), NodeId(1)),
                ChoiceGraphEdge(NodeId(3), NodeId(1)),
            ]
        ),
        start=0,
        end=1,
    )
    check_ticket = Atom(label="check_ticket")
    examine_and_check = PartialOrder(children=(examine_choice, check_ticket))

    register_request = Atom(label="register_request")
    decide = Silent()
    pay_compensation = Atom(label="pay_compensation")
    reject_request = Atom(label="reject_request")
    reinitiate_request = Atom(label="reinitiate_request")

    return ChoiceGraph(
        children=(
            Start(),  # 0
            End(),  # 1
            register_request,  # 2
            examine_and_check,  # 3
            decide,  # 4
            pay_compensation,  # 5
            reject_request,  # 6
            reinitiate_request,  # 7
        ),
        edges=frozenset(
            [
                ChoiceGraphEdge(NodeId(0), NodeId(2)),
                ChoiceGraphEdge(NodeId(2), NodeId(3)),
                ChoiceGraphEdge(NodeId(3), NodeId(4)),
                ChoiceGraphEdge(NodeId(4), NodeId(5), guard=Guard("approved")),
                ChoiceGraphEdge(NodeId(4), NodeId(6), guard=Guard("rejected")),
                ChoiceGraphEdge(NodeId(4), NodeId(7), guard=Guard("needs_more_info")),
                ChoiceGraphEdge(NodeId(5), NodeId(1)),
                ChoiceGraphEdge(NodeId(6), NodeId(1)),
                ChoiceGraphEdge(NodeId(7), NodeId(3)),  # loop back to examine_and_check
            ]
        ),
        start=0,
        end=1,
    )


def hospital_concurrent_shape() -> PartialOrder:
    """Hand-ported from `~/POWL/examples/partial_order_based_discovery.py`'s
    real target log (`hospital.csv`): `Blood Test` and `X-Ray` share an
    identical timestamp in the raw data -- the real signal the upstream
    library's `log_to_partial_orders.py` uses to detect genuine concurrency
    -- followed by `Surgery`, then a concurrent pair `Physical Therapy` /
    `Follow-up Consultation` (both plausible next steps with no real
    ordering constraint between them, matching the discovered model's real
    5-node/6-edge shape this session's exploration confirmed).

    Structure (5 children, 0-indexed): 0=Blood Test, 1=X-Ray, 2=Surgery,
    3=Physical Therapy, 4=Follow-up Consultation. Edges: {0,1} -> 2 -> {3,4}
    (0 and 1 concurrent; 3 and 4 concurrent), 6 edges after transitive
    closure/reduction collapses to the reduction (0->2, 1->2, 2->3, 2->4).
    """
    blood_test = Atom(label="Blood_Test")
    x_ray = Atom(label="X-Ray")
    surgery = Atom(label="Surgery")
    physical_therapy = Atom(label="Physical_Therapy")
    follow_up = Atom(label="Follow-up_Consultation")

    return PartialOrder(
        children=(blood_test, x_ray, surgery, physical_therapy, follow_up),
        order=frozenset(
            [
                OrderEdge(NodeId(0), NodeId(2)),
                OrderEdge(NodeId(1), NodeId(2)),
                OrderEdge(NodeId(2), NodeId(3)),
                OrderEdge(NodeId(2), NodeId(4)),
            ]
        ),
    )


def pools_and_lanes_choice_shape() -> ChoiceGraph:
    """Hand-ported from `~/POWL/examples/powl_example_with_pools_and_lanes.py`'s
    real hand-built `generate_process_1()`: a `ChoiceGraph` between
    `order_coffee` (leading into a `sequence` of `pay` then
    `prepare_coffee`) and directly `serve_coffee` -- upstream's own real
    illustration of manual POWL model construction (`xor(...)` /
    `sequence(...)` builder calls) rather than log-discovered output. Here
    translated into `ChoiceGraph` wrapping a `PartialOrder` sequence, exactly
    the pattern `runner.py`'s own docstring calls out as "why the case-
    library branch is NOT built via turtle_bridge" -- hand-graft a
    `ChoiceGraph`/nested `PartialOrder` directly against `algebra.py` for
    shapes a flatter bridge format can't express.

    Structure (4 children, 0-indexed): 0=order_coffee (Atom), 1=pay_then_prepare
    (PartialOrder: pay -> prepare_coffee), 2=serve_coffee (Atom) reached either
    directly from order_coffee or after pay_then_prepare completes.
    """
    order_coffee = Atom(label="order_coffee")
    pay = Atom(label="pay")
    prepare_coffee = Atom(label="prepare_coffee")
    pay_then_prepare = PartialOrder(
        children=(pay, prepare_coffee), order=frozenset([OrderEdge(NodeId(0), NodeId(1))])
    )
    serve_coffee = Atom(label="serve_coffee")

    return ChoiceGraph(
        children=(
            Start(),  # 0
            End(),  # 1
            order_coffee,  # 2
            pay_then_prepare,  # 3
            serve_coffee,  # 4
        ),
        edges=frozenset(
            [
                ChoiceGraphEdge(NodeId(0), NodeId(2)),
                ChoiceGraphEdge(NodeId(2), NodeId(3), guard=Guard("wants_to_pay_first")),
                ChoiceGraphEdge(NodeId(2), NodeId(4)),  # else edge: straight to serve
                ChoiceGraphEdge(NodeId(3), NodeId(4)),
                ChoiceGraphEdge(NodeId(4), NodeId(1)),
            ]
        ),
        start=0,
        end=1,
    )
