#!/usr/bin/env python3
"""Isolated stdio worker for the AutoFDE SELECT-only discovery planner."""

from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

PROTOCOL = "urn:autofde-lab:discovery-worker:v1"


def _load_discovery() -> ModuleType:
    path = Path(__file__).with_name("discovery.py")
    spec = importlib.util.spec_from_file_location("_autofde_isolated_discovery", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("DISCOVERY_MODULE_LOAD_REFUSED")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _read_message() -> dict[str, Any]:
    line = sys.stdin.readline()
    if not line:
        raise RuntimeError("DISCOVERY_PROTOCOL_EOF")
    value = json.loads(line)
    if not isinstance(value, dict):
        raise TypeError("DISCOVERY_PROTOCOL_OBJECT_REQUIRED")
    return value


def _write_message(value: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def _receipt_digest(receipt_ids: tuple[str, ...]) -> str:
    payload = json.dumps(list(receipt_ids), separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


async def _run() -> int:
    discovery = _load_discovery()
    _write_message(
        {
            "type": "ready",
            "protocol": PROTOCOL,
            "isolated": bool(sys.flags.isolated),
            "cwd_sources": sorted(path.name for path in Path.cwd().glob("*.py")),
            "sys_path": list(sys.path),
            "environment_keys": sorted(os.environ),
        }
    )

    request = _read_message()
    if request.get("type") != "challenge":
        raise ValueError("DISCOVERY_CHALLENGE_REQUIRED")

    challenge = discovery.DiscoveryChallenge(
        subject=request["subject"],
        initial_facts=frozenset(request["initial_facts"]),
        goal_facts=frozenset(request["goal_facts"]),
        action_ids=tuple(request["action_ids"]),
        max_states=int(request.get("max_states", 100_000)),
        max_probes=int(request.get("max_probes", 1_000_000)),
    )

    async def probe(prefix: tuple[str, ...], action_id: str):
        _write_message(
            {
                "type": "probe",
                "prefix": list(prefix),
                "action_id": action_id,
            }
        )
        response = _read_message()
        if response.get("type") != "probe_result":
            raise ValueError("DISCOVERY_PROBE_RESULT_REQUIRED")
        if (
            response.get("action_id") != action_id
            or tuple(response.get("prefix", ())) != prefix
        ):
            raise ValueError("DISCOVERY_PROBE_RESULT_IDENTITY_MISMATCH")
        return discovery.ProbeEvidence(
            action_id=action_id,
            prefix=prefix,
            accepted=bool(response["accepted"]),
            before_facts=frozenset(response["before_facts"]),
            after_facts=frozenset(response["after_facts"]),
            standing=str(response["standing"]),
            receipt_ids=tuple(response["receipt_ids"]),
            reason=response.get("reason"),
        )

    result = await discovery.discover_procedure(challenge, probe)
    _write_message(
        {
            "type": "result",
            "subject": result.subject,
            "plan": list(result.plan),
            "goal_state": sorted(result.goal_state),
            "probes": result.probes,
            "rejected_probes": result.rejected_probes,
            "visited_states": result.visited_states,
            "learned_transition_count": len(result.learned_transitions),
            "evidence_receipt_count": len(result.evidence_receipt_ids),
            "evidence_receipt_sha256": _receipt_digest(result.evidence_receipt_ids),
        }
    )
    return 0


def main() -> int:
    try:
        return asyncio.run(_run())
    except Exception as exc:
        _write_message(
            {
                "type": "error",
                "error_type": type(exc).__name__,
                "message": str(exc),
            }
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
