# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style test for authority-threading through `MaterializationIntent`.

The defect this pins: `gymact.models.MaterializationIntent` carries a real
`authority_ref` field (confirmed via `MaterializationIntent.model_fields`),
but neither `_BRIDGE_SCRIPT` (discovery) nor `_EXECUTE_SCRIPT` (actuation)
ever populated it -- only `ActuationIntent` calls did. Any provider whose
`materialization_requires_authority` is True (a class attribute on every
`gymact.gyms.vendor_benchmarks.VendorBenchmarkProvider` instance, among
others) was therefore refused with `LIVE_AUTHORITY_REQUIRED` before
`capabilities()` was ever reached -- reproduced live on `terragoat` before
this fix, and confirmed resolved after it, both via real `gymact` calls
(not the repo's own reimplementation).

Every collaborator is real: the real `gymact` kernel, the real
`AllowListAuthorityResolver`, the real `VendorBenchmarkProvider('terragoat')`
class (a currently-unwired vendor -- this test exercises the authority
mechanism only, and adds no `_PROVIDERS` entry or goal predicate for it, so
nothing about this fix makes `terragoat` reachable through `run_real_trial`).
No mocks.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from autofde_lab.hub.domain.gym_procedure.level4_crown import GYMACT_VENV_PYTHON
from autofde_lab.hub.domain.gym_procedure.level4_gymact_bridge import _PROVIDERS

pytestmark = pytest.mark.skipif(
    not Path(GYMACT_VENV_PYTHON).exists(),
    reason=f"real gymact interpreter absent at {GYMACT_VENV_PYTHON}",
)


def test_materialization_intent_carries_a_real_authority_ref_field() -> None:
    """Ground the premise on the real pydantic model before relying on it."""
    from gymact.models import ActuationIntent, MaterializationIntent

    assert "authority_ref" in MaterializationIntent.model_fields
    assert "authority_ref" in ActuationIntent.model_fields


def test_authority_required_provider_refused_without_ref_and_admitted_with_it() -> None:
    """The real, live before/after: reproduces the exact refusal this fix
    closes, then confirms the fix, both via real `gymact` calls in
    `~/gymact`'s own venv (the interpreter every real bridge invocation
    uses)."""
    import asyncio

    from gymact import AllowListAuthorityResolver, GymAct, MaterializationIntent
    from gymact.gyms.vendor_benchmarks import VendorBenchmarkProvider

    authority_ref = "urn:autofde-lab:level4-crown-authority"

    async def _without_ref() -> tuple[bool, str | None]:
        gym = GymAct(authority_resolver=AllowListAuthorityResolver({authority_ref}))
        gym.register_provider(VendorBenchmarkProvider("terragoat"))
        m = await gym.materialize(MaterializationIntent(provider="terragoat", config={}))
        return m.accepted, (m.receipt.reason if m.receipt else None)

    async def _with_ref() -> bool:
        gym = GymAct(authority_resolver=AllowListAuthorityResolver({authority_ref}))
        gym.register_provider(VendorBenchmarkProvider("terragoat"))
        m = await gym.materialize(
            MaterializationIntent(provider="terragoat", config={}, authority_ref=authority_ref)
        )
        return m.accepted

    accepted_before, reason_before = asyncio.run(_without_ref())
    assert accepted_before is False
    assert reason_before == "LIVE_AUTHORITY_REQUIRED"

    accepted_after = asyncio.run(_with_ref())
    assert accepted_after is True


def test_fix_adds_no_provider_registry_entry_or_goal_predicate() -> None:
    """This fix is additive-only at the authority-threading layer, exactly
    like the constructor fix before it. Confirms the real, current state:
    `terragoat` (and every other vendor) is still unreachable through
    `run_real_trial` as a side effect of this change -- `_PROVIDERS` carries
    no vendor entry. (`memory` was added later this session as its own,
    separately-designed 6th tracer bullet -- see
    `tests/domains/python/test_level4_memory_gym_chicago.py` -- not as a
    side effect of the authority-threading fix this test pins.)"""
    assert set(_PROVIDERS) == {
        "cube_counter", "cube_container_counter", "switchboard",
        "resource_flow", "lock_and_key", "memory",
    }


def test_real_bridge_script_source_now_populates_authority_ref() -> None:
    """The actual fix, confirmed present in both real script constants --
    not merely in the standalone reproduction above."""
    from autofde_lab.hub.domain.gym_procedure.level4_crown import _EXECUTE_SCRIPT
    from autofde_lab.hub.domain.gym_procedure.level4_gymact_bridge import _BRIDGE_SCRIPT

    for script_text, label in ((_BRIDGE_SCRIPT, "discovery"), (_EXECUTE_SCRIPT, "actuation")):
        assert "authority_ref=_AUTHORITY_REF" in script_text, (
            f"{label} bridge script no longer threads authority_ref through "
            "MaterializationIntent"
        )
