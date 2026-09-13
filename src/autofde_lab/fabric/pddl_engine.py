# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Classical PDDL planning engine, invocable as an external subprocess.

This module exists to fill a specific, pre-existing vacancy rather than to
invent a new interface. The ~/mfw planner runner
(``mfw-planner/src/config.rs``) admits external planning engines under a
closed set of roles -- ``classical``, ``temporal``, ``validator`` -- and for
``classical`` with ``output_mode = "file"`` it requires exactly the argument
placeholders ``{domain} {problem} {plan}``. Its committed ``engines.toml``
registers ``fast-downward.py`` under that contract, so a *Python* program in
this slot is the reference case, not a novelty.

This engine satisfies that same contract using scikit-decide's own
:class:`~autofde_lab.hub.domain.pddl.PDDLDomain` and the registered ``Astar``
solver, so that a scikit-decide planner can be admitted the way any other
external engine is: canonicalized path, blake3-pinned executable digest, a
version witness, and an exit code checked against ``success_codes``.

Contract implemented here
-------------------------
argv        ``<prog> <domain.pddl> <problem.pddl> <plan-out>``
version     ``<prog> --help`` writes a stable banner to stdout whose first
            token is ``usage:`` -- usable as ``pddl:versionWitnessPrefix``
            (the same prefix ~/mfw already pins for fast-downward).
stdout      Diagnostics only. The plan is written to the ``<plan-out>``
            path, never to stdout, because ``output_mode = "file"``.
exit codes  Distinct and meaningful, so a ``success_codes`` gate is not
            vacuous:

            ``0``  plan found and written
            ``1``  parsed successfully, no plan exists / not found in bound
            ``2``  domain or problem refused by the parser
            ``3``  usage error (wrong argument count)

The engine spawns nothing, reads no environment configuration, opens no
network, and writes exactly one file: the plan path it was given. ~/mfw
spawns it with ``stdin`` closed and rejects any output path escaping the
run directory, so it must not depend on either.

