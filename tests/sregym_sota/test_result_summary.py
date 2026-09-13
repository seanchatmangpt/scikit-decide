from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REVISION = "SRE-SIG-003"


def test_result_summary_uses_only_sregym_grader_fields(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[2]
    script = repo / "scripts" / "sregym" / "summarize_result.py"
    source = tmp_path / "result.csv"
    output = tmp_path / "summary.json"
    source.write_text(
        "Diagnosis.success,Mitigation.success,TTL,TTM,attempt,problem_id\n"
        "True,True,12.5,25.0,1,problem-a\n"
    )
    subprocess.run(
        [
            sys.executable,
            str(script),
            str(source),
            "--output",
            str(output),
            "--autofde-head",
            "a" * 40,
            "--sregym-head",
            "b" * 40,
            "--problem-id",
            "problem-a",
            "--model-id",
            "model",
            "--signature-revision",
            REVISION,
        ],
        check=True,
    )
    payload = json.loads(output.read_text())
    assert payload["diagnosis_success"] is True
    assert payload["mitigation_success"] is True
    assert payload["e2e_success"] is True
    assert payload["ttl_seconds"] == 12.5
    assert payload["ttm_seconds"] == 25.0
    assert payload["subject"]["autofde_head"] == "a" * 40
    assert payload["subject"]["sregym_head"] == "b" * 40
    assert payload["subject"]["signature_revision"] == REVISION


def test_result_summary_refuses_missing_attempt_row(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[2]
    script = repo / "scripts" / "sregym" / "summarize_result.py"
    source = tmp_path / "result.csv"
    output = tmp_path / "summary.json"
    source.write_text("Diagnosis.success,Mitigation.success,attempt,problem_id\n")
    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            str(source),
            "--output",
            str(output),
            "--autofde-head",
            "a" * 40,
            "--sregym-head",
            "b" * 40,
            "--problem-id",
            "problem-a",
            "--model-id",
            "model",
            "--signature-revision",
            REVISION,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    assert not output.exists()
