"""Shell-free invocation of external planner/validator engines, with a receipted,
typed outcome for every run instead of a bare exception.

Ported pattern from mfw-planner's ``run_engine``/``probe_engine``
(``/Users/sac/mfw/mfw-planner/src/runner.rs``). Every invocation — success, timeout,
non-zero exit, or missing binary — produces a distinct ``EngineOutcome`` and an
``EngineRunReceipt`` recording exactly what ran and what was observed, mirroring mfw's
``bounded``/``tool_failed``/``no_candidate`` taxonomy.
"""

from __future__ import annotations

import hashlib
import subprocess
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .config import EngineConfig, OutputMode


class EngineOutcome(str, Enum):
    """The receipted result of one engine invocation."""

    SUCCESS = "success"
    """Process exited with a success code and produced the expected output."""

    NO_CANDIDATE = "no_candidate"
    """Process exited with a success code but produced no plan (e.g. empty/missing
    plan file under ``output_mode = "file"``) — a distinct outcome from failure,
    matching mfw's discipline that "success exit, no plan" is not the same claim as
    "solver failed"."""

    TOOL_FAILED = "tool_failed"
    """Process exited with a non-success code."""

    BOUNDED = "bounded"
    """Process was killed after exceeding the timeout — bounded, not crashed."""

    MISSING_BINARY = "missing_binary"
    """``program`` was not found on PATH / not executable."""


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hash_file(path: Path) -> str | None:
    if not path.exists():
        return None
    return _hash_bytes(path.read_bytes())


@dataclass(frozen=True)
class EngineRunReceipt:
    """Bounded, hashed evidence of one engine invocation. Never contains raw
    stdout/stderr content — only hashes and bounded metadata — so receipts stay small
    and reproducible-by-hash rather than reproducible-by-diff."""

    role: str
    program: str
    argv: tuple[str, ...]
    outcome: EngineOutcome
    exit_code: int | None
    duration_ms: int
    stdout_hash: str
    stderr_hash: str
    plan_hash: str | None

    def is_success(self) -> bool:
        return self.outcome == EngineOutcome.SUCCESS


def probe_engine(cfg: EngineConfig, *, timeout_s: float = 10.0) -> EngineRunReceipt:
    """Run ``cfg.version_args`` to confirm the engine binary is present/invocable.

    Does not touch ``output_mode`` — a probe never expects a plan.
    """
    argv = [cfg.program, *cfg.version_args]
    start = time.monotonic()
    try:
        proc = subprocess.run(
            argv, capture_output=True, timeout=timeout_s, shell=False
        )
    except FileNotFoundError:
        return EngineRunReceipt(
            role=cfg.role,
            program=cfg.program,
            argv=tuple(argv),
            outcome=EngineOutcome.MISSING_BINARY,
            exit_code=None,
            duration_ms=int((time.monotonic() - start) * 1000),
            stdout_hash=_hash_bytes(b""),
            stderr_hash=_hash_bytes(b""),
            plan_hash=None,
        )
    except subprocess.TimeoutExpired as exc:
        return EngineRunReceipt(
            role=cfg.role,
            program=cfg.program,
            argv=tuple(argv),
            outcome=EngineOutcome.BOUNDED,
            exit_code=None,
            duration_ms=int((time.monotonic() - start) * 1000),
            stdout_hash=_hash_bytes(exc.stdout or b""),
            stderr_hash=_hash_bytes(exc.stderr or b""),
            plan_hash=None,
        )
    duration_ms = int((time.monotonic() - start) * 1000)
    outcome = (
        EngineOutcome.SUCCESS
        if proc.returncode in cfg.success_codes
        else EngineOutcome.TOOL_FAILED
    )
    return EngineRunReceipt(
        role=cfg.role,
        program=cfg.program,
        argv=tuple(argv),
        outcome=outcome,
        exit_code=proc.returncode,
        duration_ms=duration_ms,
        stdout_hash=_hash_bytes(proc.stdout),
        stderr_hash=_hash_bytes(proc.stderr),
        plan_hash=None,
    )


def run_engine(
    cfg: EngineConfig,
    *,
    domain: str | Path,
    problem: str | Path,
    plan: str | Path | None = None,
    timeout_s: float = 60.0,
) -> EngineRunReceipt:
    """Invoke ``cfg`` against a domain/problem pair, substituting placeholders in
    ``cfg.args`` and returning a receipted, typed outcome.

    ``plan`` must be supplied whenever ``cfg.args`` references ``{plan}`` or
    ``cfg.output_mode == OutputMode.FILE`` (the two are usually the same file: the
    solver writes the plan there, or the validator reads a plan from there).
    """
    if cfg.output_mode == OutputMode.FILE and plan is None:
        raise ValueError(
            f"engine role {cfg.role!r} has output_mode=file but no plan path was given"
        )
    plan_path = Path(plan) if plan is not None else None
    resolved = cfg.resolve_args(domain=domain, problem=problem, plan=plan)
    argv = [cfg.program, *resolved]

    start = time.monotonic()
    try:
        proc = subprocess.run(
            argv, capture_output=True, timeout=timeout_s, shell=False
        )
    except FileNotFoundError:
        return EngineRunReceipt(
            role=cfg.role,
            program=cfg.program,
            argv=tuple(argv),
            outcome=EngineOutcome.MISSING_BINARY,
            exit_code=None,
            duration_ms=int((time.monotonic() - start) * 1000),
            stdout_hash=_hash_bytes(b""),
            stderr_hash=_hash_bytes(b""),
            plan_hash=None,
        )
    except subprocess.TimeoutExpired as exc:
        return EngineRunReceipt(
            role=cfg.role,
            program=cfg.program,
            argv=tuple(argv),
            outcome=EngineOutcome.BOUNDED,
            exit_code=None,
            duration_ms=int((time.monotonic() - start) * 1000),
            stdout_hash=_hash_bytes(exc.stdout or b""),
            stderr_hash=_hash_bytes(exc.stderr or b""),
            plan_hash=None,
        )
    duration_ms = int((time.monotonic() - start) * 1000)

    if proc.returncode not in cfg.success_codes:
        return EngineRunReceipt(
            role=cfg.role,
            program=cfg.program,
            argv=tuple(argv),
            outcome=EngineOutcome.TOOL_FAILED,
            exit_code=proc.returncode,
            duration_ms=duration_ms,
            stdout_hash=_hash_bytes(proc.stdout),
            stderr_hash=_hash_bytes(proc.stderr),
            plan_hash=None,
        )

    # Success exit code. Decide SUCCESS vs NO_CANDIDATE based on output_mode.
    plan_hash: str | None = None
    outcome = EngineOutcome.SUCCESS
    if cfg.output_mode == OutputMode.FILE:
        assert plan_path is not None
        plan_hash = _hash_file(plan_path)
        if plan_hash is None:
            outcome = EngineOutcome.NO_CANDIDATE
    elif cfg.output_mode == OutputMode.STDOUT:
        if not proc.stdout.strip():
            outcome = EngineOutcome.NO_CANDIDATE
        plan_hash = _hash_bytes(proc.stdout)
    # OutputMode.NONE: no candidate to check (e.g. a validator role) — SUCCESS stands.

    return EngineRunReceipt(
        role=cfg.role,
        program=cfg.program,
        argv=tuple(argv),
        outcome=outcome,
        exit_code=proc.returncode,
        duration_ms=duration_ms,
        stdout_hash=_hash_bytes(proc.stdout),
        stderr_hash=_hash_bytes(proc.stderr),
        plan_hash=plan_hash,
    )
