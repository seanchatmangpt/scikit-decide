"""Chicago-style tests for the FOND x HDDL product state X = (W, tau).

Real `HDDLDomain`/`ProductState` instances, real transition functions, real
`fond_policy.check_candidate_policy` runs. No mocking: this module exercises
the actual product construction end to end and asserts on real returned
state (FONDProblem contents, PolicyCheck fields, ProductState facts) -- never
on "was this called."
"""

from __future__ import annotations

from autofde_lab.planning.fond_hddl import (
    HDDLProgressWitness,
    check_fond_hddl_frontier_closure,
)
from autofde_lab.planning.fond_hddl_product import (
    FairnessClass,
    HDDLDomain,
    Method,
    Outcome,
    PrimitiveAction,
    ProductState,
    Task,
    build_fond_problem,
    candidate_policy_over_product,
    classify_action_fairness,
    flat_fond_problem_from_product,
    method_refinements,
    ready_action_transitions,
)
from autofde_lab.planning.fond_policy import (
    CandidatePolicy,
    FONDProblem,
    PolicySemantics,
    check_candidate_policy,
)


# ---------------------------------------------------------------------------
# (a) deterministic-HDDL reduction
# ---------------------------------------------------------------------------


def _deterministic_build_domain() -> HDDLDomain:
    tasks = {
        "build": Task("build", primitive=False),
        "compile": Task("compile", primitive=True),
        "link": Task("link", primitive=True),
    }
    methods = {
        "build": (
            Method(
                name="build-m1",
                task="build",
                preconditions=frozenset({"source-ready"}),
                subtasks=("compile", "link"),
            ),
        )
    }
    actions = {
        "compile": PrimitiveAction(
            name="compile",
            preconditions=frozenset({"source-ready"}),
            outcomes=frozenset({Outcome(add=frozenset({"object-ready"}))}),
        ),
        "link": PrimitiveAction(
            name="link",
            preconditions=frozenset({"object-ready"}),
            outcomes=frozenset({Outcome(add=frozenset({"binary-ready"}))}),
        ),
    }
    return HDDLDomain(tasks=tasks, methods=methods, actions=actions)


def test_deterministic_hddl_reduction_matches_manual_decomposition_and_execution() -> None:
    domain = _deterministic_build_domain()
    initial = ProductState(world=frozenset({"source-ready"}), tau=("build",))

    def is_goal(state: ProductState) -> bool:
        return not state.tau and "binary-ready" in state.world

    # Manual, non-product classical HDDL: decompose then execute by hand.
    refinements = method_refinements(domain, initial)
    assert len(refinements) == 1
    decomposed = next(iter(refinements)).successor
    assert decomposed.tau == ("compile", "link")

    step1 = next(iter(ready_action_transitions(domain, decomposed))).successor
    assert step1.world == frozenset({"source-ready", "object-ready"})
    assert step1.tau == ("link",)

    step2 = next(iter(ready_action_transitions(domain, step1))).successor
    assert step2.world == frozenset({"source-ready", "object-ready", "binary-ready"})
    assert step2.tau == ()
    manual_final = step2

    # Product construction: same domain, same initial state, explored via BFS.
    reachability = build_fond_problem(domain, initial, is_goal)
    problem = reachability.fond_problem
    assert manual_final.key() in problem.goal_states

    # Every action in a fully-deterministic domain has exactly one outcome,
    # so every transition set in the folded FONDProblem is a singleton --
    # execution is unambiguous, matching plain HDDL decomposition/execution.
    for outcomes in problem.transitions.values():
        assert len(outcomes) == 1

    policy = CandidatePolicy(
        actions={
            initial.key(): "refine:build-m1",
            decomposed.key(): "compile",
            step1.key(): "link",
        }
    )
    check = check_candidate_policy(problem, policy, semantics=PolicySemantics.STRONG)
    assert check.valid
    assert check.reachable_states == frozenset(
        {initial.key(), decomposed.key(), step1.key(), manual_final.key()}
    )


# ---------------------------------------------------------------------------
# (b) flat-FOND reduction
# ---------------------------------------------------------------------------


def _flat_toggle_domain() -> HDDLDomain:
    tasks = {"toggle": Task("toggle", primitive=True)}
    actions = {
        "toggle": PrimitiveAction(
            name="toggle",
            preconditions=frozenset(),
            outcomes=frozenset(
                {
                    Outcome(add=frozenset({"on"})),
                    Outcome(add=frozenset(), delete=frozenset()),
                }
            ),
        )
    }
    return HDDLDomain(tasks=tasks, methods={}, actions=actions)


