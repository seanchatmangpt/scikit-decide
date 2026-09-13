# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.
"""Bounded, receipted execution core for the OpenClaw bridge."""

from __future__ import annotations

import dataclasses
import datetime as dt
import enum
import hashlib
import inspect
import json
import os
import subprocess
import sys
import time
import traceback
import uuid
from collections.abc import Mapping, Sequence
from importlib import metadata
from typing import Any, Callable

MAX_EPISODES = 100
MAX_STEPS = 10_000
MAX_TIMEOUT_SECONDS = 600.0
MAX_RESULT_BYTES = 4 * 1024 * 1024


class BridgeFailure(RuntimeError):
    def __init__(self, code: str, message: str, *, status: str = "BUILD_BROKEN"):
        super().__init__(message)
        self.code = code
        self.status = status


def jsonable(value: Any, depth: int = 0) -> Any:
    if depth > 10:
        return {"type": type(value).__qualname__, "repr": repr(value)}
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, enum.Enum):
        return jsonable(value.value, depth + 1)
    if dataclasses.is_dataclass(value):
        return jsonable(dataclasses.asdict(value), depth + 1)
    if isinstance(value, Mapping):
        return {str(k): jsonable(v, depth + 1) for k, v in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [jsonable(item, depth + 1) for item in value]
    if hasattr(value, "tolist"):
        try:
            return jsonable(value.tolist(), depth + 1)
        except Exception:
            pass
    return {
        "type": f"{type(value).__module__}.{type(value).__qualname__}",
        "repr": repr(value),
    }


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=jsonable,
    ).encode()


def receipt(
    *,
    operation: str,
    subject: str,
    arguments: Mapping[str, Any],
    started_ns: int,
    status: str,
    output: Any = None,
    error: Any = None,
) -> dict[str, Any]:
    observed = output if error is None else error
    return {
        "receipt_id": str(uuid.uuid4()),
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "operation": operation,
        "subject": subject,
        "status": status,
        "input_sha256": hashlib.sha256(canonical_bytes(arguments)).hexdigest(),
        "output_sha256": hashlib.sha256(canonical_bytes(observed)).hexdigest(),
        "duration_ms": round((time.monotonic_ns() - started_ns) / 1_000_000, 3),
        "pid": os.getpid(),
        "python": sys.version.split()[0],
    }


def _load_utils() -> Any:
    try:
        from autofde_lab import utils
    except Exception as exc:
        raise BridgeFailure(
            "SKDECIDE_IMPORT_FAILED", f"Could not import autofde_lab.utils: {exc}"
        ) from exc
    return utils


def _entry_points(group: str) -> dict[str, dict[str, Any]]:
    return {
        entry.name: {
            "name": entry.name,
            "value": entry.value,
            "group": entry.group,
            "extras": sorted(entry.extras),
        }
        for entry in metadata.entry_points(group=group)
    }


def catalog(arguments: Mapping[str, Any]) -> dict[str, Any]:
    kind = arguments.get("kind", "all")
    if kind not in {"all", "domains", "solvers"}:
        raise BridgeFailure(
            "INVALID_KIND",
            "kind must be one of: all, domains, solvers",
            status="REFUSED:INVALID_ARGUMENT",
        )
    utils = _load_utils()
    result: dict[str, Any] = {}
    for label, group, names in (
        ("domains", "autofde_lab.domains", utils.get_registered_domains),
        ("solvers", "autofde_lab.solvers", utils.get_registered_solvers),
    ):
        if kind in {"all", label}:
            entries = _entry_points(group)
            result[label] = [
                entries.get(name, {"name": name}) for name in sorted(names())
            ]
    return result


def load_registered(kind: str, name: str) -> type[Any]:
    utils = _load_utils()
    if kind == "domain":
        names, loader = utils.get_registered_domains, utils.load_registered_domain
    elif kind == "solver":
        names, loader = utils.get_registered_solvers, utils.load_registered_solver
    else:
        raise BridgeFailure(
            "INVALID_KIND",
            "kind must be domain or solver",
            status="REFUSED:INVALID_ARGUMENT",
        )
    if name not in set(names()):
        raise BridgeFailure(
            "UNREGISTERED_SUBJECT",
            f"{kind} {name!r} is not registered",
            status="REFUSED:UNREGISTERED_SUBJECT",
        )
    loaded = loader(name)
    if loaded is None:
        raise BridgeFailure(
            "REGISTERED_SUBJECT_LOAD_FAILED",
            f"{kind} {name!r} is registered but could not be loaded",
        )
    return loaded


