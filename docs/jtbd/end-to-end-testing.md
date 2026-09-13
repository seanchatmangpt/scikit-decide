# JTBD: end-to-end testing for scikit-decide

## Context

scikit-decide is a plugin hub: roughly three dozen domains and several dozen
solvers register themselves via `[project.entry-points."skdecide.domains"]`
and `[project.entry-points."skdecide.solvers"]` in `pyproject.toml`, and are
discovered at runtime through `skdecide.utils.get_registered_domains()` /
`get_registered_solvers()` / `load_registered_domain()` /
`load_registered_solver()`. The only thing that guarantees a given domain and
a given solver actually work together is the `Domain`/`Solver`
characteristic-mixin contract, checked at runtime by `Solver.check_domain()`.

`tests/domains/` and `tests/solvers/` verify components in isolation, often
by hand-importing a concrete class and never going through the registration
mechanism at all. `tests/scheduling/` and `tests/flight_planning/` do the
same for their families: they construct domain instances directly and pair
them with a hand-imported solver class. None of this proves that the
documented client usage pattern (`CLAUDE.md`'s "How to Use Scikit-Decide")
actually works end-to-end:

```python
from skdecide import utils
MyDomain = utils.load_registered_domain("Maze")
MySolver = utils.load_registered_solver("Astar")
assert MySolver.check_domain(MyDomain())
with MySolver(domain_factory=lambda: MyDomain()) as solver:
    solver.solve()
```

This document names the jobs that a real, mock-free, load-by-name pipeline
test suite is hired to do, and who is hiring it.

## Jobs-to-be-done

Framed as "When I ___, I want to ___, so I can ___":

1. **When I add or modify a registered domain or solver**, I want a signal
   that it still round-trips through `check_domain → solve → rollout`, so I
   can catch integration breaks before a maintainer does in review.
2. **When I bump a heavy optional dependency** (`discrete-optimization`,
   `openap`, `cartopy`, MiniZinc, `ray`, `torch`, `jax`, ...), I want proof
   that the domains/solvers depending on it still solve real instances
   end-to-end, so I don't ship a silent breakage that unit tests — which
   often exercise domain internals directly rather than the dependency's
   real solve path — would miss.
3. **When I evaluate scikit-decide** for a scheduling (RCPSP family) or
   flight-planning use case, I want a runnable, minimal, real example
   proving the advertised hub domain + hub solver combination actually
   solves and rolls out, so I can trust the library before investing
   integration effort of my own.
4. **When I refactor `skdecide.utils`** (`rollout`, `check_domain`,
   registration loading) or the `Domain`/`Solver` builder-mixin
   composition, I want tests that fail if the *public* load-by-name
   contract breaks, independent of any single domain's or solver's own unit
   tests, so I don't regress the one thing every hub component depends on.
5. **When CI promotes a change to `master`**, I want authoritative, real
   evidence — not mocked — that a representative domain from each family
   (toy/game, scheduling, flight planning) solves with a real solver, so a
   tagged release is backed by proof, not by inference from unit tests.
6. **When a contributor's PR only touches one hub domain or solver**, I
   want the expensive, compiled-extension-dependent proof kept off the PR
   rail, so review feedback stays fast — per the two-rail design in
   `docs/ci.md`.

## Personas

- **Hub contributor** — adds or modifies a domain or solver plugin.
- **Library integrator** — a downstream user picking a domain+solver
  combination for their own scheduling or flight-ops problem.
- **Maintainer / release manager** — owns `docs/ci.md`'s full-qualification
  gate and decides what "proof" a tagged release needs.
- **CI system itself** — the two rails (`pr-ci.yml`, `ci.yml`), each with a
  different time/cost budget.

## Situations that trigger the need

- A new entry is added under `[project.entry-points."skdecide.domains"|"skdecide.solvers"]`.
- `skdecide/utils.py` (`rollout`, `check_domain`, registration helpers) or
  `skdecide/core.py`'s builder-mixin composition changes.
- An optional dependency (`discrete-optimization`, `openap`, `cartopy`,
  MiniZinc) is bumped.
- The weekly scheduled full-qualification run fires.
- A version tag is pushed for release.

## Desired outcomes

- A regression that breaks the load-by-name contract for a representative
  domain is caught by `tests/e2e/` running inside `ci.yml`'s `integration`
  job before a release is tagged.
- Every assertion in `tests/e2e/` is against real solve/rollout output — no
  mocks or stubs — matching the "Chicago-school" precedent already set by
  `tests/test_self_play_chicago.py`.
- The suite stays a bounded, representative smoke/regression check (one
  primary domain+solver pairing per domain family), not an unbounded
  N × M domain × solver matrix that would itself become a maintenance
  burden.

## Non-goals

- **Not a performance/benchmark suite.** No timing assertions beyond the
  sanity bounds (`max_steps`, episode counts) already used elsewhere.
- **Not a replacement** for `tests/scheduling/test_scheduling.py` or
  `tests/flight_planning/test_flight_planning.py`'s deep coverage of
  domain-internal correctness. `tests/e2e/` only proves the *pipeline*
  (load → check_domain → solve → rollout); those files keep owning
  domain-internal correctness.
- **Not wired into the PR rail as a compiled-extension job.** `Astar`,
  and several other hub solvers, only exist behind the compiled
  `skdecide.hub.__skdecide_hub_cpp` extension, which requires a real C++
  build to install. Building that on every pull request is exactly the
  "cross-platform release build on every PR" that `docs/ci.md`'s ERRC list
  explicitly eliminates from the PR rail. `tests/e2e/` therefore runs on
  the full-qualification (`ci.yml`) rail, against the already-built wheel,
  alongside the rest of the "Linux integration authority" evidence — not as
  a new PR-rail job.

## See also

- `tests/e2e/README.md` — what the suite covers and how it is organized.
- `docs/ci.md` — the two-rail CI model this suite is wired into.
