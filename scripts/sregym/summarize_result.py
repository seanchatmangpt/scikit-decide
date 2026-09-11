from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def _bool(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"true", "1", "yes"}


def _float(value: str | None) -> float | None:
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def summarize(csv_path: Path, *, subject: dict[str, str]) -> dict:
    with csv_path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 1:
        raise ValueError(f"expected exactly one SREGym attempt row, got {len(rows)}")
    row = rows[0]
    diagnosis = _bool(row.get("Diagnosis.success"))
    mitigation = _bool(row.get("Mitigation.success"))
    deploy_failed = _bool(row.get("deploy_failed"))
    return {
        "schema": "urn:autofde-lab:sregym-episode-summary:v1",
        "subject": subject,
        "problem_id": row.get("problem_id") or subject.get("problem_id"),
        "attempt": int(row.get("attempt") or 1),
        "diagnosis_success": diagnosis,
        "mitigation_success": mitigation,
        "e2e_success": diagnosis and mitigation and not deploy_failed,
        "deploy_failed": deploy_failed,
        "ttl_seconds": _float(row.get("TTL")),
        "ttm_seconds": _float(row.get("TTM")),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--autofde-head", required=True)
    parser.add_argument("--sregym-head", required=True)
    parser.add_argument("--problem-id", required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--signature-revision", required=True)
    args = parser.parse_args()

    payload = summarize(
        args.csv,
        subject={
            "autofde_head": args.autofde_head,
            "sregym_head": args.sregym_head,
            "problem_id": args.problem_id,
            "model_id": args.model_id,
            "signature_revision": args.signature_revision,
        },
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()