def describe(arguments: Mapping[str, Any]) -> dict[str, Any]:
    kind, name = str(arguments.get("kind", "")), str(arguments.get("name", ""))
    if not name:
        raise BridgeFailure(
            "MISSING_NAME", "name is required", status="REFUSED:INVALID_ARGUMENT"
        )
    cls = load_registered(kind, name)
    try:
        signature = str(inspect.signature(cls))
    except (TypeError, ValueError):
        signature = "<unavailable>"
    return {
        "kind": kind,
        "name": name,
        "module": cls.__module__,
        "qualname": cls.__qualname__,
        "signature": signature,
        "doc": inspect.getdoc(cls) or "",
    }


def validated_spec(value: Any, label: str) -> tuple[str, dict[str, Any]]:
    if not isinstance(value, Mapping):
        raise BridgeFailure(
            "INVALID_SPEC",
            f"{label} must be an object",
            status="REFUSED:INVALID_ARGUMENT",
        )
    name, kwargs = value.get("name"), value.get("kwargs", {})
    if not isinstance(name, str) or not name:
        raise BridgeFailure(
            "INVALID_SPEC",
            f"{label}.name must be a non-empty string",
            status="REFUSED:INVALID_ARGUMENT",
        )
    if not isinstance(kwargs, Mapping):
        raise BridgeFailure(
            "INVALID_SPEC",
            f"{label}.kwargs must be an object",
            status="REFUSED:INVALID_ARGUMENT",
        )
    return name, dict(kwargs)


def domain_factory(name: str, kwargs: Mapping[str, Any]) -> Callable[[], Any]:
    cls = load_registered("domain", name)
    return lambda: cls(**dict(kwargs))


def match_direct(arguments: Mapping[str, Any]) -> dict[str, Any]:
    name, kwargs = validated_spec(arguments.get("domain"), "domain")
    domain = domain_factory(name, kwargs)()
    utils = _load_utils()
    registered = {
        cls: solver_name
        for solver_name in utils.get_registered_solvers()
        if (cls := utils.load_registered_solver(solver_name)) is not None
    }
    return {
        "domain": name,
        "solvers": sorted(
            registered.get(cls, cls.__name__) for cls in utils.match_solvers(domain)
        ),
    }


def construct_solver(
    cls: type[Any], factory: Callable[[], Any], kwargs: Mapping[str, Any]
) -> Any:
    try:
        signature = inspect.signature(cls)
    except (TypeError, ValueError):
        signature = None
    if signature is None or "domain_factory" in signature.parameters:
        return cls(domain_factory=factory, **dict(kwargs))
    return cls(factory, **dict(kwargs))


def run_direct(arguments: Mapping[str, Any]) -> dict[str, Any]:
    domain_name, domain_kwargs = validated_spec(arguments.get("domain"), "domain")
    rollout = arguments.get("rollout", {})
    if not isinstance(rollout, Mapping):
        raise BridgeFailure(
            "INVALID_ROLLOUT",
            "rollout must be an object",
            status="REFUSED:INVALID_ARGUMENT",
        )
    episodes = int(rollout.get("num_episodes", 1))
    max_steps = int(rollout.get("max_steps", 100))
    if not 1 <= episodes <= MAX_EPISODES:
        raise BridgeFailure(
            "EPISODE_LIMIT",
            f"num_episodes must be between 1 and {MAX_EPISODES}",
            status="REFUSED:BOUND_EXCEEDED",
        )
    if not 1 <= max_steps <= MAX_STEPS:
        raise BridgeFailure(
            "STEP_LIMIT",
            f"max_steps must be between 1 and {MAX_STEPS}",
            status="REFUSED:BOUND_EXCEEDED",
        )
    factory = domain_factory(domain_name, domain_kwargs)
    domain = factory()
    solver = None
    solver_name = None
    if arguments.get("solver") is not None:
        solver_name, solver_kwargs = validated_spec(arguments["solver"], "solver")
        solver = construct_solver(
            load_registered("solver", solver_name), factory, solver_kwargs
        )
        if bool(arguments.get("solve", True)):
            solver.solve()
    episodes_result = _load_utils().rollout(
        domain=domain,
        solver=solver,
        num_episodes=episodes,
        max_steps=max_steps,
        render=False,
        verbose=False,
        return_episodes=True,
    )
    return {
        "domain": domain_name,
        "solver": solver_name,
        "num_episodes": episodes,
        "max_steps": max_steps,
        "episodes": jsonable(episodes_result),
    }


