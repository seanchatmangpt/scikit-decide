# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Real mitigation ACTUATION: select a real, safe
`sre_mitigation_portfolio.MitigationPortfolioCandidate`, execute its real
DO/READ steps as real, gated `run_kubectl` calls, and submit a real,
non-placeholder `submit_mitigation` payload.

Closes the single most load-bearing gap found while trying to reach a real
nonzero E2E score on sregym: every prior real mitigation-actuation call
site in this repo (`gymact_dspy_react.py::run_dspy_diagnosis`, and the
throwaway spike `scripts/run_gymact_mediated_trial.py`) submits the literal
payload `{"mitigation": "not_attempted", "reason":
"no_automated_command_synthesis_yet"}` -- named as a known, honest gap
directly in `gymact_dspy_react.py`'s own docstring. Since sregym's real
`Mitigation.success` can only ever be real-observed if a real mitigation
was really attempted (`sregym/conductor/conductor.py:262-276`), every real
E2E attempt before this module was structurally capped near 0%,
independent of infra reliability.

Real, not fabricated, safety gate
------------------------------------
An LM-flagged-unsafe candidate (`safe_to_actuate=False`) is never
actuated -- filtered before any real `env.actuate()` call, matching this
repo's own "typed refusal over fabricated success" law. Zero safe
candidates in a real portfolio is a real, honest, named early return
(mitigation genuinely not attempted, for a stated reason), never a silent
fallback to actuating an unsafe one.

