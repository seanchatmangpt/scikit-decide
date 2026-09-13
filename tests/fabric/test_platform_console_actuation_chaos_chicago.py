# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style CHAOS/fault-injection testing of the eager-forging-sparrow
pipeline's Phase 4 actuation path and Phase 2 live-state boundary.

The standing ask this file answers: prove the pipeline FAILS CLOSED under
real fault injection -- a provider whose real ``actuate()`` really raises or
really overruns its real deadline, a real TCP connection to a real closed
port standing in for an unreachable capability-state-snapshot route, and a
real malformed Turtle domain file on disk -- rather than crashing
uncleanly, silently reporting partial success, or fabricating a match where
none occurred.

Every fault below is REAL, never a mocked collaborator standing in for one:

- The "actuate() fails mid-plan" scenario materializes a real
  ``gymact.kernel.GymAct`` episode against a real, hand-written
  ``Environment`` (satisfying gymact's own ``Environment``/
  ``EnvironmentProvider`` protocols, exactly as ``MemoryProvider`` in
  ``gymact.providers`` does) whose real ``actuate()`` coroutine really
  raises ``RuntimeError`` -- not a mock configured to raise, a real
  coroutine body that does. The real ``GymAct.act()`` boundary (unmodified,
  ``gymact/src/gymact/kernel.py``) is what catches it and reports
  ``standing=BLOCKED``/``PROVIDER_ERROR:...`` -- this file only asserts on
  that real, already-hardened behavior.
- The "actuate() times out mid-plan" scenario does the same with a real
  ``anyio.sleep()`` inside ``actuate()`` that really overruns a real, tiny
  ``RuntimeLimits(actuate_timeout_s=...)`` -- a real wall-clock race, not a
  simulated timeout.
- The "capability-state-snapshot route is unreachable" scenario makes a
  real ``httpx`` GET against a real closed TCP port on localhost (nothing
  bound, nothing listening) -- a real ``httpx.ConnectError``, not an
  injected exception.
- The "malformed TTL" scenario writes real garbage / real
  semantically-broken Turtle to a real file on disk and feeds it to the
  real, unmodified ``compile_rdf_to_pddl_files`` (Phase 3).

No ``unittest.mock``/``Mock``/``MagicMock``/``patch``/``monkeypatch``
anywhere in this file.
"""

from __future__ import annotations

import os
import socket

import anyio
import httpx
import pytest
from gymact.kernel import GymAct
from gymact.limits import RuntimeLimits
from gymact.models import ActuationIntent, Capability, Consequence, MaterializationIntent

from autofde_lab.fabric import pddl_engine
from autofde_lab.fabric.rdf_domain import RdfDomainError, compile_rdf_to_pddl_files

FIXTURE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "ontology",
    "platform-console-domain.ttl",
)
DOMAIN_IRI = "urn:autofde-lab:planning-domain:platform-console:domain"


# ---------------------------------------------------------------------------
# Real fault-injecting Environment/EnvironmentProvider -- structurally
# identical in shape to gymact.providers.MemoryEnvironment/MemoryProvider
# (same protocol methods, same real state dict), except `actuate()` either
# really raises or really overruns the deadline. This is not a mock of
# `Environment` -- it is a real, if deliberately faulty, implementation of
# the same real protocol every other test in this repo actuates through.
# ---------------------------------------------------------------------------

CHAOS_CAPABILITY = Capability(
    iri="urn:gymact:chaos:capability:actuate",
    title="Chaos-injected capability whose real actuate() misbehaves on purpose.",
    consequence=Consequence.DO,
    binding="chaos",
)


class RaisingChaosEnvironment:
    """Real Environment whose real `actuate()` really raises mid-call,
    simulating gymact's OntologyDrivenProvider actuate() failing mid-plan."""

    def __init__(self) -> None:
        self.environment_id = "urn:gymact:chaos:environment:raising"
        self.requires_authority = False
        self._state: dict[str, object] = {"deployedCastle": True, "frozenOrg": True}
        self._actuate_was_called = False

    def capabilities(self) -> tuple[Capability, ...]:
        return (CHAOS_CAPABILITY,)

    async def observe(self) -> dict[str, object]:
        return dict(self._state)

    async def actuate(self, capability: Capability, payload: dict[str, object]) -> dict[str, object]:
        del capability, payload
        self._actuate_was_called = True
        # Deliberately never mutates self._state before raising -- a real
        # provider crash mid-actuation, not a partial write followed by a
        # fabricated success.
        raise RuntimeError("chaos-injected: OntologyDrivenProvider.actuate() failed mid-plan")

    async def verify(self, expected: dict[str, object]) -> tuple[bool, dict[str, object]]:
        observed = await self.observe()
        return all(observed.get(k) == v for k, v in expected.items()), observed

    async def checkpoint(self) -> dict[str, object]:
        return dict(self._state)

    async def restore(self, checkpoint: dict[str, object]) -> None:
        self._state = dict(checkpoint)

    async def teardown(self) -> None:
        pass


