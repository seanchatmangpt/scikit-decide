# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for `architecture_change_trigger_from_drift`.

The structural (zero-points) test is always real and LLM/binary-free. The
live test makes a real `wpm` (wasm4pm-cli) subprocess call via the real
`detect_drift()` -- `skipif`-gated on the real binary being resolvable
(`resolve_wpm_binary`/`Wasm4pmUnavailable`), the same gating pattern
`tests/ocel/test_wasm4pm_bridge.py` already uses, never a mock substitute
per `.claude/rules/testing-chicago-style.md`.

No `unittest.mock` / `Mock` / `MagicMock` / `patch` / `monkeypatch` anywhere
in this file.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from autofde_lab.ocel.wasm4pm_bridge import Wasm4pmUnavailable, detect_drift, resolve_wpm_binary
from autofde_lab.reasoning.drift_architecture_change_trigger import architecture_change_trigger_from_drift


def _require_wpm() -> str:
    try:
        return resolve_wpm_binary()
    except Wasm4pmUnavailable as exc:
        pytest.skip(str(exc))


def _write_event_log_json(path, traces: list[list[tuple[str, int]]]) -> None:
    """Same real fixture shape as `tests/ocel/test_wasm4pm_bridge.py::_write_event_log_json`."""

    def _string_attr(key: str, value: str) -> dict:
        return {"key": key, "value": {"type": "String", "content": value}, "own_attributes": None}

    doc = {
        "attributes": [],
        "traces": [
            {
                "attributes": [],
                "events": [
                    {
                        "attributes": [
                            _string_attr("concept:name", name),
                            {"key": "time:timestamp", "value": {"type": "Int", "content": ts}, "own_attributes": None},
                        ]
                    }
                    for name, ts in trace
                ],
            }
            for trace in traces
        ],
    }
    path.write_text(json.dumps(doc))


def test_zero_drift_points_is_a_real_honest_non_fabricated_zero_confidence() -> None:
    """Mirrors `falsify_candidate`'s own "zero receipts -> honest, never
    fabricated" law: no real drift points must never be coerced into a
    fabricated positive confidence."""
    trigger = architecture_change_trigger_from_drift(
        (), affected_requirement_refs=("req-latency",)
    )

    assert trigger.confidence == 0.0
    assert trigger.fires is False
    assert trigger.evidence_refs == ()
    assert trigger.detected_drift == "no real drift points detected"
    assert trigger.affected_requirement_refs == ("req-latency",)


def test_real_vocabulary_shift_drift_produces_a_real_firing_trigger(tmp_path) -> None:
    """Real, live: a real `wpm mining drift` subprocess call detects a real
    vocabulary shift (identical to
    `test_wasm4pm_bridge.py::test_real_drift_detects_vocabulary_shift`'s
    own fixture -- reused, not re-derived, since that test already proves
    the real jaccard/tv distance this test's assertions depend on), and
    the resulting `ArchitectureChangeTrigger` really fires (both real
    distances are 1.0, well above the 0.5 threshold)."""
    _require_wpm()

    log_path = tmp_path / "drift_log.json"
    traces = [[("X", 0), ("Y", 1), ("Z", 2)] for _ in range(4)]
    traces += [[("P", 0), ("Q", 1), ("R", 2)] for _ in range(4)]
    _write_event_log_json(log_path, traces)

    points = asyncio.run(detect_drift(log_path, window_size=1, timeout_s=30))
    assert len(points) == 1  # precondition proven real by test_wasm4pm_bridge.py

    trigger = architecture_change_trigger_from_drift(
        tuple(points), affected_requirement_refs=("req-latency",)
    )

    assert trigger.confidence == pytest.approx(max(points[0].jaccard_distance, points[0].tv_distance))
    assert trigger.confidence == pytest.approx(1.0)
    assert trigger.fires is True
    assert len(trigger.evidence_refs) == 1
    assert "pos=4" in trigger.evidence_refs[0]
    assert "1 real drift point(s) detected" in trigger.detected_drift
