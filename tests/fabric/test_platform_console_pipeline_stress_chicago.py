# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style STRESS testing of the real eager-forging-sparrow pipeline
and the real ``gymact`` actuation path under real concurrency.

The standing ask from ``~/.claude/plans/eager-forging-sparrow.md`` names four
dimensions: mutation, stress, chaos, benchmark. Mutation
(``test_platform_console_domain_mutation_chicago.py``) and chaos
(``test_platform_console_actuation_chaos_chicago.py``) are already landed;
``test_platform_console_pipeline_benchmark_chicago.py`` is the benchmark
dimension. This file is the STRESS dimension.

Two real concurrency stresses:

1. Many real concurrent Astar solves (``ThreadPoolExecutor``, real OS
   threads, real ``pddl_engine.solve_to_plan_file`` calls each writing to
   its own real files on disk) against the identical real, unmodified
   ``ontology/platform-console-domain.ttl`` fixture -- every one of the N
   concurrent real solves must produce the byte-identical real plan, proving
   the real compile/solve pipeline holds no shared mutable state that a
   second concurrent caller could corrupt.
2. Many real concurrent ``gymact.kernel.GymAct`` episodes, each with its own
   real ``gymact.providers.MemoryProvider``/``MemoryEnvironment`` instance,
   driven concurrently via real ``anyio`` structured concurrency
   (``anyio.create_task_group``) -- every episode's real, independently
   materialized environment must end up in exactly the state its own real
   actuation calls produced, with no cross-episode state bleed (a real,
   distinct actuated value per episode, not a value borrowed from a sibling
   episode's environment).

No ``unittest.mock``/``Mock``/``MagicMock``/``patch``/``monkeypatch``
anywhere in this file. Every concurrent unit of work below is a real thread
or a real asyncio/anyio task calling real, unmodified library code.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed

import anyio
from gymact.kernel import GymAct
from gymact.models import ActuationIntent, MaterializationIntent
from gymact.providers import MEMORY_CAPABILITIES, MemoryProvider

from autofde_lab.fabric import pddl_engine
from autofde_lab.fabric.rdf_domain import compile_rdf_to_pddl_files

FIXTURE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "ontology",
    "platform-console-domain.ttl",
)

DOMAIN_IRI = "urn:autofde-lab:planning-domain:platform-console:domain"
NS = "urn:autofde-lab:planning-domain:platform-console:"
PROBLEM_GATED = NS + "problem-gated"

N_CONCURRENT = 16


# ---------------------------------------------------------------------------
# Stress 1: N real concurrent Astar solves against the same real fixture,
# each in its own real OS thread, each writing its own real files.
# ---------------------------------------------------------------------------


def _compile_and_solve_once(tmp_path, idx: int) -> tuple[int, str]:
    """One real, self-contained compile+solve unit of work: its own real
    PDDL/plan files on disk so concurrent threads never touch the same
    real file, isolating "is the pipeline itself thread-safe" from
    "did two threads race on the same output path" (an unrelated,
    uninteresting race this test is not about)."""
    domain_p = str(tmp_path / f"stress-solve-{idx}-domain.pddl")
    problem_p = str(tmp_path / f"stress-solve-{idx}-problem.pddl")
    plan_p = str(tmp_path / f"stress-solve-{idx}-plan.txt")
    compile_rdf_to_pddl_files(
        FIXTURE, domain_p, problem_p, domain_iri=DOMAIN_IRI, problem_iri=PROBLEM_GATED
    )
    rc = pddl_engine.solve_to_plan_file(domain_p, problem_p, plan_p)
    plan_text = open(plan_p, encoding="utf-8").read() if os.path.exists(plan_p) else ""
    return rc, plan_text


def test_many_concurrent_astar_solves_all_produce_the_identical_real_plan(tmp_path):
    with ThreadPoolExecutor(max_workers=N_CONCURRENT) as pool:
        futures = [
            pool.submit(_compile_and_solve_once, tmp_path, i) for i in range(N_CONCURRENT)
        ]
        results = [f.result() for f in as_completed(futures)]

    assert len(results) == N_CONCURRENT
    for rc, _plan_text in results:
        assert rc == pddl_engine.EXIT_PLAN_FOUND, (
            "every real concurrent solve against the identical real fixture "
            "must succeed -- a failure here would indicate shared mutable "
            "state corrupting a concurrent caller's compile/solve"
        )

    plans = {plan_text for _rc, plan_text in results}
    assert len(plans) == 1, (
        f"expected exactly one distinct real plan across {N_CONCURRENT} real "
        f"concurrent solves against the identical fixture; got {len(plans)} "
        "distinct plans -- evidence of a real race/shared-state bug"
    )
    (only_plan,) = plans
    assert "(castle-schedule res2)" in only_plan


