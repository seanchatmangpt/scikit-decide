# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""A real, additive DSPy `Signature` constructing ONE candidate mitigation
*process* (a small, structured sequence of real steps), rather than the
single free-text `mitigation_intent` string
`sre_troubleshooting_signatures.ConstructSreMitigation` produces.

This module does not modify `sre_troubleshooting_signatures.py` or
`sre_troubleshooting_pipeline.py` -- it is a new, parallel capability. A
caller (`sre_mitigation_portfolio.construct_mitigation_portfolio`) calls
`ConstructSreMitigationProcess` several independent times to build a real
PORTFOLIO of alternative mitigation processes, each parsed into a real
`autofde_lab.powl.algebra.PartialOrder` of `Atom`s and admitted through
`autofde_lab.powl.validate.validate_model` -- Pareto-selectable later by a
caller, never collapsed to one choice inside DSPy itself.

The architectural law this signature encodes
----------------------------------------------
Same DSPy-reasons/GymAct-actuates law as `sre_troubleshooting_signatures.py`:
`process_steps` is a real, structured DESCRIPTION of a process -- each line
tagged with its real consequence class (READ/DO/VERIFY) -- never an
actuation. A "DO"-tagged step still must be routed through the real, gated
capability surface (`gymact_dspy_react.py`) by a caller before it does
anything; this signature's output is eligible input to that routing, not a
substitute for it.
"""

from __future__ import annotations

import dspy

__all__ = ["ConstructSreMitigationProcess"]


class ConstructSreMitigationProcess(dspy.Signature):
    """Construct ONE candidate mitigation PROCESS for an already-committed
    diagnosis: a small, real, ordered sequence of steps (not a single
    free-text intent), each step tagged with its real consequence class.
    This produces a description of a process, never an actuation --
    `safe_to_actuate=True` marks eligibility for separate, real admission
    through the gated capability surface; it never itself performs a DO."""

    root_cause: str = dspy.InputField(desc="the committed, real root cause to mitigate")
    relevant_resource_spec: str = dspy.InputField(
        desc="the current real spec/state of the resource(s) the mitigation would change"
    )
    capability_catalog: str = dspy.InputField(
        desc="the real, admitted READ/DO/VERIFY capability names available"
    )
    process_steps: str = dspy.OutputField(
        desc=(
            "one real step per line, each line in the exact format "
            "'<CONSEQUENCE>: <step description>' where <CONSEQUENCE> is exactly one of "
            "READ, DO, or VERIFY (uppercase, no other consequence values). At least two "
            "lines. A real, concrete, small mitigation process, e.g.: "
            "'READ: describe the current deployment spec'\n"
            "'DO: patch the deployment memory limit to 512Mi'\n"
            "'VERIFY: confirm the rollout status is complete'\n"
            "'VERIFY: confirm the target workload is no longer OOMKilled'. "
            "Never a placeholder line, never a DO step without at least one following VERIFY step."
        )
    )
    expected_consequence: str = dspy.OutputField(
        desc="the real, honest expected effect of executing process_steps in order, including side effects"
    )
    rollback_plan: str = dspy.OutputField(
        desc="a real, concrete way to reverse process_steps's DO step(s) if they make things worse"
    )
    safe_to_actuate: bool = dspy.OutputField(
        desc="True only if process_steps is genuinely small, reversible, and grounded in "
        "relevant_resource_spec -- an honest False is a legitimate answer"
    )
