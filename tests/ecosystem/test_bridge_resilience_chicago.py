# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for `bridge_resilience.ResilientBridge`.

Every collaborator here is real: the real `~/gymact` virtualenv, real
subprocesses, real provider semantics, real files on disk. Failure modes
are triggered with genuinely bad *inputs* and genuinely slow *real
scripts* -- never with a mock, a patch, or a monkeypatched return value.
Assertions are on final state: the typed outcome, the preserved
stdout/stderr text, and the contents of the evidence log re-read from
disk.

The one place a file is written by the test is the bridge script itself
(`evidence_dir/bridge.py`), for the timeout and malformed-output cases:
that is a real file executed by a real interpreter, i.e. a real
collaborator with real (slow, or noisy) behaviour -- not a test double
faking an interaction.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from autofde_lab.hub.domain.gym_procedure.bridge_resilience import (
    BRIDGE_MALFORMED_OUTPUT,
    BRIDGE_OK,
    BRIDGE_SUBPROCESS_FAILED,
    BRIDGE_TIMEOUT,
    MATERIALIZE_REFUSED,
    PROVIDER_REFUSED,
    TRANSIENT_KINDS,
    UNKNOWN_CAPABILITY,
    BridgeFailure,
    ResilientBridge,
)
from autofde_lab.hub.domain.gym_procedure.level4_gymact_bridge import (
    RealBlindEnvironment,
    skip_reason,
)

pytestmark = pytest.mark.skipif(
    skip_reason() is not None, reason=str(skip_reason())
)


def _env(tmp_path: Path, name: str, provider: str = "cube_counter", config=None):
    return RealBlindEnvironment(
        provider, config if config is not None else {"target": 3}, tmp_path / name
    )


# ---------------------------------------------------------------- happy path


def test_happy_path_returns_bridge_ok_and_real_state(tmp_path: Path):
    bridge = ResilientBridge(_env(tmp_path, "ok"))
    actions = bridge.available_actions()
    assert "increment" in actions

    result = bridge.try_action("increment")
    assert result.kind == BRIDGE_OK
    assert result.ok
    assert result.record["observed_post"]["counter"] == 1

    logged = bridge.logged_attempts()
    assert [a["kind"] for a in logged].count(BRIDGE_OK) >= 2
    assert any(a["record"] is not None for a in logged)


# ------------------------------------------------------------ subprocess dies


def test_subprocess_nonzero_is_typed_and_preserves_stderr(tmp_path: Path):
    """A real broken bridge script -> non-zero exit, real traceback kept."""
    env = _env(tmp_path, "boom")
    env._bridge_script.write_text(
        "import sys\n"
        "print('partial stdout before failing')\n"
        "raise ValueError('DELIBERATE_BRIDGE_EXPLOSION')\n",
        encoding="utf-8",
    )
    bridge = ResilientBridge(env)
    with pytest.raises(BridgeFailure) as excinfo:
        bridge.available_actions()

    failure = excinfo.value
    assert failure.kind == BRIDGE_SUBPROCESS_FAILED
    assert failure.returncode != 0
    assert "DELIBERATE_BRIDGE_EXPLOSION" in failure.stderr
    assert "Traceback" in failure.stderr
    assert "partial stdout before failing" in failure.stdout

    logged = bridge.logged_attempts()
    assert logged[-1]["kind"] == BRIDGE_SUBPROCESS_FAILED
    assert "DELIBERATE_BRIDGE_EXPLOSION" in logged[-1]["stderr"]
    # deterministic class: reported on the first attempt, not retried
    assert len(logged) == 1
    assert BRIDGE_SUBPROCESS_FAILED not in TRANSIENT_KINDS


# ------------------------------------------------------------------- timeout