def test_flat_fond_reduction_matches_hand_built_plain_fond_problem() -> None:
    domain = _flat_toggle_domain()
    initial = ProductState(world=frozenset(), tau=("toggle",))

    def is_goal(state: ProductState) -> bool:
        return not state.tau and "on" in state.world

    product_problem = flat_fond_problem_from_product(domain, initial, is_goal)

    # No hierarchy at all: no "refine:" action id ever appears.
    assert all(
        not action.startswith("refine:") for (_, action) in product_problem.transitions
    )

    on_state = ProductState(world=frozenset({"on"}), tau=()).key()
    off_state = ProductState(world=frozenset(), tau=()).key()

    # Hand-built plain FONDProblem over the identical state/action space,
    # using fond_policy.py's own types directly, no product machinery.
    plain_problem = FONDProblem(
        initial_state=initial.key(),
        goal_states=frozenset({on_state}),
        transitions={(initial.key(), "toggle"): frozenset({on_state, off_state})},
    )
    assert product_problem.initial_state == plain_problem.initial_state
    assert product_problem.goal_states == plain_problem.goal_states
    assert product_problem.transitions == plain_problem.transitions

    policy = candidate_policy_over_product({initial.key(): "toggle"})
    product_check = check_candidate_policy(
        product_problem, policy, semantics=PolicySemantics.STRONG_CYCLIC
    )
    plain_check = check_candidate_policy(
        plain_problem, policy, semantics=PolicySemantics.STRONG_CYCLIC
    )
    assert product_check == plain_check


# ---------------------------------------------------------------------------
# (c) incompatible-frontier rejection
# ---------------------------------------------------------------------------


def test_incompatible_world_and_hddl_frontier_is_rejected_not_silently_accepted() -> None:
    tasks = {
        "deploy": Task("deploy", primitive=False),
        "ship": Task("ship", primitive=True),
    }
    methods = {
        "deploy": (
            Method(
                name="deploy-m1",
                task="deploy",
                preconditions=frozenset({"approved"}),
                subtasks=("ship",),
            ),
        )
    }
    actions = {
        "ship": PrimitiveAction(
            name="ship",
            preconditions=frozenset({"approved"}),
            outcomes=frozenset({Outcome(add=frozenset({"shipped"}))}),
        )
    }
    domain = HDDLDomain(tasks=tasks, methods=methods, actions=actions)

    # World lacks "approved": the only method is inadmissible AND the only
    # primitive alternative is disabled. Product construction must record a
    # dead end, never a silently accepted refinement or action.
    incompatible = ProductState(world=frozenset(), tau=("deploy",))
    assert method_refinements(domain, incompatible) == frozenset()
    assert ready_action_transitions(domain, incompatible) == frozenset()

    def is_goal(state: ProductState) -> bool:
        return not state.tau and "shipped" in state.world

    reachability = build_fond_problem(domain, incompatible, is_goal)
    assert incompatible.key() in reachability.dead_end_keys
    assert reachability.fond_problem.transitions == {}

    # An empty candidate policy over this problem is rejected as missing, and
    # a policy that dishonestly claims an action for it dead-ends too --
    # neither path is silently accepted.
    empty_policy = CandidatePolicy(actions={})
    check = check_candidate_policy(
        reachability.fond_problem, empty_policy, semantics=PolicySemantics.STRONG
    )
    assert not check.valid
    assert incompatible.key() in check.missing_policy_states

    dishonest_policy = CandidatePolicy(actions={incompatible.key(): "ship"})
    dishonest_check = check_candidate_policy(
        reachability.fond_problem, dishonest_policy, semantics=PolicySemantics.STRONG
    )
    assert not dishonest_check.valid
    assert incompatible.key() in dishonest_check.dead_end_states

    # Cross-check against #132's own frontier checker: a witness claiming
    # "ship" is permitted at this world state does not correspond to any real
    # product-derived permission (ready_action_transitions is empty here), so
    # a policy that picks "ship" anyway must be rejected there too.
    world_state_id = "w-unapproved"
    witnesses = {world_state_id: frozenset({HDDLProgressWitness("deploy-frontier", frozenset())})}
    frontier_problem = FONDProblem(
        initial_state=world_state_id,
        goal_states=frozenset({"w-shipped"}),
        transitions={(world_state_id, "ship"): frozenset({"w-shipped"})},
    )
    frontier_policy = CandidatePolicy(actions={world_state_id: "ship"})
    frontier_check = check_fond_hddl_frontier_closure(
        frontier_problem,
        frontier_policy,
        semantics=PolicySemantics.STRONG,
        hierarchy_witnesses=witnesses,
    )
    assert not frontier_check.valid
    assert world_state_id in frontier_check.hierarchy_rejected_action_states


# ---------------------------------------------------------------------------
# (d) strong-cyclic FOND typed correctly against deterministic repair
# ---------------------------------------------------------------------------


