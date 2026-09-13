#!/usr/bin/env python3
"""Real end-to-end GymAct episode through `AzureGoatPrivescProvider`, using the
real `gymact.runtime.GymAct` orchestrator (not the bare provider/environment
API directly) -- so every operation (materialize/act x10/verify/teardown)
produces a real `gymact.models.Receipt`, and those real receipts are converted
to a real OCEL 2.0 log via `gymact.ocel.write_ocel_log`.

Mirrors the pattern in `~/gymact/scripts/discover_and_actuate.py`: `receipt.
standing == ALIVE` on an `act` receipt only means the actuation mechanism ran
without raising -- it does NOT by itself mean the domain's goal was reached.
The real observed goal-achievement truth (from a real `gym.verify()` call
against the real environment, after the real plan's final step) is attached
onto the final `act` receipt's own `reason` field (the only free-text
evidence channel `Receipt` carries) via `model_copy`, so the OCEL log itself
carries `solved=True`/`solved=False` -- not this script's stdout.

Usage:
    .venv/bin/python scripts/run_azuregoat_gymact_ocel_episode.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from gymact import AllowListAuthorityResolver, GymAct, MaterializationIntent
from gymact.models import ActuationIntent
from gymact.ocel import write_ocel_log

from autofde_lab.hub.domain.azuregoat_privesc.gymact_bridge import AzureGoatPrivescProvider

AUTHORITY_REF = "urn:gymact:azuregoat-privesc:authority:lab-episode-run"
LOG_PATH = (
    Path(__file__).parent.parent
    / "reports"
    / "ocel"
    / "azuregoat-privesc-gymact"
    / "episode.ocel.json"
)


async def main() -> None:
    gym = GymAct(authority_resolver=AllowListAuthorityResolver({AUTHORITY_REF}))
    gym.register_provider(AzureGoatPrivescProvider())
    receipts = []

    materialization = await gym.materialize(
        MaterializationIntent(provider="azuregoat_privesc", config={})
    )
    receipts.append(materialization.receipt)
    if not materialization.accepted:
        raise RuntimeError(f"materialize refused: {materialization.receipt.reason!r}")

    episode_id = materialization.episode.episode_id
    capabilities = gym.capabilities(episode_id)
    print(f"episode_id: {episode_id}")
    print(f"num capabilities: {len(capabilities)}")

    act_result = None
    for capability in capabilities:
        act_result = await gym.act(
            ActuationIntent(
                episode_id=episode_id,
                capability=capability.iri,
                authority_ref=AUTHORITY_REF,
            )
        )
        if not act_result.accepted:
            raise RuntimeError(
                f"act refused for {capability.iri}: {act_result.receipt.reason!r}"
            )
        print(f"acted: {capability.iri} -> standing={act_result.receipt.standing.value}")
        receipts.append(act_result.receipt)

    assert act_result is not None

    verification = await gym.verify(episode_id, {})
    print(f"verify({{}}) -> passed={verification.passed} observed={verification.observed}")

    solved_marker = f"solved={verification.passed}"
    last_receipt = receipts[-1]
    receipt_with_solved = last_receipt.model_copy(
        update={
            "reason": (
                f"{last_receipt.reason}; {solved_marker}" if last_receipt.reason else solved_marker
            )
        }
    )
    receipts[-1] = receipt_with_solved

    receipts.append(await gym.teardown(episode_id))

    log, digest = write_ocel_log(LOG_PATH, receipts)
    print(f"wrote {LOG_PATH} sha256={digest}")
    print(f"events={len(log['events'])} objects={len(log['objects'])}")


if __name__ == "__main__":
    asyncio.run(main())