VERIFY steps are never actuated as a second, competing check
------------------------------------------------------------
A candidate's real `VERIFY`-tagged steps are recorded as intent in the
returned trajectory only. The one real, authoritative verification stays
`environment.verify(...)` (sregym's own conductor oracle) -- actuating an
ad hoc "VERIFY" kubectl read here and treating it as a second truth would
be exactly the dual-bookkeeping failure `.claude/rules/no-dual-bookkeeping.md`
names for evidence, applied here to verification instead.

Topological order
------------------
Every real candidate this module consumes comes from
`sre_mitigation_portfolio.parse_process_steps`, which always builds a
total chain (`node.children[i]` precedes `node.children[j]` for every
`i < j`) -- so `candidate.node.children`'s own tuple order IS the real
execution order. This module does not implement a general topological
sort; it relies on (and is coupled to) that specific, documented
construction law.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import dspy

from autofde_lab.powl.algebra import Atom
from autofde_lab.powl.guard_executor import ExecutionStep
from autofde_lab.powl.ocel_bridge import OcelExecutionRecorder
from autofde_lab.reasoning.mitigation_kubectl_translation_signatures import (
    TranslateMitigationStepToKubectlCommand,
)
from autofde_lab.reasoning.sre_mitigation_portfolio import (
    MitigationPortfolioCandidate,
    construct_mitigation_portfolio,
)

__all__ = ["MitigationExecutionResult", "execute_and_submit_mitigation"]


@dataclass(frozen=True, slots=True)
class MitigationExecutionResult:
    """Real, typed outcome of one real mitigation-execution attempt."""

    attempted: bool
    reason: str
    selected_candidate: MitigationPortfolioCandidate | None
    executed_commands: tuple[str, ...]
    kubectl_responses: tuple[Any, ...]
    submit_mitigation_response: Any | None
    trajectory: dict[str, Any]


def _capability(capabilities: Any, name: str) -> Any:
    for cap in capabilities:
        if cap.binding == name:
            return cap
    raise KeyError(f"no real gymact capability named {name!r}")


async def execute_and_submit_mitigation(
    environment: Any,
    gate: Any,
    capabilities: Any,
    *,
    root_cause: str,
    relevant_resource_spec: str,
    capability_catalog: str,
    namespace: str,
    portfolio_size: int = 3,
    portfolio_program: dspy.Module | None = None,
    translator: dspy.Module | None = None,
    recorder: OcelExecutionRecorder | None = None,
) -> MitigationExecutionResult:
    """Construct a real mitigation portfolio, actuate one real, safe
    candidate's real DO/READ steps through the gated `run_kubectl`
    capability, and submit a real, non-placeholder `submit_mitigation`
    payload.

    Never actuates an `safe_to_actuate=False` candidate. Zero safe
    candidates in the real portfolio is an honest, named early return
    (`attempted=False`), never a silent fallback.

    `recorder`, when supplied, records one real OCEL event per executed
    step via `OcelExecutionRecorder.record_atom` -- same real, proven
    pattern this session already wired into `breed_ensemble.py`/
    `breed_ensemble_loop.py`/`gymact_dspy_react.py.decide`.
    """
    trajectory: dict[str, Any] = {"namespace": namespace, "stages": []}

    portfolio = construct_mitigation_portfolio(
        root_cause=root_cause,
        relevant_resource_spec=relevant_resource_spec,
        capability_catalog=capability_catalog,
        portfolio_size=portfolio_size,
        program=portfolio_program,
    )
    trajectory["stages"].append(
        {"stage": "construct_portfolio", "portfolio_size_returned": len(portfolio)}
    )

    safe_candidates = [c for c in portfolio if c.safe_to_actuate]
    if not safe_candidates:
        reason = (
            f"no safe_to_actuate candidate in a real portfolio of {len(portfolio)} "
            "admitted candidate(s) -- mitigation genuinely not attempted"
        )
        trajectory["stages"].append({"stage": "no_safe_candidate", "reason": reason})
        return MitigationExecutionResult(
            attempted=False,
            reason=reason,
            selected_candidate=None,
            executed_commands=(),
            kubectl_responses=(),
            submit_mitigation_response=None,
            trajectory=trajectory,
        )

    selected = safe_candidates[0]
    trajectory["stages"].append(
        {
            "stage": "select_candidate",
            "expected_consequence": selected.expected_consequence,
            "rollback_plan": selected.rollback_plan,
        }
    )

    translate = translator if translator is not None else dspy.Predict(TranslateMitigationStepToKubectlCommand)

    run_kubectl_cap = _capability(capabilities, "run_kubectl")
    executed_commands: list[str] = []
    kubectl_responses: list[Any] = []
    step_timestamp_ns = 0

    for atom in selected.node.children:
        if not isinstance(atom, Atom):
            continue  # defensive -- parse_process_steps only ever emits Atom children
        if atom.consequence == "VERIFY":
            # Intent only -- the real, authoritative verification stays
            # environment.verify(...), never duplicated here.
            trajectory["stages"].append({"stage": "verify_intent", "description": atom.label})
            continue

        prediction = translate(
            step_description=atom.label,
            step_consequence=atom.consequence,
            relevant_resource_spec=relevant_resource_spec,
        )
        command = str(getattr(prediction, "kubectl_command", ""))
        is_safe = bool(getattr(prediction, "is_safe_readonly_or_reversible", False))

        if not command.startswith("kubectl "):
            trajectory["stages"].append(
                {
                    "stage": "translate_step_refused",
                    "reason": "translated command did not start with the required 'kubectl ' prefix",
                    "description": atom.label,
                }
            )
            continue
        if not is_safe:
            trajectory["stages"].append(
                {
                    "stage": "translate_step_refused",
                    "reason": "LM marked this command neither read-only nor reversible",
                    "description": atom.label,
                    "kubectl_command": command,
                }
            )
            continue

        gate.guard_capability(run_kubectl_cap)
        response = await environment.actuate(run_kubectl_cap, {"command": command})
        executed_commands.append(command)
        kubectl_responses.append(response)
        trajectory["stages"].append(
            {"stage": "executed_step", "description": atom.label, "kubectl_command": command}
        )
        if recorder is not None:
            recorder.record_atom(
                ExecutionStep(kind="Atom", label=command, consequence=atom.consequence),
                timestamp_ns=step_timestamp_ns,
            )
            step_timestamp_ns += 1

    submit_cap = _capability(capabilities, "submit_mitigation")
    gate.guard_capability(submit_cap)
    mitigation_description = (
        f"{len(executed_commands)} real step(s) executed for candidate targeting root cause "
        f"{root_cause!r}. rollback_plan={selected.rollback_plan!r}"
    )
    submit_response = await environment.actuate(
        submit_cap,
        {
            "mitigation": mitigation_description,
            "reason": "real_mitigation_portfolio_candidate_executed",
            "executed_commands": executed_commands,
        },
    )
    trajectory["stages"].append({"stage": "submit_mitigation", "executed_command_count": len(executed_commands)})

    return MitigationExecutionResult(
        attempted=True,
        reason="real, safe candidate selected and its DO/READ steps executed",
        selected_candidate=selected,
        executed_commands=tuple(executed_commands),
        kubectl_responses=tuple(kubectl_responses),
        submit_mitigation_response=submit_response,
        trajectory=trajectory,
    )
