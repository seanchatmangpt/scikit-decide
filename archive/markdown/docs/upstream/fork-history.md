# Fork history

AutoFDE Lab is a fork of [`airbus/scikit-decide`](https://github.com/airbus/scikit-decide),
hosted at [`seanchatmangpt/autofde-lab`](https://github.com/seanchatmangpt/autofde-lab). This
page states the factual history: what was inherited, what is new, and when the fork's own
history begins in `git log`.

## What the commit history actually shows

This repository's `git log` is continuous back to the original scikit-decide project — a fork
keeps the full upstream history, it does not truncate it. The first commit in the tree is:

```
4a8542d 2020-10-10 19:07:11 +0200  galleon  first commit
```

Airbus development continues in this same history for hundreds of commits (799 total commits in
the tree as of this writing). The first commit authored under this fork's own identity is:

```
29d8d93 2026-08-05 14:58:57 -0700  Sean Chatman  Add capability-aware caching layer
```

So: roughly six years of Airbus scikit-decide history, followed by fork-specific work starting
2026-08-05. There is no ambiguity about where upstream ends and the fork's own contributions
begin — it is a `git log --author` boundary, not a narrative one.

## What is inherited unchanged

- The domain/solver catalog architecture: builder-mixin composition
  (`autofde_lab.builders.domain`, `autofde_lab.builders.solver`), domain presets
  (`autofde_lab.domains`), and the plugin/entry-point registration system.
- The C++ solver core (`cpp/`) and its pybind11 bindings — A*, MCTS, LRTDP, IW, RIW, and the
  rest of the hub solvers listed in `CLAUDE.md`.
- The autocast type-conversion system connecting domains and solvers.
- The scheduling subsystem (RCPSP and variants).
- The MIT license and the inherited AIRBUS copyright notice on every file that originated
  upstream — see `NOTICE`.

## What is new to this fork

- **Persistent decision agents** (`autofde_lab.agent`) — session, bridge, epoch/receipt
  tracking, deterministic fault matrix, replan handling.
- **POWL 2.0 process semantics** (`autofde_lab.powl`) — algebra, semantics, and an executor for
  process-oriented workflow language plans.
- **OCEL evidence** (`autofde_lab.ocel`) — object-centric event log sink, threading ledger
  objects/activities/timestamps into a standard evidence format.
- **The decision fabric** (`autofde_lab.fabric`) — a protocol-independent service (CLI, MCP, A2A,
  DSPy projections) with a multi-tier ERRC cache, PDDL requirements gate, and a generated
  capability ontology (`ontology/skdecide-capabilities.ttl`).
- **An AutoFDE reference vertical** (`autofde_lab.autofde`, `docs/autofde/`,
  `infra/azure/`, `infra/github/`) — explicitly a laboratory prototype, not a product; see
  `docs/autofde/EXPLORE.md` for the boundary this repository does not cross.
- **The rename itself** — `autofde-lab` distribution name, `autofde_lab` Python namespace, with
  a bounded, deprecation-warning `skdecide` compatibility alias (see
  `docs/migration/python-namespace.md`).

## Standing discipline

This page is a factual history, not a standing claim. Whether any inherited or new capability
is `ALIVE` is governed by `.claude/rules/standing-law.md` and ledgered in `docs/STATUS.md`; this
page does not supersede either.

## See also

- `docs/migration/AUTOFDE_LAB_RENAME.md` — the four-category rename contract
  (RENAME_NOW / COMPATIBILITY_ALIAS / VERSIONED_MIGRATION / DO_NOT_RENAME).
- `docs/migration/from-scikit-decide.md` — what changed for a user of the old package.
- `NOTICE` — the fork relationship and copyright statement.
- `docs/autofde/EXPLORE.md` — the AutoFDE-the-product boundary this repository does not cross.
