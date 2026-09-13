# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Typed hardening around `level4_gymact_bridge.RealBlindEnvironment`.

`RealBlindEnvironment` is correct on the happy path and deliberately left
unmodified here. Its *failure* surface, however, was measured (probe runs,
2026-08-08) to collapse five materially different situations into three
untyped Python exceptions, two of which discard the subprocess output
entirely:

| real situation                              | raw bridge behaviour                    |
|---------------------------------------------|-----------------------------------------|
| subprocess exits non-zero                    | `RuntimeError` with stdout+stderr inline in the message string |
| subprocess exceeds the hardcoded 120 s       | `subprocess.TimeoutExpired` propagates; `.stdout` is **bytes** even under `text=True`, `.stderr` is `None` |
| last stdout line is not JSON                 | `json.JSONDecodeError` — **stdout and stderr are lost** |
| stdout empty with returncode 0               | `IndexError: list index out of range` — **no context at all** |
| provider refuses a lawful action             | not an error: a normal record with `applicable=False` |
| unknown capability binding requested         | the bridge script `continue`s past the observe, then dereferences an unbound `after_state` → `UnboundLocalError` → non-zero exit → `RuntimeError` |
| provider config rejected by `materialize()`  | **no error at all**: `{"materialize_failed": true, ...}` flows through and `available_actions()` silently returns `[]` |

`ResilientBridge` turns each of those into one of five typed outcomes
(`BRIDGE_SUBPROCESS_FAILED`, `BRIDGE_TIMEOUT`, `BRIDGE_MALFORMED_OUTPUT`,
`UNKNOWN_CAPABILITY`, `PROVIDER_REFUSED`), always carrying the real
`stdout`/`stderr` it saw, and appends every attempt — successes and
failures alike — to `attempts.jsonl` in the trial evidence directory, so a
failure is evidence rather than a silent gap.

Retrying a refusal is forbidden
-------------------------------
`PROVIDER_REFUSED` and `UNKNOWN_CAPABILITY` are **real answers from the
provider**, not transport faults. Retrying them would re-drive a fresh
episode against the same history and could return a different record for
reasons unrelated to the question asked — manufacturing an outcome the
provider never gave. The discovery agent would then learn that a refused
action is available, which is precisely the defect
`level4_gymact_bridge`'s own `effect.get("applicable", True)` guard exists
to prevent. Only `BRIDGE_TIMEOUT` is retried, because a wall-clock
overrun under host contention is the one class here whose cause is
genuinely outside the question being asked. `BRIDGE_SUBPROCESS_FAILED`
and `BRIDGE_MALFORMED_OUTPUT` are deterministic given the same script and
arguments, so retrying them only burns wall clock — they are reported on
the first attempt.

