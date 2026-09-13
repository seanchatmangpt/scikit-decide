# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Two real timeout mechanisms, for two shapes of "run this without a bound."

No timeout mechanism existed anywhere in this repo for either shape before this
module: confirmed this session against ``fabric/coverage.py::_run_solver`` (the
only prior "run every solver" precedent) and against a hand-rolled
``subprocess.run()`` call built for a new MCP-driven catalog sweep
(``notebooks/18_mcp_user_simulation_ocel.ipynb``). Several real registered
solvers are RL-training methods (``RayRLlib``, ``StableBaseline``,
``AugmentedRandomSearch``, ``MaxentIRL``) with no bound on training time, so
this is not a hypothetical gap -- the sweep genuinely needed both mechanisms
to avoid hanging, in two different situations that call for different fixes:

``run_subprocess_bounded``
    For a call that is *already* a subprocess invocation (a fresh Python
    process, argv-addressable). Uses ``asyncio.create_subprocess_exec`` +
    ``asyncio.wait_for`` -- not blocking ``subprocess.run()``, which was found
    this session to race an already-running asyncio event loop's own
    child-process reaping (SIGCHLD/``waitpid``) when called from a coroutine,
    silently returning bogus near-instant nonzero exit codes instead of real
    results. Kills the child on timeout.

``run_callable_bounded``
    For an arbitrary in-process Python callable that cannot be reduced to a
    subprocess argv -- ``fabric/coverage.py``'s ``domain_factory`` is a
    caller-supplied closure (e.g. ``lambda: CareerAdmission()``), not a
    registry name a fresh process could reconstruct on its own. Uses
    ``signal.alarm`` (POSIX, main-thread only) to raise a real
    :class:`TimeoutError` inside the callable rather than letting it block
    forever -- this cannot forcibly kill CPU-bound native code the way a
    subprocess kill can, but it does interrupt anything that returns to the
    Python interpreter or blocks in an interruptible syscall, which covers
    every registered solver's ``solve()`` + rollout loop in this repo today.
"""

from __future__ import annotations

import asyncio
import signal
from dataclasses import dataclass
from typing import Callable, Optional, Sequence, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class SubprocessOutcome:
    """Result of :func:`run_subprocess_bounded`."""

    standing: str  # "SOLVED" | "TIMEOUT" | "ERROR"
    elapsed_s: float
    stdout: str = ""
    stderr: str = ""
    returncode: Optional[int] = None


async def run_subprocess_bounded(
    argv: Sequence[str],
    *,
    timeout_s: float,
    env: Optional[dict] = None,
) -> SubprocessOutcome:
    """Run ``argv`` as a subprocess, killed if it exceeds ``timeout_s``.

    Never call this from inside a blocking ``subprocess.run()`` in an
    asyncio-driven caller -- that combination is exactly the bug this
    function exists to avoid (see module docstring).
    """
    import time

    started = time.monotonic()
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(), timeout=timeout_s
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return SubprocessOutcome(
            standing="TIMEOUT", elapsed_s=time.monotonic() - started
        )

    elapsed = time.monotonic() - started
    return SubprocessOutcome(
        standing="SOLVED" if proc.returncode == 0 else "ERROR",
        elapsed_s=elapsed,
        stdout=stdout_bytes.decode(errors="replace"),
        stderr=stderr_bytes.decode(errors="replace"),
        returncode=proc.returncode,
    )


class _AlarmTimeout(TimeoutError):
    pass


def run_callable_bounded(fn: Callable[[], T], *, timeout_s: float) -> T:
    """Run ``fn()`` in-process, raising :class:`TimeoutError` past ``timeout_s``.

    POSIX + main-thread only (``signal.alarm``'s own restriction -- raises
    :class:`RuntimeError` outside the main thread, since ``SIGALRM`` cannot be
    delivered to a specific non-main thread). Restores any previously
    installed ``SIGALRM`` handler and cancels the pending alarm in a
    ``finally``, so a caller with its own alarm in flight is not silently
    clobbered by a nested call.
    """
    previous_handler = signal.signal(
        signal.SIGALRM, lambda _signum, _frame: (_ for _ in ()).throw(_AlarmTimeout())
    )
    previous_alarm = signal.alarm(0)  # cancel any pending alarm, read its remaining time
    try:
        signal.alarm(max(1, int(timeout_s)))
        try:
            return fn()
        except _AlarmTimeout as exc:
            raise TimeoutError(
                f"exceeded {timeout_s:g}s wall-clock bound"
            ) from exc
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous_handler)
        if previous_alarm:
            signal.alarm(previous_alarm)
