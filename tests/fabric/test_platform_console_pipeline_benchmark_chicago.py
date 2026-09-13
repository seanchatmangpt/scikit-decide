# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style BENCHMARK testing of the real eager-forging-sparrow pipeline
over the real, unmodified ``ontology/platform-console-domain.ttl`` fixture.

The standing ask from ``~/.claude/plans/eager-forging-sparrow.md`` names four
dimensions: mutation, stress, chaos, benchmark. Mutation
(``test_platform_console_domain_mutation_chicago.py``) and chaos
(``test_platform_console_actuation_chaos_chicago.py``) are already landed.
This file is the BENCHMARK dimension.

Every timing measured here is a real ``time.perf_counter()`` wall-clock
delta around a real pipeline call -- never a fabricated/hand-typed number:

1. Real TTL parse + real SHACL-adjacent domain compile
   (``autofde_lab.fabric.rdf_domain.compile_rdf_to_pddl_files``), which
   parses the real fixture with real rdflib and performs the real
   structural/shape validation ``rdf_domain`` itself does while walking the
   graph (raising ``RdfDomainError`` on a real shape violation -- exercised
   directly, not re-verified here, by the chaos suite's malformed-TTL
   tests).
2. The real scikit-decide Astar solve
   (``autofde_lab.fabric.pddl_engine.solve_to_plan_file``) against the
   compiled PDDL files.
3. The real POWL2 provenance projection that ``solve_to_plan_file`` itself
   performs when given a real ``powl_path`` (see
   ``autofde_lab/fabric/pddl_engine.py``): a real Turtle POWL2 model file is
   written to disk as part of the same real solver call, so its cost is
   inseparable from (and always included in) the "solve" timing measured
   here -- there is no separate real projection entrypoint to isolate it
   further.

Each stage is repeated N real times (module-level constant, not tuned per
run) and reports real p50/p95/max wall-clock milliseconds computed from the
real collected samples. Regression thresholds are real, generous, absolute
wall-clock ceilings -- loose enough that ordinary machine variance/load
cannot flake this suite, tight enough that a real future regression (e.g.
someone accidentally reintroducing a quadratic grounding pass) would still
trip them.