Isolation
---------
Every `ResilientBridge` writes its attempt log under the evidence
directory of the `RealBlindEnvironment` it wraps, which `level4_generator`
already mints per-trial from a `uuid4` run id. No path here is derived
from a fixed scratch name — the Level 3 incident in which two parallel
agents shared a scratch filename and one run consumed the other's state
cannot recur through this module by construction, and
`tests/ecosystem/test_bridge_resilience_chicago.py` proves it with a real
concurrent run.
"""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .level4_gymact_bridge import GYMACT, GYMACT_VENV_PYTHON, RealBlindEnvironment

# ---------------------------------------------------------------- outcomes

BRIDGE_OK = "BRIDGE_OK"
BRIDGE_SUBPROCESS_FAILED = "BRIDGE_SUBPROCESS_FAILED"
BRIDGE_TIMEOUT = "BRIDGE_TIMEOUT"
BRIDGE_MALFORMED_OUTPUT = "BRIDGE_MALFORMED_OUTPUT"
UNKNOWN_CAPABILITY = "UNKNOWN_CAPABILITY"
PROVIDER_REFUSED = "PROVIDER_REFUSED"
MATERIALIZE_REFUSED = "MATERIALIZE_REFUSED"

#: The only class retried. See the module docstring: a refusal is a real
#: answer and retrying it would manufacture a different one.
TRANSIENT_KINDS = frozenset({BRIDGE_TIMEOUT})

#: Real answers from the provider. Retrying any of these is forbidden.
REFUSAL_KINDS = frozenset(
    {PROVIDER_REFUSED, UNKNOWN_CAPABILITY, MATERIALIZE_REFUSED}
)


def _text(raw: Any) -> str:
    """Normalise a stream that may be `str`, `bytes`, or `None`.

    `subprocess.TimeoutExpired.stdout` is bytes even when the call used
    `text=True` (measured), and `.stderr` is `None`. Losing that is how
    the raw bridge drops evidence.
    """
    if raw is None:
        return ""
    if isinstance(raw, bytes):
        return raw.decode("utf-8", errors="replace")
    return str(raw)


@dataclass
class BridgeAttempt:
    """One real invocation, successful or not."""

    kind: str
    attempt: int
    action: str | None = None
    detail: str = ""
    stdout: str = ""
    stderr: str = ""
    returncode: int | None = None
    elapsed_s: float = 0.0
    record: dict | None = None

    def to_json(self) -> dict:
        return {
            "kind": self.kind,
            "attempt": self.attempt,
            "action": self.action,
            "detail": self.detail,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "returncode": self.returncode,
            "elapsed_s": round(self.elapsed_s, 4),
            "record": self.record,
        }


class BridgeFailure(RuntimeError):
    """A typed bridge failure that never swallows the real output."""

    def __init__(
        self,
        kind: str,
        detail: str,
        *,
        stdout: str = "",
        stderr: str = "",
        returncode: int | None = None,
        attempts: list[BridgeAttempt] | None = None,
    ) -> None:
        self.kind = kind
        self.detail = detail
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode
        self.attempts: list[BridgeAttempt] = list(attempts or [])
        super().__init__(
            f"{kind}: {detail}\n--- stdout ---\n{stdout}\n--- stderr ---\n{stderr}"
        )


@dataclass
class BridgeResult:
    """Outcome of one `try_action`, refusals included (they are answers)."""

    kind: str
    record: dict | None = None
    attempts: list[BridgeAttempt] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.kind == BRIDGE_OK

    @property
    def refused(self) -> bool:
        return self.kind in REFUSAL_KINDS


# ------------------------------------------------------------------ wrapper


class ResilientBridge:
    """Typed, evidence-logging wrapper over a `RealBlindEnvironment`.

    Retrying a refusal is forbidden — see the module docstring for why.

    `timeout` (seconds) overrides the wrapped bridge's hardcoded 120 s by
    driving the *same* real bridge script through this class's own
    `subprocess.run`. The argv is reconstructed from the wrapped
    environment's own fields, so there is exactly one bridge script in
    play, written by the wrapped object into its own per-trial evidence
    directory.
    """

    def __init__(
        self,
        env: RealBlindEnvironment,
        *,
        timeout: float | None = None,
        max_retries: int = 2,
        retry_backoff_s: float = 0.0,
    ) -> None:
        self._env = env
        self._timeout = timeout
        self._max_retries = max(0, int(max_retries))
        self._backoff = float(retry_backoff_s)
        self._evidence_dir = Path(env._evidence_dir)
        self._evidence_dir.mkdir(parents=True, exist_ok=True)
        self._attempts_path = self._evidence_dir / "attempts.jsonl"
        self.attempts: list[BridgeAttempt] = []

    # -- evidence ---------------------------------------------------------

    @property
    def attempts_path(self) -> Path:
        return self._attempts_path

    def _record(self, attempt: BridgeAttempt) -> BridgeAttempt:
        self.attempts.append(attempt)
        with self._attempts_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(attempt.to_json(), default=str) + "\n")
        return attempt

    def logged_attempts(self) -> list[dict]:
        """Re-read the evidence log from disk (real file, real state)."""
        if not self._attempts_path.is_file():
            return []
        return [
            json.loads(line)
            for line in self._attempts_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    # -- raw invocation ---------------------------------------------------

    def _argv(self, requests: list[dict]) -> list[str]:
        env = self._env
        return [
            str(GYMACT_VENV_PYTHON),
            str(env._bridge_script),
            env._module_path,
            env._class_name,
            env._provider_name,
            json.dumps(env._config),
            json.dumps(requests),
        ]

    def _invoke_once(self, requests: list[dict], attempt_no: int, action: str | None):
        """One real subprocess round-trip, classified. Returns (kind, payload, attempt)."""
        started = time.monotonic()
        try:
            completed = subprocess.run(
                self._argv(requests),
                capture_output=True,
                text=True,
                cwd=str(GYMACT),
                timeout=self._timeout if self._timeout is not None else 120,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            return (
                BRIDGE_TIMEOUT,
                None,
                BridgeAttempt(
                    kind=BRIDGE_TIMEOUT,
                    attempt=attempt_no,
                    action=action,
                    detail=f"gymact bridge exceeded {exc.timeout}s",
                    stdout=_text(exc.stdout),
                    stderr=_text(exc.stderr),
                    elapsed_s=time.monotonic() - started,
                ),
            )
        elapsed = time.monotonic() - started
        if completed.returncode != 0:
            return (
                BRIDGE_SUBPROCESS_FAILED,
                None,
                BridgeAttempt(
                    kind=BRIDGE_SUBPROCESS_FAILED,
                    attempt=attempt_no,
                    action=action,
                    detail=f"gymact bridge exited {completed.returncode}",
                    stdout=completed.stdout,
                    stderr=completed.stderr,
                    returncode=completed.returncode,
                    elapsed_s=elapsed,
                ),
            )
        lines = completed.stdout.strip().splitlines()
        if not lines:
            return (
                BRIDGE_MALFORMED_OUTPUT,
                None,
                BridgeAttempt(
                    kind=BRIDGE_MALFORMED_OUTPUT,
                    attempt=attempt_no,
                    action=action,
                    detail="gymact bridge exited 0 with empty stdout",
                    stdout=completed.stdout,
                    stderr=completed.stderr,
                    returncode=0,
                    elapsed_s=elapsed,
                ),
            )
        try:
            payload = json.loads(lines[-1])
        except json.JSONDecodeError as exc:
            return (
                BRIDGE_MALFORMED_OUTPUT,
                None,
                BridgeAttempt(
                    kind=BRIDGE_MALFORMED_OUTPUT,
                    attempt=attempt_no,
                    action=action,
                    detail=f"last stdout line is not JSON ({exc}); line={lines[-1]!r}",
                    stdout=completed.stdout,
                    stderr=completed.stderr,
                    returncode=0,
                    elapsed_s=elapsed,
                ),
            )
        if payload.get("materialize_failed"):
            return (
                MATERIALIZE_REFUSED,
                payload,
                BridgeAttempt(
                    kind=MATERIALIZE_REFUSED,
                    attempt=attempt_no,
                    action=action,
                    detail=f"materialize refused: {payload.get('reason')}",
                    stdout=completed.stdout,
                    stderr=completed.stderr,
                    returncode=0,
                    elapsed_s=elapsed,
                ),
            )
        return (
            BRIDGE_OK,
            payload,
            BridgeAttempt(
                kind=BRIDGE_OK,
                attempt=attempt_no,
                action=action,
                stdout="",  # success payload is the record; stdout is large
                stderr=completed.stderr,
                returncode=0,
                elapsed_s=elapsed,
            ),
        )

    def _call(self, requests: list[dict], action: str | None = None):
        """Invoke with retries on transient classes only."""
        last = None
        for attempt_no in range(1, self._max_retries + 2):
            kind, payload, attempt = self._invoke_once(requests, attempt_no, action)
            self._record(attempt)
            last = (kind, payload, attempt)
            if kind == BRIDGE_OK or kind not in TRANSIENT_KINDS:
                break
            if self._backoff:
                time.sleep(self._backoff)
        assert last is not None
        return last

    # -- public surface ---------------------------------------------------

    def available_actions(self) -> list[str]:
        """Real actuatable surface. Raises `BridgeFailure` rather than
        returning a silently-empty list when materialization was refused —
        the raw bridge returns `[]`, which reads as "provider has no
        actions" and is indistinguishable from a real empty surface."""
        kind, payload, attempt = self._call([], action=None)
        if kind != BRIDGE_OK:
            raise BridgeFailure(
                kind,
                attempt.detail,
                stdout=attempt.stdout,
                stderr=attempt.stderr,
                returncode=attempt.returncode,
                attempts=list(self.attempts),
            )
        # Delegate arity expansion to the real bridge, which owns
        # `_ACTION_PARAMS` / `_STATIC_PAYLOADS`.
        return self._env.available_actions()

    def payload_for(self, action_id: str) -> dict:
        return self._env.payload_for(action_id)

    def try_action(self, action: str, payload: dict | None = None) -> BridgeResult:
        """Probe one action. Never raises on a refusal — a refusal is an
        answer and is returned as `BridgeResult(kind=PROVIDER_REFUSED)`.

        An unknown binding is classified as `UNKNOWN_CAPABILITY` *before*
        any subprocess runs: the real bridge script's own handling of an
        unknown binding leaves `after_state` unbound and crashes the
        subprocess with `UnboundLocalError`, so probing it would produce
        `BRIDGE_SUBPROCESS_FAILED` and hide the actual cause.
        """
        known = set(self._env.available_actions())
        if action not in known:
            attempt = self._record(
                BridgeAttempt(
                    kind=UNKNOWN_CAPABILITY,
                    attempt=1,
                    action=action,
                    detail=f"{action!r} is not in the provider's real DO surface {sorted(known)}",
                )
            )
            return BridgeResult(UNKNOWN_CAPABILITY, None, [attempt])

        binding, decoded = self._decode(action)
        if payload is None:
            payload = self._env.payload_for(action)
        req = {"action": binding, "action_id": action, "payload": dict(payload)}
        requests = list(self._env._history) + [req]
        kind, out, attempt = self._call(requests, action=action)
        if kind != BRIDGE_OK:
            raise BridgeFailure(
                kind,
                attempt.detail,
                stdout=attempt.stdout,
                stderr=attempt.stderr,
                returncode=attempt.returncode,
                attempts=list(self.attempts),
            )

        record = out["results"][-1]
        self._env._last_episode_id = out.get("episode_id")
        self._env._last_ocel = out.get("ocel_log")
        if record.get("applicable"):
            self._env._history.append(req)
            with self._env._log_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record) + "\n")
            attempt.record = record
            self._rewrite_last(attempt)
            return BridgeResult(BRIDGE_OK, record, [attempt])

        with self._env._log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
        refusal = self._record(
            BridgeAttempt(
                kind=PROVIDER_REFUSED,
                attempt=attempt.attempt,
                action=action,
                detail=f"provider reported applicable=False (standing={record.get('standing')}, reason={record.get('reason')})",
                stdout="",
                stderr=attempt.stderr,
                returncode=0,
                record=record,
            )
        )
        return BridgeResult(PROVIDER_REFUSED, record, [attempt, refusal])

    # -- helpers ----------------------------------------------------------

    def _rewrite_last(self, attempt: BridgeAttempt) -> None:
        """Append the successful record as its own evidence line (the
        first line was written before the record was known)."""
        with self._attempts_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(attempt.to_json(), default=str) + "\n")

    @staticmethod
    def _decode(action: str) -> tuple[str, dict]:
        from .level4_gymact_bridge import decode_action

        return decode_action(action)

    def episode_id(self) -> str | None:
        return self._env.episode_id()

    def episode_ocel_log(self) -> dict | None:
        return self._env.episode_ocel_log()
