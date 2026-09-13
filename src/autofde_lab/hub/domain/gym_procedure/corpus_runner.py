# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Run the whole real gym recipe corpus through :class:`GymProcedureDomain`.

Every recipe under ``recipes/`` is loaded for real and solved for real with a
real registered solver. Nothing is stubbed: a failure to load, a solver that
raises, a solver that exhausts its budget, and a solver that terminates
without reaching the goal are four *distinct, recorded* outcomes rather than
one blurred "didn't work".

Each (recipe, solver) pair is executed in its **own OS process** with its own
result queue. That is not decoration: the prior Level 3 incident in this repo
was parallel work sharing scratch state, one run silently consuming another's.
Process isolation makes cross-run state sharing impossible by construction,
and it is also what makes ``timeout_s`` a real bound -- a wedged solver is
terminated, not merely measured after the fact.
"""

from __future__ import annotations

import multiprocessing as mp
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

from autofde_lab.hub.domain.gym_procedure.gym_procedure import (
    GymProcedureDomain,
    Recipe,
    load_recipe,
)

#: Typed outcomes. Never collapse two of these into one.
SOLVED = "SOLVED"
GOAL_UNREACHED = "GOAL_UNREACHED"
TIMEOUT = "TIMEOUT"
LOAD_ERROR = "LOAD_ERROR"
SOLVER_ERROR = "SOLVER_ERROR"


@dataclass(frozen=True)
class RecipeResult:
    recipe_id: str  # recipe filename stem
    gym: str
    task: str
    n_steps: int  # steps declared by the recipe
    solver: str
    outcome: str
    plan_length: int
    plan: tuple[str, ...]
    duration_s: float
    detail: str = ""


def _step_bound(recipe: Recipe) -> int:
    # A plan can never usefully be longer than the number of distinct steps:
    # every step establishes facts and is filtered out once its effects hold
    # (see ``_get_applicable_actions_from``), so re-applying one is never
    # progress. +2 gives slack for the terminal check without hiding a loop.
    return len(recipe.steps) + 2


def solve_recipe(recipe: Recipe, solver_name: str, step_bound: Optional[int] = None):
    """Solve one recipe with one real registered solver. Returns
    ``(outcome, plan, detail)``. Raises nothing for solver failure -- a
    failure is evidence and is returned typed."""
    from autofde_lab import utils

    bound = step_bound if step_bound is not None else _step_bound(recipe)
    # Separate rollout domain: `Solver.__init__` wraps the factory in a
    # `cast_domain_factory` that MUTATES the returned instance via
    # `autocast_all`. Handing the same object to the solver and to the rollout
    # shares mutable state across a boundary. The rollout domain is never
    # given to a solver.
    domain = GymProcedureDomain(recipe)
    try:
        cls = utils.load_registered_solver(solver_name)
        if cls is None:
            return SOLVER_ERROR, (), f"solver {solver_name!r} is not registered"
        with cls(domain_factory=lambda: GymProcedureDomain(recipe)) as solver:
            solver.solve()
            obs = domain.reset()
            plan: list[str] = []
            for _ in range(bound):
                if domain._is_terminal(obs):
                    break
                action = solver.sample_action(obs)
                # `_get_next_state` applies a step's effects unconditionally.
                # Without this check, a solver proposing a precondition-violating
                # action gets it applied anyway and the harness records SOLVED
                # for a plan that could never run.
                legal = domain._get_applicable_actions_from(obs).get_elements()
                if action not in legal:
                    return (
                        SOLVER_ERROR,
                        tuple(plan),
                        f"proposed inapplicable action {action!r} at step "
                        f"{len(plan)}; applicable={sorted(legal)}",
                    )
                plan.append(action)
                obs = domain.step(action).observation
            if domain._is_goal(obs):
                return SOLVED, tuple(plan), ""
            return (
                GOAL_UNREACHED,
                tuple(plan),
                f"goal facts not reached within {bound} steps; "
                f"missing={sorted(recipe.goal_facts - obs.facts)}",
            )
    except Exception as exc:  # noqa: BLE001 - typed evidence, not a crash
        return SOLVER_ERROR, (), f"{type(exc).__name__}: {exc}"[:300]


def _worker(path_str: str, solver_name: str, queue) -> None:  # pragma: no cover - child process
    try:
        recipe = load_recipe(Path(path_str))
    except Exception as exc:  # noqa: BLE001
        queue.put((LOAD_ERROR, (), f"{type(exc).__name__}: {exc}"[:300]))
        return
    queue.put(solve_recipe(recipe, solver_name))


def run_corpus(
    recipes_dir: Path,
    solver_names: Sequence[str] = ("Astar",),
    timeout_s: float = 30.0,
) -> list[RecipeResult]:
    """Load and solve every ``*.json`` recipe in ``recipes_dir`` with each solver.

    One isolated OS process per (recipe, solver) pair; ``timeout_s`` is a hard
    bound enforced by terminating that process.
    """
    ctx = mp.get_context("spawn")
    results: list[RecipeResult] = []
    for path in sorted(Path(recipes_dir).glob("*.json")):
        # Load once in the parent purely for metadata + typed LOAD_ERROR.
        try:
            recipe = load_recipe(path)
            meta = (recipe.gym, recipe.task, len(recipe.steps))
            load_detail = None
        except Exception as exc:  # noqa: BLE001
            meta = ("", "", 0)
            load_detail = f"{type(exc).__name__}: {exc}"[:300]
        for solver_name in solver_names:
            if load_detail is not None:
                results.append(
                    RecipeResult(path.stem, "", "", 0, solver_name, LOAD_ERROR, 0, (), 0.0, load_detail)
                )
                continue
            queue = ctx.Queue()
            proc = ctx.Process(target=_worker, args=(str(path), solver_name, queue))
            start = time.monotonic()
            proc.start()
            proc.join(timeout_s)
            if proc.is_alive():
                proc.terminate()
                proc.join(5)
                results.append(
                    RecipeResult(
                        path.stem, meta[0], meta[1], meta[2], solver_name, TIMEOUT,
                        0, (), time.monotonic() - start,
                        f"exceeded timeout_s={timeout_s}",
                    )
                )
                continue
            duration = time.monotonic() - start
            try:
                outcome, plan, detail = queue.get_nowait()
            except Exception:  # noqa: BLE001 - child died without reporting
                outcome, plan, detail = (
                    SOLVER_ERROR, (), f"child exited with code {proc.exitcode} and no result",
                )
            results.append(
                RecipeResult(
                    path.stem, meta[0], meta[1], meta[2], solver_name,
                    outcome, len(plan), tuple(plan), duration, detail,
                )
            )
    return results


def format_table(results: Sequence[RecipeResult]) -> str:
    """Plain-text table of real results -- no rounding of failures into successes."""
    w = max((len(r.recipe_id) for r in results), default=10)
    lines = [f"{'recipe':<{w}}  {'steps':>5}  {'solver':<10}  {'outcome':<14}  {'plan':>4}  {'sec':>6}  detail"]
    for r in results:
        lines.append(
            f"{r.recipe_id:<{w}}  {r.n_steps:>5}  {r.solver:<10}  {r.outcome:<14}  "
            f"{r.plan_length:>4}  {r.duration_s:>6.2f}  {r.detail}"
        )
    counts: dict[str, int] = {}
    for r in results:
        counts[r.outcome] = counts.get(r.outcome, 0) + 1
    lines.append("")
    lines.append(f"TOTAL {len(results)}: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    return "\n".join(lines)


if __name__ == "__main__":  # pragma: no cover
    import sys

    default_dir = Path(__file__).parent / "recipes"
    d = Path(sys.argv[1]) if len(sys.argv) > 1 else default_dir
    solvers = sys.argv[2].split(",") if len(sys.argv) > 2 else ["Astar"]
    to = float(sys.argv[3]) if len(sys.argv) > 3 else 30.0
    print(format_table(run_corpus(d, solvers, to)))
