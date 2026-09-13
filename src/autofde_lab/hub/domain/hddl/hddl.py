# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from __future__ import annotations

from os import PathLike
from typing import Union

from unified_planning.io import PDDLReader
from unified_planning.model.htn import HierarchicalProblem

from autofde_lab.hub.domain.up import UPDomain

Pathish = Union[str, PathLike[str]]


class HDDLDomain(UPDomain):
    """Bridge a real Unified Planning hierarchical problem into AutoFDE Lab.

    The hierarchical task network remains part of ``HierarchicalProblem``.
    This domain reuses :class:`UPDomain` only for the primitive world-state
    transition semantics needed to inspect/execute a solved action projection;
    it does not flatten the HTN into classical PDDL and it does not encode
    task-network progress into the world state.
    """

    def __init__(self, problem: HierarchicalProblem, **kwargs) -> None:
        if not isinstance(problem, HierarchicalProblem):
            raise TypeError(
                "HDDLDomain requires a unified_planning.model.htn.HierarchicalProblem; "
                "flat Problem instances are not admitted."
            )
        # UPDomain's simulator defaults to `error_on_failed_checks=True`, which
        # UP's own sequential-simulator engine always raises for any problem
        # carrying `ProblemKind.HIERARCHICAL` -- its compatibility table simply
        # never enumerates hierarchical features (real, confirmed via
        # `UPUsageError: We cannot establish whether sequential_simulator is
        # able to handle this problem!`). Relaxed here, not silently defaulted
        # upstream in `UPDomain` -- see that parameter's docstring for the
        # real verification that primitive execution over the hierarchical
        # problem's underlying fluents/actions is genuinely unaffected.
        kwargs.setdefault("simulator_error_on_failed_checks", False)
        super().__init__(problem, **kwargs)

    @classmethod
    def from_files(
        cls,
        domain_filename: Pathish,
        problem_filename: Pathish,
        **kwargs,
    ) -> "HDDLDomain":
        """Parse HDDL domain/problem files with Unified Planning's real reader."""
        problem = PDDLReader().parse_problem(
            str(domain_filename),
            str(problem_filename),
        )
        if not isinstance(problem, HierarchicalProblem):
            raise ValueError(
                "The supplied files did not parse as an HDDL hierarchical problem."
            )
        return cls(problem, **kwargs)

    @classmethod
    def from_strings(
        cls,
        domain: str,
        problem: str,
        **kwargs,
    ) -> "HDDLDomain":
        """Parse HDDL source strings without translating them to flat PDDL."""
        parsed = PDDLReader().parse_problem_string(domain, problem)
        if not isinstance(parsed, HierarchicalProblem):
            raise ValueError(
                "The supplied sources did not parse as an HDDL hierarchical problem."
            )
        return cls(parsed, **kwargs)

    @property
    def hierarchical_problem(self) -> HierarchicalProblem:
        """Return the authoritative hierarchical planning problem."""
        return self._problem
