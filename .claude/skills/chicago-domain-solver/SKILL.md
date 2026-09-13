---
name: chicago-domain-solver
description: Add or modify a scikit-decide domain or solver, closing the loop with a Chicago-style test in the same change so the resulting ALIVE claim has evidence.
---

# chicago-domain-solver

Use this skill when adding a new domain (`src/autofde_lab/hub/domain/`), adding a
new solver (`src/autofde_lab/hub/solver/`), or modifying an existing one's
behavior.

## Workflow

1. **Find the nearest working sibling first.** Domains: read
   `src/autofde_lab/hub/domain/maze/` as the reference shape. Solvers: read any
   pure-Python solver under `src/autofde_lab/hub/solver/` (or, for C++ solvers,
   a sibling under `cpp/` — A* for a simple template, MCTS for a complex
   one). Do not re-derive the mixin/registration pattern from scratch; copy
   the sibling's shape and diverge only where the new subject actually
   differs.

2. **Respect the three-tier method naming** (`CLAUDE.md` §4) when
   implementing: `get_X()` is the public autocast wrapper, `_get_X()` is the
   LRU-cached middle layer, `_get_X_()` is the override point. Implement at
   the `_get_X_()` / `_state_step()` / `_state_reset()` level; don't override
   the cached or public layers.

3. **Write the fixture + test in the same change, not a follow-up.** A
   Chicago-style test exercises `solve()` (or `step()`/`reset()` for a bare
   domain) against a real instance — no mocked domain internals. Place it
   under the matching `tests/domains/` or `tests/solvers/` subtree, following
   the naming and fixture conventions of the sibling test file next to the
   sibling implementation you copied.

4. **Run the test this session and observe the output.** Per `CLAUDE.md`
   §1, a solver/domain claim is `ALIVE` only with an executed test this
   session — "compiles" or "the happy path looks right" is not evidence.
   Quote the command and result when reporting standing:
   `.venv/bin/python -m pytest tests/<path>::<test> -v` — not `uv run
   pytest`, which re-checks the native build on every invocation (see
   `CLAUDE.md`'s Build section).

5. **If registering a new entry point** (for the domain/solver to be
   reachable through the OpenClaw bridge or fabric CLI — see the
   `openclaw-lawful-call` skill), confirm it appears in
   `autofde_lab.domains`/`autofde_lab.solvers` via `python -m autofde_lab.fabric
   catalog` or `skdecide_catalog`, don't assume registration from the code
   change alone.

## Standing vocabulary

Report using `CLAUDE.md` §1's vocabulary (`ALIVE`, `PARTIAL_ALIVE`,
`BLOCKED:<reason>`, `BUILD_BROKEN`, `UNKNOWN`, `UNSUPPORTED`), scoped to the
exact test/command run — not a broader claim than the evidence supports.
