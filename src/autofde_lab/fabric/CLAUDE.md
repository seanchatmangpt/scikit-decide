# Role

Agent-facing projection of the existing domain/solver registry: one typed service (`models.py`,
`service.py`, `backend.py`) surfaced through Typer CLI (`cli.py`), FastMCP (`mcp.py`), A2A
(`a2a.py`), DSPy (`dspy.py`), plus an ERRC cache (`cache.py`), the classical PDDL engine
(`pddl_engine.py`), POWL projection (`powl.py`), ontology generation (`ontology.py`), and the
coverage report (`coverage.py`).

# Authority

- Route requests to the registry and return typed results and typed refusals.
- Generate `ontology/autofde-lab-capabilities.ttl` from entry points + live import probe +
  `get_domain_requirements()` MRO derivation.
- Refuse PDDL problems whose requirements the backend cannot honour.
- Emit `plan.powl.ttl` documents carrying real BLAKE3 digests.

# Non-authority

- **Adds no authority to the registry it calls.** A fabric result is a candidate, exactly as
  the underlying `solve()` result was.
- Does not admit, broker, actuate, or execute. `powl.py` writes a document; it does not run a
  workflow. An earlier pass let the projector stand in for an executor and had to be retracted
  (`docs/ecosystem-standing.md`).
- `canonical.py` / `cache.py` hashes are content identities for caching and call integrity,
  not admission receipts.

# Inputs

`pyproject.toml` entry points; PDDL domain/problem files; fabric request models; DSPy job text.

# Outputs

Plan files in VAL format; `.powl.ttl` Turtle; the generated `.ttl` ontology; JSON coverage
reports; MCP tools `decision_catalog` / `decision_match` / `decision_solve` /
`decision_cache_stats` / `decision_cache_hotset` (and `decision_compile` when a DSPy compiler
is configured).

# Invariants

1. **The `--help` banner of `pddl_engine.py` must keep starting with `usage:`.** That string is
   pinned as `pddl:versionWitnessPrefix` in an `mfw` `PlannerProfile`; changing it silently
   invalidates admission upstream.
2. **The requirements gate is never removed.** The C++ backend parses `:derived-predicates`,
   `:constraints` and `:preferences` and implements none of them, silently — derived atoms are
   never true, `GoalChecker::is_goal` never reads `get_constraints()`, and `Preference::holds`
   turns a soft preference into a hard constraint. Without the gate the engine emits a
   confident, plausible, wrong plan. A wrong plan that can be admitted downstream is strictly
   worse than a typed refusal (`REFUSED: UNSUPPORTED_REQUIREMENT`, exit 2).
3. **CLI contract**: `python -m autofde_lab.fabric.pddl_engine <domain> <problem> <plan>` —
   exactly three positional arguments, plan written to file, not stdout. That is `mfw`'s
   `classical` + `output_mode="file"` contract (`mfw-planner/src/config.rs`).
4. `powl.py` raises `DigestUnavailable` rather than emitting a non-BLAKE3 digest under a
   `blake3:` label — a forged identity mismatches `mfw`'s `PLANNER_ENVIRONMENT_DRIFT` check
   with a misleading reason.
5. `coverage.py` must classify **every** declared solver: selected, compared, or excluded with
   a machine-readable cause. Comparison is measured by running, because `match_solvers`
   ignores `ranked`.
6. No packaged console script exists (no `[project.scripts]`); everything is `python -m`.

# Neighboring components

`autofde_lab.utils` (registry loaders), `hub/domain/pddl` + `cpp/src/hub/domain/pddl/semantics/`
(the parser whose gaps invariant 2 guards), `ontology/` (generated artifact),
`tests/ecosystem/` (asserts these boundaries), `~/mfw` (consumer of the engine and of POWL).

# Verification

```bash
uv run pytest tests/fabric
uv run python -m autofde_lab.fabric.pddl_engine --help                 # must print "usage: ..."
uv run python -m autofde_lab.fabric.ontology ontology/autofde-lab-capabilities.ttl
```

# Standing ceiling

Strongest establishable claim: **`ALIVE` for candidate-plan computation and for
document projection** — the engine ran and produced a VAL-format plan; the projector wrote a
`.powl.ttl` with digests cross-checked against an independent `b3sum`.

Explicitly not establishable here, at any evidence level: that the plan was admitted by `mfw`,
executed by any component, or that the projection was ingested by anything. As of 2026-08-06
no component in the portfolio executes a POWL plan end to end (three representations, zero
converters). `mfw` admission is `BLOCKED:MFW_PLANNER_BUILD_BROKEN` — only the engine's
*contract conformance* is tested, which is weaker and must be labelled as such.

# Update obligations

- Any change to the engine's argv handling, exit codes, or `--help` prefix → re-run
  `tests/ecosystem/` and update `docs/ecosystem-standing.md` S3.
- Any change to the registry (added/removed capability) → regenerate the ontology.
- Any new POWL predicate → check it against `~/mfw`'s committed
  `runs/ticket-10/plan.powl.ttl` vocabulary before emitting it.
