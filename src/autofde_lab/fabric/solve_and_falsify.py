# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""The one real, in-process callable step: fabric solve, then falsify.

Extracted from `scripts/solve_then_falsify.py` (which closed the smallest
real gap named in `docs/2026-08-11-autofde-lab-togaf-autonomic-architecture-plan.md`
section 11: `autofde_lab.reasoning.laboratory.falsify_candidate` existed but
was only ever invoked once, inside the one-shot `reasoning/togaf_loop_demo.py`
demo function, never wired to the real solve path).

This module is the shared, importable home for that logic so both the manual
CLI script and `fabric/phase_h_trigger.py`'s real, unattended, drift-triggered
solve path can call the SAME real solve+falsify step -- one implementation,
not two independently maintained copies.

Not a scheduler. Not the full OCEL->process-inference->conformance pipeline
section 13 describes. One callable step: `solve_and_falsify(...)`.
"""

from __future__ import annotations

from autofde_lab.fabric.cli import get_fabric
from autofde_lab.fabric.models import DecisionRequest, DecisionResult, DecisionStanding
from autofde_lab.reasoning.laboratory import (
    ArchitectureCandidate,
    ExperimentReceipt,
    FalsificationResult,
    falsify_candidate,
)


def receipt_from_solve(intent_id: str, result: DecisionResult) -> ExperimentReceipt:
    """Real receipt built only from what the real solve actually observed --
    never a value invented for this module. `SOLVED` with a terminal
    trajectory is the one real postcondition this fabric result can support
    ("bounded rollout reached a terminal state"); anything else is recorded
    as violated, never silently dropped."""
    reached_terminal = result.standing == DecisionStanding.SOLVED and result.terminal
    return ExperimentReceipt(
        intent_id=intent_id,
        observed_outcome_refs=(f"fabric-receipt:{result.receipt_sha256}",),
        authority_standing="ADMITTED",
        postconditions_observed=("bounded-rollout-reached-terminal-state",)
        if reached_terminal
        else (),
        postconditions_violated=()
        if reached_terminal
        else ("bounded-rollout-reached-terminal-state",),
        ocel_evidence_ref=None,
        standing="OBSERVED",
    )


def solve_and_falsify(
    domain: str,
    domain_arguments: dict | None = None,
    max_steps: int = 100,
    solver: str | None = None,
) -> tuple[DecisionResult, FalsificationResult]:
    """The one callable per-cycle step: real fabric solve, then the real
    falsification check run immediately against that real solve's output.

    In-process (calls `fabric.solve()` directly), not a subprocess -- the
    caller gets typed `DecisionResult`/`FalsificationResult` objects, not a
    stdout string to reparse.
    """
    fabric = get_fabric()
    request = DecisionRequest(
        domain=domain,
        solver=solver,
        domain_arguments=domain_arguments or {},
        max_steps=max_steps,
        use_cache=False,
    )
    result = fabric.solve(request)

    candidate = ArchitectureCandidate(
        candidate_id=f"fabric-solve:{domain}:{result.trajectory_sha256[:16]}",
        target_state_assertions=(f"{domain} bounded rollout reaches a terminal state",),
        verification_criteria=("bounded-rollout-reached-terminal-state",),
    )
    intent_id = f"solve-then-falsify:{result.trajectory_sha256}"
    receipt = receipt_from_solve(intent_id, result)
    falsification = falsify_candidate(candidate, receipts=(receipt,))
    return result, falsification
