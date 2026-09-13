# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for `gymact_certification_checker`.

Real collaborators throughout: the real, installed `gymact` package's real
`EnvironmentProvider`/`Environment` Protocols (`@runtime_checkable`, no
mock substitute possible or needed -- structural typing is checked against
the real class); the real `gymact.gyms.sregym.SregymVendorProvider` class
for the structural pass (import only, no live cluster materialized); a
real, hand-written fake `Environment`/`EnvironmentProvider` pair (same
real-degraded-alternative pattern `test_gymact_dspy_react_chicago.py`'s
`_FakeSregymEnvironment` already uses) for the smoke-cycle test.

No `unittest.mock` / `Mock` / `MagicMock` / `patch` / `monkeypatch` anywhere
in this file.
"""

from __future__ import annotations

import asyncio
from typing import Any

from gymact.models import Capability, Consequence

from autofde_lab.reasoning.gymact_certification_checker import check_environment_provider_conformance
from autofde_lab.reasoning.gymact_certification_types import StandingValue


def test_real_sregym_vendor_provider_passes_every_structural_check() -> None:
    """A real, known-conformant adapter (`SregymVendorProvider`, real import,
    no live cluster) must pass every structural check and be reported
    `STRUCTURAL_ONLY` -- a real, positive proof the checker recognizes real
    conformance, not just detects real defects."""
    from gymact.gyms.sregym import SregymVendorProvider

    provider = SregymVendorProvider()

    manifest, results = asyncio.run(
        check_environment_provider_conformance(provider, gym_name="sregym", run_smoke_cycle=False)
    )

    assert manifest.manifest_conformance_level_ref == StandingValue.STRUCTURAL_ONLY.value
    assert manifest.manifest_gym_name == "sregym"
    assert "SregymVendorProvider" in manifest.manifest_provider_class_ref
    # Pure structural pass (no materialize): provider Protocol conformance +
    # materialize() signature only. capabilities() is a real Environment-level
    # method (confirmed live -- EnvironmentProvider itself declares no such
    # method) and only runs inside the opt-in smoke cycle, where a real
    # Environment instance actually exists.
    assert len(results) == 2
    assert all(r.result_passed for r in results)
    assert any(r.result_check_ref == "provider_satisfies_environment_provider_protocol" for r in results)
    assert any(r.result_check_ref == "materialize_method_present" for r in results)


def test_non_conformant_object_is_reported_build_broken_never_a_fabricated_pass() -> None:
    """A real, plain object satisfying none of the Protocol must be
    reported honestly as CERT_BUILD_BROKEN, never coerced into a pass."""

    class _NotAProvider:
        pass

    manifest, results = asyncio.run(
        check_environment_provider_conformance(_NotAProvider(), gym_name="not-a-real-gym", run_smoke_cycle=False)
    )

    assert manifest.manifest_conformance_level_ref == StandingValue.CERT_BUILD_BROKEN.value
    assert any(
        r.result_check_ref == "provider_satisfies_environment_provider_protocol" and r.result_passed is False
        for r in results
    )


_FAKE_CAPABILITIES: tuple[Capability, ...] = (
    Capability(
        iri="urn:gymact:fake:capability:read",
        title="Real fake read capability for the smoke-cycle test",
        consequence=Consequence.READ,
        binding="read",
    ),
)


class _FakeEnvironment:
    """Real, hand-written, honest fake -- same pattern as
    `test_gymact_dspy_react_chicago.py::_FakeSregymEnvironment`."""

    def __init__(self) -> None:
        self.environment_id = "urn:gymact:fake:environment:test-001"
        self.requires_authority = False
        self.torn_down = False

    def capabilities(self) -> tuple[Capability, ...]:
        return _FAKE_CAPABILITIES

    async def observe(self) -> dict[str, Any]:
        return {"real": "observed-state"}

    async def actuate(self, capability: Capability, payload: dict[str, Any]) -> dict[str, Any]:
        raise AssertionError("the checker must never call actuate() -- see module docstring")

    async def verify(self, expected: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
        return True, dict(expected)

    async def checkpoint(self) -> dict[str, Any]:
        return {"real": "checkpoint-state"}

    async def restore(self, checkpoint: dict[str, Any]) -> None:
        return None

    async def teardown(self) -> None:
        self.torn_down = True


class _FakeProvider:
    """Real, hand-written fake `EnvironmentProvider`."""

    def __init__(self) -> None:
        self.name = "fake-gym"
        self.materialization_requires_authority = False
        self.materialized_env: _FakeEnvironment | None = None

    async def materialize(self, *, scenario: str | None, config: dict[str, Any]) -> _FakeEnvironment:
        env = _FakeEnvironment()
        self.materialized_env = env
        return env


def test_real_smoke_cycle_against_a_conformant_fake_reports_smoke_tested() -> None:
    provider = _FakeProvider()

    manifest, results = asyncio.run(
        check_environment_provider_conformance(
            provider, gym_name="fake-gym", scenario="test-scenario", run_smoke_cycle=True
        )
    )

    assert manifest.manifest_conformance_level_ref == StandingValue.SMOKE_TESTED.value
    assert all(r.result_passed for r in results)
    assert any(r.result_check_ref == "smoke_teardown_succeeds" for r in results)
    assert provider.materialized_env is not None
    assert provider.materialized_env.torn_down is True
    # Never actuate() -- the fake would raise AssertionError if it were
    # called for real. "smoke_environment_has_method_actuate" (a real,
    # presence-only check, never an invocation) is expected and fine.
    assert any(r.result_check_ref == "smoke_environment_has_method_actuate" for r in results)


def test_smoke_cycle_is_skipped_when_structural_checks_already_failed() -> None:
    """A real object that fails the structural Protocol check must never
    have a smoke cycle run against it -- named and skipped, never crashed
    into or silently attempted."""

    class _StructurallyBroken:
        pass

    manifest, results = asyncio.run(
        check_environment_provider_conformance(
            _StructurallyBroken(), gym_name="broken-gym", run_smoke_cycle=True
        )
    )

    assert manifest.manifest_conformance_level_ref == StandingValue.CERT_BUILD_BROKEN.value
    assert any(r.result_check_ref == "smoke_cycle_skipped_due_to_structural_failure" for r in results)
    assert not any((r.result_check_ref or "").startswith("smoke_materialize") for r in results)
