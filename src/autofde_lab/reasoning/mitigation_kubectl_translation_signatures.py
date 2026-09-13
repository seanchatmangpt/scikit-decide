# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""A real, additive DSPy `Signature` translating one free-text mitigation
step description into a literal, directly-executable `kubectl` command.

Closes the one genuinely new reasoning gap found while trying to actuate a
real `sre_mitigation_portfolio.py` candidate against a live cluster: every
existing mitigation-reasoning signature in this repo stops at free-text
description --

- `k8s_signatures.ProposeKubernetesRemediation.remediation_action`: a
  description, not a literal command.
- `sre_mitigation_portfolio_signatures.ConstructSreMitigationProcess.process_steps`:
  one free-text description per real step (`"DO: patch the deployment
  memory limit to 512Mi"`), matching the process-construction signature's
  own job (describe a process), never a literal command.

Neither of those is a defect -- both are deliberately about REASONING
(what should happen, and why), never actuation. This signature is the one,
narrow, additive translation atom between "a real step was decided" and
"a real, literal, gated `run_kubectl` capability call can execute it" --
matching this repo's own DSPy-reasons/GymAct-actuates law exactly the same
way `sre_mitigation_portfolio_signatures.py`'s own module docstring states
it: this signature's output is eligible input to gated capability routing,
never a substitute for it.

A real, related, narrower mechanism already exists and is NOT duplicated
here: `gymact_dspy_signatures.SynthesizeMitigation` (grounded with real
worked examples for `inject_wrong_dns_policy` and
`inject_liveness_probe_too_aggressive`) synthesizes ONE literal `kubectl`
command directly from a whole diagnosis, single-shot, with no portfolio
and no `submit_mitigation` call. This signature instead translates ONE
step of an already-constructed, safety-filtered, multi-step
`sre_mitigation_portfolio.MitigationPortfolioCandidate` -- a different
real job (portfolio-step translation vs. whole-diagnosis single-shot
synthesis), not a competing reimplementation of the same one.
"""

from __future__ import annotations

import dspy

__all__ = ["TranslateMitigationStepToKubectlCommand"]


class TranslateMitigationStepToKubectlCommand(dspy.Signature):
    """Translate ONE real mitigation-process step description into a
    literal, directly-executable `kubectl` command string -- never a
    second free-text description, never a placeholder. The command must be
    genuinely runnable as-is (a real caller passes it straight to a gated
    `run_kubectl` capability, verbatim) and must start with the literal
    text `"kubectl "` (the real MCP tool this repo's sregym trials use
    rejects any command that doesn't -- see
    `.claude/rules/gym-actuation-boundary.md`'s "kubectl-prefix bug"
    finding, and `docs/2026-08-09-powl-actuation-sregym-progress.md`
    Cycle 7's real, retracted false-anomaly caused by this exact defect).
    `is_safe_readonly_or_reversible=False` is a legitimate, honest answer
    for a genuinely destructive/irreversible step -- never coerced to
    True to make a caller's job easier."""

    step_description: str = dspy.InputField(
        desc="the real, committed step description from a mitigation-process candidate, e.g. "
        "'patch the deployment memory limit to 512Mi'"
    )
    step_consequence: str = dspy.InputField(
        desc="the real consequence class this step was tagged with in its process (READ, DO, or VERIFY)"
    )
    relevant_resource_spec: str = dspy.InputField(
        desc="the real, current spec/state of the resource(s) this step would read or change "
        "(namespace, deployment name, current field values, etc.)"
    )
    kubectl_command: str = dspy.OutputField(
        desc="one real, literal, directly-executable kubectl command, starting with the exact "
        "text 'kubectl ' -- e.g. 'kubectl patch deployment geo -n hotel-reservation "
        "-p '{\"spec\":{\"template\":{\"spec\":{\"containers\":[{\"name\":\"geo\","
        "\"resources\":{\"limits\":{\"memory\":\"512Mi\"}}}]}}}}'' -- never free text, "
        "never a placeholder, never omitting the resource/namespace it targets"
    )
    is_safe_readonly_or_reversible: bool = dspy.OutputField(
        desc="True only if kubectl_command is genuinely read-only (a 'get'/'describe'/'logs' "
        "command) or a change with a real, stated rollback path -- an honest False for a "
        "genuinely destructive/irreversible command is a legitimate answer, never coerced to True"
    )
