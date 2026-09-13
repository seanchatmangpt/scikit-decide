# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for typed prediction-mismatch evidence.

Real archived trial directories under ``docs/evidence/crown1/``, the real
``dogfood`` measurement, the real ``OcelLog`` parsed off disk, and assertions
on the real constructed evidence objects' final state. No test double of any
kind appears here -- there is nothing external to stand in for: every input is
a file already on disk in this repository.

The load-bearing case is ``resource_flow`` seed ``3979297810``: a trial whose
process conformed at every step and whose model was still wrong about
``dead_end`` and ``solved``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from autofde_lab.hub.domain.gym_procedure.mismatch_evidence import (
    UNMODELED,
    CausalModelError,
    CommitmentIdentity,
    DimensionKind,
    MismatchConstructionError,
    ModelIdentity,
    PredictionMismatch,
    StateDimension,
    UnmodeledDimension,
    causal_model_error_from_trial,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
CROWN1 = REPO_ROOT / "docs" / "evidence" / "crown1"

#: The archived trial carrying the finding. Attempt 7 is the latest archive of
#: seed 3979297810; attempts 4, 5 and 6 carry the identical two mismatches.
RESOURCE_FLOW_TRIAL = (
    CROWN1 / "attempt7" / "realtrial_3979297810_b6977405-e017-4d5f-9cb3-1d0364f136b5"
)

pytestmark = pytest.mark.skipif(
    not RESOURCE_FLOW_TRIAL.is_dir(),
    reason=f"archived crown1 evidence absent: {RESOURCE_FLOW_TRIAL}",
)


def _resource_flow_trials() -> list[Path]:
    return sorted(p for p in CROWN1.glob("attempt*/realtrial_3979297810_*") if p.is_dir())


def _unmodeled_trials() -> list[Path]:
    """Archived trials whose observation carries a dimension the model has
    none of. Discovered by running the real measurement, not hardcoded."""
    out = []
    for trial in sorted(CROWN1.glob("attempt*/realtrial_*")):
        evidence = causal_model_error_from_trial(trial)
        if isinstance(evidence, CausalModelError) and evidence.unmodeled:
            out.append(trial)
    return out


# ── the real finding ──────────────────────────────────────────────────────


def test_resource_flow_3979297810_process_conformed_and_model_was_wrong():
    evidence = causal_model_error_from_trial(RESOURCE_FLOW_TRIAL)
    assert isinstance(evidence, CausalModelError)

    assert evidence.provider == "resource_flow"
    assert evidence.commitment.plan == ("mine", "refine", "assemble", "burn_catalyst")

    # Process leg: zero divergences across all four committed steps.
    assert evidence.per_step_divergences == ((), (), (), ())
    assert evidence.process_conformed is True

    # Model leg: wrong anyway, on exactly two dimensions.
    by_dim = {m.dimension.name: m for m in evidence.mismatches}
    assert sorted(by_dim) == ["dead_end", "solved"]

    assert by_dim["dead_end"].predicted_value is True
    assert by_dim["dead_end"].observed_value is False
    assert by_dim["solved"].predicted_value is False
    assert by_dim["solved"].observed_value is True

    assert by_dim["dead_end"].dimension.kind is DimensionKind.BOOLEAN
    assert by_dim["solved"].dimension.kind is DimensionKind.BOOLEAN


def test_every_mismatch_carries_all_three_identities():
    evidence = causal_model_error_from_trial(RESOURCE_FLOW_TRIAL)
    assert isinstance(evidence, CausalModelError)
    assert evidence.mismatches

    for mismatch in evidence.mismatches:
        assert mismatch.model.digest == "3ac9d7f320c4c633"
        assert mismatch.model.n_probes > 0
        assert mismatch.model.induced_from.endswith("typed_probe_log.json")

        assert mismatch.observation.run_id == "b6977405-e017-4d5f-9cb3-1d0364f136b5"
        assert len(mismatch.observation.ocel_digest) == 64
        assert mismatch.observation.ocel_path.endswith("episode.ocel.json")

        assert mismatch.commitment.plan_digest == "220f81bf978fe490"
        assert mismatch.commitment.commitment_ref.endswith("commitment.ttl")


def test_ocel_digest_matches_the_real_log_reparsed_from_disk():
    """The observation identity is pinned to the durable document, so
    re-parsing that document independently must reproduce the same digest."""
    from autofde_lab.ocel.log import OcelLog
    import json

    evidence = causal_model_error_from_trial(RESOURCE_FLOW_TRIAL)
    assert isinstance(evidence, CausalModelError)

    document = json.loads(Path(evidence.observation.ocel_path).read_text(encoding="utf-8"))
    assert OcelLog.from_ocel2_json(document).digest() == evidence.observation.ocel_digest


def test_the_same_finding_reproduces_across_every_archived_attempt():
    """Four independent archived runs of the same seed, same two mismatches --
    this is a stable property of the induced model, not one flaky episode."""
    seen = []
    for trial in _resource_flow_trials():
        evidence = causal_model_error_from_trial(trial)
        if not isinstance(evidence, CausalModelError):
            continue
        seen.append(
            (
                trial.parent.name,
                tuple(
                    (m.dimension.name, m.predicted_value, m.observed_value)
                    for m in evidence.mismatches
                ),
                evidence.process_conformed,
            )
        )

    assert len(seen) >= 4
    with_mismatch = [row for row in seen if row[1]]
    assert len(with_mismatch) >= 4
    for _attempt, rows, conformed in with_mismatch:
        assert rows == (("dead_end", True, False), ("solved", False, True))
        assert conformed is True


# ── the unmodeled dimension: `reward` ─────────────────────────────────────


def test_reward_constructs_as_unmodeled_and_is_not_a_false_prediction():
    trials = _unmodeled_trials()
    assert trials, "no archived trial carries an unmodeled dimension"

    found = []
    for trial in trials:
        evidence = causal_model_error_from_trial(trial)
        assert isinstance(evidence, CausalModelError)
        for entry in evidence.unmodeled:
            found.append(entry)

            assert isinstance(entry, UnmodeledDimension)
            # It is NOT a mismatch: the type is different, so no consumer
            # matching on PredictionMismatch can pick it up as a wrong value.
            assert not isinstance(entry, PredictionMismatch)

            # There is no slot for a predicted value at all.
            assert not hasattr(entry, "predicted_value")
            assert entry.predicted is UNMODELED
            assert entry.predicted is not None
            assert entry.predicted is not False

            # And it refuses to answer a truth test rather than reading False.
            with pytest.raises(MismatchConstructionError):
                bool(entry.predicted)

            assert entry.status == "UNMODELED"
            assert entry.dimension.name not in entry.modeled_dimensions

    assert {e.dimension.name for e in found} == {"reward"}


def test_unmodeled_dimension_cannot_be_recorded_as_a_prediction_mismatch():
    """The coercion this module exists to block, attempted directly against
    the real identities from a real trial."""
    trial = _unmodeled_trials()[0]
    evidence = causal_model_error_from_trial(trial)
    assert isinstance(evidence, CausalModelError)
    entry = evidence.unmodeled[0]

    with pytest.raises(MismatchConstructionError, match="UNMODELED_IS_NOT_A_MISMATCH"):
        PredictionMismatch(
            dimension=entry.dimension,
            predicted_value=UNMODELED,
            observed_value=entry.observed_value,
            model=entry.model,
            observation=entry.observation,
            commitment=entry.commitment,
        )


def test_a_modeled_dimension_cannot_be_relabelled_unmodeled():
    """The inverse coercion: understating the model's error by filing a real
    wrong prediction as an absent representation."""
    evidence = causal_model_error_from_trial(RESOURCE_FLOW_TRIAL)
    assert isinstance(evidence, CausalModelError)
    solved = next(m for m in evidence.mismatches if m.dimension.name == "solved")

    with pytest.raises(MismatchConstructionError, match="DIMENSION_IS_MODELED"):
        UnmodeledDimension(
            dimension=solved.dimension,
            observed_value=solved.observed_value,
            model=solved.model,
            observation=solved.observation,
            commitment=solved.commitment,
            modeled_dimensions=evidence.predicted_state.modeled_dimensions,
        )


# ── the type surface refuses booleans ─────────────────────────────────────


def test_no_type_here_exposes_a_boolean_verdict_field():
    """No ``prediction_correct`` / ``matched`` / ``ok`` / ``accurate`` field,
    and no ``__bool__`` on any evidence type."""
    banned = {"prediction_correct", "matched", "ok", "accurate", "correct", "agrees", "valid"}
    evidence = causal_model_error_from_trial(RESOURCE_FLOW_TRIAL)
    assert isinstance(evidence, CausalModelError)

    subjects = [
        evidence,
        evidence.predicted_state,
        evidence.observed_state,
        evidence.model,
        evidence.observation,
        evidence.commitment,
        *evidence.mismatches,
    ]
    for subject in subjects:
        names = set(dir(subject))
        assert not (names & banned), f"{type(subject).__name__} exposes {names & banned}"
        # No evidence type defines its own __bool__: `if evidence:` must never
        # compile to a verdict, exactly as CrownFactor denies `if factor:`.
        assert "__bool__" not in vars(type(subject))


def test_predicted_state_reports_unmodeled_rather_than_none():
    evidence = causal_model_error_from_trial(_unmodeled_trials()[0])
    assert isinstance(evidence, CausalModelError)
    assert evidence.predicted_state.models("reward") is False
    assert evidence.predicted_state.predicted("reward") is UNMODELED


def test_mismatch_refuses_to_record_an_agreement():
    evidence = causal_model_error_from_trial(RESOURCE_FLOW_TRIAL)
    assert isinstance(evidence, CausalModelError)
    solved = next(m for m in evidence.mismatches if m.dimension.name == "solved")

    with pytest.raises(MismatchConstructionError, match="MISMATCH_REQUIRES_DISAGREEMENT"):
        PredictionMismatch(
            dimension=solved.dimension,
            predicted_value=True,
            observed_value=True,
            model=solved.model,
            observation=solved.observation,
            commitment=solved.commitment,
        )


def test_identities_are_mandatory_and_typed():
    evidence = causal_model_error_from_trial(RESOURCE_FLOW_TRIAL)
    assert isinstance(evidence, CausalModelError)
    solved = next(m for m in evidence.mismatches if m.dimension.name == "solved")

    with pytest.raises(MismatchConstructionError, match="MISMATCH_REQUIRES_MODEL_IDENTITY"):
        PredictionMismatch(
            dimension=solved.dimension,
            predicted_value=False,
            observed_value=True,
            model="3ac9d7f320c4c633",  # a bare string is not an identity
            observation=solved.observation,
            commitment=solved.commitment,
        )

    with pytest.raises(MismatchConstructionError, match="MODEL_IDENTITY_REQUIRES_OBSERVATION"):
        ModelIdentity(digest="3ac9d7f320c4c633", induced_from="x", n_probes=0)

    with pytest.raises(MismatchConstructionError, match="COMMITMENT_IDENTITY_REQUIRES_PLAN"):
        CommitmentIdentity(plan=(), plan_digest="220f81bf978fe490", commitment_ref="x")

    with pytest.raises(MismatchConstructionError, match="STATE_DIMENSION_REQUIRES_TYPED_KIND"):
        StateDimension(name="solved", kind="BOOLEAN")


def test_absent_trial_is_unknown_not_an_empty_agreement():
    from autofde_lab.hub.domain.gym_procedure.dogfood import Unknown

    result = causal_model_error_from_trial(CROWN1 / "no_such_trial_directory")
    assert isinstance(result, Unknown)
    assert result.status == "UNKNOWN"
    assert result.absent
