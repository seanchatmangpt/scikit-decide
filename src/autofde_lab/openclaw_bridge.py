# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.
"""OpenClaw native-tool CLI and newline-delimited MCP transport."""

from __future__ import annotations

import argparse
import importlib.util
import json
import pathlib
import sys
import time
from collections.abc import Mapping, Sequence
from typing import Any

try:
    from . import openclaw_runtime as runtime
except ImportError:  # Supports direct file loading in the focused verifier.
    path = pathlib.Path(__file__).with_name("openclaw_runtime.py")
    spec = importlib.util.spec_from_file_location("skdecide_openclaw_runtime", path)
    assert spec is not None and spec.loader is not None
    runtime = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runtime)

MCP_PROTOCOL_VERSION = "2025-06-18"
SERVER_NAME = "scikit-decide"
SERVER_VERSION = "0.1.0"

_SUBJECT_SCHEMA = {
    "type": "object",
    "required": ["name"],
    "additionalProperties": False,
    "properties": {
        "name": {"type": "string", "minLength": 1},
        "kwargs": {"type": "object"},
    },
}
_TOOL_SPECS = [
    {
        "name": "catalog",
        "description": "List registered scikit-decide domains and solvers.",
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {"kind": {"enum": ["all", "domains", "solvers"]}},
        },
    },
    {
        "name": "describe",
        "description": "Describe one registered domain or solver.",
        "inputSchema": {
            "type": "object",
            "required": ["kind", "name"],
            "additionalProperties": False,
            "properties": {
                "kind": {"enum": ["domain", "solver"]},
                "name": {"type": "string"},
            },
        },
    },
    {
        "name": "match",
        "description": "Construct a registered domain and list compatible solvers.",
        "inputSchema": {
            "type": "object",
            "required": ["domain"],
            "additionalProperties": False,
            "properties": {"domain": _SUBJECT_SCHEMA},
        },
    },
    {
        "name": "run",
        "description": "Run a bounded rollout using registered subjects only.",
        "inputSchema": {
            "type": "object",
            "required": ["domain"],
            "additionalProperties": False,
            "properties": {
                "domain": _SUBJECT_SCHEMA,
                "solver": _SUBJECT_SCHEMA,
                "solve": {"type": "boolean"},
                "timeout_seconds": {
                    "type": "number",
                    "exclusiveMinimum": 0,
                    "maximum": 600,
                },
                "rollout": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "num_episodes": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 100,
                        },
                        "max_steps": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 10000,
                        },
                    },
                },
            },
        },
    },
]

# Dual registration. `tools/list` advertises BOTH the current
# `autofde_lab_*` names and the legacy `skdecide_*` names, because a caller
# that discovers tools dynamically must keep working, and a caller with a
# hard-coded legacy name must too. Descriptions differ only by a deprecation
# note; input schemas are shared objects, so the two spellings cannot drift.
TOOL_DEFINITIONS = [
    {**spec, "name": runtime.TOOL_NAME_PREFIX + spec["name"]} for spec in _TOOL_SPECS
] + [
    {
        **spec,
        "name": runtime.LEGACY_TOOL_NAME_PREFIX + spec["name"],
        "description": (
            spec["description"]
            + " (legacy name; prefer "
            + runtime.TOOL_NAME_PREFIX
            + spec["name"]
            + ")"
        ),
    }
    for spec in _TOOL_SPECS
]

# Invoked as `python -m autofde_lab.openclaw_bridge`; PROG_NAME is the
# hyphenated display name only (there is no [project.scripts] console script
# yet, so nothing on PATH depends on either spelling).
PROG_NAME = "autofde-lab-openclaw"
LEGACY_PROG_NAME = "skdecide-openclaw"

CATALOG_RESOURCE_URI = "autofde-lab://catalog"
LEGACY_CATALOG_RESOURCE_URI = "skdecide://catalog"
ACCEPTED_CATALOG_RESOURCE_URIS = (
    CATALOG_RESOURCE_URI,
    LEGACY_CATALOG_RESOURCE_URI,
)


