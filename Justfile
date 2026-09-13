# Test-loop commands. See docs/STATUS.md and the 80/20 ERRC rationale in
# CLAUDE.md's Build section for why these two commands exist and what each
# excludes. Both use `.venv/bin/python -m pytest` directly (not `uv run
# pytest`) to avoid uv's per-invocation CMake/Ninja rebuild check, which adds
# tens of seconds to minutes to every invocation for no reason on an
# unchanged build.
#
# PYTHONPATH exported to the repo root for every recipe below: Ray's spawned
# worker processes (test-full's tests/solvers/python partition uses
# ray.rllib) don't inherit pytest's in-process sys.path insertion when
# unpickling test-defined classes to reimport them by name -- they only see
# the PYTHONPATH env var as set at process launch. Confirmed by reproducing
# `ModuleNotFoundError: No module named 'tests.solvers'` inside a Ray actor
# without this, and confirming it disappears with PYTHONPATH set, holding
# --import-mode/pyproject.toml constant. Harmless for every other recipe.
export PYTHONPATH := justfile_directory()

# Hot loop: unit-weight tests only, measured ~5.9-6.0s over several runs
# (-n 4). Excludes, on top of the native/RL/scheduling/crown exclusions
# test-full still covers:
#   - tests/domains and tests/flight_planning entirely -- not because their
#     *tests* are individually slow (none >5s), but because importing them
#     pays for torch_geometric/unified-planning/cartopy/gymnasium/openap/
#     pygeodesy at collection time (measured tests/domains alone: ~7s just
#     to collect). That fixed import cost is what a hot loop can't carry.
#   - tests/autofde/test_terraform_guards.py -- shells out to the real
#     `terraform` binary (~2s).
#   - tests/fabric/test_dspy_mcp_planner_loop_chicago.py and
#     tests/fabric/test_mcp_ocel_instrumentation_chicago.py -- both spin up
#     a real MCP server (fastmcp `Client`); the latter measured ~5.9s alone,
#     the single largest item in a full `--durations` breakdown of this
#     target. Both named "chicago" precisely because they're real, not
#     unit-weight; belong in test-full's catch-all partition, not here.
#   - tests/powl/test_import_separation.py -- each test forks a fresh
#     subprocess by design (see the file's own docstring: checking
#     sys.modules in-process would be unfalsifiable) -- ~1.5s across 3 tests.
#   - test_up_bridge_domain_rl (--deselect, not --ignore, since the rest of
#     its file is otherwise fast): real ray.rllib DQN training. Silently
#     free on this macOS box only because of an unrelated libomp skipif --
#     would run for real on Linux/CI, so it's pulled out structurally rather
#     than relying on that skip.
#   - tests/evidence/test_level4_witness_falsifiers_chicago.py -- same shape
#     as test_level4_ocel_vocabulary_chicago.py below (72.19s excluded from
#     the "Level 4 crown hot loop" recipe for the identical reason): its
#     module-scoped fixture runs one real `run_real_trial`, measured
#     ~73.6s alone (2026-08-08, `pytest tests/evidence/... -v`). 14 real
#     identity-mutation falsifiers against that one real trial is exactly
#     the right shape for a Chicago test; it is simply not unit-weight.
# None of the above is dropped from coverage -- everything excluded here
# still runs, unrestricted, in test-full below.
#
# -n 4: pytest-xdist, swept on a 16-core box against both this hot set and
# the earlier (domains-included) one -- 4 workers wins consistently, more
# workers make wall time *worse* because each extra worker re-pays fixed
# interpreter+import startup cost, and no test here is individually slow
# enough to benefit from finer-grained parallelism. Re-sweep if the set's
# composition changes materially.
test:
    .venv/bin/python -m pytest tests -q -n 4 \
        --ignore=tests/solvers/cpp \
        --ignore=tests/solvers/python \
        --ignore=tests/scheduling \
        --ignore=tests/ecosystem \
        --ignore=tests/domains \
        --ignore=tests/flight_planning \
        --ignore=tests/autofde/test_terraform_guards.py \
        --ignore=tests/fabric/test_dspy_mcp_planner_loop_chicago.py \
        --ignore=tests/fabric/test_mcp_ocel_instrumentation_chicago.py \
        --ignore=tests/powl/test_import_separation.py \
        --ignore=tests/test_self_play_dspy_advanced_planning_chicago.py \
        --ignore=tests/test_self_play_dspy_all_domains_chicago.py \
        --ignore=tests/test_self_play_dspy_turbofieldfare_chicago.py \
        --ignore=tests/test_chatman_wasm.py \
        --ignore=tests/test_import_all_submodules.py \
        --ignore=tests/evidence/test_level4_witness_falsifiers_chicago.py