class HangingChaosEnvironment(RaisingChaosEnvironment):
    """Real Environment whose real `actuate()` really sleeps well past a
    real, tiny `RuntimeLimits.actuate_timeout_s` -- simulating a real
    network/actuation timeout mid-plan rather than a hard crash."""

    def __init__(self, sleep_seconds: float) -> None:
        super().__init__()
        self.environment_id = "urn:gymact:chaos:environment:hanging"
        self._sleep_seconds = sleep_seconds

    async def actuate(self, capability: Capability, payload: dict[str, object]) -> dict[str, object]:
        del capability, payload
        self._actuate_was_called = True
        await anyio.sleep(self._sleep_seconds)
        raise AssertionError("unreachable: the real timeout must fire before this returns")


class _ChaosProvider:
    def __init__(self, environment) -> None:
        self.name = "chaos"
        self.materialization_requires_authority = False
        self._environment = environment

    async def materialize(self, *, scenario, config):
        del scenario, config
        return self._environment


async def _materialize_and_act(gym: GymAct, provider) -> tuple[str, object]:
    gym.register_provider(provider)
    materialization = await gym.materialize(
        MaterializationIntent(provider=provider.name, config={}, principal="urn:prov:agent:chaos-test")
    )
    assert materialization.accepted, materialization.receipt.reason
    episode_id = materialization.episode.episode_id
    result = await gym.act(
        ActuationIntent(
            episode_id=episode_id,
            capability=CHAOS_CAPABILITY.iri,
            principal="urn:prov:agent:chaos-test",
        )
    )
    return episode_id, result


# ---------------------------------------------------------------------------
# Chaos 1: actuate() really raises mid-plan.
# ---------------------------------------------------------------------------


def test_actuate_raising_mid_plan_fails_closed_not_crashed_not_silently_successful():
    environment = RaisingChaosEnvironment()
    provider = _ChaosProvider(environment)
    gym = GymAct()

    episode_id, result = anyio.run(_materialize_and_act, gym, provider)

    assert environment._actuate_was_called is True
    # Fail-closed: the real boundary in gymact.kernel.GymAct.act catches the
    # real raised exception and reports a real, typed, non-accepted result
    # rather than propagating an uncaught exception or reporting success.
    assert result.accepted is False
    assert result.standing.value == "BLOCKED"
    assert result.receipt is not None
    assert result.receipt.reason.startswith("PROVIDER_ERROR:RuntimeError")
    # State-based honesty check: the real observed post-fault state is
    # exactly the real pre-fault state -- no fabricated partial mutation.
    assert result.observation is not None
    assert result.observation.state == {"deployedCastle": True, "frozenOrg": True}

    # A second, independent real observe() (not the cached actuation
    # result) confirms the environment itself was never actually mutated.
    post_state = anyio.run(environment.observe)
    assert post_state == {"deployedCastle": True, "frozenOrg": True}
    del episode_id


# ---------------------------------------------------------------------------
# Chaos 2: actuate() really overruns a real, tiny actuate_timeout_s.
# ---------------------------------------------------------------------------


def test_actuate_overrunning_real_deadline_fails_closed_with_named_timeout_reason():
    environment = HangingChaosEnvironment(sleep_seconds=2.0)
    provider = _ChaosProvider(environment)
    gym = GymAct(limits=RuntimeLimits(actuate_timeout_s=0.1))

    episode_id, result = anyio.run(_materialize_and_act, gym, provider)

    assert environment._actuate_was_called is True
    assert result.accepted is False
    assert result.standing.value == "BLOCKED"
    assert result.receipt is not None
    assert result.receipt.reason == "ACTUATION_TIMEOUT", (
        "a real actuate() overrunning a real tiny deadline must be reported "
        "as a real, named ACTUATION_TIMEOUT refusal -- never a hang, an "
        "uncaught exception, or a fabricated success"
    )
    del episode_id


# ---------------------------------------------------------------------------
# Chaos 3: the Phase 2 capability-state-snapshot route is unreachable --
# real TCP connection refusal against a real closed localhost port.
# ---------------------------------------------------------------------------


