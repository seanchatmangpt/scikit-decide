---
paths:
  - "src/autofde_lab/**"
  - "cpp/**"
  - "tests/**"
---

# Architecture — retrieve from source, not from memory

This section is deliberately thin. Treat it as an index into where to look,
not a description to reason from — the source is the witness, this file
drifts.

**Core design**: domains and solvers compose orthogonal builder mixins
(`src/autofde_lab/builders/domain/`, `src/autofde_lab/builders/solver/`), one
single-inheritance chain per dimension (agent, concurrency, dynamics,
events, memory, observability, value, initialization). Presets in
`src/autofde_lab/domains.py` (`Domain`, `RLDomain`, `MDPDomain`,
`GoalMDPDomain`, `DeterministicPlanningDomain`, `POMDPDomain`, ...).

**Three-tier method naming** — read the actual class before assuming a
signature:

```
domain.get_X()    # public API — autocast wrapper, user calls this
domain._get_X()   # LRU-cached middle layer
domain._get_X_()  # override point — implement here
```

`step()`/`reset()` follow the same shape via `_state_step()`/`_state_reset()`.

**CLI / MCP surface** — no packaged console script exists yet (no
`[project.scripts]` in `pyproject.toml`); everything is invoked via `python
-m`:

- `python -m autofde_lab.fabric` — Typer CLI over the domain/solver registry:
  `catalog`, `match`, `solve`, `cache-stats`, `cache-hotset`, `serve-mcp`,
  `serve-a2a`. Full design in `docs/agentic-fabric.md`.
- `src/autofde_lab/fabric/mcp.py` (`serve-mcp` above) — FastMCP server exposing
  `decision_catalog`, `decision_match`, `decision_solve`,
  `decision_cache_stats`, `decision_cache_hotset`, and optionally
  `decision_compile` when a DSPy compiler is configured.
- `python -m autofde_lab.openclaw_bridge {inspect|call|mcp}` — a second,
  hand-rolled stdio MCP transport backing the OpenClaw integration (see `.claude/rules/actuation-boundary.md`);
  independent of the fabric MCP server above.

**Source layout**:

```
src/autofde_lab/
├── core.py, domains.py, solvers.py, utils.py
├── builders/domain/, builders/solver/   # capability mixins
├── hub/domain/, hub/solver/, hub/space/gym/
├── constitution/         # ggen-manufactured projection of ontology/{lab,world,planning,
│                         # process,authority,evidence,standing,interop}.ttl (PR #37) —
│                         # regenerate via `ggen sync run` from the repo root, never hand-edit
│                         # the 8 non-__init__ files. Additive only; not wired into any other
│                         # module. See docs/2026-08-08-ggen-manufactures-the-constitution.md.
├── fabric/               # CLI + MCP + A2A layer over the registry — see above
│   ├── pddl_engine.py    # classical PDDL engine for mfw's external-engine seam — see ecosystem-boundary.md
│   ├── powl.py           # plan → POWL2 projection (projection only, NOT execution)
│   ├── ontology.py       # generates ontology/autofde-lab-capabilities.ttl from entry points
│   └── coverage.py       # ontology-driven capability-coverage report
├── openclaw_runtime.py, openclaw_bridge.py   # OpenClaw bridge — see actuation-boundary.md
└── wasm/                 # Chatman Ecosystem WASM adapters — see docs/chatman-ecosystem-wasm.md

cpp/            # C++20 performance solvers — pybind11 wrapper per solver
ontology/       # ontology/autofde-lab-capabilities.ttl is GENERATED — regenerate, never
                # hand-edit; see ecosystem-boundary.md. The 9 files from PR #37
                # (lab/world/planning/process/authority/evidence/standing/interop/manufacture)
                # are HAND-AUTHORED (the semantic constitution); ggen.toml + templates/ +
                # queries/constitution/ at the repo root manufacture src/autofde_lab/constitution/
                # from 8 of them.
tests/          # pytest — autocast/, domains/, solvers/, scheduling/, fabric/
tests/ecosystem/         # cross-repo crown test — drives real sibling binaries; see ecosystem-boundary.md
notebooks/      # nbmake-tested tutorials
examples/       # 153 example scripts
integrations/openclaw/   # plugin + skill + MCP bridge — see actuation-boundary.md
docs/           # explanation and projections; never a standing/authority source
docs/ecosystem-standing.md   # the cross-repo standing ledger — see ecosystem-boundary.md
```

**Adding a domain/solver** — nearest working example first
(`src/autofde_lab/hub/domain/maze/` for domains, any pure-Python solver under
`src/autofde_lab/hub/solver/` for solvers); close the loop with a fixture +
Chicago-style test in the same change, not a follow-up (also available as
the invocable `chicago-domain-solver` skill, see project-tooling.md). C++ solvers follow one
shared architecture (template header, impl, pybind wrapper, `.cc.in`,
`CMakeLists.txt`) — read a sibling solver (A* for simple, MCTS for complex)
rather than re-deriving the pattern here.

**Build**: `uv sync --extra=all -v`; `pre-commit run --all-files`;
`uv run pytest --nbmake notebooks -v`. For `pytest tests/...`, see
`CLAUDE.md`'s Build section (`just test` / `just test-full`, and why
`uv run pytest` is the wrong command for routine runs) — don't restate that
guidance here, it drifts. Python 3.10+ per `pyproject.toml`; the verified
working dev environment this session is 3.13.9 (pyproject.toml carries
explicit 3.13 compatibility pins for numpy/pyRDDLGym-rl/ray) — treat 3.13 as
current, not merely supported. CMake/C++20/pybind11 for the compiled
extension.

## See also

- `CLAUDE.md` — the index and routing table that points here.
- `.claude/rules/standing-law.md` — the status vocabulary every claim uses.
- `.claude/rules/project-tooling.md` — the `chicago-domain-solver` skill that automates the add-a-domain loop.
