# Migrating from scikit-decide

This page is for anyone with existing code against `pip install scikit-decide` /
`import skdecide`. It covers what changed, what still works unmodified, and the deprecation
window on the compatibility path.

## What changed

- **Distribution name**: `scikit-decide` → `autofde-lab` on PyPI-equivalent install
  (`pip install autofde-lab[all]`). See `docs/install.md`.
- **Python namespace**: `skdecide` → `autofde_lab`. See `docs/migration/python-namespace.md`
  for the full before/after import mapping.
- **Repository**: `github.com/airbus/scikit-decide` → `github.com/seanchatmangpt/autofde-lab`.
  This is a fork, not a takeover of the original — see `NOTICE`.

## What did not change

- The domain/solver API surface: `Domain`, `Solver`, the builder mixins, `match_solvers`,
  `get_registered_domains`/`get_registered_solvers`, `load_registered_domain`/
  `load_registered_solver` all keep their names and signatures. Only the module path they live
  under moved.
- The C++ extension module and every hub domain/solver's behavior.
- The MIT license and the inherited AIRBUS copyright headers on unmodified files.
- Externally-persisted identifiers are handled as `VERSIONED_MIGRATION`, not renamed by
  substitution — see `docs/migration/persisted-artifacts.md`.

## The compatibility shim

`import skdecide` still works. `src/skdecide/__init__.py` is now a thin compatibility alias: it
emits a `DeprecationWarning` and forwards every attribute and submodule lookup
(`skdecide.hub.domain...`, `skdecide.solvers`, …) to the real `autofde_lab` package via a
`sys.meta_path` finder, so `import skdecide.utils` and similar deep imports keep working without
each submodule needing its own forwarding stub.

The shim contains **no new implementation** — it is forwarding only, by contract
(`docs/migration/AUTOFDE_LAB_RENAME.md`'s `COMPATIBILITY_ALIAS` category). Any new feature will
only ever be reachable via `autofde_lab`.

### Update your imports

```python
# before
import skdecide
from skdecide import DeterministicPlanningDomain
from skdecide.hub.solver.astar import Astar

# after
import autofde_lab
from autofde_lab import DeterministicPlanningDomain
from autofde_lab.hub.solver.astar import Astar
```

A mechanical search/replace of `skdecide` → `autofde_lab` in import statements is sufficient for
the module rename itself; see `docs/migration/python-namespace.md` if you also reference
`SKDECIDE_DATA` / `~/skdecide_data` or `urn:skdecide:*` identifiers, which follow a different
(dual-read) migration path.

### Deprecation window

The shim is bounded to one removal milestone,
`LEGACY_NAMESPACE_REMOVAL_AFTER`, recorded in `docs/migration/AUTOFDE_LAB_RENAME.md`. Code that
still imports `skdecide` after that milestone will fail with `ModuleNotFoundError` rather than a
warning. Update imports now rather than relying on the shim past that point.

## See also

- `docs/migration/python-namespace.md` — the namespace move in detail, with more import examples.
- `docs/migration/persisted-artifacts.md` — what happens to on-disk / externally-consumed
  identifiers (cache schema, data directory, IRIs) that cannot be renamed by substitution.
- `docs/migration/AUTOFDE_LAB_RENAME.md` — the four-category contract this migration follows.
- `docs/upstream/fork-history.md` — what's inherited from Airbus scikit-decide vs. new to this fork.
- `NOTICE` — the fork relationship and copyright statement.
