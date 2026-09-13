from __future__ import annotations

from dataclasses import dataclass

import pytest

from autofde_lab.fabric.dspy import compile_request_text
from autofde_lab.fabric.models import (
    DecisionCatalog,
    DecisionRefusal,
    DecisionRequest,
    RefusalCode,
)


@dataclass
class FakeCompiler:
    calls: int = 0

    def compile(self, job: str, catalog: DecisionCatalog) -> DecisionRequest:
        self.calls += 1
        assert job == "reach the goal"
        assert "Counter" in catalog.domains
        return DecisionRequest(domain="Counter")


def test_json_request_bypasses_dspy() -> None:
    compiler = FakeCompiler()
    request = compile_request_text(
        '{"domain":"Counter","max_steps":4}',
        DecisionCatalog(domains=("Counter",), solvers=("CounterSolver",)),
        compiler,
    )

    assert request.domain == "Counter"
    assert request.max_steps == 4
    assert compiler.calls == 0


def test_natural_language_uses_compiler_only_at_frontier() -> None:
    compiler = FakeCompiler()
    request = compile_request_text(
        "reach the goal",
        DecisionCatalog(domains=("Counter",), solvers=("CounterSolver",)),
        compiler,
    )

    assert request.domain == "Counter"
    assert compiler.calls == 1


def test_natural_language_without_compiler_fails_closed() -> None:
    with pytest.raises(DecisionRefusal) as captured:
        compile_request_text(
            "reach the goal",
            DecisionCatalog(domains=("Counter",), solvers=("CounterSolver",)),
        )

    assert captured.value.code is RefusalCode.NATURAL_LANGUAGE_COMPILER_UNAVAILABLE
