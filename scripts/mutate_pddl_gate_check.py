#!/usr/bin/env python3
# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Mutation check for the PDDL requirements gate (``CLAUDE.md`` rule 3).

Adapted from ``~/mfw/mfw-pddl-exploration/scripts/checkpoint_gate.py``'s
``run_mutant_test()`` pattern (reviewed this session): patch a real gate out,
confirm the existing static test that depends on it now fails, then restore
the source exactly. A static refusal test only proves the gate currently
fires for one fixture; it says nothing about whether the *gate itself* is
what's making it fire, versus some unrelated coincidence. This script closes
that gap for exactly one named invariant:
``src/autofde_lab/fabric/pddl_engine.py``'s ``UNIMPLEMENTED_REQUIREMENTS``
tuple, which ``CLAUDE.md`` rule 3 says must never be removed:

    Never remove the PDDL requirements gate in ``fabric/pddl_engine.py``.
    The C++ backend parses ``:derived-predicates``, ``:constraints`` and
    ``:preferences`` and implements none of them, silently -- so planning
    would return a confident, plausible, *wrong* plan.

This is a standing regression guard, run manually (or from CI as a distinct
job), not part of the default ``pytest`` invocation -- it edits and restores
a real source file on disk and is not safe to run concurrently with other
processes editing the same file.

Usage::

    uv run python scripts/mutate_pddl_gate_check.py

Exit 0: the mutation genuinely broke the gate (proving the gate is real),
and the source was restored byte-identical. Exit 1: the source could not be
restored identically (do not trust the working tree; check ``git diff``
immediately). Exit 2: the gate did *not* break under mutation -- i.e. the
requirement is enforced somewhere the mutation didn't touch, or the mutation
itself is wrong; either way, this check has stopped proving what it claims to
prove and needs attention before being trusted again.
"""

from __future__ import annotations

import hashlib
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GATE_FILE = REPO_ROOT / "src" / "autofde_lab" / "fabric" / "pddl_engine.py"

# The exact tuple entry the gate depends on to refuse a domain declaring
# `:derived-predicates`. Mutating this one line is enough: removing it drops
# the requirement from `UNIMPLEMENTED_REQUIREMENTS`, so
# `unsupported_requirements()` (fabric/pddl_engine.py) stops naming it.
GATE_LINE = '    ("has_derived_predicates", ":derived-predicates"),\n'

# A minimal domain/problem pair declaring exactly the requirement the gate
# above exists to catch -- self-contained, no dependency on ggen-legacy's
# corpus (which the existing static test,
# tests/ecosystem/test_chatman_chain_chicago.py::
# test_unimplemented_requirements_are_refused_not_planned, skips without).
DOMAIN_PDDL = """\
(define (domain mutate-gate-check)
  (:requirements :strips :typing :derived-predicates)
  (:types obj)
  (:predicates (raw ?x - obj) (derived ?x - obj))
  (:derived (derived ?x - obj) (raw ?x))
  (:action mark
    :parameters (?x - obj)
    :precondition (raw ?x)
    :effect (derived ?x)))
"""
PROBLEM_PDDL = """\
(define (problem mutate-gate-check-p1)
  (:domain mutate-gate-check)
  (:objects a - obj)
  (:init (raw a))
  (:goal (derived a)))
"""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _check_gate_fires(domain_path: Path, problem_path: Path) -> bool:
    """True iff the live gate (re-imported fresh) names :derived-predicates."""
    import importlib
    import autofde_lab.fabric.pddl_engine as pddl_engine

    importlib.reload(pddl_engine)
    found = pddl_engine.unsupported_requirements(str(domain_path), str(problem_path))
    return ":derived-predicates" in found


def main() -> int:
    if not GATE_FILE.exists():
        print(f"REFUSED: gate file not found at {GATE_FILE}", file=sys.stderr)
        return 1

    original_bytes = GATE_FILE.read_bytes()
    original_hash = _sha256(GATE_FILE)

    if GATE_LINE not in original_bytes.decode("utf-8"):
        print(
            "REFUSED: fixture drifted -- expected gate line not found "
            f"verbatim in {GATE_FILE}:\n{GATE_LINE!r}",
            file=sys.stderr,
        )
        return 1

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        domain_path = tmp_path / "mutate_gate_check_domain.pddl"
        problem_path = tmp_path / "mutate_gate_check_problem.pddl"
        domain_path.write_text(DOMAIN_PDDL)
        problem_path.write_text(PROBLEM_PDDL)

        try:
            before = _check_gate_fires(domain_path, problem_path)
            print(f"BEFORE mutation: gate fires on :derived-predicates = {before}")
            if not before:
                print(
                    "REFUSED: gate did not fire before mutation at all -- "
                    "this check cannot prove anything about the gate's "
                    "removal if it was never verified to be active.",
                    file=sys.stderr,
                )
                return 2

            mutated = original_bytes.decode("utf-8").replace(GATE_LINE, "", 1)
            GATE_FILE.write_text(mutated)
            try:
                after = _check_gate_fires(domain_path, problem_path)
                print(f"AFTER mutation:  gate fires on :derived-predicates = {after}")
            finally:
                GATE_FILE.write_bytes(original_bytes)
                import importlib
                import autofde_lab.fabric.pddl_engine as pddl_engine

                importlib.reload(pddl_engine)

            restored_hash = _sha256(GATE_FILE)
            if restored_hash != original_hash:
                print(
                    f"RESTORE_FAILED: {GATE_FILE} hash after restore "
                    f"({restored_hash}) != original ({original_hash}). "
                    "Do not trust the working tree -- check `git diff` now.",
                    file=sys.stderr,
                )
                return 1
            print(f"RESTORED: {GATE_FILE} byte-identical to before mutation "
                  f"(sha256 {restored_hash}).")

        except Exception:
            # Any failure mid-mutation must still restore the source before
            # propagating -- an unrestored gate file is worse than a failed
            # check.
            GATE_FILE.write_bytes(original_bytes)
            raise

    if before and not after:
        print(
            "ALIVE: mutating out the has_derived_predicates gate entry "
            "made the existing refusal test's precondition fail -- the "
            "gate genuinely is what makes CLAUDE.md rule 3 hold, source "
            "restored."
        )
        return 0

    print(
        "BUILD_BROKEN: the gate still fired (or never fired) after removing "
        "its own tuple entry -- either this mutation no longer exercises "
        "the real code path (e.g. the check moved elsewhere), or the "
        "regression this check exists to catch has already happened "
        "silently. Investigate before trusting rule 3's standing claim.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