# Full loop: everything, matching .github/workflows/ci.yml's `integration`
# job partitioning -- actually 5 pytest invocations, not 4: the python
# partition is itself split (test_optuna_rayrllib.py separately), plus
# scheduling, the catch-all, and cpp (--timeout=300, only there).
# Minutes, not seconds -- run before finishing a branch, not on every edit.
# Nothing `test` ignores/deselects is dropped here -- domains, flight_planning,
# test_up_bridge_domain_rl, terraform_guards, dspy_mcp_planner_loop_chicago,
# and import_separation all still run unrestricted in the catch-all partition
# below (none of their parent dirs are ignored there).
# tests/solvers/python and tests/*/cpp are NOT run under xdist: both already
# parallelize internally (Ray rollout workers; cpp's own
# TestHSVIParallel/-type tests spawn their own worker pools) -- stacking
# xdist workers on top risks resource contention (competing Ray clusters,
# oversubscribed cores) this pass didn't have budget to validate safely.
# tests/scheduling has neither: function-scoped fixtures only, no internal
# parallelism -- confirmed safe and measured faster (35.0s serial -> 26.2s
# at -n 4, same 6 pre-existing failures, no new ones) before adding -n 4.
test-full:
    .venv/bin/python -m pytest -vv tests/solvers/python --ignore tests/solvers/python/test_optuna_rayrllib.py
    .venv/bin/python -m pytest -vv tests/solvers/python/test_optuna_rayrllib.py
    .venv/bin/python -m pytest -vv tests/scheduling -n 4
    .venv/bin/python -m pytest -vv --ignore-glob 'tests/*/cpp' --ignore tests/solvers/python --ignore tests/scheduling
    .venv/bin/python -m pytest -vv --timeout=300 tests/*/cpp

# Level 4 crown hot loop: the four Level 4 suites whose wall time is NOT
# dominated by planner federation. Measured this session (2026-08-08,
# `.venv/bin/python -m pytest <file> -q --durations=10`, one file per
# invocation, real `/usr/bin/time -p` wall clock):
#
#   test_level4_definition_of_done.py          5.90s   22 passed
#   test_level4_isolation_chicago.py           3.54s    3 passed
#   test_level4_shacl_conformance_chicago.py   1.41s    8 passed
#   test_crown_factor_typed_acceptance.py      1.10s   11 passed
#   test_level4_ocel_vocabulary_chicago.py    72.19s    <- EXCLUDED here
#
# Combined, in one process: 8.54s serial -> 4.84s at -n 4, 44 passed.
#
# Why ocel_vocabulary is excluded and NOT skipped: 69.87s of its 72.19s is a
# single module-scoped fixture, `executed_trial`, running one real
# `run_real_trial`. cProfile of that trial (cumulative, real run this
# session) attributes it as:
#
#   69.60s  total trial
#   65.10s  planner_federation.run_federation   <- 94% of the trial
#             49 x _solve_one_isolated, SERIAL, each fork()s a child that
#             re-imports the whole solver stack (torch, discrete_optimization,
#             ...) -- ~1.33s per solver, and the solve itself is a fraction
#             of that.
#    4.15s  12 x RealBlindEnvironment.try_action (real gymact subprocess)
#
# So this suite is FEDERATION-bound, not gymact-subprocess-bound. The gymact
# bridge is 6% of the cost. Note separately that `try_action` REPLAYS THE
# FULL COMMITTED HISTORY on every call (`self._history + prefix + [req]` sent
# to one subprocess), so actuation work grows O(n^2) in the number of
# committed probes -- at 12 probes that is still only 4.15s, but it is the
# term that will dominate if probe budgets grow. Not changed here: that file
# is owned elsewhere; this is a measurement, not a fix.
#
# Nothing is deleted or skipped -- `test-level4-full` below runs all five.
test-level4:
    .venv/bin/python -m pytest -q -n 4 \
        tests/ecosystem/test_level4_definition_of_done.py \
        tests/ecosystem/test_level4_shacl_conformance_chicago.py \
        tests/ecosystem/test_crown_factor_typed_acceptance.py \
        tests/ecosystem/test_level4_isolation_chicago.py

# Every Level 4 suite, federation-bound ones included. Minutes, not seconds.
test-level4-full:
    .venv/bin/python -m pytest -q tests/ecosystem
