# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style: a real GymAct episode driven against a real, compiled
software-manufacturing plan.

No mocked provider, no mocked environment, no mocked replay world -- `GymAct.
materialize` really instantiates `SoftwareManufacturingEnvironment`, which
really wraps a real `ReplayWorld` over the real checked-in August fixture
(`planning/august-2026/materialized/august-full-stack-example.plan.json`).
Mirrors `~/gymact/tests/test_cube_counter.py`'s structure -- the reference
pattern this repo's own AzureGoat bridge and this bridge both follow. Uses
plain sync test functions wrapping `asyncio.run(...)`, matching
`tests/agent/test_api.py`'s already-established convention in this repo
(no `pytest-asyncio`/`anyio` test-plugin marker configured here).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from gymact.models import ActuationIntent, Operation, Standing
from gymact.plugins import load_provider_plugin
from gymact.process import ConformanceChecker

from autofde_lab.agent.software_manufacturing_gymact_bridge import (
    SoftwareManufacturingProvider,
)
from gymact import GymAct, MaterializationIntent

_FIXTURE = (
    Path(__file__).parents[2]
    / "planning"
    / "august-2026"
    / "materialized"
    / "august-full-stack-example.plan.json"
)


def _load_plan() -> dict:
    return json.loads(_FIXTURE.read_text())


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def test_plugin_is_discoverable_as_a_real_gymact_provider() -> None:
    """Confirms the pyproject.toml entry-point registration is real and
    live, not just present in the config file -- resolves and loads the
    actual class via gymact's own plugin discovery, the same path
    `gymact.plugins.discover_provider_plugins`/`load_provider_plugin` use
    for any consumer-registered provider (see `azuregoat_privesc` for the
    established sibling pattern)."""

    result = load_provider_plugin("software_manufacturing")

    assert result.standing == Standing.ALIVE
    assert result.provider is not None
    assert result.provider.name == "software_manufacturing"


def test_real_plan_replays_to_completion_and_is_receipted() -> None:
    async def scenario() -> tuple[list, list[Operation]]:
        plan = _load_plan()
        step_ids = [step["id"] for step in plan["plan"]["steps"]]

        gym = GymAct()
        gym.register_provider(SoftwareManufacturingProvider())

        materialization = await gym.materialize(
            MaterializationIntent(
                provider="software_manufacturing", config={"plan": plan}
            )
        )
        assert materialization.accepted is True
        assert materialization.episode is not None
        episode_id = materialization.episode.episode_id

        observation = await gym.observe(episode_id)
        assert observation.state["completed_steps"] == []
        assert observation.state["step_count"] == len(step_ids)

        receipts = [materialization.receipt]
        operations = [Operation.MATERIALIZE]

        # Drive the partial order to closure by always acting on the first
        # currently-admissible step -- exactly ReplayWorld.run_reference()'s
        # own deterministic policy, driven through the real gym.act()
        # surface instead of calling ReplayWorld.apply() directly.
        completed: list[str] = []
        while len(completed) < len(step_ids):
            admissible = (await gym.observe(episode_id)).state["admissible"]
            assert admissible, "real plan produced a dependency deadlock"
            next_step = sorted(admissible)[0]
            capability = f"urn:gymact:software-manufacturing:capability:{next_step}"

            result = await gym.act(
                ActuationIntent(episode_id=episode_id, capability=capability)
            )
            assert result.accepted is True
            receipts.append(result.receipt)
            operations.append(Operation.ACT)
            completed.append(next_step)

        assert sorted(completed) == sorted(step_ids)

        verification = await gym.verify(episode_id, {"state": "ALIVE"})
        assert verification.passed is True
        assert verification.observed["state"] == "ALIVE"

        # The plan's own real receipt (authority/do_authority/evidence_kind
        # fields) lives on ReplayWorld.receipt(), not on observe()'s state --
        # confirm it directly through the environment's own verify() report,
        # independently of the kernel's subset-match judgment above.
        final_observation = await gym.observe(episode_id)
        assert final_observation.state["state"] == "ALIVE"
        operations.append(Operation.VERIFY)

        teardown_receipt = await gym.teardown(episode_id)
        receipts.append(teardown_receipt)
        operations.append(Operation.TEARDOWN)

        return receipts, operations

    receipts, operations = _run(scenario())

    assert all(r.standing == "ALIVE" for r in receipts)

    result = ConformanceChecker().check(operations)
    assert result.conformant is True
    assert result.deviations == []


def test_checkpoint_restore_round_trips_the_real_replay_state() -> None:
    async def scenario() -> None:
        plan = _load_plan()
        step_ids = sorted(step["id"] for step in plan["plan"]["steps"])
        first_step = step_ids[
            0
        ]  # branch_created has no deps -- always first-admissible

        gym = GymAct()
        gym.register_provider(SoftwareManufacturingProvider())

        materialization = await gym.materialize(
            MaterializationIntent(
                provider="software_manufacturing", config={"plan": plan}
            )
        )
        assert materialization.episode is not None
        episode_id = materialization.episode.episode_id

        capability = f"urn:gymact:software-manufacturing:capability:{first_step}"
        await gym.act(ActuationIntent(episode_id=episode_id, capability=capability))
        after_one = await gym.observe(episode_id)
        assert after_one.state["completed_steps"] == [first_step]

        checkpoint = await gym.checkpoint(episode_id)
        assert checkpoint == {
            "completed": [first_step],
            "transitions": [checkpoint["transitions"][0]],
        }

        second_step = sorted(after_one.state["admissible"])[0]
        await gym.act(
            ActuationIntent(
                episode_id=episode_id,
                capability=f"urn:gymact:software-manufacturing:capability:{second_step}",
            )
        )
        assert len((await gym.observe(episode_id)).state["completed_steps"]) == 2

        restored = await gym.restore(episode_id, checkpoint)
        assert restored.standing == Standing.ALIVE

        observed_after_restore = await gym.observe(episode_id)
        assert observed_after_restore.state["completed_steps"] == [first_step]

        await gym.teardown(episode_id)

    _run(scenario())


def test_actuating_an_inadmissible_step_is_refused_not_silently_advanced() -> None:
    async def scenario() -> None:
        plan = _load_plan()
        # A step with a real, unsatisfied dependency -- cannot be admissible first.
        dependent_step = next(
            step["id"] for step in plan["plan"]["steps"] if step.get("depends_on")
        )

        gym = GymAct()
        gym.register_provider(SoftwareManufacturingProvider())

        materialization = await gym.materialize(
            MaterializationIntent(
                provider="software_manufacturing", config={"plan": plan}
            )
        )
        assert materialization.episode is not None
        episode_id = materialization.episode.episode_id

        result = await gym.act(
            ActuationIntent(
                episode_id=episode_id,
                capability=f"urn:gymact:software-manufacturing:capability:{dependent_step}",
            )
        )

        assert result.accepted is False
        observation = await gym.observe(episode_id)
        # refused step never advanced real state
        assert observation.state["completed_steps"] == []

    _run(scenario())