def run_bounded(arguments: Mapping[str, Any]) -> dict[str, Any]:
    timeout = float(arguments.get("timeout_seconds", 120.0))
    if not 0 < timeout <= MAX_TIMEOUT_SECONDS:
        raise BridgeFailure(
            "TIMEOUT_LIMIT",
            f"timeout_seconds must be in (0, {MAX_TIMEOUT_SECONDS}]",
            status="REFUSED:BOUND_EXCEEDED",
        )
    worker_args = dict(arguments)
    worker_args.pop("timeout_seconds", None)
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "autofde_lab.openclaw_bridge", "_worker"],
            input=canonical_bytes(worker_args),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise BridgeFailure("EXECUTION_TIMEOUT", f"Execution exceeded {timeout}s") from exc
    if len(completed.stdout) + len(completed.stderr) > MAX_RESULT_BYTES:
        raise BridgeFailure(
            "RESULT_LIMIT",
            f"Bridge output exceeded {MAX_RESULT_BYTES} bytes",
            status="REFUSED:BOUND_EXCEEDED",
        )
    try:
        payload = json.loads(completed.stdout)
    except Exception as exc:
        detail = completed.stderr.decode(errors="replace")[-4000:]
        raise BridgeFailure(
            "WORKER_PROTOCOL_FAILURE",
            f"Worker returned invalid JSON (exit={completed.returncode}): {detail}",
        ) from exc
    if not payload.get("ok"):
        error = payload.get("error") or {}
        raise BridgeFailure(
            str(error.get("code", "WORKER_FAILURE")),
            str(error.get("message", "Worker failed")),
            status=str(payload.get("status", "BUILD_BROKEN")),
        )
    return {"worker_receipt": payload["receipt"], **payload["result"]}


# MCP tool names are an external protocol contract: an OpenClaw plugin, a
# skill file, or a pinned agent config elsewhere calls them by name, and
# nothing in this repository can observe those callers. Renaming a tool
# therefore breaks a caller we cannot see, with an UNKNOWN_TOOL refusal as
# the only symptom. Both spellings are registered against the SAME handler
# object -- not a copy, not a wrapper -- so the two names cannot drift into
# different behaviour. The legacy names are the current contract and are not
# scheduled for removal here.
_CANONICAL_HANDLERS: dict[str, Callable[[Mapping[str, Any]], Any]] = {
    "catalog": catalog,
    "describe": describe,
    "match": match_direct,
    "run": run_bounded,
}

TOOL_NAME_PREFIX = "autofde_lab_"
LEGACY_TOOL_NAME_PREFIX = "skdecide_"

HANDLERS: dict[str, Callable[[Mapping[str, Any]], Any]] = {
    prefix + suffix: handler
    for suffix, handler in _CANONICAL_HANDLERS.items()
    for prefix in (TOOL_NAME_PREFIX, LEGACY_TOOL_NAME_PREFIX)
}

#: Legacy -> current tool name, for callers that want to migrate.
TOOL_NAME_ALIASES: dict[str, str] = {
    LEGACY_TOOL_NAME_PREFIX + suffix: TOOL_NAME_PREFIX + suffix
    for suffix in _CANONICAL_HANDLERS
}


def execute(name: str, arguments: Mapping[str, Any] | None = None) -> dict[str, Any]:
    args, started = dict(arguments or {}), time.monotonic_ns()
    try:
        if name not in HANDLERS:
            raise BridgeFailure(
                "UNKNOWN_TOOL", f"Unknown tool: {name}", status="REFUSED:UNKNOWN_TOOL"
            )
        result = jsonable(HANDLERS[name](args))
        return {
            "ok": True,
            "status": "ALIVE",
            "result": result,
            "receipt": receipt(
                operation="tool.call",
                subject=name,
                arguments=args,
                started_ns=started,
                status="ALIVE",
                output=result,
            ),
        }
    except BridgeFailure as exc:
        error = {"code": exc.code, "message": str(exc)}
        return {
            "ok": False,
            "status": exc.status,
            "error": error,
            "receipt": receipt(
                operation="tool.call",
                subject=name,
                arguments=args,
                started_ns=started,
                status=exc.status,
                error=error,
            ),
        }
    except Exception as exc:
        error = {
            "code": "UNEXPECTED_EXECUTION_FAILURE",
            "message": str(exc),
            "type": f"{type(exc).__module__}.{type(exc).__qualname__}",
        }
        if os.environ.get("SKDECIDE_OPENCLAW_DEBUG") == "1":
            error["traceback"] = traceback.format_exc()
        return {
            "ok": False,
            "status": "BUILD_BROKEN",
            "error": error,
            "receipt": receipt(
                operation="tool.call",
                subject=name,
                arguments=args,
                started_ns=started,
                status="BUILD_BROKEN",
                error=error,
            ),
        }
