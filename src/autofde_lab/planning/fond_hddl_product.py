"""Gate 1 of the FOND x HDDL product: an explicit combined state X = (W, tau).

`fond_hddl.py` (PR #132) is a *frontier* check between an already-computed FOND
policy and an opaque, externally-supplied HDDL progress witness string. Its own
docstring says what it is not: "This is deliberately a frontier check, not a
synchronized FOND×HDDL product proof. It does not establish witness provenance,
hierarchy-progress transitions, plan admission, authorization, or actuation."

This module is that missing product construction, scoped to Gate 1:

- `W` is a set of world facts (ground atoms), not an opaque string.
- `tau` is a real remaining HDDL task network: an ordered tuple of task names,
  built from real `Task`/`Method`/`PrimitiveAction` objects, not a witness label.
- `X = (W, tau)` is the explicit combined state (`ProductState`).
- HDDL method refinement is a real transition `X --m--> X'` that changes `tau`
  only (no world effect, no actuation): `method_refinements`.
- A ready primitive action is a real FOND transition `X --(a,o)--> X'` for each
  outcome `o` of `a`, changing `W` and popping `tau`'s head: `ready_action_transitions`.
- `build_fond_problem` folds the full product reachability graph into the exact
  `FONDProblem` type `fond_policy.py` already checks, so `check_candidate_policy`
  runs on product states unmodified -- no parallel checker, no new semantics for
  policy validity.

This remains planning-side and candidate-only. No SELECT/CONSTRUCT/DO authority;
BRCE and every actuation boundary in this repo are untouched. One level of HDDL
hierarchy is modeled (a compound task's methods decompose it directly into a
primitive-task sequence); recursive compound-in-compound decomposition is out of
scope for Gate 1 and is not claimed.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Mapping

from .fond_policy import ActionId, CandidatePolicy, FONDProblem, StateId

Fact = str
TaskName = str

REFINE_PREFIX = "refine:"


@dataclass(frozen=True)
class Task:
    """A named HDDL task; primitive tasks map 1:1 to a `PrimitiveAction`."""

    name: TaskName
    primitive: bool


@dataclass(frozen=True)
class Method:
    """One decomposition method for a compound task, gated on world facts."""

    name: str
    task: TaskName
    preconditions: frozenset[Fact]
    subtasks: tuple[TaskName, ...]


@dataclass(frozen=True)
class Outcome:
    """One nondeterministic effect of a primitive action: add/delete facts."""

    add: frozenset[Fact] = frozenset()
    delete: frozenset[Fact] = frozenset()


@dataclass(frozen=True)
class PrimitiveAction:
    name: TaskName
    preconditions: frozenset[Fact]
    outcomes: frozenset[Outcome]


@dataclass(frozen=True)
class HDDLDomain:
    """A minimal, real HDDL domain: tasks, their methods, and FOND actions."""

    tasks: Mapping[TaskName, Task]
    methods: Mapping[TaskName, tuple[Method, ...]]
    actions: Mapping[TaskName, PrimitiveAction]


TaskNetwork = tuple[TaskName, ...]


@dataclass(frozen=True)
class ProductState:
    """X = (W, tau): world facts plus the remaining HDDL task network."""

    world: frozenset[Fact]
    tau: TaskNetwork

    def key(self) -> StateId:
        return "W={" + ",".join(sorted(self.world)) + "}|tau=(" + ",".join(self.tau) + ")"


@dataclass(frozen=True)
class MethodRefinement:
    """X --m--> X'. HDDL decomposition only; no world change, no actuation."""

    method: str
    successor: ProductState


@dataclass(frozen=True)
class ActionTransition:
    """A ready primitive FOND transition X --(a,o)--> X'."""

    action: TaskName
    outcome: Outcome
    successor: ProductState


def method_refinements(domain: HDDLDomain, state: ProductState) -> frozenset[MethodRefinement]:
    """All X --m--> X' for methods of tau's head compound task admitted by W."""

    if not state.tau:
        return frozenset()
    head, rest = state.tau[0], state.tau[1:]
    task = domain.tasks.get(head)
    if task is None or task.primitive:
        return frozenset()
    return frozenset(
        MethodRefinement(method.name, ProductState(state.world, method.subtasks + rest))
        for method in domain.methods.get(head, ())
        if method.preconditions <= state.world
    )


def ready_action_transitions(domain: HDDLDomain, state: ProductState) -> frozenset[ActionTransition]:
    """All X --(a,o)--> X' when tau's head is a primitive task enabled in W."""

    if not state.tau:
        return frozenset()
    head, rest = state.tau[0], state.tau[1:]
    task = domain.tasks.get(head)
    if task is None or not task.primitive:
        return frozenset()
    action = domain.actions.get(head)
    if action is None or not (action.preconditions <= state.world):
        return frozenset()
    return frozenset(
        ActionTransition(
            head,
            outcome,
            ProductState((state.world - outcome.delete) | outcome.add, rest),
        )
        for outcome in action.outcomes
    )


