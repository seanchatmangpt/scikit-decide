from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
DISCOVERY_SOURCE = ROOT / "src/autofde_lab/hub/domain/gym_procedure/discovery.py"
WORKER_SOURCE = ROOT / "src/autofde_lab/hub/domain/gym_procedure/discovery_worker.py"


def _load_discovery() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "_autofde_test_discovery", DISCOVERY_SOURCE
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("DISCOVERY_MODULE_LOAD_REFUSED")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


DISCOVERY = _load_discovery()


@pytest.mark.asyncio
async def test_discovers_without_transition_model_and_preserves_failed_edges() -> None:
    challenge = DISCOVERY.DiscoveryChallenge(
        subject="held-out/task",
        initial_facts=frozenset({"start"}),
        goal_facts=frozenset({"done"}),
        action_ids=("opaque-b", "opaque-a"),
    )
    hidden = {
        "opaque-a": (frozenset({"start"}), frozenset({"middle"})),
        "opaque-b": (frozenset({"middle"}), frozenset({"done"})),
    }

    async def probe(prefix: tuple[str, ...], action_id: str) -> DISCOVERY.ProbeEvidence:
        state = frozenset({"start"})
        for prior in prefix:
            required, effect = hidden[prior]
            assert required <= state
            state |= effect
        required, effect = hidden[action_id]
        accepted = required <= state and not effect <= state
        after = state | effect if accepted else state
        return DISCOVERY.ProbeEvidence(
            action_id=action_id,
            prefix=prefix,
            accepted=accepted,
            before_facts=state,
            after_facts=after,
            standing="ALIVE" if accepted else "REFUSED",
            receipt_ids=(f"receipt:{len(prefix)}:{action_id}",),
            reason=None if accepted else "PRECONDITION_REFUSED",
        )

    result = await DISCOVERY.discover_procedure(challenge, probe)
    assert result.plan == ("opaque-a", "opaque-b")
    assert challenge.goal_facts <= result.goal_state
    assert result.rejected_probes >= 1
    assert result.evidence_receipt_ids


@pytest.mark.asyncio
async def test_refuses_unreceipted_probe_evidence() -> None:
    challenge = DISCOVERY.DiscoveryChallenge(
        subject="held-out/task",
        initial_facts=frozenset({"start"}),
        goal_facts=frozenset({"done"}),
        action_ids=("opaque-a",),
    )

    async def probe(prefix: tuple[str, ...], action_id: str) -> DISCOVERY.ProbeEvidence:
        return DISCOVERY.ProbeEvidence(
            action_id=action_id,
            prefix=prefix,
            accepted=True,
            before_facts=frozenset({"start"}),
            after_facts=frozenset({"start", "done"}),
            standing="ALIVE",
            receipt_ids=(),
        )

    with pytest.raises(
        DISCOVERY.DiscoveryRefused, match="UNRECEIPTED_DISCOVERY_PROBE_REFUSED"
    ):
        await DISCOVERY.discover_procedure(challenge, probe)


def test_worker_isolated_stdio_protocol_has_no_parent_object_graph() -> None:
    with tempfile.TemporaryDirectory(prefix="autofde-discovery-test-") as directory:
        worker_root = Path(directory)
        shutil.copyfile(DISCOVERY_SOURCE, worker_root / "discovery.py")
        shutil.copyfile(WORKER_SOURCE, worker_root / "discovery_worker.py")
        env = {
            "LANG": os.environ.get("LANG", "C.UTF-8"),
            "PYTHONIOENCODING": "utf-8",
        }
        process = subprocess.Popen(
            [sys.executable, "-I", str(worker_root / "discovery_worker.py")],
            cwd=worker_root,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        assert process.stdin is not None
        assert process.stdout is not None

        ready = json.loads(process.stdout.readline())
        assert ready["type"] == "ready"
        assert ready["isolated"] is True
        assert set(ready["cwd_sources"]) == {"discovery.py", "discovery_worker.py"}
        assert set(ready["environment_keys"]) <= {"LANG", "PYTHONIOENCODING"}
        assert all(str(ROOT) not in entry for entry in ready["sys_path"])

        process.stdin.write(
            json.dumps(
                {
                    "type": "challenge",
                    "subject": "held-out/task",
                    "initial_facts": ["start"],
                    "goal_facts": ["done"],
                    "action_ids": ["opaque-b", "opaque-a"],
                    "max_states": 10,
                    "max_probes": 20,
                }
            )
            + "\n"
        )
        process.stdin.flush()

        hidden = {
            "opaque-a": ({"start"}, {"middle"}),
            "opaque-b": ({"middle"}, {"done"}),
        }
        result = None
        while result is None:
            message = json.loads(process.stdout.readline())
            if message["type"] == "result":
                result = message
                continue
            assert message["type"] == "probe"
            state = {"start"}
            for prior in message["prefix"]:
                required, effect = hidden[prior]
                assert required <= state
                state |= effect
            required, effect = hidden[message["action_id"]]
            accepted = required <= state and not effect <= state
            after = state | effect if accepted else state
            process.stdin.write(
                json.dumps(
                    {
                        "type": "probe_result",
                        "action_id": message["action_id"],
                        "prefix": message["prefix"],
                        "accepted": accepted,
                        "before_facts": sorted(state),
                        "after_facts": sorted(after),
                        "standing": "ALIVE" if accepted else "REFUSED",
                        "receipt_ids": [
                            f"receipt:{len(message['prefix'])}:{message['action_id']}"
                        ],
                        "reason": None if accepted else "PRECONDITION_REFUSED",
                    }
                )
                + "\n"
            )
            process.stdin.flush()

        process.stdin.close()
        assert process.wait(timeout=10) == 0
        assert result["plan"] == ["opaque-a", "opaque-b"]
        assert result["evidence_receipt_count"] > 0
        assert len(result["evidence_receipt_sha256"]) == 64
        assert result["learned_transition_count"] > 0