def test_real_timeout_is_typed_and_keeps_partial_stdout(tmp_path: Path):
    """A real sleeping script exceeds a real, short deadline."""
    env = _env(tmp_path, "slow")
    env._bridge_script.write_text(
        "import time\nprint('bridge started', flush=True)\ntime.sleep(30)\n",
        encoding="utf-8",
    )
    bridge = ResilientBridge(env, timeout=2, max_retries=1)
    with pytest.raises(BridgeFailure) as excinfo:
        bridge.available_actions()

    failure = excinfo.value
    assert failure.kind == BRIDGE_TIMEOUT
    assert "exceeded 2" in failure.detail
    # TimeoutExpired.stdout is bytes even under text=True; normalisation
    # must not lose it.
    assert "bridge started" in failure.stdout

    logged = bridge.logged_attempts()
    assert [a["kind"] for a in logged] == [BRIDGE_TIMEOUT, BRIDGE_TIMEOUT]
    assert all("bridge started" in a["stdout"] for a in logged)
    assert BRIDGE_TIMEOUT in TRANSIENT_KINDS


# ----------------------------------------------------------- malformed stdout


def test_trailing_non_json_line_is_typed_malformed(tmp_path: Path):
    """A real provider-side print landing after the JSON payload."""
    env = _env(tmp_path, "noisy")
    original = env._bridge_script.read_text(encoding="utf-8")
    env._bridge_script.write_text(
        original + "\nprint('UserWarning: something deprecated')\n", encoding="utf-8"
    )
    bridge = ResilientBridge(env)
    with pytest.raises(BridgeFailure) as excinfo:
        bridge.available_actions()

    failure = excinfo.value
    assert failure.kind == BRIDGE_MALFORMED_OUTPUT
    assert "not JSON" in failure.detail
    assert "UserWarning: something deprecated" in failure.detail
    # the real JSON payload is still preserved for a human to read
    assert '"episode_id"' in failure.stdout
    assert bridge.logged_attempts()[-1]["kind"] == BRIDGE_MALFORMED_OUTPUT


def test_empty_stdout_with_zero_exit_is_typed_malformed(tmp_path: Path):
    """Raw bridge raised a bare `IndexError` with zero context here."""
    env = _env(tmp_path, "silent")
    env._bridge_script.write_text("import sys\nsys.exit(0)\n", encoding="utf-8")
    bridge = ResilientBridge(env)
    with pytest.raises(BridgeFailure) as excinfo:
        bridge.available_actions()
    assert excinfo.value.kind == BRIDGE_MALFORMED_OUTPUT
    assert "empty stdout" in excinfo.value.detail


# ------------------------------------------------------- unknown capability


def test_unknown_capability_is_typed_and_never_crashes_subprocess(tmp_path: Path):
    """The raw bridge script leaves `after_state` unbound for an unknown
    binding and dies with `UnboundLocalError`; the wrapper answers first."""
    bridge = ResilientBridge(_env(tmp_path, "unknown"))
    result = bridge.try_action("no_such_binding")
    assert result.kind == UNKNOWN_CAPABILITY
    assert result.refused
    assert result.record is None
    assert "no_such_binding" in result.attempts[-1].detail

    logged = bridge.logged_attempts()
    assert logged[-1]["kind"] == UNKNOWN_CAPABILITY
    assert UNKNOWN_CAPABILITY not in TRANSIENT_KINDS


def test_raw_bridge_really_does_crash_on_unknown_binding(tmp_path: Path):
    """Pins the real defect the wrapper is guarding, so this test fails
    loudly if `level4_gymact_bridge` is ever fixed and the guard becomes
    dead weight."""
    env = _env(tmp_path, "rawcrash")
    env.available_actions()
    with pytest.raises(RuntimeError) as excinfo:
        env.try_action("no_such_binding")
    assert "UnboundLocalError" in str(excinfo.value)


# ---------------------------------------------------------- provider refusal