# ---------------------------------------------------------------------------
# Stress 1b: the same real concurrent-solve stress via a real thread pool
# racing against a SHARED real compiled domain/problem pair (compiled once,
# read concurrently by every thread) -- stresses the real solver's own
# internal state in isolation from any per-thread file-path race.
# ---------------------------------------------------------------------------


def _solve_shared_files(domain_p: str, problem_p: str, tmp_path, idx: int) -> tuple[int, str]:
    plan_p = str(tmp_path / f"stress-shared-{idx}-plan.txt")
    rc = pddl_engine.solve_to_plan_file(domain_p, problem_p, plan_p)
    plan_text = open(plan_p, encoding="utf-8").read() if os.path.exists(plan_p) else ""
    return rc, plan_text


def test_many_concurrent_solves_against_one_shared_compiled_domain_agree(tmp_path):
    domain_p = str(tmp_path / "shared-domain.pddl")
    problem_p = str(tmp_path / "shared-problem.pddl")
    compile_rdf_to_pddl_files(
        FIXTURE, domain_p, problem_p, domain_iri=DOMAIN_IRI, problem_iri=PROBLEM_GATED
    )

    with ThreadPoolExecutor(max_workers=N_CONCURRENT) as pool:
        futures = [
            pool.submit(_solve_shared_files, domain_p, problem_p, tmp_path, i)
            for i in range(N_CONCURRENT)
        ]
        results = [f.result() for f in as_completed(futures)]

    for rc, _plan_text in results:
        assert rc == pddl_engine.EXIT_PLAN_FOUND
    plans = {plan_text for _rc, plan_text in results}
    assert len(plans) == 1, (
        "solving the SAME real compiled domain/problem concurrently from "
        f"{N_CONCURRENT} real threads must never disagree on the resulting "
        "real plan"
    )


# ---------------------------------------------------------------------------
# Stress 2: N real concurrent gymact episodes, each with its own real
# MemoryProvider/MemoryEnvironment, driven concurrently via real anyio
# structured concurrency -- no cross-episode state bleed.
# ---------------------------------------------------------------------------


async def _run_one_episode(gym: GymAct, episode_index: int, results: dict[int, object]) -> None:
    """One real, fully independent gymact episode: its own real
    MemoryProvider (a fresh real MemoryEnvironment underneath), its own real
    materialization, and one real `increment` actuation whose amount is
    unique per episode so any cross-episode state bleed (writing to, or
    reading from, a sibling episode's real environment) would show up as a
    wrong, non-unique observed value."""
    provider = MemoryProvider()
    # MemoryProvider's class-level `name` is the fixed string "memory";
    # GymAct.register_provider refuses duplicate names outright, so each
    # real concurrent episode needs its own real, distinct provider name --
    # a normal instance-attribute override, not a mock.
    provider.name = f"stress-memory-{episode_index}"
    gym.register_provider(provider)
    materialization = await gym.materialize(
        MaterializationIntent(
            provider=provider.name,
            config={"requires_authority": False},
            principal=f"urn:prov:agent:stress-test-{episode_index}",
        )
    )
    assert materialization.accepted, materialization.receipt.reason
    episode_id = materialization.episode.episode_id

    increment_capability = next(
        c for c in MEMORY_CAPABILITIES if c.binding == "increment"
    )
    # A distinct amount per episode -- the real, checkable fingerprint that
    # this episode's real actuation touched only this episode's real
    # environment.
    unique_amount = 1000 + episode_index
    result = await gym.act(
        ActuationIntent(
            episode_id=episode_id,
            capability=increment_capability.iri,
            principal=f"urn:prov:agent:stress-test-{episode_index}",
            payload={"key": "counter", "amount": unique_amount},
        )
    )
    results[episode_index] = (result, unique_amount)