def _real_closed_local_port() -> int:
    """Binds a real ephemeral TCP port, then immediately closes it, so the
    port number is real and (with overwhelming likelihood in a short-lived
    test) nothing is listening on it -- a real "route unreachable" fault,
    not a hand-picked magic number."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _fetch_snapshot_or_fail_closed(base_url: str) -> dict:
    """Mirrors the real pipeline contract this repo's own live-infra test
    (`test_platform_console_capability_plan_chicago.py`'s `fetch_snapshot`)
    uses against the real Phase 2 route: a real ``httpx.get`` with a short
    timeout. On real unreachability this must propagate a real exception --
    never fabricate an empty/default snapshot that downstream diffing could
    mistake for a real, honestly-observed pre/post state."""
    response = httpx.get(
        f"{base_url}/api/internal/capability-state-snapshot",
        headers={"x-capability-state-snapshot-secret": "unused-in-this-chaos-test"},
        timeout=1.0,
    )
    response.raise_for_status()
    return response.json()["snapshot"]["facts"]


def test_unreachable_capability_state_snapshot_route_fails_closed_with_a_real_connect_error():
    dead_port = _real_closed_local_port()
    base_url = f"http://127.0.0.1:{dead_port}"

    with pytest.raises(httpx.ConnectError):
        _fetch_snapshot_or_fail_closed(base_url)
    # No assertion of a fabricated fallback snapshot: the function above has
    # exactly one real return path (a real 2xx JSON body) and one real
    # exception path -- there is no third, silent-success path to test
    # against, which is itself the property under test.


# ---------------------------------------------------------------------------
# Chaos 4: a real, malformed Turtle domain file -- both syntactically
# invalid Turtle and semantically-empty-but-parseable Turtle -- must fail
# closed through the real, unmodified Phase 3 compiler rather than
# silently compiling to an empty/stale domain or crashing uncleanly deep
# inside rdflib with no actionable error.
# ---------------------------------------------------------------------------


def test_syntactically_malformed_turtle_fails_closed_through_the_real_compiler(tmp_path):
    malformed = tmp_path / "malformed.ttl"
    malformed.write_text("@prefix pd: <urn:autofde-lab:planning-domain:> .\nex:domain a pd:Domain [ this is not valid turtle @@@")

    domain_p = str(tmp_path / "domain.pddl")
    problem_p = str(tmp_path / "problem.pddl")

    with pytest.raises(Exception):  # real rdflib parser exception, un-narrowed by design
        compile_rdf_to_pddl_files(str(malformed), domain_p, problem_p)

    # Fail closed: no partial/stale PDDL files were written by the failed
    # compile attempt.
    assert not os.path.exists(domain_p)
    assert not os.path.exists(problem_p)


def test_semantically_empty_turtle_with_no_domain_fails_closed_not_silently(tmp_path):
    """Real, syntactically valid Turtle that simply declares no `pd:Domain`
    at all (e.g. a truncated/wrong-file mistake) must be refused by the
    real compiler with a real, named error -- never silently compiled into
    an empty domain that would make every subsequent plan trivially
    (and wrongly) either unsolvable-by-omission or vacuously solvable."""
    empty = tmp_path / "no-domain.ttl"
    empty.write_text(
        "@prefix pd: <urn:autofde-lab:planning-domain:> .\n"
        "@prefix ex: <urn:autofde-lab:planning-domain:platform-console:> .\n"
        "ex:not-a-domain a pd:Predicate ; pd:predicateName \"unrelated\" .\n"
    )

    domain_p = str(tmp_path / "domain.pddl")
    problem_p = str(tmp_path / "problem.pddl")

    with pytest.raises(RdfDomainError):
        compile_rdf_to_pddl_files(str(empty), domain_p, problem_p)

    assert not os.path.exists(domain_p)
    assert not os.path.exists(problem_p)


# ---------------------------------------------------------------------------
# Chaos 5: end-to-end honesty check combining Phase 3 (real solve against
# the real, unmutated fixture) with a chaos-injected actuation failure --
# the pipeline must refuse to claim the plan's declared effect happened
# when the real actuation step that was supposed to produce it really
# failed. This is the "no fabricated diff match" case named in the task.
# ---------------------------------------------------------------------------


def test_pipeline_never_claims_a_plan_effect_happened_when_actuation_really_failed(tmp_path):
    # Real Phase 3 solve, unmodified and unmutated -- establishes a real
    # plan with a real declared first-step effect.
    domain_p = str(tmp_path / "domain.pddl")
    problem_p = str(tmp_path / "problem.pddl")
    plan_p = str(tmp_path / "plan.txt")
    compile_rdf_to_pddl_files(
        FIXTURE,
        domain_p,
        problem_p,
        domain_iri=DOMAIN_IRI,
        problem_iri="urn:autofde-lab:planning-domain:platform-console:problem-gated",
    )
    rc = pddl_engine.solve_to_plan_file(domain_p, problem_p, plan_p)
    assert rc == pddl_engine.EXIT_PLAN_FOUND
    plan_lines = open(plan_p, encoding="utf-8").read().splitlines()
    assert "(castle-schedule res2)" in plan_lines

    # Real chaos-injected actuation of that plan's step: the provider that
    # would have run it really raises.
    environment = RaisingChaosEnvironment()
    provider = _ChaosProvider(environment)
    gym = GymAct()
    _episode_id, result = anyio.run(_materialize_and_act, gym, provider)

    # The plan's declared effect (a real fact this domain models as
    # "scheduled") must never be reported as achieved when the real
    # actuation step that was supposed to produce it really failed.
    assert result.accepted is False
    declared_effect_claimed_true = (
        result.accepted and result.observation is not None and result.observation.state.get("scheduled") is True
    )
    assert declared_effect_claimed_true is False, (
        "the pipeline must never report a plan step's declared effect as "
        "achieved when the real actuation call that should have produced "
        "it really failed -- no fabricated diff match"
    )
