# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Real checks for both timeout mechanisms in fabric/bounded_exec.py.

No mocks: `run_subprocess_bounded` spawns real `sleep`/`python -c` processes;
`run_callable_bounded` uses a real `time.sleep` to trip a real `signal.alarm`.
"""

from __future__ import annotations

import asyncio
import sys
import time

import pytest

from autofde_lab.fabric.bounded_exec import (
    run_callable_bounded,
    run_subprocess_bounded,
)


class TestRunCallableBounded:
    def test_fast_callable_returns_its_result(self):
        assert run_callable_bounded(lambda: 1 + 1, timeout_s=5) == 2

    def test_slow_callable_raises_real_timeout_error(self):
        started = time.monotonic()
        with pytest.raises(TimeoutError, match="wall-clock bound"):
            run_callable_bounded(lambda: time.sleep(3), timeout_s=1)
        elapsed = time.monotonic() - started
        assert 0.9 <= elapsed < 2.5, f"alarm did not fire near the requested bound: {elapsed}s"

    def test_callable_exception_propagates_normally(self):
        def boom():
            raise ValueError("real failure")

        with pytest.raises(ValueError, match="real failure"):
            run_callable_bounded(boom, timeout_s=5)

    def test_pending_alarm_is_restored_after_a_nested_call(self):
        import signal

        signal.alarm(0)  # ensure clean slate
        try:
            signal.alarm(30)
            run_callable_bounded(lambda: 1, timeout_s=5)
            remaining = signal.alarm(0)
            assert remaining > 0, "outer alarm was clobbered, not restored"
        finally:
            signal.alarm(0)


class TestRunSubprocessBounded:
    # Plain sync test functions driving their own asyncio.run(): neither
    # pytest-asyncio nor a configured anyio-mode fixture is installed in this
    # environment (same finding as tests/fabric/test_dspy_mcp_planner_loop_chicago.py
    # this session), and a real run_subprocess_bounded call still needs an
    # event loop regardless of which plugin would otherwise supply one.

    def test_fast_subprocess_returns_real_output(self):
        async def run():
            return await run_subprocess_bounded(
                [sys.executable, "-c", "print('hello')"], timeout_s=5
            )

        outcome = asyncio.run(run())
        assert outcome.standing == "SOLVED"
        assert outcome.returncode == 0
        assert "hello" in outcome.stdout

    def test_slow_subprocess_is_killed_and_reported_as_timeout(self):
        async def run():
            return await run_subprocess_bounded(
                [sys.executable, "-c", "import time; time.sleep(5)"], timeout_s=1
            )

        outcome = asyncio.run(run())
        assert outcome.standing == "TIMEOUT"
        assert outcome.elapsed_s < 3

    def test_nonzero_exit_reported_as_error(self):
        async def run():
            return await run_subprocess_bounded(
                [sys.executable, "-c", "import sys; sys.exit(1)"], timeout_s=5
            )

        outcome = asyncio.run(run())
        assert outcome.standing == "ERROR"
        assert outcome.returncode == 1

    def test_runs_from_inside_a_coroutine_without_racing_the_event_loop(self):
        """The exact bug this function exists to avoid.

        Reproduced this session: a blocking `subprocess.run()` called from a
        coroutine returned bogus near-instant nonzero exit codes with empty
        stderr, racing the event loop's own child-process reaping. Calling
        `run_subprocess_bounded` concurrently from several coroutines (the
        shape a real notebook loop uses) must not reproduce that.
        """

        async def run():
            return await asyncio.gather(
                *[
                    run_subprocess_bounded(
                        [sys.executable, "-c", "print('ok')"], timeout_s=5
                    )
                    for _ in range(5)
                ]
            )

        results = asyncio.run(run())
        for outcome in results:
            assert outcome.standing == "SOLVED"
            assert outcome.elapsed_s > 0.001, (
                "suspiciously fast return -- the bug this test guards against "
                "produced ~0.02s bogus results instead of real subprocess time"
            )
            assert "ok" in outcome.stdout
