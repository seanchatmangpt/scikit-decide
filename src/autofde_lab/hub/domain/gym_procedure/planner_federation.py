# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Real planner-federation inventory + bounded multi-solver execution.

Not "assume 50+ planners" -- measure. `classify_registered_solvers`
enumerates every solver actually registered under the
`autofde_lab.solvers` entry-point group and classifies each via the exact
mechanism the solver framework itself uses to gate applicability
(`cls.check_domain(domain)`), against a real `GymProcedureDomain` instance.
`run_federation` then executes every classified-SUPPORTED solver within a
bounded per-solver time budget and records a `PlannerAttempt` for every
one, including solvers that time out or raise -- disagreement/failure is
evidence, not something to discard.
"""

from __future__ import annotations

import inspect
import time
from dataclasses import dataclass
from importlib.metadata import entry_points

from autofde_lab.hub.domain.gym_procedure.gym_procedure import (
    GymProcedureDomain,
    Recipe,
)


@dataclass(frozen=True)
class SolverClassification:
    name: str
    entry_point: str
    status: str  # "SUPPORTED" | "UNSUPPORTED:<reason>" | "UNAVAILABLE:<reason>"
    #: Applicability and runnability are DIFFERENT FACTS and both are reported.
    #: `status` answers "does `cls.check_domain(domain)` admit this domain?" --
    #: the ontology question. `constructibility` answers "can this class
    #: actually be instantiated with the arguments the federation supplies?"
    #: `Solver.get_domain_requirements()` derives domain *characteristics* and
    #: says nothing about *constructor* requirements (`src/autofde_lab/CLAUDE.md`
    #: invariant 2), so a solver can be SUPPORTED and still not constructible.
    #: Neither field is derivable from the other; a SUPPORTED solver is never
    #: demoted to UNSUPPORTED merely because it needs configuration.
    #:   "CONSTRUCTIBLE"                              -- defaults suffice
    #:   "CONSTRUCTIBLE:VIA_SOLVER_KWARGS(<args>)"    -- `solver_kwargs` supplies them
    #:   "NOT_CONSTRUCTIBLE:REQUIRES_CONFIGURATION(<args>)"
    #:   "UNKNOWN:<reason>"                           -- signature not introspectable
    constructibility: str = "UNKNOWN:NOT_ASSESSED"


def unmet_required_args(cls: type, provided: dict) -> tuple[str, ...]:
    """Constructor arguments `cls` requires that neither defaults nor `provided` supply.

    Deliberately STATIC (`inspect.signature`) rather than a trial
    instantiation: constructing a real solver can spawn native code, allocate
    a Ray cluster, or segfault (see `_solve_one_isolated`), none of which is
    an acceptable cost for an inventory pass. Signature inspection is exact
    for the one failure class this predicts -- `TypeError: missing 1 required
    positional argument` -- which is also what `fabric.coverage.classify_failure`
    maps to `REQUIRES_CONFIGURATION` after the fact. Measuring it *before*
    running turns a post-hoc raw TypeError into a typed, predicted outcome.
    """
    try:
        sig = inspect.signature(cls.__init__)
    except (ValueError, TypeError):
        return ()
    return tuple(
        p.name
        for p in sig.parameters.values()
        if p.name not in ("self", "domain_factory")
        and p.default is inspect.Parameter.empty
        and p.kind
        in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        )
        and p.name not in provided
    )


def _constructibility(cls: type, solver_name: str, recipe: Recipe) -> str:
    try:
        inspect.signature(cls.__init__)
    except (ValueError, TypeError) as exc:
        return f"UNKNOWN:{type(exc).__name__}"
    provided = solver_kwargs(solver_name, recipe)
    unmet = unmet_required_args(cls, provided)
    if unmet:
        return f"NOT_CONSTRUCTIBLE:REQUIRES_CONFIGURATION({','.join(unmet)})"
    if provided and not unmet_required_args(cls, {}):
        return "CONSTRUCTIBLE"
    if provided:
        return f"CONSTRUCTIBLE:VIA_SOLVER_KWARGS({','.join(sorted(provided))})"
    return "CONSTRUCTIBLE"


def recipe_problem_digest(recipe: Recipe) -> str:
    """The problem identity every attempt on this recipe is stamped with.

    Exposed (rather than computed inline in `run_federation`) so a producer
    running outside `run_federation` -- `typed_search` -- stamps its attempt
    with the SAME digest, and so its record is comparable to the others
    instead of merely adjacent to them.
    """
    import hashlib
    import json

    return hashlib.sha256(
        json.dumps(
            {
                "initial": sorted(recipe.initial_facts),
                "goal": sorted(recipe.goal_facts),
                "steps": sorted(s.id for s in recipe.steps),
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()[:16]


@dataclass(frozen=True)
class PlannerAttempt:
    planner_identity: str
    representation: str
    problem_digest: str
    # "PLAN_CANDIDATE" | "UNSUPPORTED" | "UNSUPPORTED:REQUIRES_CONFIGURATION"
    # | "TIMEOUT" | "FAILED" | "REFUSED" | "CRASHED"
    outcome: str
    candidate_plan: tuple[str, ...] = ()
    planning_duration_s: float = 0.0
    detail: str = ""


def classify_registered_solvers(recipe: Recipe) -> list[SolverClassification]:
    """Real classification against a real domain instance -- no hardcoded list."""
    domain = GymProcedureDomain(recipe)
    results: list[SolverClassification] = []
    for ep in entry_points(group="autofde_lab.solvers"):
        try:
            cls = ep.load()
        except Exception as exc:  # noqa: BLE001 - genuinely need to record any import failure as evidence
            results.append(
                SolverClassification(
                    name=ep.name,
                    entry_point=ep.value,
                    status=f"UNAVAILABLE:{type(exc).__name__}",
                )
            )
            continue
        try:
            ok = cls.check_domain(domain)
            status = "SUPPORTED" if ok else "UNSUPPORTED:CHECK_DOMAIN_FALSE"
        except Exception as exc:  # noqa: BLE001
            status = f"UNSUPPORTED:{type(exc).__name__}"
        try:
            constructibility = _constructibility(cls, ep.name, recipe)
        except Exception as exc:  # noqa: BLE001
            constructibility = f"UNKNOWN:{type(exc).__name__}"
        results.append(
            SolverClassification(
                name=ep.name,
                entry_point=ep.value,
                status=status,
                constructibility=constructibility,
            )
        )
    return results


def solver_kwargs(solver_name: str, recipe: Recipe) -> dict:
    """Real, principled constructor arguments for solvers that genuinely require them.

    `Solver.get_domain_requirements()` derives *domain characteristics* only and
    says nothing about *constructor* requirements (see
    `hub/solver/CLAUDE.md` invariant 1). So a solver can classify SUPPORTED and
    still refuse `cls(domain_factory=...)` alone. `IW`, `RIW` and `BFWS` are the
    real case here: all three implement iterated-width novelty search, which is
    *defined* over a vector of state atoms, so `state_features` is a genuine
    algorithmic input, not boilerplate. A recipe supplies exactly that vector:
    the fact universe it can ever mention, as a fixed-order 0/1 membership
    vector. This is the standard IW propositional feature set, not a stand-in.
    """
    if solver_name in ("IW", "RIW", "BFWS"):
        universe = sorted(
            set(recipe.initial_facts)
            | set(recipe.goal_facts)
            | {f for s in recipe.steps for f in s.preconditions}
            | {f for s in recipe.steps for f in s.establishes}
            | {f for s in recipe.steps for f in s.removes}
        )
        return {
            "state_features": lambda d, s, _u=tuple(universe): [
                1 if f in s.facts else 0 for f in _u
            ]
        }
    return {}


def _solve_one(
    solver_name: str, recipe: Recipe, timeout_s: float, problem_digest: str
) -> PlannerAttempt:
    from autofde_lab import utils

    # Two SEPARATE domain instances, deliberately. `Solver.__init__` wraps the
    # factory so that `autocast_all(domain, domain, T_domain)` MUTATES whatever
    # instance the factory hands back. Passing `lambda: domain` and then
    # rolling out on that same `domain` therefore rolls out on a
    # solver-mutated object -- shared mutable state across a boundary, the same
    # class of defect as the Level 3 shared-scratch incident. The rollout
    # domain below is never given to any solver.
    rollout_domain = GymProcedureDomain(recipe)
    start = time.monotonic()
    try:
        cls = utils.load_registered_solver(solver_name)
        if cls is None:
            return PlannerAttempt(
                solver_name,
                "recipe",
                problem_digest,
                "UNSUPPORTED",
                detail="not registered",
            )
        # A solver that cannot be constructed with the arguments this harness
        # supplies is NOT a failed plan search -- it never searched. Recording
        # it as the generic FAILED with a raw `TypeError: missing 1 required
        # positional argument` conflates "this planner looked and found
        # nothing" with "this planner was never configured", which are
        # different facts about the federation. Detect it up front and emit a
        # typed outcome whose cause matches
        # `fabric.coverage.CAUSE_REQUIRES_CONFIGURATION`.
        unmet = unmet_required_args(cls, solver_kwargs(solver_name, recipe))
        if unmet:
            return PlannerAttempt(
                solver_name,
                "recipe",
                problem_digest,
                "UNSUPPORTED:REQUIRES_CONFIGURATION",
                (),
                time.monotonic() - start,
                detail=(
                    "constructor requires argument(s) the federation does not "
                    f"supply: {', '.join(unmet)}; solver is check_domain-applicable "
                    "but not runnable with defaults"
                ),
            )
        step_bound = len(recipe.steps) + 2
        with cls(
            domain_factory=lambda: GymProcedureDomain(recipe),
            **solver_kwargs(solver_name, recipe),
        ) as solver:
            solver.solve()
            domain = rollout_domain
            obs = domain.reset()
            plan: list[str] = []
            for _ in range(step_bound):
                if time.monotonic() - start > timeout_s:
                    return PlannerAttempt(
                        solver_name,
                        "recipe",
                        problem_digest,
                        "TIMEOUT",
                        tuple(plan),
                        time.monotonic() - start,
                    )
                if domain._is_terminal(obs):
                    break
                action = solver.sample_action(obs)
                # A plan is only a candidate if every action in it was legal in
                # the state it was taken from. `GymProcedureDomain._get_next_state`
                # applies a step's effects unconditionally -- it trusts the
                # caller to have checked `get_applicable_actions`. Without this
                # check a solver that samples from the full action space (the
                # POMDP solvers do) gets its precondition-violating action
                # applied anyway and the federation records a PLAN_CANDIDATE
                # for a plan that could never run. Measured: SARSOP "solved"
                # agentdojo_banking_pay_bill in 1 step by paying a bill it had
                # never read. That is a false success, so it is refused here.
                legal = domain._get_applicable_actions_from(obs).get_elements()
                if action not in legal:
                    return PlannerAttempt(
                        solver_name,
                        "recipe",
                        problem_digest,
                        "REFUSED",
                        tuple(plan),
                        time.monotonic() - start,
                        detail=(
                            f"proposed inapplicable action {action!r} at step "
                            f"{len(plan)}; applicable={sorted(legal)}"
                        ),
                    )
                plan.append(action)
                outcome = domain.step(action)
                obs = outcome.observation
            duration = time.monotonic() - start
            if domain._is_goal(obs):
                return PlannerAttempt(
                    solver_name,
                    "recipe",
                    problem_digest,
                    "PLAN_CANDIDATE",
                    tuple(plan),
                    duration,
                )
            return PlannerAttempt(
                solver_name,
                "recipe",
                problem_digest,
                "FAILED",
                tuple(plan),
                duration,
                detail="goal not reached within step bound",
            )
    except Exception as exc:  # noqa: BLE001 - a solver failure is evidence, not a crash of the federation
        return PlannerAttempt(
            solver_name,
            "recipe",
            problem_digest,
            "FAILED",
            (),
            time.monotonic() - start,
            detail=f"{type(exc).__name__}: {exc}"[:200],
        )


_SIGNAL_NAMES = {6: "SIGABRT", 8: "SIGFPE", 9: "SIGKILL", 11: "SIGSEGV"}


def _solve_one_isolated(
    solver_name: str, recipe: Recipe, timeout_s: float, problem_digest: str
) -> PlannerAttempt:
    """Run one planner in a forked child so a NATIVE crash is evidence.

    `_solve_one`'s `except Exception` catches Python exceptions only. A C++
    hub solver that segfaults raises nothing -- it kills the interpreter,
    and with it every other planner's evidence and every remaining trial of
    a frozen crown. Measured: the C++ `AOstar` solver dies with SIGSEGV on
    the `lock_and_key` recipe, taking the whole harness down mid-run.

    Isolation also gives the only real wall-clock bound available: the
    in-process timeout in `_solve_one` is checked between rollout steps, so
    it cannot interrupt a native `solve()` that never returns.

    A crash is recorded as `CRASHED`, never silently dropped and never
    upgraded to a plan -- federation output is advisory in any case, and
    the typed model remains the authoritative validation gate.
    """
    import multiprocessing as mp

    try:
        ctx = mp.get_context("fork")
    except ValueError:  # platform without fork -- no isolation available
        return _solve_one(solver_name, recipe, timeout_s, problem_digest)

    parent_conn, child_conn = ctx.Pipe(duplex=False)

    def _target(conn) -> None:
        try:
            conn.send(_solve_one(solver_name, recipe, timeout_s, problem_digest))
        except BaseException as exc:  # noqa: BLE001
            conn.send(
                PlannerAttempt(
                    solver_name, "recipe", problem_digest, "FAILED", (), 0.0,
                    detail=f"{type(exc).__name__}: {exc}"[:200],
                )
            )
        finally:
            conn.close()

    proc = ctx.Process(target=_target, args=(child_conn,), daemon=True)
    start = time.monotonic()
    proc.start()
    child_conn.close()

    # Generous margin over the solver's own budget: this bound exists to
    # catch a hung native solve, not to second-guess `_solve_one`.
    attempt: PlannerAttempt | None = None
    if parent_conn.poll(timeout_s + 10.0):
        try:
            attempt = parent_conn.recv()
        except EOFError:
            attempt = None
    parent_conn.close()

    proc.join(timeout=5.0)
    if proc.is_alive():
        proc.kill()
        proc.join(timeout=5.0)
        return PlannerAttempt(
            solver_name, "recipe", problem_digest, "TIMEOUT", (),
            time.monotonic() - start,
            detail=f"killed after {timeout_s + 10.0:.1f}s wall clock (native solve did not return)",
        )
    if attempt is not None:
        return attempt

    code = proc.exitcode
    if code is not None and code < 0:
        signame = _SIGNAL_NAMES.get(-code, f"signal {-code}")
        return PlannerAttempt(
            solver_name, "recipe", problem_digest, "CRASHED", (),
            time.monotonic() - start,
            detail=f"planner process died with {signame} (native crash, no Python exception)",
        )
    return PlannerAttempt(
        solver_name, "recipe", problem_digest, "CRASHED", (),
        time.monotonic() - start,
        detail=f"planner process exited with code {code} without returning an attempt",
    )


# --------------------------------------------------------------------------
# typed_search as a FIRST-CLASS candidate producer
# --------------------------------------------------------------------------
#
# The governance defect this closes, measured on an archived trial's
# `federation.json`: 49 planners attempted, 13 produced PLAN_CANDIDATE, 0
# matched the committed plan, and `committed_plan_source` read
# `"typed_search"`. The federation was therefore OBSERVATIONAL -- its
# candidates were validated and discarded while the plan that actually
# reached commitment came from `search_plan_typed`, called directly, outside
# the `PlannerAttempt` record, outside `federation.json`, outside the
# advisory ranking, and outside the common candidate contract every other
# producer had to satisfy.
#
# The fix is NOT to remove `search_plan_typed` -- it is the only producer
# that reaches the goal on several providers, so deleting it would trade a
# governance defect for a capability regression. It joins the contract: same
# `PlannerAttempt` shape, same typed outcome vocabulary, same appearance in
# `federation.json`, same advisory ranking, same independent validation.

TYPED_SEARCH_PLANNER_ID = "typed_search"


def run_typed_search_attempt(
    typed_domain,
    typed_initial: dict,
    goal_predicate,
    problem_digest: str,
    timeout_s: float = 15.0,
    max_len: int = 12,
) -> PlannerAttempt:
    """Run `search_plan_typed` as one more federated planner.

    `representation` is `"typed_model"` rather than `"recipe"` -- that is a
    real and reportable difference from the Astar/LRTDP/EHC attempts (it
    searches the typed model, not the projected recipe), and hiding it would
    misattribute provenance. Everything else is identical: the same record
    type, the same outcome vocabulary, the same problem digest.

    Outcome mapping, all real facts about this run:
      UNSUPPORTED  -- no typed actions or no typed initial state to search from
      PLAN_CANDIDATE -- a plan was found AND survived `validate_plan_typed`
      REFUSED      -- a plan was found and its own validator rejected it
                      (model self-inconsistency; never silently upgraded)
      TIMEOUT      -- no plan, and the search exceeded the budget
      FAILED       -- no plan within the budget and the length bound
    """
    from autofde_lab.hub.domain.gym_procedure.typed_induction import (
        search_plan_typed,
        validate_plan_typed,
    )

    start = time.monotonic()
    # Guarded on ACTIONS only, deliberately. An all-False initial state is a
    # real state, not an absent one; the absent case (`typed_records` empty in
    # the crown) also leaves the model with no actions, so this catches it
    # without misreporting a legitimately empty state as UNSUPPORTED.
    if not getattr(typed_domain, "actions", None):
        return PlannerAttempt(
            TYPED_SEARCH_PLANNER_ID,
            "typed_model",
            problem_digest,
            "UNSUPPORTED",
            (),
            time.monotonic() - start,
            detail="typed model has no actions or no observed initial state",
        )
    try:
        searched = search_plan_typed(
            typed_domain, typed_initial, goal_predicate, max_len=max_len
        )
    except Exception as exc:  # noqa: BLE001 - a producer failure is evidence
        return PlannerAttempt(
            TYPED_SEARCH_PLANNER_ID,
            "typed_model",
            problem_digest,
            "FAILED",
            (),
            time.monotonic() - start,
            detail=f"{type(exc).__name__}: {exc}"[:200],
        )
    duration = time.monotonic() - start
    if searched is None:
        # The bound is checked after the fact rather than interrupting the
        # BFS: `search_plan_typed` is a pure in-process loop with no
        # cancellation point. "It ran over budget and found nothing" is still
        # a true, distinct fact from "it finished under budget and found
        # nothing", and both are reported honestly.
        outcome = "TIMEOUT" if duration > timeout_s else "FAILED"
        return PlannerAttempt(
            TYPED_SEARCH_PLANNER_ID,
            "typed_model",
            problem_digest,
            outcome,
            (),
            duration,
            detail=f"no typed-model plan within max_len={max_len}",
        )
    ok, _final, reason = validate_plan_typed(
        typed_domain, typed_initial, searched, goal_predicate
    )
    if not ok:
        return PlannerAttempt(
            TYPED_SEARCH_PLANNER_ID,
            "typed_model",
            problem_digest,
            "REFUSED",
            tuple(searched),
            duration,
            detail=f"typed search produced a plan its own validator rejected: {reason}",
        )
    return PlannerAttempt(
        TYPED_SEARCH_PLANNER_ID,
        "typed_model",
        problem_digest,
        "PLAN_CANDIDATE",
        tuple(searched),
        duration,
    )


# --------------------------------------------------------------------------
# The common candidate contract -- structural, not advisory
# --------------------------------------------------------------------------


class UngovernedCandidateRefused(Exception):
    """A plan that never entered the common candidate set tried to source a commitment."""


@dataclass(frozen=True)
class GovernedCandidate:
    """Proof that a plan entered the common set through a real PlannerAttempt.

    Forging one is not enough to source a commitment: `require_governed`
    checks membership in the issuing set's own registry, keyed by an
    admission digest that includes a per-set nonce no caller can predict.
    Constructing this dataclass by hand therefore produces an object that
    every gate rejects.
    """

    plan: tuple[str, ...]
    planner_identity: str
    representation: str
    problem_digest: str
    admission_digest: str


class CommonCandidateSet:
    """Every candidate producer's output funnels through here, or nowhere.

    This is the enforcement point for "no plan source may bypass the common
    path". It is structural for anything that asks it -- `require_governed`
    raises `UngovernedCandidateRefused` on a plan it never admitted -- and
    the call site that must ask is the commitment edge in
    `level4_crown.run_real_trial`, immediately before `commit()`.
    """

    def __init__(self, problem_digest: str) -> None:
        import secrets

        self.problem_digest = problem_digest
        self._nonce = secrets.token_hex(16)
        self._admitted: dict[str, GovernedCandidate] = {}
        self._order: list[GovernedCandidate] = []

    def _digest(self, planner: str, plan: tuple[str, ...]) -> str:
        import hashlib
        import json

        return hashlib.sha256(
            json.dumps(
                [self._nonce, self.problem_digest, planner, list(plan)], sort_keys=True
            ).encode()
        ).hexdigest()[:32]

    def admit(self, attempt: PlannerAttempt) -> GovernedCandidate | None:
        """Admit one attempt. Only `PLAN_CANDIDATE` yields a candidate.

        A non-candidate outcome is not an error and is not discarded -- it
        stays in `federation.json` as evidence -- it simply cannot become
        something a commitment may be sourced from.
        """
        if attempt.outcome != "PLAN_CANDIDATE":
            return None
        plan = tuple(attempt.candidate_plan)
        digest = self._digest(attempt.planner_identity, plan)
        cand = GovernedCandidate(
            plan=plan,
            planner_identity=attempt.planner_identity,
            representation=attempt.representation,
            problem_digest=attempt.problem_digest,
            admission_digest=digest,
        )
        if digest not in self._admitted:
            self._admitted[digest] = cand
            self._order.append(cand)
        return self._admitted[digest]

    def admit_all(self, attempts: list[PlannerAttempt]) -> list[GovernedCandidate]:
        return [c for c in (self.admit(a) for a in attempts) if c is not None]

    def candidates(self) -> tuple[GovernedCandidate, ...]:
        return tuple(self._order)

    def distinct_plans(self) -> tuple[tuple[str, ...], ...]:
        seen: list[tuple[str, ...]] = []
        for c in self._order:
            if c.plan not in seen:
                seen.append(c.plan)
        return tuple(seen)

    def is_governed(self, plan) -> bool:
        return any(c.plan == tuple(plan) for c in self._order)

    def require_governed(self, plan, planner_identity: str = "") -> GovernedCandidate:
        """Typed refusal for a plan that did not come through the common set."""
        plan_t = tuple(plan)
        for c in self._order:
            if c.plan == plan_t and (
                not planner_identity or c.planner_identity == planner_identity
            ):
                return c
        raise UngovernedCandidateRefused(
            "UNGOVERNED_CANDIDATE_SOURCED_COMMITMENT: plan "
            f"{list(plan_t)} (claimed source {planner_identity or 'unknown'!r}) "
            "did not enter the common candidate set via a PlannerAttempt; "
            f"governed candidates={[ (c.planner_identity, list(c.plan)) for c in self._order ]}"
        )


def select_governed_candidate(
    common: CommonCandidateSet,
    typed_domain,
    typed_initial: dict,
    goal_predicate,
    ranking: tuple[tuple[str, tuple[str, ...], float], ...] = (),
) -> tuple[GovernedCandidate | None, list[dict]]:
    """Validate EVERY governed candidate, in advisory-ranked order, and select.

    `ranking` is advisory: it orders the validation sweep and therefore which
    valid candidate is selected first. It cannot admit a candidate the common
    set never admitted, and it cannot skip validation for one it prefers.
    Candidates absent from `ranking` (e.g. a producer the critique layer did
    not rank) are still validated, appended after the ranked ones -- silently
    dropping them would recreate the bypass in the opposite direction.
    """
    from autofde_lab.hub.domain.gym_procedure.typed_induction import validate_plan_typed

    order = {plan: i for i, (_p, plan, _s) in enumerate(ranking)}
    ordered = sorted(
        common.candidates(), key=lambda c: order.get(c.plan, len(order) + 1)
    )
    selected: GovernedCandidate | None = None
    verdicts: list[dict] = []
    seen: set[tuple[str, ...]] = set()
    for cand in ordered:
        if cand.plan in seen:
            continue
        seen.add(cand.plan)
        ok, _final, reason = validate_plan_typed(
            typed_domain, typed_initial, cand.plan, goal_predicate
        )
        verdicts.append(
            {
                "planner": cand.planner_identity,
                "representation": cand.representation,
                "plan": list(cand.plan),
                "valid": bool(ok),
                "reason": reason,
            }
        )
        if ok and selected is None:
            selected = cand
    return selected, verdicts


def run_federation(
    recipe: Recipe, solver_names: list[str], timeout_s: float = 15.0
) -> list[PlannerAttempt]:
    """Run every named solver (already classified SUPPORTED) within a bounded
    per-solver timeout; record every attempt, including non-successes."""
    problem_digest = recipe_problem_digest(recipe)
    return [
        _solve_one_isolated(name, recipe, timeout_s, problem_digest)
        for name in solver_names
    ]