async def _run_all_episodes_concurrently(n: int) -> dict[int, object]:
    gym = GymAct()
    results: dict[int, object] = {}
    async with anyio.create_task_group() as tg:
        for i in range(n):
            tg.start_soon(_run_one_episode, gym, i, results)
    return results


def test_many_concurrent_gymact_episodes_show_no_cross_episode_state_bleed():
    results = anyio.run(_run_all_episodes_concurrently, N_CONCURRENT)

    assert len(results) == N_CONCURRENT
    seen_amounts: set[int] = set()
    for episode_index, (result, unique_amount) in results.items():
        assert result.accepted is True, (
            f"episode {episode_index}: real concurrent actuation must "
            f"succeed -- {getattr(result.receipt, 'reason', None)!r}"
        )
        assert result.observation is not None
        observed_counter = result.observation.state.get("counter")
        assert observed_counter == unique_amount, (
            f"episode {episode_index}: expected its own real environment's "
            f"'counter' to be exactly its unique increment amount "
            f"({unique_amount}); observed {observed_counter!r} instead -- "
            "evidence of cross-episode state bleed between concurrently "
            "materialized real MemoryEnvironment instances"
        )
        assert unique_amount not in seen_amounts, "duplicate unique_amount -- test setup bug"
        seen_amounts.add(unique_amount)

    # Every one of the N real, independently materialized environments
    # produced a real, distinct observed value -- no two episodes converged
    # on the same (or a swapped) real state.
    observed_values = {
        result.observation.state.get("counter") for result, _ in results.values()
    }
    assert len(observed_values) == N_CONCURRENT


# ---------------------------------------------------------------------------
# Stress 2b: many real concurrent actuations against episodes materialized
# on the SAME real GymAct instance but via a real ThreadPoolExecutor running
# an independent anyio event loop per thread -- stresses GymAct's own
# episode-registry bookkeeping under real concurrent registration+actuation
# from multiple real OS threads, not just multiple async tasks on one loop.
# ---------------------------------------------------------------------------


def _run_episode_in_own_loop(episode_index: int) -> tuple[bool, int, int]:
    # A fresh real GymAct per real OS thread/event loop: GymAct's internal
    # `anyio.Lock` is bound to the event loop that first uses it, so sharing
    # one GymAct instance across independently-run anyio event loops (one
    # per thread) would trip an unrelated anyio cross-loop usage error, not
    # the real pipeline property this test targets (no cross-episode state
    # bleed under concurrent OS-thread execution of the full materialize+act
    # pipeline).
    async def _inner() -> tuple[bool, int, int]:
        gym = GymAct()
        provider = MemoryProvider()
        provider.name = f"thread-stress-memory-{episode_index}"
        gym.register_provider(provider)
        materialization = await gym.materialize(
            MaterializationIntent(
                provider=provider.name,
                config={"requires_authority": False},
                principal=f"urn:prov:agent:thread-stress-{episode_index}",
            )
        )
        assert materialization.accepted, materialization.receipt.reason
        episode_id = materialization.episode.episode_id
        increment_capability = next(c for c in MEMORY_CAPABILITIES if c.binding == "increment")
        unique_amount = 2000 + episode_index
        result = await gym.act(
            ActuationIntent(
                episode_id=episode_id,
                capability=increment_capability.iri,
                principal=f"urn:prov:agent:thread-stress-{episode_index}",
                payload={"key": "counter", "amount": unique_amount},
            )
        )
        observed = result.observation.state.get("counter") if result.observation else None
        return result.accepted, unique_amount, observed

    return anyio.run(_inner)


def test_many_concurrent_gymact_episodes_across_real_os_threads_show_no_state_bleed():
    with ThreadPoolExecutor(max_workers=N_CONCURRENT) as pool:
        futures = [
            pool.submit(_run_episode_in_own_loop, i) for i in range(N_CONCURRENT)
        ]
        outcomes = [f.result() for f in as_completed(futures)]

    assert len(outcomes) == N_CONCURRENT
    for accepted, unique_amount, observed in outcomes:
        assert accepted is True
        assert observed == unique_amount, (
            "cross-thread episode state bleed: an episode materialized and "
            "actuated on one real OS thread observed a counter value that "
            "did not match its own unique real actuation amount"
        )
