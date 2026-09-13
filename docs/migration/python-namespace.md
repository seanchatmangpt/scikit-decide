# The `skdecide` → `autofde_lab` namespace move

This page covers the Python package rename specifically (Phase 3 of the AutoFDE Lab rename,
`docs/migration/AUTOFDE_LAB_RENAME.md`'s `RENAME_NOW` category applied to the source tree). For
the broader migration picture (distribution name, deprecation window, what's inherited), see
`docs/migration/from-scikit-decide.md`.

## What moved

```
src/skdecide/          →  src/autofde_lab/     (the real implementation)
src/skdecide/__init__.py  stays, but is now a compatibility alias only (see below)
```

Every submodule moved with it: `autofde_lab.core`, `autofde_lab.domains`, `autofde_lab.solvers`,
`autofde_lab.builders.{domain,solver}`, `autofde_lab.hub.{domain,solver}`, and the fork-specific
additions `autofde_lab.{agent,fabric,ocel,powl,adapters}` (the last five are lazily imported —
see the module docstring in `src/autofde_lab/__init__.py` — so `import autofde_lab` alone does
not pull in the full agent/fabric stack).

## Before / after import examples

```python
# Top-level re-exports
- import skdecide
+ import autofde_lab

- from skdecide import DeterministicPlanningDomain, Solver
+ from autofde_lab import DeterministicPlanningDomain, Solver

# Builder mixins
- from skdecide.builders.domain import Renderable
+ from autofde_lab.builders.domain import Renderable

# Hub domains and solvers
- from skdecide.hub.domain.maze import Maze
+ from autofde_lab.hub.domain.maze import Maze
- from skdecide.hub.solver.astar import Astar
+ from autofde_lab.hub.solver.astar import Astar

# Fork-specific modules (new, not a rename of anything upstream)
+ from autofde_lab.agent import session
+ from autofde_lab.fabric.service import DecisionFabric
+ from autofde_lab.powl import executor
+ from autofde_lab.ocel import ocel_sink
```

## Entry points

`pyproject.toml` entry-point groups (`skdecide.domains`, `skdecide.solvers`) and the plugin
targets they point at were renamed together — a domain registered as
`MyDomain = "skdecide.hub.domain.my_domain:MyDomain [domains]"` upstream now resolves through
`autofde_lab.hub.domain.my_domain`. `autofde_lab.utils.get_registered_domains()` /
`get_registered_solvers()` discover the renamed entry points; no caller-side code change is
needed beyond updating your own import statements per the table above.

## The `skdecide` package still importable

`import skdecide` and `import skdecide.hub.solver.astar` (arbitrary depth) both still resolve —
a `sys.meta_path` finder in `src/skdecide/__init__.py` forwards any `skdecide.X.Y` lookup to
`autofde_lab.X.Y` rather than executing a second, independent copy of the module. This matters
for `isinstance` checks: two independently-imported copies of the same class would compare
unequal, which the forwarding approach avoids. See `docs/migration/from-scikit-decide.md` for
the deprecation window on this path.

## What this move deliberately did not touch

Per `docs/migration/AUTOFDE_LAB_RENAME.md`'s `VERSIONED_MIGRATION` and `DO_NOT_RENAME`
categories, this namespace move did **not** rename:

- `urn:skdecide:*` IRIs used in the generated capability ontology and PDDL/POWL base IRIs
  (`autofde_lab/fabric/fde.py`, `autofde_lab/fabric/ontology.py`,
  `autofde_lab/fabric/pddl_engine.py`) — these are externally-consumed identifiers, not Python
  import paths; see `docs/migration/persisted-artifacts.md`.
- Inherited AIRBUS copyright headers, which stay on every file that originated upstream
  regardless of which namespace now imports it — see `NOTICE`.

## See also

- `docs/migration/from-scikit-decide.md` — the full migration picture, deprecation window.
- `docs/migration/persisted-artifacts.md` — persisted/externally-consumed identifiers, handled
  separately from the Python namespace.
- `docs/migration/AUTOFDE_LAB_RENAME.md` — the four-category contract.
- `CLAUDE.md` — architecture guide, now describing `src/autofde_lab/`.
