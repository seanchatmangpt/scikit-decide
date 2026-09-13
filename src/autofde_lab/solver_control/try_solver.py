"""Bounded-timeout solver-attempt primitive.

Runs an arbitrary zero-arg callable (typically "construct a solver, solve,
roll out to goal") in a SEPARATE PROCESS via multiprocessing.Process, not a
thread. This is a real, load-bearing distinction, not a style choice: a
blocking C++ call inside a DESDEOP/discrete_optimization solver (e.g.
Astar's solve()) holds the GIL-released C extension frame for its entire
duration and cannot be interrupted by a Python thread, a Python-level
timeout, or a signal handler delivered on the main thread while that frame
is running. Confirmed this session by a real >90s hang of the registered
Astar solver against the rcpsp j301_1.sm PSPLIB instance that no
threading.Timer/signal.alarm approach could abort. A separate OS process
can always be terminated by the OS regardless of what the child is blocked
on.
"""

from __future__ import annotations

import multiprocessing as mp
import time
import traceback
from typing import Any, Callable


def _child_target(fn: Callable[[], Any], conn) -> None:
    try:
        result = fn()
        conn.send(("success", result))
    except Exception as exc:  # noqa: BLE001 - we want to report ANY child exception, not swallow it
        conn.send(("error", f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"))
    finally:
        conn.close()


def try_solver(build_and_solve_fn: Callable[[], Any], timeout_seconds: int) -> dict:
    """Run build_and_solve_fn() in a separate process, bounded by timeout_seconds.

    Returns one of:
      {"status": "success", "result": <value returned by build_and_solve_fn>}
      {"status": "timeout"}
      {"status": "error", "error": <str(exception) + traceback>}

    Guarantees the child process is not left running: on timeout it is sent
    SIGTERM (process.terminate()), given up to 5s to exit cleanly via
    process.join(timeout=5), and SIGKILL'd (process.kill()) if it is still
    alive after that. The process is always joined a final time so it does
    not become a zombie.
    """
    ctx = mp.get_context("spawn")
    parent_conn, child_conn = ctx.Pipe(duplex=False)
    process = ctx.Process(target=_child_target, args=(build_and_solve_fn, child_conn))
    process.start()
    child_conn.close()  # parent doesn't write to this end

    deadline = time.monotonic() + timeout_seconds
    outcome: dict = {"status": "timeout"}
    got_result = False

    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        if parent_conn.poll(timeout=min(remaining, 0.25)):
            try:
                kind, payload = parent_conn.recv()
            except EOFError:
                # child died without sending a result (e.g. killed by OS OOM)
                outcome = {"status": "error", "error": "child process closed connection without a result"}
                got_result = True
                break
            if kind == "success":
                outcome = {"status": "success", "result": payload}
            else:
                outcome = {"status": "error", "error": payload}
            got_result = True
            break
    else:
        outcome = {"status": "timeout"}

    # IMPORTANT: a child that already sent its result via the pipe can still
    # be technically alive for a brief moment afterward -- finishing
    # interpreter/library teardown (e.g. closing native handles, atexit
    # hooks) before the OS actually reaps it. `process.is_alive()` alone
    # cannot distinguish "still computing, past the deadline" from "already
    # answered, mid-exit" -- confirmed this session by a real race: the
    # flight_planning heuristic-Astar candidate sent {"status": "success",
    # ...} at ~0.3s into a 30s budget, yet was still `is_alive() == True`
    # a poll cycle later, and the old code below (with no `got_result`
    # guard) clobbered the real success with a fabricated "timeout" and
    # needlessly SIGTERM'd/SIGKILL'd an already-finished child. Only treat
    # "still alive" as a real hang when we never received an answer.
    if not got_result and process.is_alive():
        # We hit the deadline without a result: terminate the hung child for real.
        outcome = {"status": "timeout"}
        process.terminate()
        process.join(timeout=5)
        if process.is_alive():
            process.kill()
            process.join(timeout=5)

    process.join()  # reap; never leave a zombie
    parent_conn.close()
    return outcome
