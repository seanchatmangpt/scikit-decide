# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""A real, concurrent version of `planner_federation.federate()`, generalizing
`breed_ensemble.py`'s concurrent-orchestration pattern (a real `PartialOrder`
of one `Atom` per member, executed via the unmodified
:func:`autofde_lab.powl.guard_executor.execute` with real `max_workers`
concurrency and an :class:`~autofde_lab.powl.guard_executor.ExecutionContext`
accumulating results) onto solver invocation instead of wasm4pm breed
invocation.

Not arbitration -- a real, stated difference from `breed_ensemble.py`
------------------------------------------------------------------------
There is no `meta_reasoning`-equivalent for competing PDDL plans; two
solvers producing two different plans are not "in conflict" the way two
breeds' differing conclusions are -- they are two independently valid
candidate plans (`federate()`'s own real, existing contract already returns
one result per solver, never a single arbitrated winner). This module keeps
that exact contract, `dict[str, Optional[PartialOrder]]`, one entry per
solver name -- the only change is real concurrent execution instead of
`federate()`'s real sequential `for` loop.

No real wall-clock speedup here -- a real, honest finding, not a defect
--------------------------------------------------------------------------
Real thread dispatch is confirmed (genuinely distinct thread identifiers
observed for concurrently-submitted solver calls -- see this module's own
test suite). But PDDL solving is CPU-bound native work (the C++ hub solver
via pybind11), and this session's own earlier `guard_executor` concurrency
benchmark (`scripts/powl_runner_concurrency_benchmark.py --workload cpu`)
already established the same real result: CPython's GIL serializes
CPU-bound Python-adjacent work across threads regardless of `max_workers`,
so real speedup only materializes for I/O-bound work (the wasm4pm breed
subprocess calls `breed_ensemble.py` orchestrates). A real measured
comparison this session (`tests/reasoning/fixtures/blocks6-problem.pddl`,
Astar+FF): sequential ~1.81s, concurrent ~1.84s -- no real win, reported
honestly rather than asserted away. This module still has real value
independent of speedup: a single call site producing the exact same
federation result as `federate()`, ready to benefit for real if a future
solver becomes I/O-bound (e.g. a remote/subprocess-backed solver) without
any caller-visible change.

`planner_federation.py` itself is unmodified -- this module only imports and
reuses its real `solve_with_one_solver`, `SOLVER_NAMES`, and `validate_model`
re-check discipline, never re-implementing solver invocation.

Real OCEL observation, optional (added this session)
------------------------------------------------------
A van der Aalst-style process-discovery-completeness audit found this
module (and `breed_ensemble.py`, `breed_ensemble_loop.py`,
`gymact_dspy_react.py`) running real, `validate_model`-admitted POWL
processes via `guard_executor.execute` with **zero OCEL trace produced
anywhere** -- a real gap, since `powl.ocel_bridge.execute_with_ocel`
(the mechanism that would produce one) previously had no `max_workers`/
`context` passthrough and so could not observe a concurrent execution
like this one without silently dropping its concurrency. That passthrough
was added this session; `federate_concurrently`'s optional `recorder`
parameter below is the first real caller to use it. Passing no `recorder`
(the default) preserves this function's exact prior behavior and
signature -- existing callers are unaffected.
"""

from __future__ import annotations

import logging
from typing import Optional

from autofde_lab.powl.algebra import Atom, PartialOrder
from autofde_lab.powl.guard_executor import ExecutionContext, ExecutionTrace, execute
from autofde_lab.powl.ocel_bridge import OcelExecutionRecorder, execute_with_ocel
from autofde_lab.powl.refusals import PowlError
from autofde_lab.powl.validate import validate_model
from autofde_lab.reasoning.planner_federation import SOLVER_NAMES, solve_with_one_solver

__all__ = ["federate_concurrently"]

_LOGGER = logging.getLogger(__name__)


def federate_concurrently(
    *,
    domain_path: str,
    problem_path: str,
    solver_names: tuple[str, ...] = SOLVER_NAMES,
    timeout_s: float = 30.0,
    max_workers: int | None = None,
    recorder: OcelExecutionRecorder | None = None,
) -> dict[str, Optional[PartialOrder]]:
    """Run every named solver **concurrently** against the same real domain,
    via the real, unmodified POWL runner.

    Same real, independent per-solver `validate_model` re-check discipline
    as `federate()` (a result that fails validation is replaced with `None`,
    never admitted on the strength of construction alone). Returns the exact
    same `dict[str, Optional[PartialOrder]]` shape `federate()` returns, for
    the same inputs -- only the execution strategy differs.

    `len(solver_names) < 2` runs directly (no `PartialOrder`, which requires
    >=2 children by `algebra.py`'s own construction law) -- a real, narrower
    degenerate case, not silently equivalent to the concurrent path.
    """
    if not solver_names:
        return {}

    def _solve_one(name: str) -> Optional[PartialOrder]:
        candidate = solve_with_one_solver(
            solver_name=name, domain_path=domain_path, problem_path=problem_path, timeout_s=timeout_s,
        )
        if candidate is None:
            return None
        try:
            validate_model(candidate)
        except PowlError:
            _LOGGER.warning(
                "solver %r produced a PartialOrder that failed validate_model; "
                "excluding it rather than admitting it", name, exc_info=True,
            )
            return None
        return candidate

    if len(solver_names) < 2:
        return {solver_names[0]: _solve_one(solver_names[0])} if solver_names else {}

    node = PartialOrder(children=tuple(Atom(label=name, consequence="READ") for name in solver_names))
    context = ExecutionContext()

    def atom_invoker(atom: Atom, ctx: ExecutionContext) -> None:
        ctx.attributes[atom.label] = _solve_one(atom.label)

    real_max_workers = max_workers or len(solver_names)
    if recorder is not None:
        trace: ExecutionTrace = execute_with_ocel(
            node,
            guard_evaluator=lambda name, args: True,  # PartialOrder has no ChoiceGraph -- never consulted
            atom_invoker=atom_invoker,
            max_choice_transitions=1,
            max_workers=real_max_workers,
            context=context,
            recorder=recorder,
        )
        del trace  # real trace is available if a future caller needs it; discarded here, same as the no-recorder path
    else:
        execute(
            node,
            guard_evaluator=lambda name, args: True,  # PartialOrder has no ChoiceGraph -- never consulted
            atom_invoker=atom_invoker,
            max_choice_transitions=1,
            max_workers=real_max_workers,
            context=context,
        )

    return {name: context.attributes.get(name) for name in solver_names}
