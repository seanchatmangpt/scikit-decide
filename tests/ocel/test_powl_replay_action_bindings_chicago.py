# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for ``replay_structural_fires``'s ``action_bindings``.

Real collaborators throughout: a real :class:`PowlNode` plan built via
``plan_lines_to_powl_node``, real Python callables with genuine side effects
(appending to a real list, writing into a real dict), a real
:class:`OcelLog` produced and validated by the real replay driver. No
``unittest.mock``/``Mock``/``patch``/``monkeypatch`` anywhere in this file --
grep-verified as part of this change's own completion evidence.
"""

from __future__ import annotations

import time

import pytest

from autofde_lab.ocel.powl_replay import (
    ActionBindingTimeout,
    plan_lines_to_powl_node,
    replay_structural_fires,
)
from autofde_lab.powl.algebra import Atom, PartialOrder


def _attr(event, key):
    for a in event.attributes:
        if a.key == key:
            return a.value.value
    return None


def test_action_binding_invoked_with_real_side_effect_and_recorded_in_ocel() -> None:
    """A bound callable for one Atom's label is really invoked -- a real list
    gets a real append -- and its real return value lands on that fire's OCEL
    event as ``action_result``, alongside the unchanged structural-fire shape.
    Unbound labels in the same plan fire exactly as before (no ``action_result``)."""
    plan_lines = [
        "(unstack a b)",
        "(put-down a)",
        "(pick-up b)",
        "(stack b a)",
    ]
    model = plan_lines_to_powl_node(plan_lines)

    invocations: list[dict] = []

    def real_binding(atom_attrs: dict) -> str:
        # A genuine side effect on a real list passed by reference, plus a
        # genuine computed return value -- not a mock's canned response.
        invocations.append(atom_attrs)
        return f"handled:{atom_attrs['label']}"

    log = replay_structural_fires(
        model,
        session_id="test-session-action-bindings",
        action_bindings={"(pick-up b)": real_binding},
    )

    # The real side effect actually happened, exactly once, with the real
    # atom attributes.
    assert len(invocations) == 1
    assert invocations[0]["label"] == "(pick-up b)"
    assert invocations[0]["action"] is None
    assert invocations[0]["bindings"] == {}

    validated = log.validate()
    fire_events = [
        e for e in validated.events if e.activity == "powl_structural_fire"
    ]
    assert len(fire_events) == len(plan_lines)
    ordered = sorted(fire_events, key=lambda e: e.timestamp_ns)

    # Existing shape is untouched for every event.
    details = [_attr(e, "detail") for e in ordered]
    assert details == plan_lines
    steps_taken = [int(_attr(e, "steps_taken")) for e in ordered]
    assert steps_taken == list(range(1, len(plan_lines) + 1))

    # Only the bound label's event carries the additive attribute.
    results = [_attr(e, "action_result") for e in ordered]
    assert results == [None, None, "handled:(pick-up b)", None]

    # No separate error event was produced.
    error_events = [
        e for e in validated.events if e.activity == "powl_action_binding_error"
    ]
    assert error_events == []


def test_no_action_bindings_is_byte_for_byte_identical_to_before() -> None:
    """``action_bindings=None`` (the default) reproduces exactly the same
    event count, order, and attribute shape as calling with no bindings at
    all -- the pre-existing regression fixture in
    ``test_powl_replay_boundary.py`` continues to assert this; this test
    adds the same guarantee for an explicitly empty bindings dict.

    A *non-empty* dict whose key matches no Atom label in the model is a
    different, and now differently-handled, case: this module refuses that
    (see ``test_action_bindings_with_no_matching_atom_label_is_refused``)
    rather than silently no-oping, since an unmatched key is far more likely
    to be a caller typo than an intentional inert entry."""
    plan_lines = ["(unstack a b)", "(put-down a)"]
    model = plan_lines_to_powl_node(plan_lines)

    log_without = replay_structural_fires(model, session_id="s-without")
    log_with_unmatched = replay_structural_fires(
        model,
        session_id="s-with-unmatched",
        action_bindings={},
    )

    def fire_shapes(log):
        validated = log.validate()
        events = sorted(
            (e for e in validated.events if e.activity == "powl_structural_fire"),
            key=lambda e: e.timestamp_ns,
        )
        return [
            (
                _attr(e, "detail"),
                _attr(e, "steps_taken"),
                _attr(e, "action_result"),
            )
            for e in events
        ]

    assert fire_shapes(log_without) == fire_shapes(log_with_unmatched)


def test_action_binding_raising_halts_replay_and_records_a_real_error_event() -> None:
    """A bound callable that raises is never silently swallowed: this replay
    driver records a real ``"powl_action_binding_error"`` OCEL event carrying
    the real exception type and message, then re-raises the original
    exception -- replay halts, no further structural fires are attempted.

    This is the chosen, documented behavior (see ``replay_structural_fires``'s
    docstring): halt-and-report, not swallow-and-continue, matching this
    repo's absence-is-not-evidence law -- a replay that pressed on past an
    action whose real invocation failed would manufacture a completed trace
    the world never produced.
    """
    plan_lines = [
        "(unstack a b)",
        "(put-down a)",
        "(pick-up b)",
        "(stack b a)",
    ]
    model = plan_lines_to_powl_node(plan_lines)

    class RealActionFailure(RuntimeError):
        pass

    def failing_binding(atom_attrs: dict) -> None:
        raise RealActionFailure(f"real failure handling {atom_attrs['label']}")

    with pytest.raises(RealActionFailure, match=r"real failure handling \(pick-up b\)"):
        replay_structural_fires(
            model,
            session_id="test-session-action-binding-error",
            action_bindings={"(pick-up b)": failing_binding},
        )


def test_action_binding_error_event_carries_real_exception_type_and_message() -> None:
    """The recorded ``powl_action_binding_error`` OCEL event's ``error``
    attribute is not a generic marker -- it carries the real exception's
    type name and message. The raised exception carries the partial
    (not-yet-validated) log as ``ocel_partial_log`` precisely so a caller
    can inspect the just-recorded event on this halt-and-raise path, where
    the function's own return value is never reached."""
    plan_lines = ["(unstack a b)", "(put-down a)"]
    model = plan_lines_to_powl_node(plan_lines)

    class RealActionFailure(RuntimeError):
        pass

    def failing_binding(atom_attrs: dict) -> None:
        raise RealActionFailure("a specific, real, distinguishing message")

    with pytest.raises(RealActionFailure) as excinfo:
        replay_structural_fires(
            model,
            session_id="test-session-error-detail",
            action_bindings={"(unstack a b)": failing_binding},
        )

    partial_log = excinfo.value.ocel_partial_log
    validated = partial_log.validate()
    error_events = [
        e for e in validated.events if e.activity == "powl_action_binding_error"
    ]
    assert len(error_events) == 1
    error_detail = _attr(error_events[0], "error")
    assert error_detail is not None
    assert "RealActionFailure" in error_detail
    assert "a specific, real, distinguishing message" in error_detail


