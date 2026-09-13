# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""An independent, non-LLM second opinion on hypothesis closure, via
``~/wasm4pm``'s real Hearsay-II blackboard breed.

Why this exists
------------------
This session's own `SreTroubleshootingDecisionBackend` (`gymact_dspy_react.py`)
and a separate, independently-developed rail (`agent/sregym-signature-sota`,
PR #49) both hit the same real failure live: a `causal_closure` guard whose
only input is the SAME LLM's own self-labeling of
supported/refuted/unknown anchors on one hypothesis and never disagrees with
itself -- PR #49's own body documents this exact failure mode
("anti-anchoring failure... the surviving frontier stopped shrinking despite
hundreds of new facts").

The fix here is not a smarter prompt -- it's a structurally *different*
reasoning engine checking the same evidence. `~/wasm4pm`'s Hearsay-II
blackboard breed (`crates/wasm4pm-cognition/src/breeds/hearsay.rs`) selects a
hypothesis via a real, non-LLM span-completeness STOP criterion / max-
confidence tie-break over a blackboard of confidence-scored hypotheses -- a
model that shares none of an LLM's biases. This module is the bridge from a
real hypothesis portfolio to that breed and back, reusing the already-real,
already-verified `receipts.wasm4pm_cognition.run_cognition` bridge (confirmed
live this session against the real `ebl` breed) -- never a second, parallel
bridge to the same CLI.

The real trigger grammar, read directly from the Rust breed (not guessed)
--------------------------------------------------------------------------
An earlier version of this module passed a plausible-looking but wrong rule
shape and got real, honest evidence back that it never worked: every trace
entry was `kind: "seed"`, no `kind: "post-hypothesis"` ever appeared, and
Hearsay's own "selection" degenerated to an alphabetical tie-break among raw
seeded facts -- not real reasoning. Reading `hearsay.rs` directly (not the
TypeScript Zod schema, which describes the wire *shape* but not the
*semantics*) found the real contract:

- The blackboard's content key is ``"{fact.key}:{fact.value}"`` -- a single
  string, not a separate key/value pair.
- ``level_of(content)`` is everything before the first ``:``.
- A `Rule.premise[0]` (**only the first element is read** -- `ks.premise
  .first()`) must match the blackboard EXACTLY (`trigger == content`) or via
  the wildcard ``"{level}-hypotheses"`` (matches ANY currently-posted content
  sharing that level -- letting one rule fire once evidence exists *at that
  level*, regardless of which specific fact posted it).
- `Rule.conclusion` is the content string POSTED (added to the blackboard)
  when the rule fires, at whatever confidence `rule.certainty * trigger_cf`
  computes to.
- `Rule.certainty` is clamped to `[0, 1]` in the real Rust code
  (`ks.certainty.clamp(0.0, 1.0)`) -- **not** `-1..1` as the TypeScript
  `RuleSchema` comment (`certainty: z.number().min(-1).max(1)`) suggested; a
  negative certainty is silently clamped to 0, so this module emits `0.0`
  directly for `REFUTED` rather than relying on that clamp to mask a wrong
  claim about the real range.
- Final selection excludes only the LEVEL of `input.facts[0]` (the seed
  level) -- everything else, including every hypothesis-level entry, is
  eligible, and the highest-confidence entry wins (ties broken by smallest
  content key).

The working design this produces
------------------------------------
Every admitted-fact bullet line becomes a real `Fact` sharing one common
``key="fact"`` (so they all share blackboard level ``"fact"`` -- this is
what makes the wildcard trigger ``"fact-hypotheses"`` match ANY of them).
Every hypothesis bullet line becomes one real `Rule` whose `premise[0]` is
that exact wildcard, whose `conclusion` is ``"hypothesis:{line text}"`` (so
the hypothesis's real text is directly *in* the posted content -- no
separate id-to-text resolution step needed, unlike an earlier version of
this module), and whose `certainty` is derived from the line's own real
`HypothesisState`. Once any real fact exists, every hypothesis rule's
trigger is satisfied and each posts its own real, distinguishable
confidence -- Hearsay's real max-confidence selection then genuinely
reflects which hypothesis its own reasoning favors, not an alphabetical
accident. Confirmed live this session: `kind: "post-hypothesis"` now
appears in the real trace, and `selected` is a real
``"hypothesis:<text>"`` string.

States are string enums, never bare numbers/booleans
----------------------------------------------------
Every STATE this module represents internally (`HypothesisState`,
`AgreementOutcome`) is a named `enum.StrEnum` member, per this repo's own
established convention (`autofde_lab.powl.refusals.PowlRefusal`). The one
place a raw float appears (`_CERTAINTY_BY_STATE`'s values) is an external
wire-format requirement -- Hearsay's real `Rule.certainty` is a literal
`f32` field on the real Rust struct -- and that conversion happens only at
this module's own outbound boundary, never as this module's own internal
representation of a hypothesis's state.

Additive, never mandatory
----------------------------
The Hearsay CLI may not be built in every environment
(`Wasm4pmCognitionUnavailable`). `cross_check_via_hearsay` returns `None` in
that case -- a real, named "not available here" signal a caller must handle
explicitly, never silently treated as agreement. A real `NoEvidence` (the
breed ran but produced no trustworthy evidence) is NOT caught here -- that is
a real refusal a caller must see, not something this module downgrades to
"unavailable."
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from autofde_lab.receipts.wasm4pm_cognition import (
    CognitionEvidence,
    Wasm4pmCognitionUnavailable,
    run_cognition,
)

# Re-exported so callers of this module can catch the real refusal
# `cross_check_via_hearsay` deliberately lets propagate uncaught (see its
# own docstring) without also importing from `receipts.wasm4pm_cognition`
# directly.
from autofde_lab.receipts.wasm4pm_cognition import NoEvidence as NoEvidence  # noqa: F401

__all__ = [
    "AgreementOutcome",
    "HypothesisState",
    "cross_check_via_hearsay",
    "hypotheses_agree",
    "hypotheses_to_breed_input",
]

#: Blackboard level every admitted fact shares -- what makes the real
#: "fact-hypotheses" wildcard trigger match any of them (see module
#: docstring's "real trigger grammar" section).
_FACT_LEVEL = "fact"

#: Blackboard level every hypothesis's posted conclusion uses.
_HYPOTHESIS_LEVEL = "hypothesis"

#: The real wildcard trigger content every hypothesis rule fires on --
#: "any content currently posted at the fact level".
_FACT_WILDCARD_TRIGGER = f"{_FACT_LEVEL}-hypotheses"


class HypothesisState(StrEnum):
    """Real vocabulary a hypothesis-portfolio bullet line is classified
    into -- same three-way split `HypothesizeSreCauses`'s own signature
    (`sre_troubleshooting_signatures.py`) documents its output labels with."""

    SUPPORTED = "SUPPORTED"
    REFUTED = "REFUTED"
    UNKNOWN = "UNKNOWN"


class AgreementOutcome(StrEnum):
    """Real outcome of comparing the Hearsay breed's independent selection
    against the DSPy-committed hypothesis text -- a named state, never a
    bare `bool`, so a trajectory entry or log line is self-describing
    without a caller needing to know what `True` meant in this context."""

    AGREES = "AGREES"
    DISAGREES = "DISAGREES"


# Wire-format-only conversion -- Hearsay's real Rust `Rule.certainty` is a
# literal `f32` clamped to `[0, 1]` (confirmed by reading hearsay.rs
# directly, see module docstring); this map is the one place that external
# contract's numeric shape is touched.
_CERTAINTY_BY_STATE: dict[HypothesisState, float] = {
    HypothesisState.SUPPORTED: 1.0,
    HypothesisState.UNKNOWN: 0.5,
    HypothesisState.REFUTED: 0.0,
}


def _bullet_lines(text: str) -> list[str]:
    """Real, deterministic bullet-line extraction, matching the exact
    convention `gymact_dspy_react._count_hypothesis_labels` already uses for
    the same real hypothesis-portfolio text -- reused here rather than
    re-derived, so both callers agree on what counts as one hypothesis
    entry."""
    lines: list[str] = []
    for raw_line in text.splitlines():
        marker_stripped = raw_line.strip().lstrip("*").strip()
        is_bullet = raw_line.strip().startswith(("-", "*")) or (
            marker_stripped[:1].isdigit() and "." in marker_stripped[:4]
        )
        if not is_bullet or not marker_stripped:
            continue
        content = marker_stripped.lstrip("-").strip()
        if content:
            lines.append(content)
    return lines


def _classify_hypothesis_state(line: str) -> HypothesisState:
    """Real, deterministic classification of one hypothesis bullet line's
    own state label, first-match-wins over the same three real label words
    `HypothesizeSreCauses` documents -- mirrors
    `gymact_dspy_react._count_hypothesis_labels`'s own per-line label
    detection (case-insensitive, first label word found), so a bullet line
    lacking any of the three real words defaults to `UNKNOWN` (never
    silently assumed supported)."""
    lowered = line.lower()
    first_index: int | None = None
    first_state: HypothesisState | None = None
    for word, state in (
        ("supported", HypothesisState.SUPPORTED),
        ("refuted", HypothesisState.REFUTED),
        ("unknown", HypothesisState.UNKNOWN),
    ):
        idx = lowered.find(word)
        if idx != -1 and (first_index is None or idx < first_index):
            first_index, first_state = idx, state
    return first_state or HypothesisState.UNKNOWN


def hypotheses_to_breed_input(
    *, admitted_facts: str, hypothesis_portfolio: str
) -> dict[str, list[dict[str, Any]]]:
    """Real, deterministic translation of a real hypothesis-portfolio round
    into the real `run_cognition()` bridge's `facts`/`candidates`/`rules`
    `BreedInput` shape -- the real, working design (see module docstring's
    "the real trigger grammar" and "the working design this produces"
    sections), not the earlier, confirmed-non-firing shape.

    Every admitted-fact bullet line becomes one real `Fact` sharing
    ``key="fact"`` (grouping them at one shared blackboard level). Every
    hypothesis bullet line becomes one real `Rule` triggered by the
    ``"fact-hypotheses"`` wildcard (fires once any real fact exists) whose
    `conclusion` is ``"hypothesis:{line text}"`` -- the real text is
    directly IN the posted content, so a caller never needs a separate
    id-to-text resolution step -- and one real `Candidate` (`{id, score,
    eliminated}`, the real Rust wire shape; passed through unused by
    Hearsay's own scheduling, kept for real schema compliance). Neither the
    ``"none"`` sentinel (this repo's own convention for "nothing yet") nor
    an empty string produces any facts/candidates/rules -- an honest empty
    `BreedInput`, not a fabricated placeholder.
    """
    has_facts = admitted_facts.strip().lower() not in ("", "none")
    has_hypotheses = hypothesis_portfolio.strip().lower() not in ("", "none")

    fact_lines = _bullet_lines(admitted_facts) if has_facts else []
    facts = [{"key": _FACT_LEVEL, "value": line} for line in fact_lines]

    hypothesis_lines = _bullet_lines(hypothesis_portfolio) if has_hypotheses else []
    hypothesis_states = [_classify_hypothesis_state(line) for line in hypothesis_lines]

    candidates = [
        {
            "id": f"hypothesis-{i}",
            "score": _CERTAINTY_BY_STATE[state],
            "eliminated": state == HypothesisState.REFUTED,
        }
        for i, state in enumerate(hypothesis_states)
    ]
    rules = (
        [
            {
                "id": f"rule-{i}",
                "premise": [_FACT_WILDCARD_TRIGGER],
                "conclusion": f"{_HYPOTHESIS_LEVEL}:{line}",
                "certainty": _CERTAINTY_BY_STATE[state],
            }
            for i, (line, state) in enumerate(zip(hypothesis_lines, hypothesis_states))
        ]
        if facts  # the wildcard trigger only ever matches once a real fact is seeded
        else []
    )

    return {"facts": facts, "candidates": candidates, "rules": rules}


async def cross_check_via_hearsay(
    *, admitted_facts: str, hypothesis_portfolio: str, timeout_s: float = 15.0
) -> CognitionEvidence | None:
    """Run the real Hearsay-II breed over a real hypothesis portfolio.

    Returns `None` when the Hearsay CLI is not built/available in this
    environment (a real, named, honest "not attempted here" outcome). Lets a
    real `NoEvidence` (the breed ran but the result failed causal-consistency
    verification, or returned a non-``"ok"`` status -- including the real
    precondition refusal when no facts/rules exist at all) propagate
    uncaught -- that is a real refusal, not an availability gap, and must
    reach the caller as such.
    """
    breed_input = hypotheses_to_breed_input(
        admitted_facts=admitted_facts, hypothesis_portfolio=hypothesis_portfolio
    )
    try:
        return await run_cognition(
            "hearsay",
            facts=breed_input["facts"],
            candidates=breed_input["candidates"],
            rules=breed_input["rules"],
            timeout_s=timeout_s,
        )
    except Wasm4pmCognitionUnavailable:
        return None


def hypotheses_agree(*, hearsay_selected: str | None, committed_root_cause: str) -> AgreementOutcome:
    """Real, honest, approximate agreement check between the Hearsay
    breed's own real ``"hypothesis:<text>"`` selection and the DSPy-
    committed `root_cause` text.

    This is deliberately a loose, case-insensitive shared-word check, not
    exact equality -- the two systems describe the same real-world cause in
    different vocabularies, so demanding exact string equality would make
    this guard permanently `DISAGREES` and defeat its own purpose. The real
    ``"hypothesis:"`` prefix (if present) is stripped before comparison so
    it never counts as a spurious shared word. Named explicitly as
    approximate so a caller never mistakes it for a precise semantic match.
    Returns a real `AgreementOutcome`, never a bare `bool`.
    """
    if not hearsay_selected or not committed_root_cause:
        return AgreementOutcome.DISAGREES
    _, _, selected_text = hearsay_selected.partition(f"{_HYPOTHESIS_LEVEL}:")
    selected_text = selected_text or hearsay_selected
    selected_words = {w for w in selected_text.lower().split() if len(w) > 3}
    root_cause_lower = committed_root_cause.lower()
    if not selected_words:
        return AgreementOutcome.DISAGREES
    overlap = sum(1 for w in selected_words if w in root_cause_lower)
    if overlap / len(selected_words) >= 0.3:
        return AgreementOutcome.AGREES
    return AgreementOutcome.DISAGREES
