# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from __future__ import annotations

import logging
from typing import Optional, cast

from autofde_lab import DeterministicPolicySolver, Domain, EnumerableSpace, Memory
from autofde_lab.builders.domain import (
    EnumerableTransitions,
    FullyObservable,
    SingleAgent,
)
from autofde_lab.core import autocast

logger = logging.getLogger(__name__)


class D(Domain, SingleAgent, EnumerableTransitions, FullyObservable):
    pass


class SimpleGreedy(DeterministicPolicySolver):
    T_domain = D

    @classmethod
    def _check_domain_additional(cls, domain: Domain) -> bool:
        # Signature must accept `Domain`, matching `Solver._check_domain_additional`;
        # `check_domain()` has already established the `T_domain` isinstance test
        # before calling this hook.
        return isinstance(domain.get_action_space(), EnumerableSpace)

    def _solve(self) -> None:
        self._domain = (
            self._domain_factory()
        )  # no further solving code required here since everything is computed online

    def _get_next_action(
        self, observation: D.T_observation, domain: Optional[Domain] = None
    ) -> D.T_concurrency[D.T_event]:
        # `T_domain` is `SingleAgent`, for which `T_agent` is the identity
        # `typing.Union` marker; `D.T_agent[X]` is therefore `Union[X]`, which is
        # not a valid type expression. The single-agent shape is spelled directly.
        # `domain` is typed `Domain` to match `DeterministicPolicies._get_next_action`
        # and narrowed to `D` below.
        already_autocast = False
        if domain is None:
            domain = self._domain
            # `self._domain` came from `self._domain_factory()`, and
            # `Solver.__init__` wraps that factory in `cast_domain_factory`,
            # which already ran `autocast_all(domain, domain, self.T_domain)`
            # on the instance. Wrapping its methods a *second* time below
            # applies the same cast twice. For most domains the second cast is
            # a silent no-op; for a domain whose `T_state` is itself a
            # sequence (e.g. a `NamedTuple` state), the `(Memory, Union)` cast
            # rule `obj[0]` fires again and hands `_get_applicable_actions_from`
            # the state's *first field* instead of the state. Observed as
            # `AttributeError: 'frozenset' object has no attribute 'facts'`
            # against `GymProcedureDomain`, whose `State` is a NamedTuple.
            already_autocast = True
            logger.warning(
                "Rollout domain not given. Using domain seen during solve instead."
            )
        d = cast(D, domain)
        # This solver selects the first action with the highest expected immediate reward (greedy)
        memory = Memory(
            [observation]
        )  # note: observation == state (because FullyObservable)

        def _cast(f):
            return f if already_autocast else autocast(f, d, self.T_domain)

        get_applicable_actions = _cast(d.get_applicable_actions)
        get_next_state_distribution = _cast(d.get_next_state_distribution)
        get_transition_value = _cast(d.get_transition_value)
        applicable_actions = get_applicable_actions(memory)
        if d.is_transition_value_dependent_on_next_state():
            values = []
            for a in applicable_actions.get_elements():
                next_state_prob = get_next_state_distribution(memory, [a]).get_values()
                expected_value = sum(
                    p * get_transition_value(memory, [a], s).reward
                    for s, p in next_state_prob
                )
                values.append(expected_value)
        else:
            values = [
                get_transition_value(memory, a).reward for a in applicable_actions
            ]
        argmax = max(range(len(values)), key=lambda i: values[i])
        return [
            applicable_actions.get_elements()[argmax]
        ]  # list of action here because we handle Parallel domains

    def _is_policy_defined_for(self, observation: D.T_observation) -> bool:
        # The greedy policy is defined wherever the domain reports at least one
        # applicable action; that is every non-terminal state, and terminal
        # states are never queried by a rollout. Parameter is unused by design
        # and its name is fixed by `DeterministicPolicies._is_policy_defined_for`.
        del observation
        return True
