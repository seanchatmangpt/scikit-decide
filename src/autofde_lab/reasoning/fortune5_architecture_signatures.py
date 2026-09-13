# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Real, typed DSPy `Signature`s for TOGAF Phase A (Architecture Vision)
through Phase E (Opportunities & Solutions), per
`docs/2026-08-11-v26.8.11-fortune5-togaf-prd.md`.

**The core claim this module makes real, not just asserted**: a typed
`InputField`/`OutputField` contract is a smaller, more reviewable diff
surface than a prose architecture-vision document -- narrowing (never
eliminating) the Phase-A root-of-trust-corruption risk this session
identified. Nothing here closes that risk to zero; see
`.claude/rules/fde-authority-boundary.md`.

**What this module is not, stated directly**: none of these signatures'
outputs are an `adoption decision` or `sunset authorization`
(`fde-authority-boundary.md`'s seven-kind table). Every output here is a
`technical consequence` -- a candidate, never an authorization. A caller
that treats `ArchitectureVision`'s output as license to actuate anything
is misusing this module; nothing in its type signature grants that
license, matching `sre_troubleshooting_signatures.py`'s same "intent, not
actuation" discipline for a different domain.

**Grounding discipline**: every `InputField` here is plain text/data a
caller supplies -- this module never itself fetches, infers, or invents
"the industry's Phase A" from an external ontology (this session's 5-agent
audit found no such ingestion pipeline exists in `ggen`/`ggen-marketplace`
today). A caller who has such real, admitted data (e.g. from
`world_transformation_orchestrator.py`'s real `ScenarioMetadata`) folds it
into these fields; a caller with only prose folds that in instead. This
module makes no claim about where the input came from -- only that its
own output is typed and reviewable.
"""

from __future__ import annotations

import dspy

__all__ = [
    "InferArchitectureVision",
    "DeriveBusinessArchitecture",
    "SelectTransformationCandidate",
]


class InferArchitectureVision(dspy.Signature):
    """TOGAF Phase A: given observed enterprise state and a business
    objective, produce a typed architecture vision statement -- never free
    prose, and never itself an authorization to act. `stakeholder_concerns`
    must be echoed back into `vision_statement` explicitly addressed, never
    silently dropped -- an unaddressed concern is a real gap to surface,
    not an oversight to hide."""

    observed_state: str = dspy.InputField(
        desc="admitted, real facts about current enterprise state (e.g. OCEL-derived observations)"
    )
    business_objective: str = dspy.InputField(desc="the real business goal driving this architecture work")
    stakeholder_concerns: str = dspy.InputField(
        desc="real, named stakeholder concerns this vision must address, one per line"
    )
    vision_statement: str = dspy.OutputField(
        desc="a typed, scoped statement of architecture work -- names what is and is not in scope"
    )
    unaddressed_concerns: str = dspy.OutputField(
        desc="any stakeholder_concerns the vision_statement could not address -- 'none' only if genuinely none, never omitted"
    )


class DeriveBusinessArchitecture(dspy.Signature):
    """TOGAF Phase B: given an architecture vision, derive real,
    checkable objectives and constraints -- matching
    `ontology/world-transformation-taxonomy.ttl`'s own `Objective`/
    `Constraint` distinction (a target to approach vs. a hard bound never
    to violate). Never conflate the two."""

    vision_statement: str = dspy.InputField()
    objectives: str = dspy.OutputField(
        desc="real, measurable targets to approach, one per line, each with a comparator and threshold if numeric"
    )
    constraints: str = dspy.OutputField(
        desc="real, hard bounds that must never be violated, one per line -- distinct from objectives"
    )


class SelectTransformationCandidate(dspy.Signature):
    """TOGAF Phase E: given a real computed delta (observed vs. desired
    state, one item per violated objective/constraint), propose a
    candidate transformation. This is the DSPy-Module counterpart to
    `world_transformation_orchestrator.select_transformation`'s
    deterministic, rule-based version -- both exist because a rule-based
    selector is auditable but bounded to its lookup table, while this
    signature can reason over deltas the rule-based table has no entry
    for. Neither replaces the other. Must explicitly refuse (output
    `"NONE"` for `candidate_label`) rather than fabricate a candidate when
    the delta gives no real basis for one -- matching
    `select_transformation`'s own `None`-return discipline."""

    delta_summary: str = dspy.InputField(
        desc="real per-objective/constraint delta: kind, comparator, current value (or 'UNKNOWN'), target"
    )
    candidate_label: str = dspy.OutputField(
        desc="a short, real transformation label, or the literal string 'NONE' if no real basis exists"
    )
    rationale: str = dspy.OutputField(desc="why this candidate addresses the real, named delta item(s)")