Scope boundary: this produces a *candidate plan*. It performs no admission,
emits no receipt, and actuates nothing -- per the ecosystem's own division
("planning selects, the broker authorizes, the executor performs, the
verifier evaluates").
"""

from __future__ import annotations

import sys
import traceback
from typing import List, Optional, Sequence, TextIO

#: First token of the ``--help`` banner. Pinned as ``versionWitnessPrefix``
#: in a PlannerProfile; changing it invalidates existing profiles.
VERSION_WITNESS_PREFIX = "usage:"

PROG = "autofde_lab-classical-engine"

EXIT_PLAN_FOUND = 0
EXIT_NO_PLAN = 1
EXIT_REFUSED = 2
EXIT_USAGE = 3

#: Hard cap on rollout length, so a pathological domain cannot hang a
#: subprocess that ~/mfw is timing out from the outside.
MAX_PLAN_STEPS = 10_000

#: Requirements that scikit-decide's PDDL backend PARSES but does NOT
#: implement -- the dangerous class. Verified against the C++ semantics in
#: ``cpp/src/hub/domain/pddl/semantics/`` this session:
#:
#: ``:derived-predicates``  Derivation rules are parsed into the AST and
#:     then never expanded -- no semantics file references them at all.
#:     Derived atoms are therefore *never true*, so any action gated on one
#:     is silently never applicable.
#: ``:constraints``  ``GoalChecker::is_goal`` evaluates only the goal;
#:     ``problem->get_constraints()`` is never read. Trajectory constraints
#:     are neither enforced nor reported as violated.
#: ``:preferences``  ``Preference::holds`` returns the inner formula (or
#:     ``true``), i.e. a soft preference is treated as a hard constraint,
#:     and ``is-violated`` in a ``:metric`` is not wired to anything.
#:
#: None of these raise. Without this gate the engine would emit a
#: confident, plausible, wrong plan -- a failure mode strictly worse than
#: refusing, because a wrong plan can be admitted downstream. Refusing here
#: is what makes an ``UNSUPPORTED`` finding honest instead of invisible.
UNIMPLEMENTED_REQUIREMENTS: tuple[tuple[str, str], ...] = (
    ("has_derived_predicates", ":derived-predicates"),
    ("has_constraints", ":constraints"),
    ("has_preferences", ":preferences"),
)


def unsupported_requirements(domain_path: str, problem_path: str) -> List[str]:
    """Return declared-but-unimplemented PDDL requirements, if any.

    Parses only (no grounding), so this is cheap and safe to run as a
    pre-flight gate before handing anything to :class:`PDDLDomain`.
    """
    from autofde_lab.hub.domain.pddl import PDDLReader

    reader = PDDLReader(domain_path, problem_path)
    requirements = reader.domains[0].get_requirements()
    return [
        label
        for accessor, label in UNIMPLEMENTED_REQUIREMENTS
        if getattr(requirements, accessor)()
    ]

USAGE = f"""\
{VERSION_WITNESS_PREFIX} {PROG} <domain.pddl> <problem.pddl> <plan-file>

Classical PDDL planning engine backed by scikit-decide (PDDLDomain + Astar).
Writes a VAL-consumable plan file; exits 0 plan found, 1 no plan, 2 refused,
3 usage error.
"""


def _write_plan(
    plan_path: str, actions: Sequence[object], total_cost: float
) -> None:
    """Serialize a plan in the standard VAL-consumable format.

    One ground action per line as ``(name arg1 arg2)`` followed by a cost
    comment -- matching the shape of plan files the ecosystem already
    produces (e.g. ``~/mfw/runs/ticket-10/work/candidate.plan``).
    """
    lines = [f"{action}" for action in actions]
    lines.append(f"; cost = {total_cost:g} (unit cost)")
    with open(plan_path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def solve_to_plan_file(
    domain_path: str,
    problem_path: str,
    plan_path: str,
    log: Optional[TextIO] = None,
    powl_path: Optional[str] = None,
    powl_base_iri: str = "urn:skdecide:plan",
) -> int:
    """Parse, solve, and write a plan file. Returns a process exit code.

    Separated from :func:`main` so tests can drive it in-process while the
    subprocess contract stays exercised end-to-end elsewhere.
    """
    log = log if log is not None else sys.stdout

    # -- parse ------------------------------------------------------------
    # A parse failure is a refusal (exit 2), distinct from "parsed fine but
    # no plan exists" (exit 1). Collapsing the two would make an admission
    # gate unable to tell an unsupported domain from an unsolvable problem.
    try:
        from autofde_lab.hub.domain.pddl import PDDLDomain

        # Pre-flight: refuse declared-but-unimplemented requirements BEFORE
        # grounding. These parse cleanly and then produce wrong answers
        # silently, so this gate is a correctness requirement, not polish.
        unsupported = unsupported_requirements(domain_path, problem_path)
        if unsupported:
            print(
                f"{PROG}: REFUSED: UNSUPPORTED_REQUIREMENT: "
                f"{','.join(unsupported)} declared by {domain_path}. "
                "scikit-decide's PDDL backend parses these but does not "
                "implement them; planning would silently return an "
                "incorrect plan. Refusing rather than emitting one.",
                file=log,
            )
            return EXIT_REFUSED

        domain = PDDLDomain(domain_path, problem_path)
    except Exception as exc:  # noqa: BLE001 - must map any parser failure
        print(f"{PROG}: REFUSED: cannot parse domain/problem: {exc}", file=log)
        traceback.print_exc(file=log)
        return EXIT_REFUSED

    # -- solve ------------------------------------------------------------
    try:
        from autofde_lab import utils

        astar_cls = utils.load_registered_solver("Astar")
    except Exception as exc:  # noqa: BLE001
        print(f"{PROG}: REFUSED: Astar solver unavailable: {exc}", file=log)
        return EXIT_REFUSED

    actions: List[object] = []
    total_cost = 0.0
    try:
        with astar_cls(domain_factory=lambda: domain) as solver:
            solver.solve()
            observation = domain.reset()

            for _ in range(MAX_PLAN_STEPS):
                if domain._is_terminal(observation):
                    break
                # NOTE: no is_policy_defined_for() guard here -- Astar
                # inherits the abstract version, which raises
                # NotImplementedError (builders/solver/policy.py:72).
                # Verified this session. A state the search never covered
                # surfaces as an exception from sample_action instead, and
                # is caught below as EXIT_NO_PLAN; the final goal check is
                # the real correctness gate either way.
                action = solver.sample_action(observation)
                actions.append(action)
                outcome = domain.step(action)
                total_cost += float(outcome.value.cost)
                observation = outcome.observation
            else:
                print(
                    f"{PROG}: exceeded MAX_PLAN_STEPS={MAX_PLAN_STEPS}",
                    file=log,
                )
                return EXIT_NO_PLAN

            if not domain._is_goal(observation):
                print(f"{PROG}: rollout ended in a non-goal state", file=log)
                return EXIT_NO_PLAN
    except Exception as exc:  # noqa: BLE001
        print(f"{PROG}: search failed: {exc}", file=log)
        traceback.print_exc(file=log)
        return EXIT_NO_PLAN

    _write_plan(plan_path, actions, total_cost)
    print(
        f"{PROG}: plan found, {len(actions)} step(s), cost {total_cost:g} "
        f"-> {plan_path}",
        file=log,
    )

    # Optional POWL2 projection. The plan is the selected transition
    # sequence; POWL is the process geometry it becomes (CHATMAN-EQUATION
    # "Recursive Process Manufacture"). Emitted only on request so the
    # mfw classical-engine contract (exactly 3 args) stays exact.
    if powl_path is not None:
        from autofde_lab.fabric.powl import DigestUnavailable, project_plan_to_powl

        try:
            turtle = project_plan_to_powl(
                [f"{action}" for action in actions],
                base_iri=powl_base_iri,
                domain_path=domain_path,
                problem_path=problem_path,
            )
        except DigestUnavailable as exc:
            print(f"{PROG}: POWL projection refused: {exc}", file=log)
            return EXIT_REFUSED
        with open(powl_path, "w", encoding="utf-8") as handle:
            handle.write(turtle)
        print(f"{PROG}: POWL2 projection -> {powl_path}", file=log)

    return EXIT_PLAN_FOUND


def main(argv: Optional[Sequence[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    # Version witness. Must not import or parse anything, so the banner is
    # never polluted by backend logging and always starts with the pinned
    # prefix.
    if not argv or argv[0] in ("--help", "-h", "--version"):
        sys.stdout.write(USAGE)
        return EXIT_PLAN_FOUND if argv else EXIT_USAGE

    # 3 args is the exact mfw `classical` + `output_mode = "file"` contract.
    # A 4th is accepted as an OPTIONAL POWL2 projection path -- extra, never
    # required, so the mfw placeholder set stays satisfied verbatim.
    if len(argv) not in (3, 4):
        sys.stderr.write(
            f"{PROG}: expected 3 arguments "
            f"(domain, problem, plan-out) or 4 with a POWL output path, "
            f"got {len(argv)}\n"
        )
        sys.stderr.write(USAGE)
        return EXIT_USAGE

    domain_path, problem_path, plan_path = argv[:3]
    powl_path = argv[3] if len(argv) == 4 else None
    return solve_to_plan_file(
        domain_path, problem_path, plan_path, powl_path=powl_path
    )


if __name__ == "__main__":
    raise SystemExit(main())
