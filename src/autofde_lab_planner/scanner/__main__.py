"""Minimal stdin/stdout CLI boundary over the real, already-tested scanner.

Reads a `ClusterState`-shaped JSON document from stdin (or `--state-file
PATH`), calls the real `scan()` (registry.py) and the real `classify()`
(taxonomy.py) on each resulting Anomaly, and prints ONE JSON array to
stdout: `[{...Anomaly fields, "taxonomy": "INJECT_..." | "UNCLASSIFIED"}]`.

This file adds no new diagnostic logic -- it is a thin I/O shim over
`scan()`/`classify()`, which are exercised for real by tests/scanner/. Exit
0 on success. Exit 1 with a message on stderr for malformed/non-object
input, unreadable state file, or any other input-shape error -- never a
fabricated finding on failure.

Usage:
    echo '{"deployments": [...], "pods": [...]}' | python -m autofde_lab_planner.scanner
    python -m autofde_lab_planner.scanner --state-file cluster_state.json
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys

from autofde_lab_planner.scanner.registry import ClusterState, scan
from autofde_lab_planner.scanner.taxonomy import classify


def _load_state(state_file: str | None) -> ClusterState:
    raw = sys.stdin.read() if state_file is None else open(state_file, encoding="utf-8").read()
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError(f"expected a JSON object (ClusterState), got {type(data).__name__}")
    return data  # type: ignore[return-value]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m autofde_lab_planner.scanner")
    parser.add_argument(
        "--state-file",
        default=None,
        help="Path to a ClusterState-shaped JSON file. Defaults to reading stdin.",
    )
    args = parser.parse_args(argv)

    try:
        state = _load_state(args.state_file)
    except FileNotFoundError as exc:
        print(f"state file not found: {exc.filename}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print(f"malformed JSON input: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"malformed input: {exc}", file=sys.stderr)
        return 1

    try:
        anomalies = scan(state)
    except Exception as exc:  # noqa: BLE001 -- surface any scan() failure honestly, no partial output
        print(f"scan() failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    findings = []
    for anomaly in anomalies:
        record = dataclasses.asdict(anomaly)
        record["taxonomy"] = classify(anomaly)
        findings.append(record)

    print(json.dumps(findings))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