def execute_tool(
    name: str, arguments: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    return runtime.execute(name, arguments)


def _mcp_response(request: Mapping[str, Any]) -> dict[str, Any] | None:
    request_id, method = request.get("id"), request.get("method")
    if request_id is None:
        return None
    try:
        if method == "initialize":
            result = {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}, "resources": {}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                "instructions": (
                    "Use registered subjects only; every call returns a receipt."
                ),
            }
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": TOOL_DEFINITIONS}
        elif method == "tools/call":
            params = request.get("params") or {}
            payload = execute_tool(
                str(params.get("name", "")), params.get("arguments") or {}
            )
            result = {
                "content": [
                    {"type": "text", "text": json.dumps(payload, sort_keys=True)}
                ],
                "structuredContent": payload,
                "isError": not payload["ok"],
            }
        elif method == "resources/list":
            result = {
                "resources": [
                    {
                        "uri": CATALOG_RESOURCE_URI,
                        "name": "AutoFDE Lab registry catalog",
                        "mimeType": "application/json",
                    },
                    {
                        "uri": LEGACY_CATALOG_RESOURCE_URI,
                        "name": "AutoFDE Lab registry catalog (legacy URI)",
                        "mimeType": "application/json",
                    },
                ]
            }
        elif method == "resources/read":
            params = request.get("params") or {}
            requested = params.get("uri")
            if requested not in ACCEPTED_CATALOG_RESOURCE_URIS:
                raise runtime.BridgeFailure(
                    "UNKNOWN_RESOURCE",
                    f"Unknown resource: {params.get('uri')}",
                    status="REFUSED:UNKNOWN_RESOURCE",
                )
            payload = execute_tool(
                runtime.TOOL_NAME_PREFIX + "catalog", {"kind": "all"}
            )
            result = {
                "contents": [
                    {
                        # Echo the URI the caller asked for, so a legacy
                        # client's response matches its own request.
                        "uri": requested,
                        "mimeType": "application/json",
                        "text": json.dumps(payload, sort_keys=True),
                    }
                ]
            }
        else:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            }
        return {"jsonrpc": "2.0", "id": request_id, "result": result}
    except runtime.BridgeFailure as exc:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": -32000,
                "message": str(exc),
                "data": {"code": exc.code, "status": exc.status},
            },
        }
    except Exception as exc:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32603, "message": str(exc)},
        }


def serve_mcp() -> int:
    for raw_line in sys.stdin.buffer:
        if not raw_line.strip():
            continue
        try:
            response = _mcp_response(json.loads(raw_line))
        except Exception as exc:
            response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"Parse error: {exc}"},
            }
        if response is not None:
            sys.stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
            sys.stdout.flush()
    return 0


def _write_json(value: Any) -> None:
    sys.stdout.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")


# Receipt subject for the out-of-process worker. Held at the legacy
# spelling deliberately: it is written into call-integrity receipts, and
# both tool names dispatch to this one worker, so a stable label keeps
# receipts from the two spellings comparable to each other and to receipts
# already emitted.
_WORKER_RECEIPT_SUBJECT = runtime.LEGACY_TOOL_NAME_PREFIX + "run"


def _worker(arguments: Mapping[str, Any]) -> dict[str, Any]:
    started = time.monotonic_ns()
    try:
        result = runtime.jsonable(runtime.run_direct(arguments))
        return {
            "ok": True,
            "status": "ALIVE",
            "result": result,
            "receipt": runtime.receipt(
                operation="worker.run",
                subject=_WORKER_RECEIPT_SUBJECT,
                arguments=arguments,
                started_ns=started,
                status="ALIVE",
                output=result,
            ),
        }
    except runtime.BridgeFailure as exc:
        error = {"code": exc.code, "message": str(exc)}
        return {
            "ok": False,
            "status": exc.status,
            "error": error,
            "receipt": runtime.receipt(
                operation="worker.run",
                subject=_WORKER_RECEIPT_SUBJECT,
                arguments=arguments,
                started_ns=started,
                status=exc.status,
                error=error,
            ),
        }
    except Exception as exc:
        error = {"code": "UNEXPECTED_EXECUTION_FAILURE", "message": str(exc)}
        return {
            "ok": False,
            "status": "BUILD_BROKEN",
            "error": error,
            "receipt": runtime.receipt(
                operation="worker.run",
                subject=_WORKER_RECEIPT_SUBJECT,
                arguments=arguments,
                started_ns=started,
                status="BUILD_BROKEN",
                error=error,
            ),
        }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog=PROG_NAME)
    sub = parser.add_subparsers(dest="command", required=True)
    inspect_parser = sub.add_parser("inspect")
    inspect_parser.add_argument("--catalog", action="store_true")
    call_parser = sub.add_parser("call")
    call_parser.add_argument("tool", choices=sorted(runtime.HANDLERS))
    call_parser.add_argument("--arguments", default="{}")
    sub.add_parser("mcp")
    sub.add_parser("_worker", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.command == "inspect":
        payload: dict[str, Any] = {
            "name": SERVER_NAME,
            "version": SERVER_VERSION,
            "mcp_protocol": MCP_PROTOCOL_VERSION,
            "tools": TOOL_DEFINITIONS,
        }
        if args.catalog:
            payload["catalog"] = execute_tool(
                runtime.TOOL_NAME_PREFIX + "catalog", {"kind": "all"}
            )
        _write_json(payload)
        return 0
    if args.command == "call":
        try:
            call_args = json.loads(args.arguments)
        except json.JSONDecodeError as exc:
            parser.error(f"--arguments must be valid JSON: {exc}")
        payload = execute_tool(args.tool, call_args)
        _write_json(payload)
        return 0 if payload["ok"] else 1
    if args.command == "mcp":
        return serve_mcp()
    if args.command == "_worker":
        payload = _worker(json.load(sys.stdin))
        _write_json(payload)
        return 0 if payload["ok"] else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
