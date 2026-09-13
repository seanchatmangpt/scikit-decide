# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style test: scripts/ocel_failure_signatures.py against real
`.ocel2.sqlite` fixtures built with the real recording path.

Real components throughout: real `OcelSessionRecorder` objects, real
`record_and_flush` calls (the same function
`vendor/gyms/sregym/clients/autofde_lab_planner/driver.py`'s
`_record_event`/`_record_kubectl_event` call live during an actual SREGym
trial), real SQLite files written to `tmp_path`, and the script's own real
`from_sqlite`-backed `extract_trial`/`detect_signatures`/`build_report`
functions run against those files. No mocks anywhere in this module --
every fixture is a real OCEL 2.0 log, on real disk, read back by the real
loader.

Never touches `docs/ocel/sregym/` (the real accumulated trial data) or
`vendor/gyms/sregym/` -- every fixture lives under `tmp_path`.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

from autofde_lab.ocel.live_flush import record_and_flush
from autofde_lab.ocel.mcp_instrumentation import OcelSessionRecorder

import ocel_failure_signatures as fsig


def _write_trial(
    path: Path,
    *,
    session_id: str,
    problem_id: str,
    events: list[tuple[str, dict]],
) -> None:
    """Build one real trial's OCEL log the same way the real driver does:
    one `record_and_flush` call per event, each a real append + real SQLite
    overwrite -- not a single bulk write."""
    recorder = OcelSessionRecorder(session_id)
    recorder.ensure_object(f"problem-{problem_id}", "Problem")
    for activity, outcome in events:
        record_and_flush(
            recorder,
            activity=activity,
            objects=[(f"problem-{problem_id}", "Problem")],
            outcome=outcome,
            path=path,
        )


def test_recurring_kubectl_error_signature_is_detected_across_trials(tmp_path):
    # Two trials hit the exact same kubectl failure (same command prefix,
    # same exception class); a third trial has a real, different error --
    # must not be folded into the recurring group.
    _write_trial(
        tmp_path / "problem-a.ocel2.sqlite",
        session_id="sess-a",
        problem_id="problem-a",
        events=[
            (
                "kubectl get",
                {
                    "standing": "ERROR",
                    "elapsed_s": 0.4,
                    "detail": "TimeoutError: kubectl get pods -n prod timed out after 30s",
                },
            ),
            ("kubectl describe", {"standing": "COMPLETED", "elapsed_s": 0.2}),
            ("submit", {"standing": "COMPLETED", "elapsed_s": 0.1, "detail": "root cause is the misconfigured probe"}),
        ],
    )
    _write_trial(
        tmp_path / "problem-b.ocel2.sqlite",
        session_id="sess-b",
        problem_id="problem-b",
        events=[
            (
                "kubectl get",
                {
                    "standing": "ERROR",
                    "elapsed_s": 0.5,
                    "detail": "TimeoutError: kubectl get pods -n staging timed out after 30s",
                },
            ),
            ("submit", {"standing": "COMPLETED", "elapsed_s": 0.1, "detail": "ingress targetPort mismatch"}),
        ],
    )
    _write_trial(
        tmp_path / "problem-c.ocel2.sqlite",
        session_id="sess-c",
        problem_id="problem-c",
        events=[
            (
                "kubectl apply",
                {
                    "standing": "ERROR",
                    "elapsed_s": 0.3,
                    "detail": "ValueError: invalid manifest",
                },
            ),
            ("submit", {"standing": "COMPLETED", "elapsed_s": 0.1, "detail": "cronjob schedule was mutated"}),
        ],
    )

    report = fsig.build_report(tmp_path)

    assert report["trials_analyzed"] == 3
    recurring = report["kubectl_error_recurrences"]
    assert len(recurring) == 1
    group = recurring[0]
    assert group["signature"] == "kubectl_error:kubectl get:TimeoutError"
    assert group["trial_count"] == 2
    assert set(group["problem_ids"]) == {"problem-a", "problem-b"}
    assert "TimeoutError" in group["excerpt"]

    # The genuinely different error must not appear in the recurring report
    # at all (min_count=2, and it shares no signature with anything else).
    signatures = {g["signature"] for g in recurring}
    assert "kubectl_error:kubectl apply:ValueError" not in signatures


