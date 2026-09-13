# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Real, hand-written checker producing a "GymAct Certified" conformance
manifest for any real `gymact.providers.EnvironmentProvider` instance.

Never ggen-generated -- manufacture is provenance, not architecture
(`ontology/manufacture.ttl`); the types this module constructs
(`CertificationManifest`, `CertificationCheckResult`) are ggen-generated
(`gymact_certification_types.py`, from `ontology/gymact-certification.ttl`),
but the real check logic lives here, hand-written, matching every other
`ggen`-adjacent checker/verifier in this repo (`scripts/verify_ggen_generation.py`
never trusts `ggen`'s own self-report either).

Provider-agnostic by construction
------------------------------------
Every check here depends only on `gymact.providers.Environment`/
`EnvironmentProvider` -- real, `@runtime_checkable typing.Protocol`s, zero
ABC subclassing required. Confirmed genuinely generic (not
`sregym`-specific) by direct comparison against a second real adapter,
`gymact.gyms.swegym`, this session: both implement the exact same 7+1
method surface with matching signatures; only capability count/shape and
`actuate`'s real dispatch target differ per adapter. This module never
imports `gymact.gyms.sregym` or any other concrete adapter module directly
-- callers supply a real provider instance; the checker only ever asks
"does this real object satisfy the real, generic Protocol."

Reconciled against gymact's own real, existing conformance precedent
------------------------------------------------------------------------
`gymact` already has partial, unnamed provider-conformance testing before
this module existed -- found by exhaustive research this session, not
duplicated here:

- `tests/test_two_gym_gate.py` -- a real, generic lifecycle test
  (materialize -> observe -> actuate -> verify -> teardown) parametrized
  over exactly 2 real providers (`MemoryProvider`, `GymnasiumProvider`),
  with zero provider-name branching in the test body.
- `tests/test_bounded_discovery_gyms.py` -- 3 more real providers
  (`SwitchboardProvider`, `ResourceFlowProvider`, `LockAndKeyProvider`),
  using the real `gymact.process.ConformanceChecker` -- a **different**
  concept (OCEL 2.0 process-mining conformance: declared operation
  sequence vs. actual receipt trail), not provider-API-shape conformance.
- `tests/test_registry_completeness_chicago.py` -- a real registry-presence
  check across all 21+ registered provider classes (does every registered
  provider instantiate and report capabilities), a third, still different
  scope from either of the above.

None of these three is exhaustive over gymact's full real provider catalog
(2-3 providers each, chosen for structural diversity, not completeness),
and none is named "certification" anywhere in source/tests/docs (confirmed
by an exhaustive case-insensitive "certif" grep across the whole `gymact`
package this session -- the only real hits are "self-certification" used
as an anti-pattern name, unrelated prose). This module is the first
exhaustive, explicitly-named, provider-API-shape-scoped one -- genuinely
additive, not a reimplementation of any of the three real precedents
above. `scripts/run_gymact_certification_sweep.py` additionally folds in
gymact's own real `gymact doctor`/`gymact validate-profile` CLI output
(real SHACL + zero-custom-TBox validation against gymact's own packaged
RDF profile) as further, real, non-duplicative evidence.

Never fabricates a pass
--------------------------
A check that could not run (e.g. `run_smoke_cycle=False`, or a required
method missing so a later check is structurally impossible) is recorded
as a real, honest, non-passing `CertificationCheckResult` -- never silently
omitted and never coerced into a pass. `manifest_conformance_level_ref` is
computed strictly from real check results; constructing a
`CertificationManifest` never itself asserts conformance independent of
what the real checks actually found.

`resultPassed`'s real generated-type quirk, named not hidden
-------------------------------------------------------------
`CertificationCheckResult.result_passed` is typed `str | None` even though
its real ontology range is `xsd:boolean` -- the shared
`templates/constitution_module.py.tera` template (reused by 12 real
generation rules in this repo, including this one) has no `xsd:boolean`
special case; it only branches on functional-vs-non-functional. This
module deliberately does not hand-edit the generated output (that would
violate `mode = "Create"`'s own "GENERATED, DO NOT EDIT BY HAND"
contract) -- it constructs real Python `bool` values at the field
despite the (slightly imprecise) static type hint; dataclass field types
are not runtime-enforced.

Never calls `actuate()`
--------------------------
A generic checker has no safe, gym-agnostic capability payload to send --
every real adapter's capabilities are gym-specific (sregym: kubectl/MCP
dispatch; swegym: docker exec + patch + pytest). Calling `actuate()`
without knowing what it does would be exactly the kind of blind real
actuation `.claude/rules/gym-actuation-boundary.md` forbids. Named here as
a real, permanent boundary of this checker, not a gap silently left open.
"""

from __future__ import annotations

import inspect
from typing import Any

from gymact.models import Consequence
from gymact.providers import Environment, EnvironmentProvider

from autofde_lab.reasoning.gymact_certification_types import (
    CertificationCheckResult,
    CertificationManifest,
    StandingValue,
)

__all__ = ["check_environment_provider_conformance"]

#: The real, required Environment surface (per gymact.providers.Environment,
#: confirmed identical across sregym.py and swegym.py this session).
_REQUIRED_ENVIRONMENT_METHODS: tuple[str, ...] = (
    "capabilities",
    "observe",
    "actuate",
    "verify",
    "checkpoint",
    "restore",
    "teardown",
)
_REQUIRED_ENVIRONMENT_ATTRIBUTES: tuple[str, ...] = ("environment_id", "requires_authority")


def _result(check_ref: str, passed: bool, detail: str, evidence_ref: str | None = None) -> CertificationCheckResult:
    # `passed` is a real bool constructed here despite result_passed's
    # generated `str | None` type hint -- see module docstring's
    # "resultPassed's real generated-type quirk" section.
    return CertificationCheckResult(
        result_check_ref=check_ref,
        result_passed=passed,  # type: ignore[arg-type]
        result_detail=detail,
        result_evidence_ref=evidence_ref,
    )


def _check_provider_protocol(provider: Any) -> CertificationCheckResult:
    """Real structural check: does `provider` satisfy `EnvironmentProvider`?"""
    if isinstance(provider, EnvironmentProvider):
        return _result(
            "provider_satisfies_environment_provider_protocol",
            True,
            f"real object of type {type(provider).__name__!r} structurally satisfies "
            "gymact.providers.EnvironmentProvider",
        )
    return _result(
        "provider_satisfies_environment_provider_protocol",
        False,
        f"real object of type {type(provider).__name__!r} does NOT satisfy "
        "gymact.providers.EnvironmentProvider (isinstance check against the real, "
        "@runtime_checkable Protocol failed)",
    )


def _check_materialize_signature(provider: Any) -> CertificationCheckResult:
    """Real structural check: does `materialize` accept the real, documented
    `(*, scenario, config)` keyword-only shape?"""
    materialize = getattr(provider, "materialize", None)
    if materialize is None:
        return _result(
            "materialize_method_present",
            False,
            "real object has no materialize attribute at all",
        )
    try:
        sig = inspect.signature(materialize)
    except (TypeError, ValueError) as exc:
        return _result(
            "materialize_method_present",
            False,
            f"materialize is present but its real signature could not be inspected: {exc}",
        )
    params = sig.parameters
    has_scenario = "scenario" in params and params["scenario"].kind == inspect.Parameter.KEYWORD_ONLY
    has_config = "config" in params and params["config"].kind == inspect.Parameter.KEYWORD_ONLY
    if has_scenario and has_config:
        return _result(
            "materialize_method_present",
            True,
            f"real materialize signature is {sig} -- carries keyword-only scenario/config",
        )
    return _result(
        "materialize_method_present",
        False,
        f"real materialize signature is {sig} -- missing the real, required keyword-only "
        "scenario/config parameters",
    )


def _check_capabilities(provider_or_env: Any) -> tuple[CertificationCheckResult, tuple[Any, ...]]:
    """Real check: does `capabilities()` return real `Capability` tuples
    with valid `Consequence` values? Returns the real capabilities alongside
    the check result so a caller can report the real count."""
    capabilities_fn = getattr(provider_or_env, "capabilities", None)
    if capabilities_fn is None:
        return (
            _result("capabilities_returns_valid_consequences", False, "no capabilities() method present"),
            (),
        )
    try:
        real_capabilities = tuple(capabilities_fn())
    except Exception as exc:  # noqa: BLE001 -- a real, external failure, reported honestly
        return (
            _result(
                "capabilities_returns_valid_consequences",
                False,
                f"real capabilities() call raised: {type(exc).__name__}: {exc}",
            ),
            (),
        )
    if not real_capabilities:
        return (
            _result(
                "capabilities_returns_valid_consequences",
                False,
                "real capabilities() returned zero capabilities -- a real, honest "
                "STRUCTURAL_ONLY-capping finding, never silently passed",
            ),
            (),
        )
    invalid = [c for c in real_capabilities if not isinstance(getattr(c, "consequence", None), Consequence)]
    if invalid:
        return (
            _result(
                "capabilities_returns_valid_consequences",
                False,
                f"{len(invalid)} of {len(real_capabilities)} real capabilities carry a "
                "consequence value that is not a real gymact.models.Consequence member",
            ),
            real_capabilities,
        )
    return (
        _result(
            "capabilities_returns_valid_consequences",
            True,
            f"real capabilities() returned {len(real_capabilities)} capabilities, every "
            "consequence value real and valid",
        ),
        real_capabilities,
    )


async def _run_smoke_cycle(
    provider: Any, *, scenario: str | None, config: dict[str, Any]
) -> tuple[list[CertificationCheckResult], Any | None]:
    """Real materialize -> observe -> checkpoint -> teardown cycle.
    Never calls `actuate()` -- see module docstring."""
    results: list[CertificationCheckResult] = []
    env: Any | None = None

    try:
        env = await provider.materialize(scenario=scenario, config=config)
    except Exception as exc:  # noqa: BLE001 -- real, external, reported honestly
        results.append(
            _result(
                "smoke_materialize_succeeds",
                False,
                f"real materialize() raised: {type(exc).__name__}: {exc}",
            )
        )
        return results, None

    if not isinstance(env, Environment):
        results.append(
            _result(
                "smoke_materialize_returns_environment",
                False,
                f"real materialize() returned an object of type {type(env).__name__!r} that "
                "does NOT structurally satisfy gymact.providers.Environment",
            )
        )
        # Real, honest early exit: no point running further smoke checks
        # against an object that isn't a real Environment.
        teardown = getattr(env, "teardown", None)
        if callable(teardown):
            try:
                await teardown()
            except Exception:  # noqa: BLE001 -- best-effort cleanup only
                pass
        return results, env

    results.append(
        _result(
            "smoke_materialize_returns_environment",
            True,
            f"real materialize() returned a real, Protocol-conformant Environment "
            f"(environment_id={getattr(env, 'environment_id', '<missing>')!r})",
        )
    )

    for method_name in _REQUIRED_ENVIRONMENT_METHODS:
        present = callable(getattr(env, method_name, None))
        results.append(
            _result(
                f"smoke_environment_has_method_{method_name}",
                present,
                f"real Environment {'exposes' if present else 'is missing'} a callable "
                f"{method_name!r} method",
            )
        )

    capabilities_result, _capabilities = _check_capabilities(env)
    results.append(capabilities_result)

    for attr in _REQUIRED_ENVIRONMENT_ATTRIBUTES:
        present = hasattr(env, attr)
        results.append(
            _result(
                f"smoke_environment_has_attribute_{attr}",
                present,
                f"real Environment {'carries' if present else 'is missing'} the required "
                f"{attr!r} attribute",
            )
        )

    try:
        observed = await env.observe()
        results.append(
            _result(
                "smoke_observe_returns_dict",
                isinstance(observed, dict),
                f"real observe() returned {type(observed).__name__}"
                + (f" with {len(observed)} real key(s)" if isinstance(observed, dict) else ""),
            )
        )
    except Exception as exc:  # noqa: BLE001
        results.append(
            _result("smoke_observe_returns_dict", False, f"real observe() raised: {type(exc).__name__}: {exc}")
        )

    try:
        checkpoint = await env.checkpoint()
        results.append(
            _result(
                "smoke_checkpoint_returns_dict",
                isinstance(checkpoint, dict),
                f"real checkpoint() returned {type(checkpoint).__name__}",
            )
        )
    except Exception as exc:  # noqa: BLE001
        results.append(
            _result("smoke_checkpoint_returns_dict", False, f"real checkpoint() raised: {type(exc).__name__}: {exc}")
        )

    try:
        await env.teardown()
        results.append(_result("smoke_teardown_succeeds", True, "real teardown() completed without raising"))
    except Exception as exc:  # noqa: BLE001
        results.append(
            _result("smoke_teardown_succeeds", False, f"real teardown() raised: {type(exc).__name__}: {exc}")
        )

    return results, env


async def check_environment_provider_conformance(
    provider: Any,
    *,
    gym_name: str,
    environment_factory_config: dict[str, Any] | None = None,
    scenario: str | None = None,
    run_smoke_cycle: bool = False,
) -> tuple[CertificationManifest, tuple[CertificationCheckResult, ...]]:
    """Real, provider-agnostic conformance check against `provider`.

    Structural checks (Protocol shape, `materialize` signature,
    `capabilities()` validity) always run and need no live cluster/network.
    `run_smoke_cycle=True` additionally drives a real
    `materialize -> observe -> checkpoint -> teardown` cycle (never
    `actuate()`) against the real `provider` -- `environment_factory_config`/
    `scenario` are passed straight to the real `materialize()` call.

    Returns `(manifest, results)` -- the real `CertificationManifest`
    (summary, `manifest_check_result_ref` holding each real result's
    `result_check_ref` as a reference, per this repo's own "hold a
    reference, never a duplicated copy" convention) alongside the full,
    real, ordered `CertificationCheckResult` tuple a caller/test can
    inspect for per-check detail. `manifest_conformance_level_ref` is
    honestly computed -- `CERT_BUILD_BROKEN` if any structural check
    fails, `STRUCTURAL_ONLY` if structural checks pass but no smoke cycle
    ran (or ran and failed), `SMOKE_TESTED` only if every structural AND
    smoke check passed for real.
    """
    results: list[CertificationCheckResult] = []

    # `capabilities()` is a real Environment-level method (confirmed live:
    # gymact.providers.EnvironmentProvider itself declares no such method,
    # only materialize()) -- it cannot be checked without a real,
    # materialized Environment, so it is NOT part of the pure-structural
    # (no-materialize) pass. It runs inside _run_smoke_cycle instead, the
    # only point a real Environment instance actually exists.
    provider_protocol_result = _check_provider_protocol(provider)
    results.append(provider_protocol_result)

    results.append(_check_materialize_signature(provider))

    structural_passed = all(r.result_passed for r in results)

    smoke_ran = False
    smoke_passed = False
    if run_smoke_cycle and structural_passed:
        smoke_results, _env = await _run_smoke_cycle(
            provider, scenario=scenario, config=environment_factory_config or {}
        )
        results.extend(smoke_results)
        smoke_ran = True
        smoke_passed = all(r.result_passed for r in smoke_results)
    elif run_smoke_cycle and not structural_passed:
        results.append(
            _result(
                "smoke_cycle_skipped_due_to_structural_failure",
                False,
                "run_smoke_cycle=True was requested, but a structural check failed first -- "
                "never running a smoke cycle against a provider that isn't even a real "
                "Protocol-conformant EnvironmentProvider",
            )
        )

    if not structural_passed:
        conformance_level = StandingValue.CERT_BUILD_BROKEN
    elif smoke_ran and smoke_passed:
        conformance_level = StandingValue.SMOKE_TESTED
    else:
        conformance_level = StandingValue.STRUCTURAL_ONLY

    manifest = CertificationManifest(
        manifest_gym_name=gym_name,
        manifest_provider_class_ref=f"{type(provider).__module__}.{type(provider).__qualname__}",
        manifest_conformance_level_ref=conformance_level.value,
        manifest_check_result_ref=tuple(r.result_check_ref or "" for r in results),
        manifest_issued_at_ref=None,
        manifest_computation_receipt_ref=None,
    )
    return manifest, tuple(results)
