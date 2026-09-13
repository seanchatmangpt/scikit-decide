# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.
"""Minimal stdlib HTTP wrapper around the OpenClaw MCP JSON-RPC bridge.

`openclaw_bridge.serve_mcp()` speaks newline-delimited JSON-RPC over
stdin/stdout, which is the right transport for a locally-spawned MCP
client but cannot be reached over a Kubernetes Service ClusterIP. This
module exposes the exact same dispatch (`openclaw_bridge._mcp_response`,
unmodified, imported directly -- not reimplemented, not a stub) behind a
single HTTP endpoint so platform-console can reach it from a separate
container:

  POST /rpc   body: one JSON-RPC 2.0 request object     -> JSON-RPC response
  GET  /healthz                                          -> 200 {"status":"ok"}

Each request is dispatched in-process against `_mcp_response` -- the
identical function `python -m autofde_lab.openclaw_bridge mcp` uses, so
tools/list, tools/call, resources/read, etc. all come from the real
`autofde_lab.openclaw_runtime` catalog/execute dispatch, not a
reimplementation of it. No persistent stdio pipe management, no
subprocess-per-request: the runtime module (and the domain/solver
registry `catalog()` reads via `importlib.metadata.entry_points`) is
already imported once at process start, same as the stdio server.
"""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from autofde_lab import openclaw_bridge as bridge

MAX_BODY_BYTES = 4 * 1024 * 1024  # matches openclaw_runtime.MAX_RESULT_BYTES


class _Handler(BaseHTTPRequestHandler):
    server_version = "autofde-lab-openclaw-http/1.0"

    def log_message(self, fmt: str, *args) -> None:  # quiet, structured-enough default
        pass

    def _write_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 (stdlib method name)
        if self.path == "/healthz":
            self._write_json(200, {"status": "ok"})
            return
        self._write_json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802 (stdlib method name)
        if self.path != "/rpc":
            self._write_json(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0 or length > MAX_BODY_BYTES:
            self._write_json(
                400,
                {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32600, "message": "invalid or oversized body"},
                },
            )
            return
        raw = self.rfile.read(length)
        try:
            request = json.loads(raw)
        except Exception as exc:  # real parse error, not fabricated
            self._write_json(
                400,
                {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": f"Parse error: {exc}"},
                },
            )
            return
        response = bridge._mcp_response(request)  # real dispatch, same as stdio server
        if response is None:
            # Notification (no "id") -- JSON-RPC has no response; ack with 204.
            self.send_response(204)
            self.end_headers()
            return
        self._write_json(200, response)


def main() -> int:
    port = int(os.environ.get("PORT", "8090"))
    host = os.environ.get("BIND_HOST", "0.0.0.0")
    server = ThreadingHTTPServer((host, port), _Handler)
    server.serve_forever()
    return 0  # pragma: no cover -- serve_forever() only returns on shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