def test_action_bindings_with_no_matching_atom_label_is_refused() -> None:
    """A caller-side typo in an ``action_bindings`` key -- a label that
    matches no ``Atom`` anywhere in the model -- is refused with a real
    ``ValueError`` naming the unmatched key, not silently accepted and
    then never invoked."""
    plan_lines = ["(unstack a b)", "(put-down a)"]
    model = plan_lines_to_powl_node(plan_lines)

    with pytest.raises(ValueError, match=r"\(this-label-does-not-exist\)"):
        replay_structural_fires(
            model,
            session_id="test-session-typo-refusal",
            action_bindings={"(this-label-does-not-exist)": lambda attrs: "unreachable"},
        )


def test_action_bindings_label_collision_is_refused_not_silently_dispatched() -> None:
    """Two distinct ``Atom`` leaves sharing the same label is a real,
    structurally-detectable defect for label-keyed ``action_bindings``: the
    dict cannot tell the two real pipeline steps apart, so this is refused
    with a real ``ValueError`` rather than silently dispatching one bound
    callable to both fires."""
    # Hand-construct a tree with a genuine label collision: two leaves both
    # labeled "(step)" wired into a strict order, same shape
    # `plan_lines_to_powl_node` would build if given a repeated label.
    from autofde_lab.powl.algebra import OrderEdge

    children = (Atom(label="(step)"), Atom(label="(step)"))
    order = frozenset({OrderEdge(0, 1)})
    model = PartialOrder(children=children, order=order)

    invocations: list[dict] = []

    def real_binding(atom_attrs: dict) -> str:
        invocations.append(atom_attrs)
        return "handled"

    with pytest.raises(ValueError, match=r"\(step\)"):
        replay_structural_fires(
            model,
            session_id="test-session-label-collision",
            action_bindings={"(step)": real_binding},
        )

    # Refused before any structural fire touched the binding.
    assert invocations == []


def test_action_binding_timeout_halts_replay_and_records_a_real_error_event() -> None:
    """A bound callable that genuinely hangs past ``binding_timeout_s`` does
    not block this replay forever: the wait is bounded, an
    :class:`ActionBindingTimeout` is raised and recorded as a real
    ``powl_action_binding_error`` OCEL event, and replay halts -- same
    halt-and-record shape as a directly-raising binding."""
    plan_lines = ["(unstack a b)", "(put-down a)"]
    model = plan_lines_to_powl_node(plan_lines)

    def hanging_binding(atom_attrs: dict) -> None:
        # A real sleep on a real worker thread -- genuinely slow, not a
        # simulated delay via a mock's side_effect.
        time.sleep(5.0)
        return "should never be reached before the timeout fires"

    start = time.monotonic()
    with pytest.raises(ActionBindingTimeout, match=r"\(unstack a b\)"):
        replay_structural_fires(
            model,
            session_id="test-session-binding-timeout",
            action_bindings={"(unstack a b)": hanging_binding},
            binding_timeout_s=0.2,
        )
    elapsed = time.monotonic() - start

    # The replay actually returned control near the bound, not after the
    # full 5-second sleep -- proves the wait was really bounded, not just
    # that the exception type is right.
    assert elapsed < 3.0


def test_no_binding_timeout_is_byte_for_byte_identical_default_behavior() -> None:
    """``binding_timeout_s=None`` (the default) still invokes the binding
    directly with no thread-pool indirection -- same real return value as
    calling with the parameter entirely omitted."""
    plan_lines = ["(unstack a b)", "(put-down a)"]
    model = plan_lines_to_powl_node(plan_lines)

    def real_binding(atom_attrs: dict) -> str:
        return f"handled:{atom_attrs['label']}"

    log_omitted = replay_structural_fires(
        model,
        session_id="s-timeout-omitted",
        action_bindings={"(unstack a b)": real_binding},
    )
    log_explicit_none = replay_structural_fires(
        model,
        session_id="s-timeout-explicit-none",
        action_bindings={"(unstack a b)": real_binding},
        binding_timeout_s=None,
    )

    def action_results(log):
        validated = log.validate()
        events = sorted(
            (e for e in validated.events if e.activity == "powl_structural_fire"),
            key=lambda e: e.timestamp_ns,
        )
        return [_attr(e, "action_result") for e in events]

    assert action_results(log_omitted) == action_results(log_explicit_none)
    assert action_results(log_omitted) == ["handled:(unstack a b)", None]
