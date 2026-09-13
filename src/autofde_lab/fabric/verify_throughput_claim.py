# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""One real, narrow falsification check: does a claimed ops/sec (or
solves/sec) throughput number match a real logged benchmark result?

This closes the exact failure mode this session's own discipline exists
to prevent -- an ops/sec or throughput number asserted in prose with no
real log backing it. `verify_throughput_claim` never accepts a claim on
faith: it reads a real log file on disk, parses the real
`RESULTS_JSON` block a real benchmark run wrote (see
`logs/throughput-benchmark-2026-08-20.log`, produced by a real
`n`-solve timed loop over a real domain/solver), and compares the real
logged `solves_per_sec` against the claimed number within a tolerance.
No log, no parseable number, or a claim outside tolerance -> `False`
(falsified). A claim that matches real logged evidence -> `True`
(survives).

Mirrors `fabric/solve_and_falsify.py`'s `receipt_from_solve` pattern:
`receipt_from_throughput_claim` builds a real `ExperimentReceipt` from
only what was actually observed in the log, so a throughput claim can be
run through the same real `falsify_candidate` used everywhere else in
`reasoning/laboratory.py`, not a bespoke ad hoc comparison living
outside the falsification vocabulary.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from autofde_lab.reasoning.laboratory import ExperimentReceipt

_RESULTS_JSON_MARKER = "=== RESULTS_JSON ==="


def _load_results_json(log_path: Path) -> dict:
    """Real parse of the real `RESULTS_JSON` block a benchmark log
    writes. Raises `ValueError` (never silently returns `{}`) if the
    marker or a valid JSON object after it is not found -- an unparsable
    log is honest failure, not a fabricated empty result."""
    text = log_path.read_text(encoding="utf-8")
    idx = text.find(_RESULTS_JSON_MARKER)
    if idx == -1:
        raise ValueError(f"no {_RESULTS_JSON_MARKER!r} marker found in {log_path}")
    remainder = text[idx + len(_RESULTS_JSON_MARKER) :]
    match = re.search(r"\{.*\}", remainder, re.DOTALL)
    if not match:
        raise ValueError(f"no JSON object found after {_RESULTS_JSON_MARKER!r} marker in {log_path}")
    return json.loads(match.group(0))


def real_logged_solves_per_sec(log_path: Path, domain_key: str) -> float:
    """Real logged `solves_per_sec` for `domain_key` (e.g. `"maze"` or
    `"blocksworld"`) out of the real `RESULTS_JSON` block. Raises
    `KeyError` if that domain was never actually benchmarked in this
    log -- never returns a fabricated default."""
    results = _load_results_json(log_path)
    if domain_key not in results:
        raise KeyError(f"domain {domain_key!r} not present in {log_path}'s real RESULTS_JSON")
    return float(results[domain_key]["solves_per_sec"])


def verify_throughput_claim(
    claimed_ops_per_sec: float,
    log_path: Path,
    domain_key: str,
    *,
    tolerance: float = 0.05,
) -> bool:
    """The one real falsification check.

    `False` (falsified) when:
    - the log file does not exist,
    - the log has no parseable `RESULTS_JSON` block or `domain_key`
      entry, or
    - `claimed_ops_per_sec` differs from the real logged
      `solves_per_sec` by more than `tolerance` (relative, default 5%).

    `True` (survives) only when a real logged number exists for
    `domain_key` and the claim is within tolerance of it.
    """
    if not log_path.exists():
        return False
    try:
        real_value = real_logged_solves_per_sec(log_path, domain_key)
    except (ValueError, KeyError, json.JSONDecodeError):
        return False
    if real_value <= 0:
        return False
    relative_error = abs(claimed_ops_per_sec - real_value) / real_value
    return relative_error <= tolerance


def receipt_from_throughput_claim(
    intent_id: str,
    claimed_ops_per_sec: float,
    log_path: Path,
    domain_key: str,
    *,
    tolerance: float = 0.05,
) -> ExperimentReceipt:
    """Real `ExperimentReceipt` built only from what
    `verify_throughput_claim` actually observed -- runnable through the
    real `falsify_candidate` in `reasoning/laboratory.py`, same as any
    other real receipt in this repo."""
    survives = verify_throughput_claim(
        claimed_ops_per_sec, log_path, domain_key, tolerance=tolerance
    )
    return ExperimentReceipt(
        intent_id=intent_id,
        observed_outcome_refs=(f"throughput-log:{log_path}:{domain_key}",),
        authority_standing="ADMITTED",
        postconditions_observed=("throughput-claim-matches-real-log",) if survives else (),
        postconditions_violated=() if survives else ("throughput-claim-matches-real-log",),
        ocel_evidence_ref=None,
        standing="OBSERVED",
    )
