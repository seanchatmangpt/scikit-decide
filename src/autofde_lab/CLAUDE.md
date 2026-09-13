# Role

The Python package. Domains model decision problems, solvers search them, and the fabric /
WASM / OpenClaw layers project that registry outward. Everything here computes **candidate
plans**; nothing here actuates.

# Authority

- Define domain and solver types by composing builder mixins (`builders/domain/`,
  `builders/solver/`) — one single-inheritance chain per dimension.
- Own the entry-point registry (`autofde_lab.domains`, `autofde_lab.solvers` in `pyproject.toml`)
  and the loaders in `utils.py`.
- Compute plans, policies, and values; project them (POWL, PDDL plan files, MCP/A2A results).

# Non-authority

- No admission, no broker, no actuation, no standing verdict. `mfw` owns those.
- No plan execution. `bcinr` owns the symbolic partial-order scheduler; `ggen` implements μ
  (deterministic manufacture + BLAKE3 receipt).
- The SHA-256 hashes emitted by `openclaw_bridge.py` (`receipt()`) and `fabric/canonical.py`
  are **call-integrity digests over input/output JSON**, not admission receipts. They record
  what was asked and answered; they authorize nothing. Do not let the word "receipt" in these
  modules drift into admission semantics.

# Inputs

Domain instances constructed by callers; entry points; PDDL/RDDL/UP/Gym problem files;
fabric request models (`fabric/models.py`).

# Outputs

Plans, policies, values, `Value`/`Distribution` objects; `plan.powl.ttl` documents;
CLI/MCP/A2A responses; `ontology/autofde-lab-capabilities.ttl` (generated).

# Invariants

1. **Three-tier method naming.** `get_X()` public autocast wrapper → `_get_X()` LRU-cached →
   `_get_X_()` override point. `step()`/`reset()` go through `_state_step()`/`_state_reset()`.
   Read the concrete class before assuming a signature.
2. **Importability is not execution.** `Solver.get_domain_requirements()` (`solvers.py:85`)
   derives required domain characteristics from the `T_domain` MRO and says nothing about
   constructor requirements. 7 solvers are ontology-applicable yet not runnable with defaults
   (`REQUIRES_CONFIGURATION`).
3. **`match_solvers(..., ranked=True)` accepts the flag and ignores it** (`utils.py:126`,
   `# TODO: implement ranking heuristic`). Any dominance claim must be measured by running,
   never delegated to that call.
4. **Failed solver loads surface as `None`, never as an exception** (`utils.py:94` logs a
   warning). Treat `None` as positive `UNSUPPORTED` evidence, not as absence.
5. Abstract `raise NotImplementedError` in `builders/` are extension points by design, not WIP.

# Neighboring components

`fabric/` (agent-facing projection), `hub/domain/`, `hub/solver/`, `wasm/` (Chatman WASM
adapters), `openclaw_runtime.py` / `openclaw_bridge.py` (bounded external invocation — see
`.claude/rules/actuation-boundary.md`), `cpp/` (compiled hub solvers).

# Verification

```bash
uv run pytest tests/domains tests/solvers/python tests/fabric   # by path; see tests/CLAUDE.md
uv run python -m autofde_lab.fabric catalog
```

Whole-suite collection is `BUILD_BROKEN` — run by path.

# Standing ceiling

The strongest claim work in this package can establish is:
**`ALIVE` for candidate-plan computation of a named domain/solver pair, evidenced by a
Chicago-style test that constructed a real domain and ran `solve()` this session.**

It cannot establish, at any evidence level: that a plan was admitted, executed, actuated, or
independently verified. Those are `mfw` / `bcinr` / `ggen-legacy` standing and stay `UNKNOWN`
from here.

# Update obligations

- Adding/removing a registered domain or solver → regenerate
  `ontology/autofde-lab-capabilities.ttl` (`python -m autofde_lab.fabric.ontology`) or
  `tests/ecosystem/` fails on drift.
- Changing a public method's tier → update the concrete overrides, not just the wrapper.
- If `ranked` is ever implemented, delete invariant 3 here and in
  `.claude/rules/ecosystem-boundary.md` and `docs/ecosystem-standing.md` together.