def is_ready_frontier(domain: HDDLDomain, state: ProductState) -> bool:
    """True iff tau's head is a primitive task with at least one live outcome."""

    return bool(ready_action_transitions(domain, state))


@dataclass(frozen=True)
class ProductReachability:
    """The full BFS-explored product graph, folded into a checkable `FONDProblem`."""

    fond_problem: FONDProblem
    states_by_key: Mapping[StateId, ProductState]
    dead_end_keys: frozenset[StateId]


def build_fond_problem(
    domain: HDDLDomain,
    initial: ProductState,
    is_goal: Callable[[ProductState], bool],
) -> ProductReachability:
    """Explore the reachable product graph and fold it into a `FONDProblem`.

    Two transition kinds share one `FONDProblem`:

    - method refinement, `ActionId = "refine:<method-name>"`, deterministic
      (one outcome per method choice -- decomposition is not actuation);
    - a ready primitive action, `ActionId = <action-name>`, whose FOND
      transitions collect *every* outcome of that action into one outcome set,
      exactly the nondeterminism `fond_policy.FONDProblem` already models.

    A product state with no HDDL method applicable and no enabled primitive
    action (an incompatible world/frontier pairing) is recorded with zero
    outgoing transitions -- a dead end, not a silently accepted plan step.
    """

    states: dict[StateId, ProductState] = {}
    transitions: dict[tuple[StateId, ActionId], frozenset[StateId]] = {}
    goal_keys: set[StateId] = set()
    dead_ends: set[StateId] = set()

    queue: deque[ProductState] = deque([initial])
    seen: set[StateId] = set()
    while queue:
        state = queue.popleft()
        key = state.key()
        if key in seen:
            continue
        seen.add(key)
        states[key] = state

        if is_goal(state):
            goal_keys.add(key)
            continue

        refinements = method_refinements(domain, state)
        for refinement in refinements:
            action_id = REFINE_PREFIX + refinement.method
            successor_key = refinement.successor.key()
            transitions[(key, action_id)] = frozenset({successor_key})
            if successor_key not in seen:
                queue.append(refinement.successor)

        action_transitions = ready_action_transitions(domain, state)
        if action_transitions:
            by_action: dict[TaskName, set[StateId]] = {}
            for at in action_transitions:
                by_action.setdefault(at.action, set()).add(at.successor.key())
                if at.successor.key() not in seen:
                    queue.append(at.successor)
            for action_name, successor_keys in by_action.items():
                transitions[(key, action_name)] = frozenset(successor_keys)

        if not refinements and not action_transitions:
            dead_ends.add(key)

    problem = FONDProblem(
        initial_state=initial.key(),
        goal_states=frozenset(goal_keys),
        transitions=transitions,
    )
    return ProductReachability(
        fond_problem=problem,
        states_by_key=states,
        dead_end_keys=frozenset(dead_ends),
    )


class FairnessClass(str, Enum):
    """A single deterministic bad outcome cannot be repaired by fair retry."""

    FAIR_REPEATABLE = "fair_repeatable"
    REPAIR_REQUIRED = "repair_required"


def classify_action_fairness(action: PrimitiveAction) -> FairnessClass:
    """Type a primitive action's failure mode from its outcome structure.

    An action with exactly one outcome is deterministic: if that outcome does
    not progress the plan, no amount of fair retry ever succeeds -- the only
    lawful next step is a distinct repair method, so it is typed
    `REPAIR_REQUIRED`. An action with two or more outcomes is genuinely
    nondeterministic; under a strong-cyclic FOND fairness assumption, retrying
    it is guaranteed to eventually hit a progressing outcome, so it is typed
    `FAIR_REPEATABLE`. No `REPAIR_REQUIRED`/`FAIR_REPEATABLE` vocabulary
    pre-existed in this repo (grepped for it before adding this) -- these are
    Gate 1's own typed names for the standard FOND fairness distinction.
    """

    if len(action.outcomes) <= 1:
        return FairnessClass.REPAIR_REQUIRED
    return FairnessClass.FAIR_REPEATABLE


def flat_fond_problem_from_product(
    domain: HDDLDomain,
    initial: ProductState,
    is_goal: Callable[[ProductState], bool],
) -> FONDProblem:
    """Build the product `FONDProblem` for a single, unstructured flat task.

    When `initial.tau` is one primitive task with no compound wrapper (no
    hierarchy at all), `build_fond_problem` never emits a `refine:` action --
    every `ActionId` in the resulting problem is a bare primitive action name,
    identical in shape to a `FONDProblem` built directly against
    `fond_policy.py` for the same world-fact action set. This is the
    flat-FOND reduction claim, made checkable rather than asserted.
    """

    reachability = build_fond_problem(domain, initial, is_goal)
    return reachability.fond_problem


def candidate_policy_over_product(actions: Mapping[StateId, ActionId]) -> CandidatePolicy:
    """Thin constructor so callers never hand-build `fond_policy` types."""

    return CandidatePolicy(actions=dict(actions))
