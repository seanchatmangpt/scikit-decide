# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Backend abstraction over the existing scikit-decide registry."""

from __future__ import annotations

from typing import Any, Protocol

from autofde_lab.fabric.models import DecisionRefusal, RefusalCode


class DecisionBackend(Protocol):
    """Minimal registry contract consumed by the agentic fabric."""

    def list_domains(self) -> list[str]: ...

    def list_solvers(self) -> list[str]: ...

    def load_domain(self, name: str) -> type[Any]: ...

    def load_solver(self, name: str) -> type[Any]: ...

    def match_solvers(self, domain: Any) -> list[type[Any]]: ...


class ScikitDecideBackend:
    """Adapter that preserves scikit-decide as the solver authority."""

    @staticmethod
    def _utils() -> Any:
        try:
            from autofde_lab import utils
        except ImportError as error:
            raise DecisionRefusal(
                RefusalCode.DEPENDENCY_UNAVAILABLE,
                "scikit-decide registry utilities are unavailable",
            ) from error
        return utils

    def list_domains(self) -> list[str]:
        return sorted(str(name) for name in self._utils().get_registered_domains())

    def list_solvers(self) -> list[str]:
        return sorted(str(name) for name in self._utils().get_registered_solvers())

    def load_domain(self, name: str) -> type[Any]:
        domain_type = self._utils().load_registered_domain(name)
        if domain_type is None:
            raise DecisionRefusal(
                RefusalCode.DOMAIN_UNKNOWN,
                f"registered domain not found or could not be loaded: {name}",
                details={"domain": name},
            )
        return domain_type

    def load_solver(self, name: str) -> type[Any]:
        solver_type = self._utils().load_registered_solver(name)
        if solver_type is None:
            raise DecisionRefusal(
                RefusalCode.SOLVER_UNKNOWN,
                f"registered solver not found or could not be loaded: {name}",
                details={"solver": name},
            )
        return solver_type

    def match_solvers(self, domain: Any) -> list[type[Any]]:
        return list(self._utils().match_solvers(domain))
