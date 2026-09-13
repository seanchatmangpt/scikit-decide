# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from __future__ import annotations

import importlib.util
import json
import pathlib

MODULE_PATH = (
    pathlib.Path(__file__).parents[1] / "src" / "autofde_lab" / "openclaw_bridge.py"
)
SPEC = importlib.util.spec_from_file_location("openclaw_bridge_under_test", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
bridge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge)


class FakeDomain:
    def __init__(self, size=1):
        self.size = size


class FakeSolver:
    def __init__(self, domain_factory, bias=0):
        self.domain_factory = domain_factory
        self.bias = bias
        self.solved = False

    @classmethod
    def check_domain(cls, domain):
        return isinstance(domain, FakeDomain)

    def solve(self):
        self.solved = True


class FakeUtils:
    @staticmethod
    def get_registered_domains():
        return ["FakeDomain"]

    @staticmethod
    def get_registered_solvers():
        return ["FakeSolver"]

    @staticmethod
    def load_registered_domain(name):
        return FakeDomain if name == "FakeDomain" else None

    @staticmethod
    def load_registered_solver(name):
        return FakeSolver if name == "FakeSolver" else None

    @staticmethod
    def match_solvers(domain):
        return [FakeSolver] if FakeSolver.check_domain(domain) else []

    @staticmethod
    def rollout(**kwargs):
        domain = kwargs["domain"]
        solver = kwargs["solver"]
        return [([{"size": domain.size}], [solver.bias if solver else 0], [1.0])]


def setup_module():
    bridge.runtime._load_utils = lambda: FakeUtils
    bridge.runtime._entry_points = lambda group: {
        "FakeDomain": {
            "name": "FakeDomain",
            "group": group,
            "value": "fake:FakeDomain",
        },
        "FakeSolver": {
            "name": "FakeSolver",
            "group": group,
            "value": "fake:FakeSolver",
        },
    }


def test_catalog_and_receipt_are_deterministically_shaped():
    payload = bridge.execute_tool("skdecide_catalog", {"kind": "all"})
    assert payload["ok"] is True
    assert payload["status"] == "ALIVE"
    assert payload["result"]["domains"][0]["name"] == "FakeDomain"
    assert len(payload["receipt"]["input_sha256"]) == 64
    assert len(payload["receipt"]["output_sha256"]) == 64


def test_unregistered_subject_is_a_typed_refusal():
    payload = bridge.execute_tool(
        "skdecide_describe", {"kind": "domain", "name": "Missing"}
    )
    assert payload["ok"] is False
    assert payload["status"] == "REFUSED:UNREGISTERED_SUBJECT"
    assert payload["error"]["code"] == "UNREGISTERED_SUBJECT"
    assert payload["receipt"]["status"] == payload["status"]


def test_match_uses_only_registered_subjects():
    payload = bridge.execute_tool(
        "skdecide_match", {"domain": {"name": "FakeDomain", "kwargs": {"size": 3}}}
    )
    assert payload["ok"] is True
    assert payload["result"] == {"domain": "FakeDomain", "solvers": ["FakeSolver"]}


def test_direct_run_constructs_solves_and_rolls_out():
    result = bridge.runtime.run_direct(
        {
            "domain": {"name": "FakeDomain", "kwargs": {"size": 5}},
            "solver": {"name": "FakeSolver", "kwargs": {"bias": 7}},
            "rollout": {"num_episodes": 1, "max_steps": 4},
        }
    )
    assert result["domain"] == "FakeDomain"
    assert result["solver"] == "FakeSolver"
    assert result["episodes"][0][0][0] == {"size": 5}
    assert result["episodes"][0][1] == [7]


def test_mcp_lifecycle_and_tool_call():
    initialize = bridge._mcp_response(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": bridge.MCP_PROTOCOL_VERSION},
        }
    )
    assert initialize["result"]["serverInfo"]["name"] == "scikit-decide"

    listed = bridge._mcp_response({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = {tool["name"] for tool in listed["result"]["tools"]}
    # Dual registration: the legacy names are still advertised -- an existing
    # OpenClaw plugin or pinned agent config calls them and cannot be seen
    # from here -- and the current names are advertised alongside.
    assert names == {
        "skdecide_catalog",
        "skdecide_describe",
        "skdecide_match",
        "skdecide_run",
        "autofde_lab_catalog",
        "autofde_lab_describe",
        "autofde_lab_match",
        "autofde_lab_run",
    }

    called = bridge._mcp_response(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "skdecide_catalog", "arguments": {"kind": "domains"}},
        }
    )
    structured = called["result"]["structuredContent"]
    assert structured["ok"] is True
    assert json.loads(called["result"]["content"][0]["text"])["status"] == "ALIVE"
