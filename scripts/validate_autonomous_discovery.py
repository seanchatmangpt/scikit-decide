#!/usr/bin/env python3
"""Validate isolated autonomous no-leak procedure discovery across every recipe.

AutoFDE Lab remains SELECT-only. Each recipe's planner runs in a fresh isolated
Python process that receives only admitted observations, a public goal, opaque
capability IDs, and receipted probe results. A separate GymAct benchmark harness
owns the private transition model and executes probes outside the planner process.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from gymact.discovery import DiscoveryProbeRunner
from gymact.gyms.opaque_procedure import OpaqueProcedureProvider
from gymact.models import Operation, Standing
from gymact.ocel import digest_ocel_log, validate_ocel_log
from gymact.process import ConformanceChecker
from gymact.runtime import ProductionGymAct

ROOT = Path(__file__).resolve().parents[1]
RECIPES = ROOT / "src/autofde_lab/hub/domain/gym_procedure/recipes"
DISCOVERY_SOURCE = ROOT / "src/autofde_lab/hub/domain/gym_procedure/discovery.py"
WORKER_SOURCE = ROOT / "src/autofde_lab/hub/domain/gym_procedure/discovery_worker.py"
DEFAULT_RECEIPT = ROOT / "reports/autonomous-discovery/receipt.json"
GYMACT_BASE_SHA = "c839d76125bde97b9eb3dfd82f0e08a1b9dcdf96"
GYMACT_VERSION = "26.8.7"
PLANNER_PROTOCOL = "urn:autofde-lab:discovery-worker:v1"
PLANNER_INPUT_KEYS = frozenset(
    {
        "type",
        "subject",
        "initial_facts",
        "goal_facts",
        "action_ids",
        "max_states",
        "max_probes",
    }
)
FORBIDDEN_PLANNER_KEYS = frozenset(
    {
        "steps",
        "source_ref",
        "source",
        "description",
        "preconditions",
        "establishes",
        "removes",
        "requires_authority",
        "provider_private_config",
        "walkthrough",
    }
)
PLANNER_ENV_KEYS = frozenset({"LANG", "PYTHONIOENCODING"})


def _canonical_digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def _private_world(recipe: dict[str, Any]) -> dict[str, Any]:
    """Build provider-private transition data; omit source/provenance text."""
    return {
        "subject": f"{recipe['gym']}/{recipe['task']}",
        "initial_facts": list(recipe["initial_facts"]),
        "goal_facts": list(recipe["goal_facts"]),
        "steps": [
            {
                "id": step["id"],
                "preconditions": list(step.get("preconditions", [])),
                "establishes": list(step.get("establishes", [])),
                "removes": list(step.get("removes", [])),
            }
            for step in recipe["steps"]
        ],
        "requires_authority": False,
    }


def _forbidden_planner_key_present(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            key in FORBIDDEN_PLANNER_KEYS or _forbidden_planner_key_present(item)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_forbidden_planner_key_present(item) for item in value)
    return False


def _independent_ocel_replay(log: dict[str, Any]) -> tuple[bool, int]:
    validate_ocel_log(log)
    events = sorted(log["events"], key=lambda event: (event["time"], event["id"]))
    operations = [Operation(event["type"]) for event in events]
    conformance = ConformanceChecker().check(operations)
    return conformance.conformant, len(operations)


async def _read_worker_message(
    process: asyncio.subprocess.Process, *, timeout_s: float = 30.0
) -> dict[str, Any]:
    if process.stdout is None:
        raise RuntimeError("DISCOVERY_WORKER_STDOUT_REQUIRED")
    line = await asyncio.wait_for(process.stdout.readline(), timeout=timeout_s)
    if not line:
        stderr = b""
        if process.stderr is not None:
            stderr = await process.stderr.read()
        raise RuntimeError(
            "DISCOVERY_WORKER_EOF:" + stderr.decode("utf-8", errors="replace")[-1000:]
        )
    value = json.loads(line)
    if not isinstance(value, dict):
        raise TypeError("DISCOVERY_WORKER_OBJECT_REQUIRED")
    if value.get("type") == "error":
        raise RuntimeError(
            f"DISCOVERY_WORKER_ERROR:{value.get('error_type')}:{value.get('message')}"
        )
    return value


async def _write_worker_message(
    process: asyncio.subprocess.Process, value: dict[str, Any]
) -> None:
    if process.stdin is None:
        raise RuntimeError("DISCOVERY_WORKER_STDIN_REQUIRED")
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    process.stdin.write(payload)
    await process.stdin.drain()


async def _discover_in_isolated_process(
    runner: DiscoveryProbeRunner,
    challenge: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    if set(challenge) != PLANNER_INPUT_KEYS:
        raise RuntimeError("DISCOVERY_PLANNER_INPUT_SURFACE_DRIFT")
    if _forbidden_planner_key_present(challenge):
        raise RuntimeError("DISCOVERY_PRIVATE_FIELD_LEAKAGE_REFUSED")

    with tempfile.TemporaryDirectory(prefix="autofde-discovery-") as directory:
        worker_root = Path(directory)
        planner_copy = worker_root / "discovery.py"
        worker_copy = worker_root / "discovery_worker.py"
        shutil.copyfile(DISCOVERY_SOURCE, planner_copy)
        shutil.copyfile(WORKER_SOURCE, worker_copy)

        env = {
            "LANG": os.environ.get("LANG", "C.UTF-8"),
            "PYTHONIOENCODING": "utf-8",
        }
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-I",
            str(worker_copy),
            cwd=worker_root,
            env=env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            ready = await _read_worker_message(process)
            if (
                ready.get("type") != "ready"
                or ready.get("protocol") != PLANNER_PROTOCOL
            ):
                raise RuntimeError("DISCOVERY_WORKER_HANDSHAKE_REFUSED")
            if ready.get("isolated") is not True:
                raise RuntimeError("DISCOVERY_WORKER_NOT_ISOLATED")
            if set(ready.get("cwd_sources", ())) != {
                "discovery.py",
                "discovery_worker.py",
            }:
                raise RuntimeError("DISCOVERY_WORKER_CWD_NOT_SPARSE")
            if set(ready.get("environment_keys", ())) - PLANNER_ENV_KEYS:
                raise RuntimeError("DISCOVERY_WORKER_ENVIRONMENT_NOT_SANITIZED")
            if any(str(ROOT) in item for item in ready.get("sys_path", ())):
                raise RuntimeError("DISCOVERY_REPOSITORY_PATH_VISIBLE_TO_WORKER")

            await _write_worker_message(process, challenge)
            while True:
                message = await _read_worker_message(process)
                kind = message.get("type")
                if kind == "probe":
                    prefix = tuple(message["prefix"])
                    action_id = str(message["action_id"])
                    observed = await runner.probe(prefix=prefix, action_id=action_id)
                    await _write_worker_message(
                        process,
                        {
                            "type": "probe_result",
                            "action_id": observed.action_id,
                            "prefix": list(observed.prefix),
                            "accepted": observed.accepted,
                            "before_facts": list(observed.before_facts),
                            "after_facts": list(observed.after_facts),
                            "standing": observed.standing.value,
                            "receipt_ids": list(observed.receipt_ids),
                            "reason": observed.reason,
                        },
                    )
                    continue
                if kind == "result":
                    result = message
                    break
                raise RuntimeError(f"DISCOVERY_WORKER_MESSAGE_REFUSED:{kind}")

            if process.stdin is not None:
                process.stdin.close()
            exit_code = await asyncio.wait_for(process.wait(), timeout=10.0)
            if exit_code != 0:
                raise RuntimeError(f"DISCOVERY_WORKER_EXIT:{exit_code}")
        except BaseException:
            if process.returncode is None:
                process.kill()
                await process.wait()
            raise

        isolation = {
            "protocol": PLANNER_PROTOCOL,
            "isolated_interpreter": True,
            "sparse_working_directory": True,
            "repository_path_absent_from_sys_path": True,
            "sanitized_environment": True,
            "planner_git_blob_sha": _git_blob_sha(planner_copy),
            "worker_git_blob_sha": _git_blob_sha(worker_copy),
            "planner_sha256": hashlib.sha256(planner_copy.read_bytes()).hexdigest(),
            "worker_sha256": hashlib.sha256(worker_copy.read_bytes()).hexdigest(),
        }
        return result, isolation


def _pattern_evidence(
    *,
    challenge: dict[str, Any],
    discovered: dict[str, Any],
    isolation: dict[str, Any],
) -> dict[str, bool]:
    exact_admission_surface = set(challenge) == PLANNER_INPUT_KEYS
    forbidden_fields_absent = not _forbidden_planner_key_present(challenge)
    opaque_actions = all(
        str(action_id).startswith("urn:gymact:opaque:action:")
        for action_id in challenge["action_ids"]
    )
    process_cut = all(
        isolation[name]
        for name in (
            "isolated_interpreter",
            "sparse_working_directory",
            "repository_path_absent_from_sys_path",
            "sanitized_environment",
        )
    )
    admitted_no_leak = exact_admission_surface and forbidden_fields_absent
    return {
        "recipe_hidden_source_visible": admitted_no_leak,
        "recipe_and_walkthrough_hidden": admitted_no_leak and process_cut,
        "unknown_action_semantics_active_probing": opaque_actions
        and discovered["probes"] > 0,
        "entire_task_held_out": admitted_no_leak and opaque_actions,
        "entire_family_held_out": admitted_no_leak and process_cut,
        "full_corpus_no_solution_leakage": admitted_no_leak
        and process_cut
        and discovered["evidence_receipt_count"] > 0,
    }


async def _run_recipe(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    recipe = json.loads(raw)
    private_world = _private_world(recipe)
    subject = private_world["subject"]

    # The external benchmark harness owns the private transition model.
    # AutoFDE's planner process receives only serialized admitted observations.
    runtime = ProductionGymAct(validate_profile=False)
    runtime.register_provider(OpaqueProcedureProvider())
    runner = DiscoveryProbeRunner(
        runtime,
        provider="opaque-procedure",
        subject=subject,
        private_config=private_world,
    )
    initial_facts, action_ids = await runner.challenge()

    challenge = {
        "type": "challenge",
        "subject": subject,
        "initial_facts": list(initial_facts),
        "goal_facts": list(recipe["goal_facts"]),
        "action_ids": list(action_ids),
        "max_states": 100_000,
        "max_probes": 1_000_000,
    }
    discovered, isolation = await _discover_in_isolated_process(runner, challenge)
    replay = await runner.replay(plan=tuple(discovered["plan"]))
    conformant, event_count = _independent_ocel_replay(replay.ocel_log)

    if replay.standing is not Standing.ALIVE:
        raise AssertionError(f"{path.name}: final replay standing={replay.standing}")
    if not replay.goal_reached:
        raise AssertionError(f"{path.name}: provider-hidden goal was not verified")
    if not conformant:
        raise AssertionError(f"{path.name}: OCEL lifecycle is non-conformant")
    if not replay.receipt_ids:
        raise AssertionError(f"{path.name}: final replay has no receipts")

    patterns = _pattern_evidence(
        challenge=challenge,
        discovered=discovered,
        isolation=isolation,
    )
    if not all(patterns.values()):
        raise AssertionError(
            f"{path.name}: no-leak pattern evidence failed: {patterns}"
        )

    return {
        "recipe": path.name,
        "subject": subject,
        "standing": "ALIVE",
        "recipe_sha256": hashlib.sha256(raw).hexdigest(),
        "challenge_digest": _canonical_digest(challenge),
        "plan": discovered["plan"],
        "plan_length": len(discovered["plan"]),
        "probes": discovered["probes"],
        "rejected_probes": discovered["rejected_probes"],
        "visited_states": discovered["visited_states"],
        "learned_transitions": discovered["learned_transition_count"],
        "discovery_receipts": discovered["evidence_receipt_count"],
        "discovery_receipt_sha256": discovered["evidence_receipt_sha256"],
        "final_receipts": list(replay.receipt_ids),
        "ocel_sha256": digest_ocel_log(replay.ocel_log),
        "ocel_events": event_count,
        "ocel_schema_valid": True,
        "lifecycle_conformant": True,
        "goal_verified": True,
        "planner_isolation": isolation,
        "patterns": patterns,
    }


async def _main(output: Path) -> int:
    autofde_head_sha = os.environ.get("AUTOFDE_HEAD_SHA")
    gymact_head_sha = os.environ.get("GYMACT_HEAD_SHA")
    if not autofde_head_sha or not gymact_head_sha:
        raise RuntimeError("EXECUTION_IDENTITY_REQUIRED")

    recipe_paths = sorted(RECIPES.glob("*.json"))
    if not recipe_paths:
        raise RuntimeError(f"NO_RECIPES_FOUND:{RECIPES}")

    results = [await _run_recipe(path) for path in recipe_paths]
    alive = sum(item["standing"] == "ALIVE" for item in results)
    pattern_names = tuple(results[0]["patterns"])
    pattern_counts = {
        pattern: sum(bool(item["patterns"][pattern]) for item in results)
        for pattern in pattern_names
    }
    isolated = sum(
        bool(item["planner_isolation"]["isolated_interpreter"]) for item in results
    )
    standing = (
        "ALIVE"
        if alive == len(results)
        and isolated == len(results)
        and all(count == len(results) for count in pattern_counts.values())
        else "BLOCKED"
    )
    receipt = {
        "schema": "urn:autofde-lab:autonomous-discovery-receipt:v2",
        "standing": standing,
        "autofde_head_sha": autofde_head_sha,
        "gymact_head_sha": gymact_head_sha,
        "gymact_base_sha": GYMACT_BASE_SHA,
        "gymact_version": GYMACT_VERSION,
        "corpus_size": len(results),
        "alive": alive,
        "isolated_planner_processes": isolated,
        "pattern_counts": pattern_counts,
        "planner_boundary": PLANNER_PROTOCOL,
        "planner_input_keys": sorted(PLANNER_INPUT_KEYS),
        "planner_forbidden_keys": sorted(FORBIDDEN_PLANNER_KEYS),
        "execution_path": (
            "autofde SELECT isolated process -> external GymAct benchmark harness "
            "-> verified consequence -> OCEL -> conformance replay"
        ),
        "results": results,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt, sort_keys=True))
    return 0 if standing == "ALIVE" else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_RECEIPT)
    args = parser.parse_args()
    return asyncio.run(_main(args.output))


if __name__ == "__main__":
    raise SystemExit(main())
