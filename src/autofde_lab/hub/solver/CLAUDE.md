# Role

Concrete solvers: search procedures over domains. Pure-Python solvers live here directly; ~35
are thin wrappers over C++20 implementations in `cpp/` bound with pybind11 (`astar/`, `mcts/`,
`iw/`, `riw/`, `lrtdp/`, `martdp/`, `sarsop/`, `bfws/`, …). Third-party bridges:
`ray_rllib/`, `stable_baselines/`, `up/`, `do_solver/`, `dspy_policy/`.

# Authority

- Search a domain and return a candidate: a plan, a policy, or a value function.
- Declare applicability structurally via `T_domain` — `get_domain_requirements()`
  (`src/autofde_lab/solvers.py:85`) derives the required domain characteristics from that MRO, and
  `check_domain()` (`solvers.py:123`) tests `isinstance` plus the `_check_domain_additional()`
  hook.

# Non-authority

- **A solver result is a candidate, never an actuation.** It is not admitted, not authorized,
  not executed. `mfw` admits; `bcinr` schedules; a broker actuates.
- A solver may not declare itself preferable to another. There is no ranking authority in this
  repo (see invariant 2).

# Inputs

A domain factory, solver hyperparameters, optional callbacks, optional heuristics.

# Outputs

`Solver` subclasses registered under the `autofde_lab.solvers` entry-point group; `solve()` /
`get_next_action()` / `get_utility()` results.

# Invariants

1. **Importability is not execution.** All 57 registered solvers import in a full-extras
   environment, which says nothing about runnability. `get_domain_requirements()` describes
   *domain characteristics* only and says nothing about *constructor* requirements — 7 solvers
   are ontology-applicable yet not runnable with defaults (`IW`, `RIW`, `RayRLlib`,
   `StableBaseline`, `UPSolver`, `MAHD`, …). That is `REQUIRES_CONFIGURATION`, a distinct
   category from inapplicable.
2. **`match_solvers(..., ranked=True)` accepts the flag and ignores it**
   (`src/autofde_lab/utils.py:126`, `# TODO: implement ranking heuristic`); it always returns a
   plain list. Any claim that one solver dominates another must come from running both and
   comparing measured plans/costs. A tie is reported as a tie, not as N wins.
3. **Failed loads surface as `None`** (`utils.py:94` warns and returns `None`). A coverage tally
   must treat `None` as positive `UNSUPPORTED` evidence or a broken solver vanishes silently.
4. Three-tier method naming applies: implement `_solve_()` / `_get_next_action_()`; do not
   override the public autocast wrappers.
5. C++ solvers share one architecture — template header, impl, pybind wrapper, `.cc.in`,
   `CMakeLists.txt`. Read a sibling (A* for simple, MCTS for complex) rather than re-deriving.
6. Skipped tests gated on missing extras (`z3-solver`, `optuna`, `plado`, macOS `libomp`
   segfault) are environment gates — `UNSUPPORTED`, not incomplete work.

# Neighboring components

`src/autofde_lab/builders/solver/` (mixins), `src/autofde_lab/solvers.py` (base + applicability),
`src/autofde_lab/utils.py` (registry + matching), `hub/domain/` (subjects), `cpp/` (compiled
backends), `fabric/coverage.py` (classifies every solver against a domain),
`tests/solvers/python/`, `tests/solvers/cpp/`.

# Verification

```bash
uv run pytest tests/solvers/python/test_<name>.py -v
uv run python -m autofde_lab.fabric match --domain <Domain>
```

A solver claim is `ALIVE` only with a Chicago-style test running `solve()` on a real domain
this session — never "compiles", never "the happy path works".

# Standing ceiling

Strongest establishable claim: **`ALIVE` for "solver S ran on domain D and returned result R
with measured cost/quality Q"**, output quoted.

Explicitly not establishable: that S is the best solver for D (no ranking exists — measure or
say nothing); that S will run on D given only ontology applicability (constructor requirements
are outside the derivation); that R is correct where the underlying semantics are unimplemented
(the PDDL backend's `:derived-predicates` / `:constraints` / `:preferences` gaps are silent —
see `../../fabric/CLAUDE.md`); or that R was admitted or executed.

# Update obligations

- New or removed solver → `pyproject.toml` entry point **and** regenerate
  `ontology/autofde-lab-capabilities.ttl`; `tests/ecosystem/` asserts the ontology's requirement
  set equals the live `get_domain_requirements()` derivation.
- Changed `T_domain` → applicability moved; re-run `fabric/coverage.py`.
- If ranking is implemented, retract invariant 2 here, in `src/autofde_lab/CLAUDE.md`,
  `.claude/rules/ecosystem-boundary.md`, and `docs/ecosystem-standing.md` in the same change.