def test_recurring_generic_non_answer_is_detected_across_trials(tmp_path):
    _write_trial(
        tmp_path / "problem-d.ocel2.sqlite",
        session_id="sess-d",
        problem_id="problem-d",
        events=[
            ("kubectl get", {"standing": "COMPLETED", "elapsed_s": 0.2}),
            ("submit", {"standing": "COMPLETED", "elapsed_s": 0.1, "detail": "No anomaly detected."}),
        ],
    )
    _write_trial(
        tmp_path / "problem-e.ocel2.sqlite",
        session_id="sess-e",
        problem_id="problem-e",
        events=[
            ("kubectl describe", {"standing": "COMPLETED", "elapsed_s": 0.2}),
            ("submit", {"standing": "COMPLETED", "elapsed_s": 0.1, "detail": "  No Anomaly Detected  "}),
        ],
    )
    _write_trial(
        tmp_path / "problem-f.ocel2.sqlite",
        session_id="sess-f",
        problem_id="problem-f",
        events=[
            ("kubectl get", {"standing": "COMPLETED", "elapsed_s": 0.2}),
            ("submit", {"standing": "COMPLETED", "elapsed_s": 0.1, "detail": "the readiness probe path is wrong, fix it"}),
        ],
    )

    report = fsig.build_report(tmp_path)

    assert report["trials_analyzed"] == 3
    recurring = report["generic_non_answer_recurrences"]
    assert len(recurring) == 1
    group = recurring[0]
    assert group["signature"] == "no anomaly detected"
    assert group["trial_count"] == 2
    assert set(group["problem_ids"]) == {"problem-d", "problem-e"}


def test_zero_kubectl_before_submit_is_flagged_even_once(tmp_path):
    # The exact live bug this session: an agent reaches `submit` having
    # issued zero real kubectl calls first -- flagged even as a single
    # occurrence, unlike the other two families' >=2 threshold.
    _write_trial(
        tmp_path / "problem-g.ocel2.sqlite",
        session_id="sess-g",
        problem_id="problem-g",
        events=[
            ("submit", {"standing": "COMPLETED", "elapsed_s": 0.1, "detail": "the deployment has a bad image tag"}),
        ],
    )
    _write_trial(
        tmp_path / "problem-h.ocel2.sqlite",
        session_id="sess-h",
        problem_id="problem-h",
        events=[
            ("kubectl get", {"standing": "COMPLETED", "elapsed_s": 0.2}),
            ("submit", {"standing": "COMPLETED", "elapsed_s": 0.1, "detail": "real diagnosis after real investigation"}),
        ],
    )

    report = fsig.build_report(tmp_path)

    assert report["trials_analyzed"] == 2
    flagged = report["zero_kubectl_before_submit"]
    assert len(flagged) == 1
    assert flagged[0]["trial_count"] == 1
    assert flagged[0]["problem_ids"] == ["problem-g"]
    # The trial with a real kubectl call before submit must not appear.
    assert "problem-h" not in flagged[0]["problem_ids"]


def test_extract_trial_reads_real_activities_errors_and_submit_detail(tmp_path):
    path = tmp_path / "problem-i.ocel2.sqlite"
    _write_trial(
        path,
        session_id="sess-i",
        problem_id="problem-i",
        events=[
            ("kubectl get", {"standing": "COMPLETED", "elapsed_s": 0.1}),
            (
                "kubectl logs",
                {"standing": "ERROR", "elapsed_s": 0.2, "detail": "ConnectionError: refused"},
            ),
            ("submit", {"standing": "COMPLETED", "elapsed_s": 0.05, "detail": "final answer text"}),
        ],
    )

    trial = fsig.extract_trial(path)

    assert trial["problem_id"] == "problem-i"
    assert trial["activities"] == ["kubectl get", "kubectl logs", "submit"]
    assert len(trial["errors"]) == 1
    assert trial["errors"][0]["error_class"] == "ConnectionError"
    assert trial["submit_detail"] == "final answer text"
    assert trial["kubectl_before_submit"] == 2
    assert trial["submitted"] is True


def test_empty_directory_produces_an_empty_not_erroring_report(tmp_path):
    report = fsig.build_report(tmp_path)
    assert report["trials_analyzed"] == 0
    assert report["kubectl_error_recurrences"] == []
    assert report["generic_non_answer_recurrences"] == []
    assert report["zero_kubectl_before_submit"] == []
