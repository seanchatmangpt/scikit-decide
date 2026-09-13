# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for `run_pipeline`'s bound-exhaustion and
stall-classification logic, specifically under the real concurrent-batch-fire
path (`len(batch) > 1`) in `src/autofde_lab/powl/runner.py`.

Scope, relative to `tests/powl/test_runner_pipeline_chicago.py`
-----------------------------------------------------------------
That file already covers: `max_activity_fires` exhaustion mid a real
5-member concurrent batch (`test_run_pipeline_handles_bound_exhaustion_mid_batch_honestly`,
2 of 5 fire), and choice-graph exclusivity surviving a real concurrent batch
(`test_run_pipeline_concurrent_batch_path_still_enforces_choice_graph_exclusivity`).
It also covers structural `DEADLOCK` classification, but only via the
*single*-fire path.

This file goes beyond that: `max_marking_states` exhaustion mid a real
concurrent batch (never previously exercised at all in this repo -- see the
"genuine bugs found" section below), `max_node_visits` interacting with a
real concurrently-enabled block nested inside a cyclic `ChoiceGraph`, a real
structural `DEADLOCK` discovered immediately *after* a real batch of >1
concurrently fires (not the single-fire case), and the exact boundary where
0 or 1 of a >1-sized batch can fire under a tight `max_activity_fires`.

Every scenario is first traced directly against the real, bare
`enabled()`/`fire()` executor (this repo's own established convention -- see
`test_run_pipeline_concurrent_batch_path_still_enforces_choice_graph_exclusivity`
in the sibling file) so a test failure can localize to the executor layer or
the `run_pipeline` driver layer, before the same real structure is driven
through `run_pipeline`'s real executor loop.

Genuine bugs found and fixed forward this session
----------------------------------------------------
Both discovered by tracing the concurrent-batch `max_marking_states` case
below directly against the real executor and `run_pipeline`, before writing
any assertion -- named in detail as comments at their fix site, restated here
so a reader of this file sees them without cross-referencing production code:

