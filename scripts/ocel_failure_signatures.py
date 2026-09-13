#!/usr/bin/env python3
"""Proactive failure-signature detector over the SREGym batch's per-problem
OCEL 2.0 SQLite logs.

Companion to ``scripts/ocel_procint_report.py`` (bottleneck ranking); reuses
its file-discovery pattern (``glob`` over ``docs/ocel/sregym/*.ocel2.sqlite``,
``problem_id`` derived from the filename) but answers a different question.
The bottleneck report tells you *what was slow*; this script tells you *what
is repeating* -- the same kubectl error, the same generic non-answer, the
same "gave up before doing any real diagnosis" pattern -- across multiple
independent trials, so a recurring bug in the agent's own tool-calling path
surfaces without anyone having to read logs one at a time after the fact.

Unlike ``ocel_procint_report.py`` (which reads the SQLite schema directly
with plain SQL), this script goes through the real
``autofde_lab.ocel.sqlite_store.from_sqlite`` loader, since it needs the
full ordered event list (activity + attributes) per trial rather than
aggregate SQL, and that loader already reconstructs exactly that shape as a
real ``OcelLog``.

Three signature families detected, each named for a real defect class:

1. ``kubectl_error:<verb> <noun>:<error class>`` -- the same kubectl
   subcommand failing with the same exception type across >=2 trials (a
   real infra/tooling problem, not one flaky run).
2. ``generic_non_answer`` -- the trial's final ``submit`` event's ``detail``
   text collapses (after normalization) to one of a small set of known
   non-diagnoses ("no anomaly detected", "unable to determine", "unknown
   issue", ...) that carries no case-specific information.
3. ``zero_kubectl_before_submit`` -- the trial reached ``submit`` having
   issued zero kubectl-family events first. Found live in this session with
   the DSPy agent: an early warning sign of a broken tool-calling path (the
   agent believes it investigated but no tool call actually happened), not
   a real diagnosis attempt -- and, unlike (1) and (2), a single occurrence
   is already worth flagging, since it always indicates the same defect
   class regardless of how many trials share it.

Usage:
    .venv/bin/python scripts/ocel_failure_signatures.py [--dir DOCS_OCEL_DIR]
"""

from __future__ import annotations

import argparse
import glob
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from autofde_lab.ocel.sqlite_store import from_sqlite

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DIR = REPO_ROOT / "docs" / "ocel" / "sregym"

#: Kubectl-family activities are recorded as `"<verb> <noun>"` (e.g. "kubectl
#: get", "kubectl describe") by the real driver's
#: `_record_kubectl_event`/`_record_event` (see
#: `vendor/gyms/sregym/clients/autofde_lab_planner/driver.py`); "submit" is
#: the one non-kubectl activity every trial ends with.
NON_KUBECTL_ACTIVITIES = {"submit"}

#: Normalized (lowercased, whitespace-collapsed) generic non-answer strings.
#: A `submit` detail that equals one of these (after normalization) carries
#: zero case-specific information -- it is the same non-diagnosis regardless
#: of which problem produced it.
GENERIC_NON_ANSWERS = {
    "no anomaly detected",
    "no anomaly detected.",
    "unable to determine root cause",
    "unable to determine the root cause",
    "unknown issue",
    "unknown error",
    "no issue found",
    "no issues found",
    "unable to diagnose",
    "unable to diagnose the issue",
    "cannot determine root cause",
    "no root cause identified",
}

_WS_RE = re.compile(r"\s+")


def _normalize(text: str) -> str:
    return _WS_RE.sub(" ", text.strip().lower()).rstrip(".")


def _attr_dict(attributes) -> dict[str, Any]:
    """Project an ``OcelEvent.attributes`` tuple of ``OcelAttribute`` into a
    plain ``{key: value}`` dict -- the same flattening
    ``ocel_procint_report.py`` does at the SQL layer, done here at the
    ``OcelLog`` object layer instead."""
    return {attr.key: attr.value.value for attr in attributes}


def _problem_id_from_path(path: Path) -> str:
    return path.name.removesuffix(".ocel2.sqlite")


def _error_class(detail: str | None) -> str:
    """First `ExceptionClassName:` token of an ERROR event's detail, or the
    whole (truncated) detail if no such token is present -- the real driver
    records errors as ``f"{type(exc).__name__}: {exc}"`` (see
    ``driver.py``'s ``call_kubectl``), so this recovers the exception class
    without needing to import that module."""
    if not detail:
        return "<no detail>"
    head = detail.split(":", 1)[0].strip()
    return head if head else detail[:40]


