#!/usr/bin/env python3
"""Real, cross-problem process-intelligence report over the SREGym batch's
per-problem OCEL 2.0 SQLite logs.

Each problem in the batch (`scripts/run_representative_sample.sh`) writes its
own `docs/ocel/sregym/<problem_id>.ocel2.sqlite` -- one MCPSession object per
file, flushed live via `autofde_lab.ocel.live_flush.record_and_flush` as the
trial's own `driver.py` runs (see
`vendor/gyms/sregym/clients/autofde_lab_planner/driver.py`'s
`call_kubectl`/`submit` instrumentation). This script reads every such file
directly with plain SQL -- the same schema-level query style as
`src/autofde_lab/ocel/queries.py` -- and aggregates real `elapsed_s`/
`standing` event attributes across the whole batch.

Runnable at ANY point mid-batch (files that don't exist yet are simply
absent from the report -- not an error) and again after the batch completes
for the final report.

Usage:
    .venv/bin/python scripts/ocel_procint_report.py [--dir DOCS_OCEL_DIR]
"""

from __future__ import annotations

import argparse
import glob
import json
import sqlite3
import statistics
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DIR = REPO_ROOT / "docs" / "ocel" / "sregym"


def _events_with_attrs(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT id, activity, timestamp_ns FROM events ORDER BY timestamp_ns").fetchall()
    out = []
    for event_id, activity, ts_ns in rows:
        attr_rows = conn.execute(
            "SELECT key, value_json FROM attributes WHERE owner_table='event' AND owner_id=?",
            (event_id,),
        ).fetchall()
        attrs = {key: json.loads(value_json) for key, value_json in attr_rows}
        out.append({"id": event_id, "activity": activity, "timestamp_ns": ts_ns, **attrs})
    return out


def _problem_id_from_path(path: Path) -> str:
    return path.name.removesuffix(".ocel2.sqlite")


def build_report(ocel_dir: Path) -> dict:
    db_paths = sorted(Path(p) for p in glob.glob(str(ocel_dir / "*.ocel2.sqlite")))

    per_problem: list[dict] = []
    activity_elapsed: dict[str, list[float]] = {}
    activity_standings: dict[str, dict[str, int]] = {}

    for db_path in db_paths:
        problem_id = _problem_id_from_path(db_path)
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = None
        try:
            events = _events_with_attrs(conn)
        finally:
            conn.close()

        total_elapsed = sum(e.get("elapsed_s", 0.0) for e in events)
        error_count = sum(1 for e in events if e.get("standing") == "ERROR")
        submit_events = [e for e in events if e["activity"] == "submit"]

        per_problem.append(
            {
                "problem_id": problem_id,
                "event_count": len(events),
                "total_kubectl_elapsed_s": round(total_elapsed, 2),
                "error_count": error_count,
                "submitted": len(submit_events) > 0,
            }
        )

        for e in events:
            activity_elapsed.setdefault(e["activity"], []).append(float(e.get("elapsed_s", 0.0)))
            standing = str(e.get("standing", "UNKNOWN"))
            activity_standings.setdefault(e["activity"], {}).setdefault(standing, 0)
            activity_standings[e["activity"]][standing] += 1

    activity_report = []
    for activity, values in activity_elapsed.items():
        activity_report.append(
            {
                "activity": activity,
                "count": len(values),
                "mean_elapsed_s": round(statistics.fmean(values), 3) if values else 0.0,
                "max_elapsed_s": round(max(values), 3) if values else 0.0,
                "standings": activity_standings[activity],
            }
        )
    activity_report.sort(key=lambda r: r["mean_elapsed_s"], reverse=True)

    return {
        "ocel_dir": str(ocel_dir),
        "problems_with_telemetry": len(db_paths),
        "per_problem": per_problem,
        "bottleneck_ranking": activity_report,
    }


def _print_report(report: dict) -> None:
    print(f"OCEL 2.0 process-intelligence report -- {report['ocel_dir']}")
    print(f"Problems with real telemetry so far: {report['problems_with_telemetry']}\n")

    if not report["per_problem"]:
        print("(no .ocel2.sqlite files yet -- report is empty, not an error)")
        return

    print("Per-problem:")
    print(f"  {'problem_id':45s} {'events':>7s} {'kubectl_s':>10s} {'errors':>7s} {'submitted':>10s}")
    for row in report["per_problem"]:
        print(
            f"  {row['problem_id']:45s} {row['event_count']:7d} "
            f"{row['total_kubectl_elapsed_s']:10.2f} {row['error_count']:7d} "
            f"{'yes' if row['submitted'] else 'no':>10s}"
        )

    print("\nBottleneck ranking (slowest activity by mean elapsed_s, across the whole batch):")
    print(f"  {'activity':20s} {'count':>7s} {'mean_s':>9s} {'max_s':>9s}  standings")
    for row in report["bottleneck_ranking"]:
        standings_str = ", ".join(f"{k}={v}" for k, v in sorted(row["standings"].items()))
        print(f"  {row['activity']:20s} {row['count']:7d} {row['mean_elapsed_s']:9.3f} {row['max_elapsed_s']:9.3f}  {standings_str}")


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
