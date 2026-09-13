# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""MCP tool names and resource URIs are an external protocol contract.

`integrations/openclaw/` calls these tools by name from TypeScript, a skill
file instructs an agent to call them by name, and an operator's pinned
config may name them too -- none of which this repository can observe. A
rename therefore breaks a caller that is invisible from here, and the only
symptom is a `REFUSED:UNKNOWN_TOOL` at someone else's runtime.

So the rename is additive: both spellings are registered, and these tests
pin that the legacy ones keep working and that the two spellings cannot
diverge in behaviour.
"""

from __future__ import annotations

import pytest

from autofde_lab import openclaw_bridge as bridge
from autofde_lab import openclaw_runtime as runtime

_SUFFIXES = ["catalog", "describe", "match", "run"]


@pytest.mark.parametrize("suffix", _SUFFIXES)
def test_both_spellings_dispatch_to_the_same_handler_object(suffix):
    """Identity, not equality.

    Two entries that merely behave the same today can drift tomorrow. Being
    the same object makes drift impossible rather than merely untested.
    """
    legacy = runtime.HANDLERS[runtime.LEGACY_TOOL_NAME_PREFIX + suffix]
    current = runtime.HANDLERS[runtime.TOOL_NAME_PREFIX + suffix]
    assert legacy is current


@pytest.mark.parametrize("suffix", _SUFFIXES)
def test_both_spellings_are_advertised(suffix):
    names = {tool["name"] for tool in bridge.TOOL_DEFINITIONS}
    assert runtime.LEGACY_TOOL_NAME_PREFIX + suffix in names
    assert runtime.TOOL_NAME_PREFIX + suffix in names


@pytest.mark.parametrize("suffix", _SUFFIXES)
def test_input_schemas_are_identical_across_spellings(suffix):
    by_name = {tool["name"]: tool for tool in bridge.TOOL_DEFINITIONS}
    legacy = by_name[runtime.LEGACY_TOOL_NAME_PREFIX + suffix]
    current = by_name[runtime.TOOL_NAME_PREFIX + suffix]
    assert legacy["inputSchema"] == current["inputSchema"]


def test_unknown_tool_is_still_refused():
    """Anti-vacuity: dual registration must not accept everything."""
    payload = bridge.execute_tool("autofde_lab_nonexistent", {})
    assert payload["ok"] is False
    assert payload["status"] == "REFUSED:UNKNOWN_TOOL"


@pytest.mark.parametrize(
    "uri", ["autofde-lab://catalog", "skdecide://catalog"]
)
def test_both_catalog_uris_read(uri):
    response = bridge._mcp_response(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "resources/read",
            "params": {"uri": uri},
        }
    )
    contents = response["result"]["contents"][0]
    # The response echoes the URI the caller asked for, so a legacy client
    # matching request to response still matches.
    assert contents["uri"] == uri
    assert contents["mimeType"] == "application/json"


def test_an_unknown_uri_is_still_refused():
    response = bridge._mcp_response(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "resources/read",
            "params": {"uri": "autofde-lab://not-a-resource"},
        }
    )
    assert "error" in response or response["result"]["isError"]


def test_both_catalog_uris_are_advertised():
    response = bridge._mcp_response(
        {"jsonrpc": "2.0", "id": 1, "method": "resources/list"}
    )
    uris = {r["uri"] for r in response["result"]["resources"]}
    assert uris == set(bridge.ACCEPTED_CATALOG_RESOURCE_URIS)


@pytest.mark.parametrize("suffix", ["catalog", "describe"])
def test_legacy_and_current_calls_produce_the_same_result_payload(suffix):
    args = {"kind": "domains"} if suffix == "catalog" else {
        "kind": "domain",
        "name": "Maze",
    }
    legacy = bridge.execute_tool(runtime.LEGACY_TOOL_NAME_PREFIX + suffix, args)
    current = bridge.execute_tool(runtime.TOOL_NAME_PREFIX + suffix, args)
    assert legacy["ok"] is True
    assert legacy["result"] == current["result"]
