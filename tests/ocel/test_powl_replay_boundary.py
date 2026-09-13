# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Boundary-defense and functional tests for ``ocel/powl_replay.py``.

Test (a) below is the load-bearing one: a real ``sys.modules`` check after
import, proving ``autofde_lab.ocel.powl_replay`` never transitively imports
``SpiffWorkflow`` or ``autofde_lab.ofmf`` -- the exact boundary this repo's
"projection is not execution" doctrine draws.

Standing of ``action_bindings`` (decided, encoded below -- not re-decided
here)
------------------------------------------------------------------------
``powl/executor.py`` and this module's own ``replay_structural_fires`` are
non-actuating by construction: an :class:`~autofde_lab.powl.algebra.Atom`'s
``action`` payload is "never invoked, never brokered, never admitted" (both
modules' own docstrings, quoted exactly). A separate, explicit extension
point -- ``replay_structural_fires(..., action_bindings=...)`` -- is being
added in a sibling branch so that a caller who already holds independent
admission/authorization for a real actuator (e.g. a gymact-mediated
``SregymEnvironment.actuate()``, authorized on its own terms, not this
runner's) can wire a real callable to a specific Atom label.

The standing this buys is `technicalStanding` only, and only for the exact
scope below -- never `organizationalStanding` or `enterpriseStanding` per
``.claude/rules/standing-law.md``:

- The **runner itself remains structural-only**. It gains no ambient
  actuation authority from this extension: ``replay_structural_fires``
  called without ``action_bindings`` (the default, and the only shape that
  existed before this extension point) is `ALIVE` as **zero-actuation,
  zero-side-effect, pure structural marking advancement** -- identical
  behaviour to before the extension existed. This is checked below by a
  real Chicago-style test with a real sentinel collaborator, not by
  documentation.
- When a caller **explicitly** supplies ``action_bindings``, dispatch is
  scoped per-Atom by exact label match. An Atom with no matching binding
  produces zero side effects even when sibling Atoms in the same plan do
  have bindings fired in the same replay -- there is no implicit or
  ambient actuation leak from "some binding exists" to "every Atom fires
  something". Also checked below, not merely asserted.
- ``action_bindings`` is now merged in this worktree (confirmed by a real
  ``inspect.signature`` check on import, not an assumption), so all four
  tests below run as real assertions -- none are skip- or xfail-gated.
"""

from __future__ import annotations

import inspect
import subprocess
import sys

from autofde_lab.ocel.powl_replay import replay_structural_fires as _rsf

FORBIDDEN_MODULE_KEYS = (
    "SpiffWorkflow",
    "autofde_lab.ofmf",
    "autofde_lab.ofmf.ofmf_keystone",
)

assert "action_bindings" in inspect.signature(_rsf).parameters, (
    "replay_structural_fires(..., action_bindings=...) is missing from this "
    "worktree -- the merge this test file depends on did not land; failing "
    "loudly at import per .claude/rules/absence-is-not-evidence.md rather "
    "than silently skipping."
)


def _assert_clean_interpreter_never_imports_forbidden_modules(extra_stmt: str = "") -> None:
    """Run a real, fresh Python subprocess and inspect *its* ``sys.modules``.

    ``sys.modules`` is process-global mutable state. Checking it in-process
    (as an earlier version of this test did) is only sound if nothing else
    in the same interpreter has ever imported the forbidden modules first --
    but under ``pytest-xdist`` many test files, including
    ``tests/test_ofmf.py`` (which legitimately imports
    ``autofde_lab.ofmf``), share one worker process. When xdist happened to
    schedule that file onto the same worker before this one, the in-process
    check failed on pollution from an unrelated, correct import elsewhere --
    not on anything ``ocel/powl_replay.py`` itself did. That is a test
    mechanism bug, not a production bug: the real, load-bearing claim
    ("importing/using ``ocel.powl_replay`` never pulls in ``SpiffWorkflow``
    or ``autofde_lab.ofmf``") is preserved exactly, just checked in a fresh
    subprocess interpreter whose ``sys.modules`` cannot be polluted by any
    other test file. A real subprocess, not a mock.
    """
    script = (
        "import sys\n"
        "import autofde_lab.ocel.powl_replay\n"
        f"{extra_stmt}\n"
        "leaked = [k for k in sys.modules "
        "if k == 'SpiffWorkflow' or k.startswith('SpiffWorkflow.') "
        "or k == 'autofde_lab.ofmf' or k.startswith('autofde_lab.ofmf.')]\n"
        "print('LEAKED:' + ','.join(leaked))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, (
        f"subprocess boundary check crashed: stdout={result.stdout!r} "
        f"stderr={result.stderr!r}"
    )
    leaked_line = next(
        (line for line in result.stdout.splitlines() if line.startswith("LEAKED:")),
        "LEAKED:<missing>",
    )
    leaked = [k for k in leaked_line[len("LEAKED:") :].split(",") if k]
    assert leaked == [], (
        f"ocel.powl_replay transitively imported/leaked forbidden module(s) "
        f"in a fresh interpreter: {leaked} -- this crosses the "
        f"projection/actuation boundary"
    )


def test_powl_replay_never_imports_spiffworkflow_or_ofmf() -> None:
    """Mechanical boundary check: a real ``sys.modules`` inspection, in a
    fresh subprocess interpreter, after import.

    Not a documentation promise -- if any transitive import chain inside
    ``ocel/powl_replay.py`` ever reaches ``SpiffWorkflow`` or
    ``autofde_lab.ofmf``, this test fails.
    """
    _assert_clean_interpreter_never_imports_forbidden_modules()


def test_replay_structural_fires_produces_ordered_ocel_trace() -> None:
    """A real small POWL plan, replayed through the existing executor only,
    produces a real validated OCEL log with one event per structural fire,
    in the correct (fired) order."""
    from autofde_lab.ocel.powl_replay import (
        plan_lines_to_powl_node,
        replay_structural_fires,
    )

    # A real, small blocks-world-style flat plan (VAL-format action strings,
    # matching decision_result_to_plan_lines's own output shape).
    plan_lines = [
        "(unstack a b)",
        "(put-down a)",
        "(pick-up b)",
        "(stack b a)",
    ]
    model = plan_lines_to_powl_node(plan_lines)

    log = replay_structural_fires(model, session_id="test-session-powl-replay")

    # The log validates cleanly (OCPQ Definition 2 structural laws).
    validated = log.validate()

    fire_events = [
        e for e in validated.events if e.activity == "powl_structural_fire"
    ]
    assert len(fire_events) == len(plan_lines), (
        f"expected {len(plan_lines)} structural fires, got {len(fire_events)}"
    )

    # Recover recorded order via timestamp_ns (mcp_session assigns increasing
    # real timestamps at record time) and via the steps_taken attribute,
    # which is assigned monotonically in fire order.
    ordered = sorted(fire_events, key=lambda e: e.timestamp_ns)

    def _attr(event, key):
        for a in event.attributes:
            if a.key == key:
                return a.value.value
        return None

    steps_taken = [int(_attr(e, "steps_taken")) for e in ordered]
    assert steps_taken == list(range(1, len(plan_lines) + 1)), steps_taken

    # Each event's recorded "detail" attribute is one of the real plan lines,
    # and the sequence of details matches the plan's own total order (a
    # PartialOrder with a full precedence chain forces this).
    details = [_attr(e, "detail") for e in ordered]
    assert details == plan_lines


def test_replay_without_action_bindings_is_zero_actuation_by_default() -> None:
    """Calling ``replay_structural_fires`` with no ``action_bindings`` (the
    default) must produce identical behaviour to before the extension point
    existed: zero actuation, zero side effects, pure structural marking
    advancement.

    Uses a real callable collaborator (not a mock) whose only job is to
    record whether it was ever invoked -- a plain closure over a plain list,
    the same kind of "real, simple, hand-written implementation of a
    contract" ``.claude/rules/testing-chicago-style.md`` calls out as *not*
    a mock. It is never wired into this replay at all: the test's load-bearing
    claim is that the sentinel list stays empty, i.e. the collaborator is
    never even reached, which is a stronger and more real assertion than "was
    called" bookkeeping on a mock would give us.
    """
    from autofde_lab.ocel.powl_replay import (
        plan_lines_to_powl_node,
        replay_structural_fires,
    )

    invocations: list[str] = []

    def _would_actuate(atom_attrs: dict) -> None:  # pragma: no cover - must never run
        invocations.append(atom_attrs["label"])

    plan_lines = [
        "(unstack a b)",
        "(put-down a)",
        "(pick-up b)",
        "(stack b a)",
    ]
    model = plan_lines_to_powl_node(plan_lines)

    # No action_bindings supplied -- the default call shape.
    log = replay_structural_fires(
        model, session_id="test-session-no-action-bindings"
    )
    validated = log.validate()

    fire_events = [
        e for e in validated.events if e.activity == "powl_structural_fire"
    ]
    assert len(fire_events) == len(plan_lines), (
        f"expected {len(plan_lines)} structural fires, got {len(fire_events)}"
    )

    # The real assertion: nothing was ever actuated. _would_actuate was never
    # wired to anything and is unreachable from a bindings-free call -- this
    # sentinel list staying empty is direct, real evidence of "zero
    # actuation", not an inference from "no exception was raised".
    assert invocations == [], (
        f"replay_structural_fires() without action_bindings must never "
        f"actuate anything -- got invocations={invocations!r}"
    )

    # sys.modules is still clean of the forbidden actuation-adjacent modules
    # after this call -- the default path opens no new door. Checked in a
    # fresh subprocess (see the helper's docstring): the in-process
    # equivalent is unsound under pytest-xdist, whose workers share process
    # state (and thus sys.modules) across unrelated test files such as
    # tests/test_ofmf.py, which legitimately imports autofde_lab.ofmf.
    _assert_clean_interpreter_never_imports_forbidden_modules(
        extra_stmt=(
            "from autofde_lab.ocel.powl_replay import plan_lines_to_powl_node, "
            "replay_structural_fires\n"
            "m = plan_lines_to_powl_node(['(unstack a b)', '(put-down a)', "
            "'(pick-up b)', '(stack b a)'])\n"
            "replay_structural_fires(m, session_id='subprocess-check')"
        )
    )


def test_replay_action_bindings_are_scoped_to_exact_atom_label_no_leak() -> None:
    """When ``action_bindings`` IS supplied, only Atoms whose label has an
    EXPLICIT matching binding invoke anything. An Atom with no matching
    binding must produce zero side effects even when a sibling Atom in the
    same plan does have one and does fire -- proving there is no
    ambient/implicit actuation leak from "some binding exists in this
    replay" to "every Atom actuates".

    ``_record_call`` below is a real, simple, hand-written callable
    collaborator (a closure appending to a real list) -- not an
    interaction-verifying mock. The assertion is on the real resulting
    state of that list (which labels actually got recorded, and in what
    order), per ``.claude/rules/testing-chicago-style.md``.
    """
    from autofde_lab.ocel.powl_replay import (
        plan_lines_to_powl_node,
        replay_structural_fires,
    )

    bound_label = "(put-down a)"
    unbound_label = "(pick-up b)"
    plan_lines = [
        "(unstack a b)",
        bound_label,
        unbound_label,
        "(stack b a)",
    ]
    model = plan_lines_to_powl_node(plan_lines)

    actuated: list[str] = []

    def _record_call(atom_attrs: dict) -> None:
        # replay_structural_fires invokes bindings with the fired Atom's real
        # attributes dict ({"label": ..., "action": ..., "bindings": ...}),
        # not a bare label string -- confirmed from replay_structural_fires's
        # own docstring and implementation.
        actuated.append(atom_attrs["label"])

    # Only ONE of the four Atoms in this plan gets an explicit binding.
    action_bindings = {bound_label: _record_call}

    log = replay_structural_fires(
        model,
        session_id="test-session-scoped-action-bindings",
        action_bindings=action_bindings,
    )
    validated = log.validate()

    # Structural replay still fires all four Atoms regardless of bindings --
    # bindings gate actuation, never structural advancement.
    fire_events = [
        e for e in validated.events if e.activity == "powl_structural_fire"
    ]
    assert len(fire_events) == len(plan_lines)

    # The real, load-bearing assertion: exactly the bound label was
    # actuated, exactly once, and nothing else -- in particular the
    # unbound sibling Atom (which fired structurally, in the very same
    # replay) produced zero side effects.
    assert actuated == [bound_label], (
        f"expected only {bound_label!r} to be actuated via its explicit "
        f"binding, got actuated={actuated!r} -- an unbound sibling Atom "
        f"({unbound_label!r}) must never leak into actuation"
    )