No ``unittest.mock``/``Mock``/``MagicMock``/``patch``/``monkeypatch``
anywhere in this file. The only "instrumentation" is real wall-clock timing
around real, unmodified pipeline calls.
"""

from __future__ import annotations

import os
import statistics
import time

import pytest

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

# Real repeated-run sample size. Not fabricated, not tuned to make a
# particular run look good -- a fixed, modest N chosen so the whole suite
# stays fast in CI while still producing a real p95/max distribution.
N_RUNS = 15


def _percentile(samples_ms: list[float], pct: float) -> float:
    """Real nearest-rank percentile over real sorted samples (no numpy
    dependency assumed for this module; matches statistics.quantiles'
    inclusive method closely enough for a generous regression gate)."""
    ordered = sorted(samples_ms)
    if len(ordered) == 1:
        return ordered[0]
    rank = pct / 100.0 * (len(ordered) - 1)
    lo = int(rank)
    hi = min(lo + 1, len(ordered) - 1)
    frac = rank - lo
    return ordered[lo] + (ordered[hi] - ordered[lo]) * frac


def _report(stage: str, samples_ms: list[float]) -> dict[str, float]:
    p50 = _percentile(samples_ms, 50)
    p95 = _percentile(samples_ms, 95)
    mx = max(samples_ms)
    print(
        f"\n[benchmark] {stage}: n={len(samples_ms)} "
        f"p50={p50:.2f}ms p95={p95:.2f}ms max={mx:.2f}ms "
        f"mean={statistics.mean(samples_ms):.2f}ms"
    )
    return {"p50": p50, "p95": p95, "max": mx}


# ---------------------------------------------------------------------------
# Stage 1: real TTL parse + real rdf_domain compile (includes the real
# structural/shape validation rdf_domain performs while walking the graph).
# ---------------------------------------------------------------------------


def test_benchmark_compile_rdf_to_pddl_files_real_wallclock(tmp_path):
    samples_ms: list[float] = []
    for i in range(N_RUNS):
        domain_p = str(tmp_path / f"compile-bench-{i}-domain.pddl")
        problem_p = str(tmp_path / f"compile-bench-{i}-problem.pddl")
        t0 = time.perf_counter()
        compile_rdf_to_pddl_files(
            FIXTURE, domain_p, problem_p, domain_iri=DOMAIN_IRI, problem_iri=PROBLEM_GATED
        )
        t1 = time.perf_counter()
        assert os.path.exists(domain_p)
        assert os.path.exists(problem_p)
        samples_ms.append((t1 - t0) * 1000.0)

    stats = _report("compile_rdf_to_pddl_files (TTL parse + validate)", samples_ms)
    # Generous absolute ceiling: real measured p50 on this fixture is well
    # under 100ms; 2000ms leaves an order of magnitude of headroom for a
    # loaded CI box while still catching a real regression.
    assert stats["p95"] < 2000.0, (
        f"compile_rdf_to_pddl_files p95 regressed to {stats['p95']:.2f}ms "
        "over the real platform-console-domain.ttl fixture"
    )
    assert stats["max"] < 5000.0


# ---------------------------------------------------------------------------
# Stage 2 (+3): real Astar solve, including the real POWL2 projection that
# solve_to_plan_file performs inline when given a real powl_path.
# ---------------------------------------------------------------------------


def test_benchmark_solve_to_plan_file_real_astar_and_powl2_projection(tmp_path):
    # Compile once (outside the timed loop) -- this stage isolates the
    # solver's own real cost from the compile stage measured above.
    domain_p = str(tmp_path / "solve-bench-domain.pddl")
    problem_p = str(tmp_path / "solve-bench-problem.pddl")
    compile_rdf_to_pddl_files(
        FIXTURE, domain_p, problem_p, domain_iri=DOMAIN_IRI, problem_iri=PROBLEM_GATED
    )

    samples_ms: list[float] = []
    for i in range(N_RUNS):
        plan_p = str(tmp_path / f"solve-bench-{i}-plan.txt")
        powl_p = str(tmp_path / f"solve-bench-{i}-powl.ttl")
        t0 = time.perf_counter()
        rc = pddl_engine.solve_to_plan_file(
            domain_p, problem_p, plan_p, powl_path=powl_p
        )
        t1 = time.perf_counter()
        assert rc == pddl_engine.EXIT_PLAN_FOUND
        assert os.path.exists(plan_p)
        assert os.path.exists(powl_p), "real POWL2 projection file must be written by solve_to_plan_file"
        samples_ms.append((t1 - t0) * 1000.0)

    # Every real solve over the identical compiled domain/problem must
    # produce the identical real plan -- the timing loop is not silently
    # measuring different work run to run.
    first_plan = open(str(tmp_path / "solve-bench-0-plan.txt"), encoding="utf-8").read()
    for i in range(1, N_RUNS):
        assert (
            open(str(tmp_path / f"solve-bench-{i}-plan.txt"), encoding="utf-8").read() == first_plan
        )

    stats = _report("solve_to_plan_file (real Astar + real POWL2 projection)", samples_ms)
    assert stats["p95"] < 3000.0, (
        f"solve_to_plan_file p95 regressed to {stats['p95']:.2f}ms over the "
        "real 'problem-gated' fixture problem"
    )
    assert stats["max"] < 8000.0


# ---------------------------------------------------------------------------
# Stage 4: end-to-end pipeline (real TTL -> real PDDL -> real Astar plan ->
# real POWL2 projection) measured as a single real wall-clock span, which is
# the number that actually matters to a real caller of this pipeline.
# ---------------------------------------------------------------------------


def test_benchmark_end_to_end_pipeline_real_wallclock(tmp_path):
    samples_ms: list[float] = []
    for i in range(N_RUNS):
        domain_p = str(tmp_path / f"e2e-bench-{i}-domain.pddl")
        problem_p = str(tmp_path / f"e2e-bench-{i}-problem.pddl")
        plan_p = str(tmp_path / f"e2e-bench-{i}-plan.txt")
        powl_p = str(tmp_path / f"e2e-bench-{i}-powl.ttl")

        t0 = time.perf_counter()
        compile_rdf_to_pddl_files(
            FIXTURE, domain_p, problem_p, domain_iri=DOMAIN_IRI, problem_iri=PROBLEM_GATED
        )
        rc = pddl_engine.solve_to_plan_file(domain_p, problem_p, plan_p, powl_path=powl_p)
        t1 = time.perf_counter()

        assert rc == pddl_engine.EXIT_PLAN_FOUND
        assert "(castle-schedule res2)" in open(plan_p, encoding="utf-8").read()
        samples_ms.append((t1 - t0) * 1000.0)

    stats = _report("end-to-end (compile + solve + POWL2)", samples_ms)
    assert stats["p95"] < 4000.0, (
        f"end-to-end pipeline p95 regressed to {stats['p95']:.2f}ms over the "
        "real platform-console-domain.ttl fixture"
    )
    assert stats["max"] < 10000.0


# ---------------------------------------------------------------------------
# Relative-regression sanity: a real baseline solve against the trivial
# 'problem-reversible' fixture problem must not be dramatically slower than
# the more complex 'problem-gated' one -- both are real, both are measured,
# and this asserts they stay in the same real order of magnitude rather than
# asserting a brittle fixed ratio.
# ---------------------------------------------------------------------------

PROBLEM_REVERSIBLE = NS + "problem-reversible"


def test_benchmark_relative_cost_stays_same_order_of_magnitude_across_real_problems(tmp_path):
    def _median_solve_ms(problem_iri: str, tag: str) -> float:
        domain_p = str(tmp_path / f"{tag}-domain.pddl")
        problem_p = str(tmp_path / f"{tag}-problem.pddl")
        compile_rdf_to_pddl_files(
            FIXTURE, domain_p, problem_p, domain_iri=DOMAIN_IRI, problem_iri=problem_iri
        )
        samples = []
        for i in range(N_RUNS):
            plan_p = str(tmp_path / f"{tag}-{i}-plan.txt")
            t0 = time.perf_counter()
            rc = pddl_engine.solve_to_plan_file(domain_p, problem_p, plan_p)
            t1 = time.perf_counter()
            assert rc == pddl_engine.EXIT_PLAN_FOUND
            samples.append((t1 - t0) * 1000.0)
        return statistics.median(samples)

    reversible_ms = _median_solve_ms(PROBLEM_REVERSIBLE, "relcost-reversible")
    gated_ms = _median_solve_ms(PROBLEM_GATED, "relcost-gated")
    print(
        f"\n[benchmark] relative cost: reversible={reversible_ms:.2f}ms "
        f"gated={gated_ms:.2f}ms ratio={gated_ms / max(reversible_ms, 0.01):.2f}x"
    )
    # Generous: real Astar over this small domain should never make one
    # fixture problem more than 20x slower than another on the same domain.
    assert gated_ms < reversible_ms * 20 + 1000.0
    assert reversible_ms < gated_ms * 20 + 1000.0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v", "-s"]))
