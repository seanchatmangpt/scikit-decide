# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Optional

from unified_planning.engines.results import POSITIVE_OUTCOMES, PlanGenerationResult
from unified_planning.plans import HierarchicalPlan, SequentialPlan
from unified_planning.shortcuts import OneshotPlanner

from autofde_lab import Domain, Solver
from autofde_lab.hub.domain.hddl import HDDLDomain
from autofde_lab.hub.domain.up import SkUPAction


class HDDLSolver(Solver):
    """Solve an HDDL task network through a real Unified Planning HTN engine.

    The returned :class:`HierarchicalPlan` is authoritative. ``get_plan()``
    exposes only its sequential primitive-action projection for downstream
    execution/verification. This solver deliberately does not implement
    ``DeterministicPolicies`` because task-network progress is not, in
    general, recoverable from world state alone.
    """

    T_domain = HDDLDomain

    def __init__(
        self,
        domain_factory: Callable[[], Domain],
        engine_name: str = "aries",
        engine_params: Optional[dict[str, Any]] = None,
        **planner_params: Any,
    ) -> None:
        super().__init__(domain_factory=domain_factory)
        self._engine_name = engine_name
        self._engine_params = {} if engine_params is None else dict(engine_params)
        self._planner_params = dict(planner_params)
        self._result: Optional[PlanGenerationResult] = None
        self._hierarchical_plan: Optional[HierarchicalPlan] = None
        self._plan: list[SkUPAction] = []

    @classmethod
    def _check_domain_additional(cls, domain: Domain) -> bool:
        return isinstance(domain, HDDLDomain)

    def _solve(self) -> None:
        self._domain = self._domain_factory()
        if not isinstance(self._domain, HDDLDomain):
            raise TypeError("HDDLSolver requires HDDLDomain.")

        problem = self._domain.hierarchical_problem
        with OneshotPlanner(
            name=self._engine_name,
            **self._planner_params,
        ) as planner:
            result = planner.solve(problem, **self._engine_params)

        self._result = result
        if result.status not in POSITIVE_OUTCOMES or result.plan is None:
            raise RuntimeError(
                f"{self._engine_name} did not produce an admitted HDDL plan: "
                f"status={result.status}"
            )
        if not isinstance(result.plan, HierarchicalPlan):
            raise RuntimeError(
                f"{self._engine_name} returned {type(result.plan).__name__}, "
                "not HierarchicalPlan; refusing to erase hierarchy."
            )

        self._hierarchical_plan = result.plan
        flat_plan = result.plan.action_plan
        if not isinstance(flat_plan, SequentialPlan):
            raise RuntimeError(
                "HDDLSolver currently exposes only sequential primitive-action "
                "projections; the hierarchical result is retained but temporal "
                "execution projection is UNSUPPORTED."
            )
        self._plan = [SkUPAction(action) for action in flat_plan.actions]

    def get_hierarchical_plan(self) -> HierarchicalPlan:
        """Return the solved hierarchy, including method decomposition."""
        if self._hierarchical_plan is None:
            raise RuntimeError("solve() must succeed before reading the plan.")
        return self._hierarchical_plan

    def get_plan(self) -> list[SkUPAction]:
        """Return the sequential primitive-action projection of the hierarchy."""
        if self._hierarchical_plan is None:
            raise RuntimeError("solve() must succeed before reading the plan.")
        return list(self._plan)

    def get_plan_result(self) -> PlanGenerationResult:
        """Return the real Unified Planning generation result."""
        if self._result is None:
            raise RuntimeError("solve() must run before reading the result.")
        return self._result