def test_strong_cyclic_retry_is_fair_repeatable_not_repair_required() -> None:
    action = PrimitiveAction(
        name="install",
        preconditions=frozenset(),
        outcomes=frozenset(
            {
                Outcome(add=frozenset({"installed"})),
                Outcome(add=frozenset(), delete=frozenset()),
            }
        ),
    )
    assert classify_action_fairness(action) is FairnessClass.FAIR_REPEATABLE

    # A retry loop needs the failed attempt to re-enter the task network,
    # which one primitive-pop transition alone cannot do: model it with a
    # compound task that re-decomposes into itself until "installed" holds,
    # a standard HTN retry idiom (the method's own task name recurring in its
    # subtasks is ordinary data here, not special-cased in the transition
    # code above).
    domain = HDDLDomain(
        tasks={
            "ensure-installed": Task("ensure-installed", primitive=False),
            "install": Task("install", primitive=True),
        },
        methods={
            "ensure-installed": (
                Method("already-installed", "ensure-installed", frozenset({"installed"}), ()),
                Method("retry-install", "ensure-installed", frozenset(), ("install", "ensure-installed")),
            )
        },
        actions={"install": action},
    )
    initial = ProductState(world=frozenset(), tau=("ensure-installed",))

    def is_goal(state: ProductState) -> bool:
        return not state.tau

    reachability = build_fond_problem(domain, initial, is_goal)
    retrying = ProductState(world=frozenset(), tau=("ensure-installed",))
    attempting = ProductState(world=frozenset(), tau=("install", "ensure-installed"))
    installed_pending = ProductState(world=frozenset({"installed"}), tau=("ensure-installed",))
    policy = candidate_policy_over_product(
        {
            retrying.key(): "refine:retry-install",
            attempting.key(): "install",
            installed_pending.key(): "refine:already-installed",
        }
    )
    check = check_candidate_policy(
        reachability.fond_problem, policy, semantics=PolicySemantics.STRONG_CYCLIC
    )
    assert check.valid
    # The failure outcome closes a real cycle back onto the retrying state.
    assert retrying.key() in check.non_goal_cycle_states
    # Not strongly valid: strong FOND forbids the cycle outright, even though
    # every reachable state still has a path to the goal under fairness.
    strong_check = check_candidate_policy(
        reachability.fond_problem, policy, semantics=PolicySemantics.STRONG
    )
    assert not strong_check.valid
    assert retrying.key() in strong_check.non_goal_cycle_states


def test_deterministic_compile_error_is_repair_required_not_fair_repeatable() -> None:
    action = PrimitiveAction(
        name="compile",
        preconditions=frozenset(),
        outcomes=frozenset({Outcome(add=frozenset(), delete=frozenset())}),
    )
    assert classify_action_fairness(action) is FairnessClass.REPAIR_REQUIRED

    domain = HDDLDomain(
        tasks={"compile": Task("compile", primitive=True)},
        methods={},
        actions={"compile": action},
    )
    initial = ProductState(world=frozenset(), tau=("compile",))

    def is_goal(state: ProductState) -> bool:
        return not state.tau and "object-ready" in state.world

    reachability = build_fond_problem(domain, initial, is_goal)
    policy = candidate_policy_over_product({initial.key(): "compile"})

    # A deterministic single-outcome failure is not repairable by fair retry
    # under EITHER FOND semantics -- blind retry policy is invalid, full stop.
    for semantics in (PolicySemantics.STRONG, PolicySemantics.STRONG_CYCLIC):
        check = check_candidate_policy(reachability.fond_problem, policy, semantics=semantics)
        assert not check.valid
        assert initial.key() in check.cannot_reach_goal_states

    # A repair method exists as a *different* task, never a retry of "compile".
    repair_domain = HDDLDomain(
        tasks={
            "build": Task("build", primitive=False),
            "compile": Task("compile", primitive=True),
            "fix-source": Task("fix-source", primitive=True),
        },
        methods={
            "build": (
                Method(
                    name="repair-then-compile",
                    task="build",
                    preconditions=frozenset(),
                    subtasks=("fix-source", "compile"),
                ),
            )
        },
        actions={
            "compile": PrimitiveAction(
                name="compile",
                preconditions=frozenset({"source-fixed"}),
                outcomes=frozenset({Outcome(add=frozenset({"object-ready"}))}),
            ),
            "fix-source": PrimitiveAction(
                name="fix-source",
                preconditions=frozenset(),
                outcomes=frozenset({Outcome(add=frozenset({"source-fixed"}))}),
            ),
        },
    )
    repair_initial = ProductState(world=frozenset(), tau=("build",))

    def repair_is_goal(state: ProductState) -> bool:
        return not state.tau and "object-ready" in state.world

    repair_reach = build_fond_problem(repair_domain, repair_initial, repair_is_goal)
    fixed = ProductState(world=frozenset(), tau=("fix-source", "compile"))
    after_fix = ProductState(world=frozenset({"source-fixed"}), tau=("compile",))
    repair_policy = candidate_policy_over_product(
        {
            repair_initial.key(): "refine:repair-then-compile",
            fixed.key(): "fix-source",
            after_fix.key(): "compile",
        }
    )
    repair_check = check_candidate_policy(
        repair_reach.fond_problem, repair_policy, semantics=PolicySemantics.STRONG
    )
    assert repair_check.valid
