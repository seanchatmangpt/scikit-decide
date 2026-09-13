from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from autofde_lab.fortune5.f5bench import (
    BenchmarkMutation,
    architecture_optionality_density,
    verify_resynchronization,
)
from autofde_lab.fortune5.readiness import (
    REQUIRED_GATES,
    F5ReadinessVerifier,
    build_submission,
    evidence_digest,
    failure_rate,
)

SCENARIO = "1" * 64
OBSERVATION = "2" * 64


def pass_evidence(prefix: str) -> dict[str, tuple[str, str]]:
    return {
        gate: ("PASS", evidence_digest({"gate": gate, "witness": f"{prefix}:{gate}"}))
        for gate in REQUIRED_GATES
    }


def ready_submission(
    *, start: int = 100, submitted: int = 160, observation: str = OBSERVATION
):
    return build_submission(
        benchmark_id="F5Bench-10K",
        benchmark_version="1",
        scenario_digest=SCENARIO,
        admitted_observation_digest=observation,
        started_at_ns=start,
        submitted_at_ns=submitted,
        evidence_by_gate=pass_evidence(observation),
    )


def test_conjunctive_readiness_stops_clock_only_after_external_verification() -> None:
    verifier = F5ReadinessVerifier()
    submission = ready_submission()
    witness = verifier.verify(submission, verified_at_ns=175)
    assert witness.ready
    assert witness.technical_standing == "ALIVE"
    assert witness.ttf5_ns == 75
    assert witness.evidence_coverage_ratio == 1.0
    assert not witness.failed_gates
    assert verifier.replay(submission, witness) == witness


def test_one_failed_gate_cannot_be_compensated_by_eleven_passes() -> None:
    evidence = pass_evidence("failed-security")
    evidence["security"] = ("FAIL", evidence_digest({"security": "failed"}))
    submission = build_submission(
        benchmark_id="F5Bench-10K",
        benchmark_version="1",
        scenario_digest=SCENARIO,
        admitted_observation_digest=OBSERVATION,
        started_at_ns=0,
        submitted_at_ns=10,
        evidence_by_gate=evidence,
    )
    witness = F5ReadinessVerifier().verify(submission, verified_at_ns=12)
    assert not witness.ready
    assert witness.ttf5_ns is None
    assert witness.failed_gates == ("security",)
    assert witness.evidence_coverage_ratio == 1.0


def test_missing_gate_is_not_admitted_as_pass() -> None:
    evidence = pass_evidence("missing")
    del evidence["evidence"]
    submission = build_submission(
        benchmark_id="F5Bench-10K",
        benchmark_version="1",
        scenario_digest=SCENARIO,
        admitted_observation_digest=OBSERVATION,
        started_at_ns=0,
        submitted_at_ns=10,
        evidence_by_gate=evidence,
    )
    witness = F5ReadinessVerifier().verify(submission, verified_at_ns=11)
    assert witness.missing_gates == ("evidence",)
    assert witness.evidence_coverage_ratio == 11 / 12
    assert not witness.ready


def test_evidence_is_exact_subject_bound() -> None:
    submission = ready_submission()
    item = submission.evidence[0]
    with pytest.raises(ValueError, match="GATE_EVIDENCE_SUBJECT_MISMATCH"):
        type(submission)(
            benchmark_id=submission.benchmark_id,
            benchmark_version=submission.benchmark_version,
            scenario_digest=submission.scenario_digest,
            admitted_observation_digest=submission.admitted_observation_digest,
            reference_profile_digest=submission.reference_profile_digest,
            subject_digest=submission.subject_digest,
            started_at_ns=submission.started_at_ns,
            submitted_at_ns=submission.submitted_at_ns,
            evidence=(
                type(item)(item.gate, item.decision, item.evidence_digest, "f" * 64),
            )
            + submission.evidence[1:],
        )


