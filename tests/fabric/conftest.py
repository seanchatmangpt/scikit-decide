from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from autofde_lab.fabric.cache import SQLiteERRCCache
from autofde_lab.fabric.models import DecisionRefusal, RefusalCode
from autofde_lab.fabric.service import DecisionFabric


@dataclass
class Outcome:
    observation: int
    value: float
    termination: bool
    info: dict[str, Any]


class CounterDomain:
    def __init__(self, *, limit: int = 2) -> None:
        self.limit = limit
        self.state = 0

    def reset(self) -> int:
        self.state = 0
        return self.state

    def step(self, action: str) -> Outcome:
        assert action == "advance"
        self.state += 1
        return Outcome(
            observation=self.state,
            value=1.0,
            termination=self.state >= self.limit,
            info={"state": self.state},
        )


class CounterSolver:
    def __init__(self, *, domain_factory: Any, **_: Any) -> None:
        self.domain_factory = domain_factory
        self.solved = False

    def __enter__(self) -> CounterSolver:
        return self

    def __exit__(self, *_: Any) -> None:
        return None

    def solve(self) -> None:
        assert isinstance(self.domain_factory(), CounterDomain)
        self.solved = True

    def sample_action(self, observation: int) -> str:
        assert self.solved
        assert observation >= 0
        return "advance"


class FakeBackend:
    def list_domains(self) -> list[str]:
        return ["Counter"]

    def list_solvers(self) -> list[str]:
        return ["CounterSolver"]

    def load_domain(self, name: str) -> type[Any]:
        if name != "Counter":
            raise DecisionRefusal(
                RefusalCode.DOMAIN_UNKNOWN,
                f"unknown domain {name}",
                details={"domain": name},
            )
        return CounterDomain

    def load_solver(self, name: str) -> type[Any]:
        if name != "CounterSolver":
            raise DecisionRefusal(
                RefusalCode.SOLVER_UNKNOWN,
                f"unknown solver {name}",
                details={"solver": name},
            )
        return CounterSolver

    def match_solvers(self, domain: Any) -> list[type[Any]]:
        return [CounterSolver] if isinstance(domain, CounterDomain) else []


@pytest.fixture
def fabric() -> DecisionFabric:
    cache = SQLiteERRCCache(":memory:")
    service = DecisionFabric(backend=FakeBackend(), cache=cache)
    yield service
    cache.close()
