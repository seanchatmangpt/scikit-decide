# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Kubernetes Goat scenario 16 ("RBAC least privileges misconfiguration") as
a deterministic planning domain.

Source walkthrough (vendored in this repo, not reproduced verbatim here):
`vendor/gyms/kubernetes-goat/guide/docs/scenarios/scenario-16/scenario-16.md`,
backed by the actual manifest at
`vendor/gyms/kubernetes-goat/scenarios/insecure-rbac/setup.yaml`. That
manifest binds a pod's ServiceAccount to the built-in `cluster-admin`
ClusterRole -- an overly permissive RBAC grant. The documented walkthrough
is a strict five-step sequence: locate the mounted ServiceAccount
credentials, resolve the in-cluster API server env vars, authenticate to
the API server, enumerate namespace secrets, then read and base64-decode the
`k8svaultapikey` secret to recover the scenario's flag.

States model the attacker's cumulative knowledge/access (a monotonically
growing frozenset of facts learned), never a live cluster -- this is a
model of the documented attack path, staying strictly on the search-graph
side per `CLAUDE.md`'s "computes candidate plans, does not actuate" law.
Nothing here talks to a real Kubernetes API server, mounts a real
ServiceAccount token, or performs any actuation; `_get_transition_value`
costs are illustrative effort weights, not measured timings.

Left unregistered as an `autofde_lab.domains` entry point, matching the
`CareerAdmission` precedent (`hub/domain/career_admission/`): a
scenario-fixture domain constructed and imported directly by its own test,
not (yet) intended to be reachable through the fabric/OpenClaw catalog.
"""

from __future__ import annotations

from typing import Any, FrozenSet, NamedTuple

from autofde_lab import DeterministicPlanningDomain, ImplicitSpace, Space, Value
from autofde_lab.builders.domain import Renderable
from autofde_lab.hub.space.gym import ListSpace


class AttackStep(NamedTuple):
    """A single documented step from the scenario-16 walkthrough."""

    id: str
    cost: float
    prerequisite_ids: tuple[str, ...] = ()


#: The exact five-step sequence documented in scenario-16.md's "Method 1"
#: walkthrough, each step gated on the previous one having already been
#: performed -- this is the "chicken-and-egg" prerequisite structure that
#: makes the challenge a genuine planning problem rather than a single
#: action.
DEFAULT_STEPS: tuple[AttackStep, ...] = (
    AttackStep(
        id="read_serviceaccount_files",
        cost=1.0,
        prerequisite_ids=(),
    ),
    AttackStep(
        id="resolve_apiserver_env",
        cost=1.0,
        prerequisite_ids=("read_serviceaccount_files",),
    ),
    AttackStep(
        id="authenticate_to_apiserver",
        cost=1.0,
        prerequisite_ids=(
            "read_serviceaccount_files",
            "resolve_apiserver_env",
        ),
    ),
    AttackStep(
        id="list_namespace_secrets",
        cost=1.0,
        prerequisite_ids=("authenticate_to_apiserver",),
    ),
    AttackStep(
        id="read_and_decode_k8svaultapikey",
        cost=1.0,
        prerequisite_ids=("list_namespace_secrets",),
    ),
    # A reachable but pointless alternative: listing pods is a real,
    # documented step in the walkthrough ("query the pods in the specific
    # namespace") but is never a prerequisite for the flag -- included so a
    # cost-optimal solver must never route through it on the way to the
    # goal.
    AttackStep(
        id="list_namespace_pods",
        cost=1.0,
        prerequisite_ids=("authenticate_to_apiserver",),
    ),
)

#: The scenario's documented goal: possession of the decoded
#: `k8svaultapikey` secret value (the flag).
GOAL_STEP_ID = "read_and_decode_k8svaultapikey"


class State(NamedTuple):
    known: FrozenSet[str]


class D(DeterministicPlanningDomain, Renderable):
    T_state = State
    T_observation = T_state
    T_event = str  # attack-step id being performed
    T_value = float
    T_predicate = bool
    T_info = None


class K8sGoatRBACEscalation(D):
    """Deterministic planning domain over Kubernetes Goat scenario 16.

    A state is the (frozen) set of attack-step ids the attacker has
    performed so far, starting from a freshly-scheduled pod with no
    knowledge of its own ServiceAccount credentials. An action performs one
    not-yet-performed step whose documented prerequisites are all already
    satisfied. The goal is any state that has performed
    `read_and_decode_k8svaultapikey` -- the step that recovers the flag.
    """

    def __init__(
        self,
        steps: tuple[AttackStep, ...] = DEFAULT_STEPS,
        goal_step_id: str = GOAL_STEP_ID,
    ):
        self._steps = {step.id: step for step in steps}
        self._goal_step_id = goal_step_id

    def _get_next_state(
        self,
        memory: D.T_memory[D.T_state],
        action: D.T_agent[D.T_concurrency[D.T_event]],
    ) -> D.T_state:
        return State(known=memory.known | {action})

    def _get_transition_value(
        self,
        memory: D.T_memory[D.T_state],
        action: D.T_agent[D.T_concurrency[D.T_event]],
        next_state: D.T_state | None = None,
    ) -> D.T_agent[Value[D.T_value]]:
        step = self._steps.get(action)
        return Value(cost=step.cost if step is not None else float("inf"))

    def _is_terminal(self, state: D.T_state) -> D.T_agent[D.T_predicate]:
        return self._is_goal(state)

    def _get_applicable_actions_from(
        self, memory: D.T_memory[D.T_state]
    ) -> D.T_agent[Space[D.T_event]]:
        known = memory.known
        applicable = [
            step.id
            for step in self._steps.values()
            if step.id not in known
            and set(step.prerequisite_ids).issubset(known)
        ]
        return ListSpace(applicable)

    def _get_action_space_(self) -> D.T_agent[Space[D.T_event]]:
        return ListSpace(list(self._steps.keys()))

    def _get_goals_(self) -> D.T_agent[Space[D.T_observation]]:
        goal_step_id = self._goal_step_id

        def is_goal_state(state: State) -> bool:
            return goal_step_id in state.known

        return ImplicitSpace(is_goal_state)

    def _get_initial_state_(self) -> D.T_state:
        return State(known=frozenset())

    def _get_observation_space_(self) -> D.T_agent[Space[D.T_observation]]:
        return ImplicitSpace(lambda state: isinstance(state, State))

    def _render_from(self, memory: D.T_memory[D.T_state], **kwargs: Any) -> Any:
        return sorted(memory.known)
