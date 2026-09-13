# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Career-capability-admission planning domain.

Models the "missing prerequisite" chicken-and-egg concept named in this
repo's standing law (`.claude/rules/standing-law.md`) and the ~/mfw "Recursive
Process Manufacture" section: some capability facts are inapplicable/blocked
until their prerequisite facts have been admitted. This domain represents
that admission-ordering problem as an ordinary deterministic planning
problem, staying strictly on the search-graph side (candidate plan
construction only) -- it does not implement or claim any receipt, broker,
admission, or actuation semantics.

The fixture facts below are drawn from the user's own career history
(Intuit AutoML/ML-governance work, and the forward-deployed agentic
manufacturing work) rather than placeholders, so the case study models a
real capability-prerequisite structure rather than a toy example.
"""

from __future__ import annotations

from typing import Any, FrozenSet, NamedTuple

from autofde_lab import DeterministicPlanningDomain, ImplicitSpace, Space, Value
from autofde_lab.builders.domain import Renderable
from autofde_lab.hub.space.gym import ListSpace


class CapabilityFact(NamedTuple):
    """A single admittable career-capability fact."""

    id: str
    category: str
    cost: float
    prerequisite_ids: tuple[str, ...] = ()


#: Real facts drawn from the user's actual career content (see the resume
#: content pasted into this session), each with an explicit prerequisite
#: structure so the domain has genuine "blocked until admitted" edges to
#: solve -- this is the concrete instantiation of the chicken-and-egg
#: concept, not decoration.
DEFAULT_FACTS: tuple[CapabilityFact, ...] = (
    CapabilityFact(
        id="intuit_automl",
        category="ml_infra",
        cost=1.0,
        prerequisite_ids=(),
    ),
    CapabilityFact(
        id="intuit_ml_governance",
        category="governance",
        cost=1.0,
        prerequisite_ids=("intuit_automl",),
    ),
    CapabilityFact(
        id="agentic_orchestration",
        category="manufacturing",
        cost=1.0,
        prerequisite_ids=(),
    ),
    CapabilityFact(
        id="independent_evidence_controls",
        category="governance",
        cost=1.0,
        prerequisite_ids=("agentic_orchestration",),
    ),
    CapabilityFact(
        id="forward_deployment_loop",
        category="manufacturing",
        cost=2.0,
        prerequisite_ids=("intuit_automl", "agentic_orchestration"),
    ),
    # A reachable but strictly worse alternative to `intuit_ml_governance`
    # for the "governance" category: same category, higher cost, so an
    # optimal (Astar) plan must never choose it over the cheaper option.
    CapabilityFact(
        id="redundant_expensive_governance",
        category="governance",
        cost=5.0,
        prerequisite_ids=("intuit_automl",),
    ),
)

#: Capability categories that must all be represented in the admitted set
#: for a plan to be considered a goal (a stand-in for the Challenger
#: thesis's "manufacturing capability, not platform trivia" categories).
DEFAULT_REQUIRED_CATEGORIES: FrozenSet[str] = frozenset(
    {"ml_infra", "governance", "manufacturing"}
)


class State(NamedTuple):
    admitted: FrozenSet[str]


class D(DeterministicPlanningDomain, Renderable):
    T_state = State
    T_observation = T_state
    T_event = str  # fact id being admitted
    T_value = float
    T_predicate = bool
    T_info = None


class CareerAdmission(D):
    """Deterministic planning domain over career-capability admission.

    A state is the (frozen) set of capability-fact ids admitted so far. An
    action admits one not-yet-admitted fact whose prerequisites are all
    already admitted. The goal is an admitted set that covers every
    required capability category. Astar (or any cost-optimal solver) finds
    the minimal-cost admission order -- correctly avoiding a
    reachable-but-suboptimal fact when a cheaper equivalent exists.
    """

    def __init__(
        self,
        facts: tuple[CapabilityFact, ...] = DEFAULT_FACTS,
        required_categories: FrozenSet[str] = DEFAULT_REQUIRED_CATEGORIES,
    ):
        self._facts = {fact.id: fact for fact in facts}
        self._required_categories = required_categories

    def _get_next_state(
        self,
        memory: D.T_memory[D.T_state],
        action: D.T_agent[D.T_concurrency[D.T_event]],
    ) -> D.T_state:
        return State(admitted=memory.admitted | {action})

    def _get_transition_value(
        self,
        memory: D.T_memory[D.T_state],
        action: D.T_agent[D.T_concurrency[D.T_event]],
        next_state: D.T_state | None = None,
    ) -> D.T_agent[Value[D.T_value]]:
        # `.get` rather than `[]`: an action naming an id absent from the
        # fact set (e.g. a dangling prerequisite id) must leave the domain
        # merely *blocked*, never raise. Such an action is never applicable,
        # so this branch only guards against an out-of-band caller.
        fact = self._facts.get(action)
        return Value(cost=fact.cost if fact is not None else float("inf"))

    def _is_terminal(self, state: D.T_state) -> D.T_agent[D.T_predicate]:
        return self._is_goal(state)

    def _get_applicable_actions_from(
        self, memory: D.T_memory[D.T_state]
    ) -> D.T_agent[Space[D.T_event]]:
        admitted = memory.admitted
        applicable = [
            fact.id
            for fact in self._facts.values()
            if fact.id not in admitted
            and set(fact.prerequisite_ids).issubset(admitted)
        ]
        return ListSpace(applicable)

    def _get_action_space_(self) -> D.T_agent[Space[D.T_event]]:
        return ListSpace(list(self._facts.keys()))

    def _get_goals_(self) -> D.T_agent[Space[D.T_observation]]:
        def is_goal_state(state: State) -> bool:
            # Unknown ids contribute no category (see `.get` note above)
            # rather than raising, so a dangling prerequisite yields a
            # blocked domain instead of a crash.
            admitted_categories = {
                self._facts[fact_id].category
                for fact_id in state.admitted
                if fact_id in self._facts
            }
            return self._required_categories.issubset(admitted_categories)

        return ImplicitSpace(is_goal_state)

    def _get_initial_state_(self) -> D.T_state:
        return State(admitted=frozenset())

    def _get_observation_space_(self) -> D.T_agent[Space[D.T_observation]]:
        # Finite but not enumerated as a product space here; a ListSpace of
        # all reachable admitted-sets is unnecessary for the solvers used
        # in this case study (Astar only needs action/goal/transition APIs).
        return ImplicitSpace(lambda state: isinstance(state, State))

    def _render_from(self, memory: D.T_memory[D.T_state], **kwargs: Any) -> Any:
        return sorted(memory.admitted)