def test_resynchronization_clock_begins_at_observed_mutation() -> None:
    verifier = F5ReadinessVerifier()
    first = ready_submission(start=100, submitted=120)
    previous = verifier.verify(first, verified_at_ns=130)
    mutated = ready_submission(start=200, submitted=230, observation="3" * 64)
    mutation = BenchmarkMutation.observed(
        mutation_kind="REGULATORY_CHANGE",
        pre_subject_digest=previous.subject_digest,
        post_subject_digest=mutated.subject_digest,
        occurred_at_ns=200,
        evidence={"regulation": "v2"},
    )
    result = verify_resynchronization(
        previous=previous,
        mutation=mutation,
        submission=mutated,
        verifier=verifier,
        verified_at_ns=260,
    )
    assert result.resynchronized
    assert result.tt_delta_ea_ns == 60
    assert result.binary_architecture_synchronization_debt_ns == 60


def test_resynchronization_refuses_subject_smuggling() -> None:
    verifier = F5ReadinessVerifier()
    first = ready_submission(start=100, submitted=120)
    previous = verifier.verify(first, verified_at_ns=130)
    mutated = ready_submission(start=200, submitted=230, observation="3" * 64)
    mutation = BenchmarkMutation.observed(
        mutation_kind="M_AND_A",
        pre_subject_digest=previous.subject_digest,
        post_subject_digest="4" * 64,
        occurred_at_ns=200,
        evidence={"deal": "observed"},
    )
    with pytest.raises(ValueError, match="MUTATION_POST_SUBJECT_MISMATCH"):
        verify_resynchronization(
            previous=previous,
            mutation=mutation,
            submission=mutated,
            verifier=verifier,
            verified_at_ns=260,
        )


def test_derived_metric_family_is_bounded_and_nonvacuous() -> None:
    verifier = F5ReadinessVerifier()
    good = verifier.verify(ready_submission(), verified_at_ns=175)
    evidence = pass_evidence("bad")
    evidence["technology"] = ("FAIL", evidence_digest({"technology": "bad"}))
    bad_submission = build_submission(
        benchmark_id="F5Bench-10K",
        benchmark_version="1",
        scenario_digest=SCENARIO,
        admitted_observation_digest=OBSERVATION,
        started_at_ns=100,
        submitted_at_ns=160,
        evidence_by_gate=evidence,
    )
    bad = verifier.verify(bad_submission, verified_at_ns=175)
    assert failure_rate((good, bad)) == 0.5
    assert (
        architecture_optionality_density(
            lawful_verified_alternatives=1605, irreversible_decisions=1
        )
        == 802.5
    )


def test_independent_cli_reads_real_file_and_writes_machine_witness(
    tmp_path: Path,
) -> None:
    submission = ready_submission()
    input_path = tmp_path / "submission.json"
    output_path = tmp_path / "witness.json"
    input_path.write_text(
        json.dumps(
            {
                "benchmark_id": submission.benchmark_id,
                "benchmark_version": submission.benchmark_version,
                "scenario_digest": submission.scenario_digest,
                "admitted_observation_digest": submission.admitted_observation_digest,
                "reference_profile_digest": submission.reference_profile_digest,
                "subject_digest": submission.subject_digest,
                "started_at_ns": submission.started_at_ns,
                "submitted_at_ns": submission.submitted_at_ns,
                "evidence": [item.canonical() for item in submission.evidence],
            }
        )
    )
    env = os.environ.copy()
    repo_root = Path(__file__).parents[2]
    env["PYTHONPATH"] = str(repo_root / "src")
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "autofde_lab.fortune5.f5verify",
            str(input_path),
            "--verified-at-ns",
            "175",
            "--output",
            str(output_path),
        ],
        cwd=repo_root,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    witness = json.loads(output_path.read_text())
    assert witness["technical_standing"] == "ALIVE"
    assert witness["ttf5_ns"] == 75
    assert len(witness["witness_digest"]) == 64