def test_provider_refusal_is_an_answer_not_a_retry(tmp_path: Path):
    """`burn_catalyst` twice on the real resource-flow provider: the
    second is genuinely refused (`applicable=False`)."""
    bridge = ResilientBridge(
        _env(tmp_path, "refuse", provider="resource_flow", config={}),
        max_retries=3,
    )
    assert "burn_catalyst" in bridge.available_actions()

    first = bridge.try_action("burn_catalyst")
    assert first.kind == BRIDGE_OK
    assert first.record["observed_post"]["catalyst"] is False

    before = len(bridge.logged_attempts())
    second = bridge.try_action("burn_catalyst")
    assert second.kind == PROVIDER_REFUSED
    assert second.refused
    assert second.record["applicable"] is False
    assert second.record["observed_post"]["catalyst"] is False

    # A refusal must never be retried: exactly one subprocess round-trip
    # (BRIDGE_OK transport line) plus one PROVIDER_REFUSED evidence line.
    added = bridge.logged_attempts()[before:]
    assert [a["kind"] for a in added] == [BRIDGE_OK, PROVIDER_REFUSED]
    assert PROVIDER_REFUSED not in TRANSIENT_KINDS


def test_counter_provider_does_not_clamp_past_target_or_below_zero(tmp_path: Path):
    """Real observed semantics, reported rather than assumed: the
    cube-counter provider neither refuses nor clamps -- it goes past the
    target and below zero, and reward, not applicability, carries the
    signal."""
    bridge = ResilientBridge(_env(tmp_path, "counter", config={"target": 2}))
    bridge.available_actions()
    counters = []
    for _ in range(4):
        res = bridge.try_action("increment")
        assert res.kind == BRIDGE_OK
        counters.append(res.record["observed_post"]["counter"])
    assert counters == [1, 2, 3, 4]

    down = ResilientBridge(_env(tmp_path, "counter_down", config={"target": 2}))
    down.available_actions()
    lows = []
    for _ in range(3):
        res = down.try_action("decrement")
        assert res.kind == BRIDGE_OK
        lows.append(res.record["observed_post"]["counter"])
    assert lows == [-1, -2, -3]


# ------------------------------------------------------- materialize refusal


def test_bad_config_surfaces_as_typed_refusal_not_empty_action_list(tmp_path: Path):
    """Raw bridge returns `[]` here -- indistinguishable from a provider
    with no actions. The wrapper refuses instead."""
    env = _env(tmp_path, "badcfg", config={"target": "banana"})
    assert env.available_actions() == []  # the real, silent raw behaviour

    bridge = ResilientBridge(_env(tmp_path, "badcfg2", config={"target": "banana"}))
    with pytest.raises(BridgeFailure) as excinfo:
        bridge.available_actions()
    assert excinfo.value.kind == MATERIALIZE_REFUSED
    assert "PROVIDER_ERROR" in excinfo.value.detail
    assert MATERIALIZE_REFUSED not in TRANSIENT_KINDS


# ------------------------------------------------------------ isolation proof


def test_concurrent_bridges_never_share_evidence_or_state(tmp_path: Path):
    """Negative concurrency test for the real Level 3 incident: parallel
    runs writing to a shared scratch filename, one consuming another's
    state. Eight real bridges are driven in parallel against the real
    subprocess with distinct targets; each must end with exactly its own
    evidence and its own counter."""
    n = 8

    def run(i: int) -> tuple[int, int, Path, str]:
        bridge = ResilientBridge(
            _env(tmp_path, f"par{i}", config={"target": i + 1})
        )
        bridge.available_actions()
        last = None
        for _ in range(i + 1):
            res = bridge.try_action("increment")
            assert res.kind == BRIDGE_OK
            last = res
        return (
            i,
            last.record["observed_post"]["counter"],
            bridge.attempts_path,
            last.record["observed_post"]["target"],
        )

    with ThreadPoolExecutor(max_workers=n) as pool:
        results = list(pool.map(run, range(n)))

    paths = [r[2] for r in results]
    assert len(set(paths)) == n, "evidence paths collided"
    for i, counter, path, target in results:
        assert counter == i + 1, f"trial {i} observed another trial's counter"
        assert target == i + 1, f"trial {i} observed another trial's config"
        logged = [json.loads(x) for x in path.read_text().splitlines() if x.strip()]
        actions = {a["action"] for a in logged if a["action"]}
        assert actions == {"increment"}
        assert all(a["kind"] in (BRIDGE_OK,) for a in logged)