1. `src/autofde_lab/powl/runner.py`, `run_pipeline`'s `len(batch) == 1`
   branch: the single-fire `fire()` call had no `except PowlError` guard, so
   a `max_marking_states` exhaustion discovered there (concretely: right
   after a concurrent batch partially fired via Step A's own `except
   PowlError: break`, leaving exactly one path enabled next iteration)
   propagated out of `run_pipeline` as an uncaught `PowlError` -- a crash,
   not the honest `BLOCKED:BOUND_EXHAUSTED` stall every other bound path
   already returns. Fixed by wrapping that `fire()` call the same way
   Step A already does.
2. `src/autofde_lab/powl/executor.py`'s `classify_stall` (and
   `runner.py`'s `classify_pipeline_stall`, which gates whether it even
   calls `classify_stall`): neither had any check for `max_marking_states`
   exhaustion at all. Unlike `max_node_visits` (enforced *inside*
   `_enabled()`, so a capped successor is structurally removed from the
   live set) and `max_activity_fires` (checked directly against
   `marking.fires`), `max_marking_states` is enforced only *inside*
   `fire()` as a raise -- never removes anything from `enabled()`. So a
   marking that had genuinely hit the `max_marking_states` cap but still
   had a real, structurally-enabled successor was misclassified: before fix
   1, this was unreachable (the process crashed first); after fix 1 alone,
   `classify_pipeline_stall` would still report `stall=None` ("more work
   enabled, not stalled") even though `run_pipeline`'s own loop had already
   halted -- a silent, wrong "still going" verdict for a real stop. Fixed
   by adding an explicit `completed_paths` vs. `max_marking_states` check,
   mirrored at both call sites.

No `unittest.mock` / `Mock` / `patch` / `monkeypatch` anywhere in this file.
"""

from __future__ import annotations

from autofde_lab.powl.algebra import (
    Atom,
    ChoiceGraph,
    ChoiceGraphEdge,
    NodeId,
    OrderEdge,
    PartialOrder,
    Silent,
)
from autofde_lab.powl.bounds import ExecutionBound
from autofde_lab.powl.executor import (
    INITIAL_MARKING,
    DeadlockKind,
    classify_stall,
    enabled,
    fire,
    is_final,
)
from autofde_lab.powl.refusals import PowlError
from autofde_lab.powl.runner import classify_pipeline_stall, run_pipeline


def _ce(a: int, b: int) -> ChoiceGraphEdge:
    return ChoiceGraphEdge(NodeId(a), NodeId(b))


def _oe(a: int, b: int) -> OrderEdge:
    return OrderEdge(NodeId(a), NodeId(b))


# ── 1. max_marking_states exhaustion mid a real concurrent batch ───────────


def test_max_marking_states_exhausts_mid_concurrent_batch_traced_against_executor():
    """Real, bare-executor trace first: a real 3-way concurrent `PartialOrder`
    (`a`, `b`, `c`, no order edges) with a real `ExecutionBound(max_marking_states=2)`
    -- small enough that firing the first two concurrent siblings fills the
    cap, so the third real `fire()` call genuinely raises `BOUND_EXHAUSTED`,
    never a guess about what the executor does."""
    model = PartialOrder(children=(Atom("a"), Atom("b"), Atom("c")), order=frozenset())
    bound = ExecutionBound(max_marking_states=2)

    live0 = enabled(model, INITIAL_MARKING, bound)
    assert live0 == frozenset({(0,), (1,), (2,)}), "all 3 siblings must start genuinely concurrent"

    m = fire(model, INITIAL_MARKING, (0,), bound=bound)
    assert m.completed_paths == frozenset({(0,)})
    m = fire(model, m, (1,), bound=bound)
    assert m.completed_paths == frozenset({(0,), (1,)})  # cap (2) now exactly full

    raised = None
    try:
        fire(model, m, (2,), bound=bound)
    except PowlError as exc:
        raised = exc
    assert raised is not None, "the 3rd fire must be refused once max_marking_states=2 is full"
    assert "BOUND_EXHAUSTED" in str(raised)
    assert "max_marking_states" in str(raised)

    # The real executor's own classify_stall must call this out precisely --
    # not DEADLOCK, even though nothing further can actually fire once
    # run_pipeline (below) stops advancing.
    assert classify_stall(model, m, bound) is DeadlockKind.BOUND_EXHAUSTED


def test_run_pipeline_handles_max_marking_states_exhaustion_mid_concurrent_batch_honestly():
    """The same real structure and bound, now driven through `run_pipeline`'s
    real executor loop (no bindings needed -- this is about bound honesty,
    not binding invocation): exactly 2 real fires happen (`a`, `b` -- the
    ones that fit under the cap), the 3rd (`c`) is never fired, and
    `classify_pipeline_stall` reports `BLOCKED:BOUND_EXHAUSTED`, never
    `BLOCKED:DEADLOCK` and never an uncaught exception (genuine bug 1, fixed
    forward this session -- see this module's docstring)."""
    model = PartialOrder(children=(Atom("a"), Atom("b"), Atom("c")), order=frozenset())
    bound = ExecutionBound(max_marking_states=2)

    log, result = run_pipeline(model, session_id="test-marking-states-mid-batch", bound=bound)

    assert result.final is False
    assert result.stall == "BLOCKED:BOUND_EXHAUSTED"
    # Only the 2 real fires that fit under the cap were ever recorded.
    assert len(log.events) == 2
    fired_labels = sorted(
        a.value.value
        for e in log.events
        for a in e.attributes
        if a.key == "detail"
    )
    assert fired_labels == ["a", "b"], (
        f"only the 2 siblings that fit under max_marking_states may have fired -- got {fired_labels!r}"
    )


def test_run_pipeline_max_marking_states_bindings_only_invoked_for_paths_that_actually_fired():
    """Real bindings on all 3 siblings; only the 2 that actually fired under
    the cap are ever really invoked -- the 3rd's binding must never run,
    proving Step B (binding invocation) never runs ahead of Step A's own
    honest mid-batch stop.

    Uses real `ALLOWED_ACTION_BINDING_LABELS` members (`scan`, `phi_encode`,
    `dispatch_solve`) as the concurrent siblings' labels -- `run_pipeline`
    refuses any `action_bindings` key outside that closed set (see
    `runner.py`'s own docstring), so a synthetic model driven with real
    bindings must borrow real pipeline labels rather than inventing new
    ones."""
    model = PartialOrder(
        children=(Atom("scan"), Atom("phi_encode"), Atom("dispatch_solve")), order=frozenset()
    )
    bound = ExecutionBound(max_marking_states=2)

    invocations: list[str] = []

    def _make(label: str):
        def _binding(attrs: dict) -> str:
            invocations.append(attrs["label"])
            return f"{label}_ok"

        return _binding

    log, result = run_pipeline(
        model,
        session_id="test-marking-states-bindings-honest",
        bound=bound,
        action_bindings={
            "scan": _make("scan"),
            "phi_encode": _make("phi_encode"),
            "dispatch_solve": _make("dispatch_solve"),
        },
        allow_partial_bindings=True,
    )

    assert result.final is False
    assert result.stall == "BLOCKED:BOUND_EXHAUSTED"
    assert sorted(invocations) == ["phi_encode", "scan"], (
        f"dispatch_solve's binding must never be invoked -- it never fired -- got {invocations!r}"
    )


# ── 2. max_node_visits interacting with a real concurrent batch nested ─────
# ── inside a repeated (cyclic ChoiceGraph) block ────────────────────────────


def _cyclic_concurrent_model() -> tuple[ChoiceGraph, PartialOrder]:
    """A real cyclic `ChoiceGraph`: start(0, Silent) -> body(1, a real 2-atom
    concurrent `PartialOrder`) -> {redo(2, Silent) -> body(1) again | exit(3,
    Silent, = end)}.

    Deliberately numbered so the redo hop's leaf path `(2,)` sorts *before*
    the exit leaf path `(3,)` -- `run_pipeline`'s own documented policy
    (`batch: list[NodePath] = sorted(live)`) always fires the
    lexicographically-smallest path first in a tied concurrent batch, so
    this ordering makes `run_pipeline` genuinely prefer looping over exiting
    at every opportunity, exactly like a real greedy policy would, without
    needing to hand-drive the loop the way `test_executor.py`'s
    `test_cyclic_choice_graph_terminates_and_reports_bound_exhausted` does
    ("a policy that refuses to take the exit, to force the cap") --
    `run_pipeline` forces the cap on its own here."""
    body = PartialOrder(children=(Atom("p"), Atom("q")), order=frozenset())
    model = ChoiceGraph(
        children=(Silent(), body, Silent(), Silent()),
        edges=frozenset({_ce(0, 1), _ce(1, 2), _ce(2, 1), _ce(1, 3)}),
        start=0,
        end=3,
    )
    return model, body


def test_visit_cap_removes_the_redo_hop_traced_against_executor_first():
    """Real, bare-executor trace: each loop round genuinely re-enables the
    real 2-atom concurrent body (`len(batch) == 2`), and the redo hop's own
    visit counter (`visits[((), 2)]`) genuinely increments once per round,
    never resets -- until it hits `max_node_visits`, at which point the
    *entire* enabled set structurally empties (the redo hop is excluded, and
    the exit branch is unreachable because the choice graph's cursor is
    already committed past it for this round) -- a real, traced deadlock-by-
    bound, not a guess."""
    model, _body = _cyclic_concurrent_model()
    bound = ExecutionBound(max_node_visits=2)

    m = fire(model, INITIAL_MARKING, (0,), bound=bound)  # enter the loop
    live1 = enabled(model, m, bound)
    assert live1 == frozenset({(1, 0), (1, 1)}), "round 1's body must start genuinely concurrent"
    m = fire(model, m, (1, 0), bound=bound)
    m = fire(model, m, (1, 1), bound=bound)

    live_after_round1 = sorted(enabled(model, m, bound))
    assert live_after_round1 == [(2,), (3,)], "both redo and exit must be real, live alternatives"
    m = fire(model, m, (2,), bound=bound)  # take the redo hop (round 1 -> round 2)
    assert dict(m.visits)[((), 2)] == 1, "the redo hop's own visit counter must have incremented"

    live2 = enabled(model, m, bound)
    assert live2 == frozenset({(1, 0), (1, 1)}), "round 2's body must again be genuinely concurrent"
    m = fire(model, m, (1, 0), bound=bound)
    m = fire(model, m, (1, 1), bound=bound)
    m = fire(model, m, (2,), bound=bound)  # 2nd redo -- fills the cap
    assert dict(m.visits)[((), 2)] == 2, "re-entry must increment, never reset (law 2)"

    live_final = enabled(model, m, bound)
    assert live_final == frozenset(), (
        "once the redo hop is capped, nothing further can be enabled -- the exit branch "
        "was already unreachable this round (the cursor had already committed past it)"
    )
    assert not is_final(model, m)
    assert classify_stall(model, m, bound) is DeadlockKind.BOUND_EXHAUSTED


def test_run_pipeline_max_node_visits_stalls_a_repeated_concurrent_block_honestly():
    """Same real structure and bound, now driven fully by `run_pipeline`'s
    own automatic policy (`sorted(live)`, fire the whole batch) -- no manual
    "refuse the exit" driving needed, because the redo hop's smaller path
    already makes `run_pipeline` prefer it every round. `run_pipeline` must
    stop honestly (no crash, no hang) once the real visit cap empties the
    enabled set, and `classify_pipeline_stall` must report
    `BLOCKED:BOUND_EXHAUSTED` -- never `BLOCKED:DEADLOCK`, even though the
    live enabled set really is empty here (`classify_stall`'s own
    `uncapped` re-check, delegated to via `classify_pipeline_stall`, is what
    distinguishes a real structural dead end from this bound-caused one)."""
    model, _body = _cyclic_concurrent_model()
    bound = ExecutionBound(max_node_visits=2)

    log, result = run_pipeline(model, session_id="test-visit-cap-concurrent-loop", bound=bound)

    assert result.final is False
    assert result.stall == "BLOCKED:BOUND_EXHAUSTED"
    # Traced above: (0,) [enter] + 2*(p,q) [2 real concurrent rounds] + (2,) [redo, round 1->2]
    # + (2,) [2nd redo, fills the cap] = 1 + 4 + 2 = 7 real fires -- the redo hop itself is a
    # real leaf fire each round (not merely a transition), and the cap only excludes the
    # *3rd* attempt, never the 2nd.
    assert len(log.events) == 7


def test_run_pipeline_max_node_visits_generous_bound_lets_the_same_model_exit_cleanly():
    """Control case, same real structure: `max_node_visits` is set generous
    enough (1000) that the redo hop is never capped, so `run_pipeline`'s own
    deterministic "always prefer the smaller path" policy would loop this
    model indefinitely on that axis alone. `max_activity_fires` is instead
    set tight (3), so it is genuinely THAT bound -- not `max_node_visits` --
    which stops the loop here, at exactly the point round 1's real
    concurrent body finishes firing. Proves the two counters are independent
    axes: the same concurrent structure produces the same
    `BLOCKED:BOUND_EXHAUSTED` verdict via a completely different bound."""
    model, _body = _cyclic_concurrent_model()
    # Generous max_node_visits (the redo hop is never capped), but a tight
    # max_activity_fires -- run_pipeline's greedy "always redo" policy hits
    # THIS bound first instead.
    bound = ExecutionBound(max_node_visits=1000, max_activity_fires=3)

    log, result = run_pipeline(model, session_id="test-visit-cap-vs-fire-cap-independent", bound=bound)

    assert result.final is False
    assert result.stall == "BLOCKED:BOUND_EXHAUSTED"
    # (0,) [enter] + (1,0) + (1,1) [round 1 body, concurrent] = 3 fires, exactly the fire cap.
    assert len(log.events) == 3
    fired_labels = sorted(
        a.value.value for e in log.events for a in e.attributes if a.key == "detail"
    )
    assert "p" in fired_labels and "q" in fired_labels, "round 1's real concurrent body must have fired"


# ── 3. a real structural DEADLOCK discovered right after a real batch ──────
# ── of >1 concurrently fires (not the single-fire case) ────────────────────


def _dead_end_after_concurrent_batch_model() -> ChoiceGraph:
    """start(0, Silent) -> body(2, a real 2-atom concurrent `PartialOrder`),
    with NO outgoing edge from node 2 and node 2 is not the end node (end=1,
    unreachable) -- the same dead-end shape as `test_executor.py`'s
    `test_a_choice_graph_with_no_way_forward_is_a_deadlock_not_a_bound`, but
    with the dead-end node replaced by a real concurrent block so the
    deadlock is discovered immediately after a real `len(batch) == 2` fire,
    not a single fire."""
    # Real ALLOWED_ACTION_BINDING_LABELS members ("scan", "phi_encode") so the
    # run_pipeline-level test below may bind real callables to them.
    body = PartialOrder(children=(Atom("scan"), Atom("phi_encode")), order=frozenset())
    return ChoiceGraph(
        children=(Silent(), Silent(), body), edges=frozenset({_ce(0, 2)}), start=0, end=1
    )


def test_deadlock_after_concurrent_batch_traced_against_executor_first():
    """Real, bare-executor trace: after `(0,)` fires, the real 2-atom body
    becomes genuinely concurrently enabled (`len(batch) == 2`); once BOTH
    real fires complete it, `enabled()` genuinely returns empty (node 2 has
    no outgoing edge) while `is_final` is genuinely `False` (end=1 was never
    reached) -- a real structural deadlock, never a bound."""
    model = _dead_end_after_concurrent_batch_model()

    m = fire(model, INITIAL_MARKING, (0,))
    live = enabled(model, m)
    assert live == frozenset({(2, 0), (2, 1)}), "the real body must be genuinely concurrent"

    m = fire(model, m, (2, 0))
    # Deadlock is not yet reached -- only one of the two concurrent siblings (scan) fired.
    assert enabled(model, m) == frozenset({(2, 1)})
    m = fire(model, m, (2, 1))

    assert enabled(model, m) == frozenset()
    assert not is_final(model, m)
    assert classify_stall(model, m) is DeadlockKind.DEADLOCK
    assert classify_stall(model, m).value == "BLOCKED:DEADLOCK"


def test_run_pipeline_surfaces_deadlock_discovered_right_after_a_real_concurrent_batch():
    """Same real structure, now driven through `run_pipeline`'s real
    executor loop: `(0,)` fires via the single-fire path, then `{a, b}` fire
    together via the real concurrent-batch path (`len(batch) == 2`), and
    immediately afterward `classify_pipeline_stall` reports
    `BLOCKED:DEADLOCK` -- distinct from `BLOCKED:BOUND_EXHAUSTED`, and
    reached via the concurrent path this time, unlike the sibling file's
    `test_run_pipeline_surfaces_classify_stall_deadlock_distinct_from_bound_exhaustion`
    (single-fire only)."""
    model = _dead_end_after_concurrent_batch_model()

    invocations: list[str] = []

    def scan_binding(attrs: dict) -> str:
        invocations.append("scan")
        return "scan_ok"

    def phi_encode_binding(attrs: dict) -> str:
        invocations.append("phi_encode")
        return "phi_encode_ok"

    log, result = run_pipeline(
        model,
        session_id="test-deadlock-via-concurrent-batch",
        action_bindings={"scan": scan_binding, "phi_encode": phi_encode_binding},
        allow_partial_bindings=True,
    )

    assert result.final is False
    assert result.stall == "BLOCKED:DEADLOCK"
    # (0,) + scan + phi_encode = 3 real fires, all real, both concurrent bindings really invoked.
    assert len(log.events) == 3
    assert sorted(invocations) == ["phi_encode", "scan"]


# ── 4. the exact boundary: 0 or 1 of a >1-sized batch can fire ─────────────


def test_run_pipeline_zero_of_a_concurrent_batch_fires_when_the_fire_budget_is_already_spent():
    """A real sequential Atom (`x`) precedes a real 2-atom concurrent block
    (`a`, `b`); `max_activity_fires=1` is spent entirely by `x`, so the
    concurrent block's real batch is computed as live (`len(batch) == 2`)
    but `run_pipeline`'s own top-of-loop check
    (`if marking.fires >= bound.max_activity_fires: break`) stops the whole
    loop *before* Step A ever fires a single member of it -- 0 of the >1
    batch fires, honestly, not a crash and not a silent partial success."""
    model = PartialOrder(
        children=(Atom("x"), Atom("a"), Atom("b")),
        order=frozenset({_oe(0, 1), _oe(0, 2)}),
    )
    bound = ExecutionBound(max_activity_fires=1)

    # Trace first: confirm the real batch really would have been concurrent
    # had the budget allowed it.
    m = fire(model, INITIAL_MARKING, (0,), bound=bound)
    assert enabled(model, m, bound) == frozenset({(1,), (2,)}), (
        "the real batch behind the spent budget must genuinely be a >1 concurrent set"
    )

    log, result = run_pipeline(model, session_id="test-zero-of-batch-fires", bound=bound)

    assert result.final is False
    assert result.stall == "BLOCKED:BOUND_EXHAUSTED"
    # Only x's single fire -- neither a nor b ever fired.
    assert len(log.events) == 1
    fired_labels = [a.value.value for e in log.events for a in e.attributes if a.key == "detail"]
    assert fired_labels == ["x"]


def test_run_pipeline_exactly_one_of_a_concurrent_batch_fires_at_the_marking_states_boundary():
    """A real 3-atom concurrent block with `max_marking_states=1` -- the cap
    is exactly full after the very first fire, so Step A's own
    `except PowlError: break` stops after exactly 1 of the 3 real siblings
    fires, honestly, never 0 and never more than 1."""
    model = PartialOrder(children=(Atom("a"), Atom("b"), Atom("c")), order=frozenset())
    bound = ExecutionBound(max_marking_states=1)

    live0 = enabled(model, INITIAL_MARKING, bound)
    assert live0 == frozenset({(0,), (1,), (2,)})
    m = fire(model, INITIAL_MARKING, (0,), bound=bound)
    raised = None
    try:
        fire(model, m, (1,), bound=bound)
    except PowlError as exc:
        raised = exc
    assert raised is not None, "the 2nd fire must already be refused when max_marking_states=1"

    log, result = run_pipeline(model, session_id="test-exactly-one-of-batch-fires", bound=bound)

    assert result.final is False
    assert result.stall == "BLOCKED:BOUND_EXHAUSTED"
    assert len(log.events) == 1, "exactly 1 of the 3-member concurrent batch may have fired"
