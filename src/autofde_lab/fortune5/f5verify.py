"""Independent command-line verifier for TTF5-AR readiness submissions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .readiness import F5ReadinessVerifier, GateEvidence, ReadinessSubmission


def _submission(payload: dict[str, object]) -> ReadinessSubmission:
    raw_evidence = payload.get("evidence")
    if not isinstance(raw_evidence, list):
        raise ValueError("REFUSED:EVIDENCE_LIST_REQUIRED")
    evidence = tuple(
        GateEvidence(
            gate=str(item["gate"]),
            decision=str(item["decision"]),
            evidence_digest=str(item["evidence_digest"]),
            subject_digest=str(item["subject_digest"]),
        )
        for item in raw_evidence
        if isinstance(item, dict)
    )
    if len(evidence) != len(raw_evidence):
        raise ValueError("REFUSED:INVALID_EVIDENCE_ENTRY")
    return ReadinessSubmission(
        benchmark_id=str(payload["benchmark_id"]),
        benchmark_version=str(payload["benchmark_version"]),
        scenario_digest=str(payload["scenario_digest"]),
        admitted_observation_digest=str(payload["admitted_observation_digest"]),
        reference_profile_digest=str(payload["reference_profile_digest"]),
        subject_digest=str(payload["subject_digest"]),
        started_at_ns=int(payload["started_at_ns"]),
        submitted_at_ns=int(payload["submitted_at_ns"]),
        evidence=evidence,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify one TTF5-AR submission")
    parser.add_argument("input", type=Path)
    parser.add_argument("--verified-at-ns", required=True, type=int)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    payload = json.loads(args.input.read_text())
    if not isinstance(payload, dict):
        raise ValueError("REFUSED:SUBMISSION_OBJECT_REQUIRED")
    verifier = F5ReadinessVerifier()
    witness = verifier.verify(_submission(payload), verified_at_ns=args.verified_at_ns)
    rendered = json.dumps(witness.canonical(), sort_keys=True, separators=(",", ":"))
    if args.output is not None:
        args.output.write_text(rendered + "\n")
    else:
        print(rendered)
    return 0 if witness.ready else 3


if __name__ == "__main__":
    raise SystemExit(main())
