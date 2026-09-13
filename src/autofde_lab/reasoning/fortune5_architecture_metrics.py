# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""A real, external, non-self-certified metric for any DSPy optimizer
(GEPA/MIPROv2/...) compiled against
`fortune5_architecture_signatures.SelectTransformationCandidate`.

**The one rule this module exists to enforce**: per
`.claude/rules/no-dual-bookkeeping.md`, a metric may never be the same LLM
grading its own Signature's output -- that reproduces exactly the
self-certification failure this repo's rules already forbid, wearing
DSPy's syntax instead of a human architect's (see
`docs/2026-08-11-v26.8.11-fortune5-togaf-prd.md`'s Phase-A-corruption
section). This metric is instead grounded on
`world_transformation_orchestrator.select_transformation`'s real,
deterministic, already-tested rule-based answer -- an external,
independently-computable signal a DSPy Module's output is scored against,
never a self-report.

This does not make the metric *correct* forever -- it makes it *external*:
the rule-based selector's own lookup table
(`_KIND_TO_TRANSFORMATION_LABEL`) can be wrong or incomplete, and expanding
it is real, separate, auditable work (a diff to a Python dict), not a
silent drift inside an LLM's judgment.
"""

from __future__ import annotations

import dspy

from autofde_lab.reasoning.world_transformation_orchestrator import (
    DeltaItem,
    select_transformation,
)

__all__ = ["transformation_candidate_metric"]


def transformation_candidate_metric(
    example: dspy.Example,
    prediction: dspy.Prediction,
    trace: object | None = None,
    pred_name: str | None = None,
    pred_trace: object | None = None,
) -> dspy.Prediction:
    """Score a `SelectTransformationCandidate` prediction against the real,
    deterministic `select_transformation` answer for the same delta.

    `example.delta` must be a real `tuple[DeltaItem, ...]` (not a string --
    the caller builds this from a real `compute_delta()` call, never
    hand-typed). Score is `1.0` if the prediction's `candidate_label`
    matches the rule-based selector's real label (or both agree on `NONE`),
    `0.0` otherwise -- binary and external, never a fuzzy LLM self-grade.
    """
    delta: tuple[DeltaItem, ...] = example.delta
    expected = select_transformation(delta)
    expected_label = expected.label if expected is not None else "NONE"

    predicted_label = str(getattr(prediction, "candidate_label", "")).strip()
    score = 1.0 if predicted_label == expected_label else 0.0

    if score == 1.0:
        feedback = f"candidate_label={predicted_label!r} matches the real, rule-based selector's answer."
    else:
        feedback = (
            f"candidate_label={predicted_label!r} does not match the real, rule-based "
            f"selector's answer ({expected_label!r}), computed independently from the same "
            "delta via world_transformation_orchestrator.select_transformation -- not an LLM self-grade."
        )

    return dspy.Prediction(score=score, feedback=feedback)