def extract_trial(path: Path) -> dict[str, Any]:
    """Load one trial's real OCEL log and pull out exactly what failure-
    signature detection needs: the ordered activity sequence, every
    ``standing=ERROR`` event (activity + normalized error class + raw
    detail), and the final ``submit`` event's detail text (if any)."""
    log = from_sqlite(path)
    events = sorted(log.events, key=lambda e: e.timestamp_ns)

    activities: list[str] = []
    errors: list[dict[str, str]] = []
    submit_detail: str | None = None
    kubectl_before_submit = 0
    seen_submit = False

    for event in events:
        attrs = _attr_dict(event.attributes)
        activities.append(event.activity)

        if not seen_submit and event.activity not in NON_KUBECTL_ACTIVITIES:
            kubectl_before_submit += 1

        standing = attrs.get("standing")
        if standing == "ERROR":
            detail = attrs.get("detail")
            errors.append(
                {
                    "activity": event.activity,
                    "error_class": _error_class(detail),
                    "detail": detail or "",
                }
            )

        if event.activity == "submit" and not seen_submit:
            seen_submit = True
            submit_detail = attrs.get("detail")

    return {
        "problem_id": _problem_id_from_path(path),
        "path": str(path),
        "activities": activities,
        "errors": errors,
        "submit_detail": submit_detail,
        "kubectl_before_submit": kubectl_before_submit,
        "submitted": submit_detail is not None or "submit" in activities,
    }


def detect_signatures(trials: list[dict[str, Any]]) -> dict[str, Any]:
    """Group ``trials`` (as produced by :func:`extract_trial`) by the three
    real failure-signature families described in the module docstring.

    Returns a dict with one key per family, each a list of signature groups
    -- ``{"signature": ..., "trial_count": ..., "problem_ids": [...],
    "excerpt": ...}`` -- containing only groups that actually recurred
    (``trial_count >= 2``) for families 1 and 2, and every occurrence for
    family 3 (a single occurrence is already the finding).
    """
    kubectl_error_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    non_answer_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    zero_kubectl_trials: list[dict[str, Any]] = []

    for trial in trials:
        for err in trial["errors"]:
            signature = f"kubectl_error:{err['activity']}:{err['error_class']}"
            kubectl_error_groups[signature].append(
                {"problem_id": trial["problem_id"], "excerpt": err["detail"][:200]}
            )

        detail = trial["submit_detail"]
        if detail:
            normalized = _normalize(detail)
            if normalized in GENERIC_NON_ANSWERS:
                non_answer_groups[normalized].append(
                    {"problem_id": trial["problem_id"], "excerpt": detail[:200]}
                )

        if trial["submitted"] and trial["kubectl_before_submit"] == 0:
            zero_kubectl_trials.append(
                {
                    "problem_id": trial["problem_id"],
                    "excerpt": (trial["submit_detail"] or "")[:200],
                }
            )

    def _finalize(groups: dict[str, list[dict[str, Any]]], min_count: int) -> list[dict[str, Any]]:
        out = []
        for signature, members in groups.items():
            if len(members) < min_count:
                continue
            out.append(
                {
                    "signature": signature,
                    "trial_count": len(members),
                    "problem_ids": [m["problem_id"] for m in members],
                    "excerpt": members[0]["excerpt"],
                }
            )
        out.sort(key=lambda g: g["trial_count"], reverse=True)
        return out

    zero_kubectl_report = [
        {
            "signature": "zero_kubectl_before_submit",
            "trial_count": len(zero_kubectl_trials),
            "problem_ids": [m["problem_id"] for m in zero_kubectl_trials],
            "excerpt": zero_kubectl_trials[0]["excerpt"] if zero_kubectl_trials else "",
        }
    ] if zero_kubectl_trials else []

    return {
        "kubectl_error_recurrences": _finalize(kubectl_error_groups, min_count=2),
        "generic_non_answer_recurrences": _finalize(non_answer_groups, min_count=2),
        "zero_kubectl_before_submit": zero_kubectl_report,
    }


def build_report(ocel_dir: Path) -> dict[str, Any]:
    db_paths = sorted(Path(p) for p in glob.glob(str(ocel_dir / "*.ocel2.sqlite")))
    trials = [extract_trial(p) for p in db_paths]
    signatures = detect_signatures(trials)
    return {
        "ocel_dir": str(ocel_dir),
        "trials_analyzed": len(trials),
        **signatures,
    }


def _print_group(title: str, groups: list[dict[str, Any]]) -> None:
    print(f"\n{title}:")
    if not groups:
        print("  (none recurring)")
        return
    for group in groups:
        print(f"  [{group['trial_count']}x] {group['signature']}")
        print(f"    problem_ids: {', '.join(group['problem_ids'])}")
        excerpt = group["excerpt"].replace("\n", " ")
        print(f"    excerpt: {excerpt[:160]}")


def _print_report(report: dict[str, Any]) -> None:
    print(f"OCEL failure-signature report -- {report['ocel_dir']}")
    print(f"Trials analyzed: {report['trials_analyzed']}")

    if not report["trials_analyzed"]:
        print("(no .ocel2.sqlite files yet -- report is empty, not an error)")
        return

    _print_group("Recurring kubectl errors (same command + error class, >=2 trials)", report["kubectl_error_recurrences"])
    _print_group("Recurring generic non-answers (>=2 trials)", report["generic_non_answer_recurrences"])
    _print_group("Zero kubectl events before submit (each occurrence flagged)", report["zero_kubectl_before_submit"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", type=Path, default=DEFAULT_DIR, help="Directory of .ocel2.sqlite files")
    parser.add_argument("--json", action="store_true", help="Print raw JSON instead of a table")
    args = parser.parse_args()

    report = build_report(args.dir)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        _print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
