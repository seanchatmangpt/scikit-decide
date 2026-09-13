# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""DSPy compiler for natural-language jobs into typed decision requests."""

from __future__ import annotations

import json
from typing import Any, Protocol

from autofde_lab.fabric.models import (
    DecisionCatalog,
    DecisionRefusal,
    DecisionRequest,
    RefusalCode,
)


class DecisionCompiler(Protocol):
    """Compiler boundary used by A2A and optional MCP projections."""

    def compile(self, job: str, catalog: DecisionCatalog) -> DecisionRequest: ...


class DSPyDecisionCompiler:
    """Compile a user job into a validated scikit-decide request.

    DSPy and its LM are only used at the novelty frontier. JSON requests,
    exact cache hits, registry matching, planning, and rollout remain outside
    the language-model path.
    """

    def __init__(self, program: Any | None = None) -> None:
        try:
            import dspy
        except ImportError as error:
            raise DecisionRefusal(
                RefusalCode.DEPENDENCY_UNAVAILABLE,
                "DSPy is unavailable; install the agentic requirements",
                details={"dependency": "dspy"},
            ) from error

        if program is None:

            class JobToDecision(dspy.Signature):
                """Map a job to one registered domain and compatible solver.

                Return strict JSON objects for constructor arguments. Use AUTO
                when solver selection should be delegated to scikit-decide.
                """

                job: str = dspy.InputField()
                domains: str = dspy.InputField()
                solvers: str = dspy.InputField()
                domain: str = dspy.OutputField()
                solver: str = dspy.OutputField()
                domain_arguments_json: str = dspy.OutputField()
                solver_arguments_json: str = dspy.OutputField()
                max_steps: int = dspy.OutputField()

            program = dspy.Predict(JobToDecision)
        self._program = program

    def compile(self, job: str, catalog: DecisionCatalog) -> DecisionRequest:
        """Compile and validate one natural-language job."""
        try:
            prediction = self._program(
                job=job,
                domains=json.dumps(catalog.domains),
                solvers=json.dumps(catalog.solvers),
            )
            domain = str(prediction.domain).strip()
            solver_text = str(prediction.solver).strip()
            solver = (
                None if solver_text.upper() in {"", "AUTO", "NONE"} else solver_text
            )
            domain_arguments = _json_object(
                str(prediction.domain_arguments_json), "domain_arguments_json"
            )
            solver_arguments = _json_object(
                str(prediction.solver_arguments_json), "solver_arguments_json"
            )
            max_steps = int(prediction.max_steps)
        except DecisionRefusal:
            raise
        except Exception as error:
            raise DecisionRefusal(
                RefusalCode.NATURAL_LANGUAGE_COMPILATION_FAILED,
                "DSPy failed to compile the job into a decision request",
                details={"error": str(error)},
            ) from error

        if domain not in catalog.domains:
            raise DecisionRefusal(
                RefusalCode.NATURAL_LANGUAGE_COMPILATION_FAILED,
                "DSPy selected an unregistered domain",
                details={"domain": domain},
            )
        if solver is not None and solver not in catalog.solvers:
            raise DecisionRefusal(
                RefusalCode.NATURAL_LANGUAGE_COMPILATION_FAILED,
                "DSPy selected an unregistered solver",
                details={"solver": solver},
            )
        return DecisionRequest(
            domain=domain,
            solver=solver,
            domain_arguments=domain_arguments,
            solver_arguments=solver_arguments,
            max_steps=max_steps,
        )


def compile_request_text(
    text: str,
    catalog: DecisionCatalog,
    compiler: DecisionCompiler | None = None,
) -> DecisionRequest:
    """Prefer deterministic JSON; invoke DSPy only for natural language."""
    stripped = text.strip()
    if stripped.startswith("{"):
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError as error:
            raise DecisionRefusal(
                RefusalCode.INVALID_ARGUMENTS,
                "decision request JSON is malformed",
                details={"error": error.msg},
            ) from error
        if not isinstance(payload, dict):
            raise DecisionRefusal(
                RefusalCode.INVALID_ARGUMENTS,
                "decision request must be a JSON object",
            )
        return DecisionRequest.from_dict(payload)
    if compiler is None:
        raise DecisionRefusal(
            RefusalCode.NATURAL_LANGUAGE_COMPILER_UNAVAILABLE,
            "natural-language requests require an explicitly configured DSPy compiler",
        )
    return compiler.compile(stripped, catalog)


def _json_object(value: str, field: str) -> dict[str, Any]:
    try:
        decoded = json.loads(value or "{}")
    except json.JSONDecodeError as error:
        raise DecisionRefusal(
            RefusalCode.NATURAL_LANGUAGE_COMPILATION_FAILED,
            f"{field} is not valid JSON",
            details={"error": error.msg},
        ) from error
    if not isinstance(decoded, dict):
        raise DecisionRefusal(
            RefusalCode.NATURAL_LANGUAGE_COMPILATION_FAILED,
            f"{field} must be a JSON object",
        )
    return decoded
