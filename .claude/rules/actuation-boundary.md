---
paths:
  - "integrations/openclaw/**"
  - "src/autofde_lab/openclaw_*.py"
  - ".github/**"
---

# Actuation boundary — what needs confirmation before it runs

Local edits, tests, and notebook runs are Explore-territory — no
confirmation needed. These require it:

- `git push` to a shared branch, opening/merging a PR, a PyPI/conda release,
  docs deploy, or triggering a long CI job.
- Anything that runs through the **OpenClaw bridge** (`integrations/openclaw/`,
  `src/autofde_lab/openclaw_runtime.py`, `src/autofde_lab/openclaw_bridge.py`).
  Verified in code this session, not aspirational: the bridge only admits
  names already present in autofde-lab's own `autofde_lab.domains` /
  `autofde_lab.solvers` entry-point registries (`openclaw_runtime.py::load_registered`,
  refuses `REFUSED:UNREGISTERED_SUBJECT` otherwise); enforces bounded
  execution — episode/step/timeout/output-size caps
  (`MAX_EPISODES`/`MAX_STEPS`/`MAX_TIMEOUT_SECONDS`/`MAX_RESULT_BYTES`) plus
  two independent layers of subprocess isolation (the TS plugin spawns the
  Python bridge; the bridge spawns its own worker subprocess for the actual
  rollout); returns typed `REFUSED:*` statuses for anything outside those
  bounds (`INVALID_ARGUMENT`, `UNREGISTERED_SUBJECT`, `BOUND_EXCEEDED`,
  `UNKNOWN_TOOL`); and emits a SHA-256 receipt (`receipt()`, hashing
  canonicalized input/output JSON) on every success, refusal, and failure
  branch, exercised end-to-end by `integrations/openclaw/test/contract.test.mjs`
  against the real compiled plugin, not mocks. A merged PR adding OpenClaw
  surface is at most `PARTIAL_ALIVE` on the **technical** dimension — the
  exact-host crown
  (`openclaw plugins install/enable`, `gateway restart`,
  `plugins inspect --runtime`, `mcp doctor --probe`) is a separate,
  unmerged-until-executed boundary. Queued or pending CI is not evidence
  either way.

A planner result is a candidate, not an actuation. The CLI/MCP/A2A layer
described in `.claude/rules/architecture.md` calls the existing domain/solver registry; it does not grant
it new authority.

## See also

- `CLAUDE.md` — the index and routing table that points here.
- `.claude/rules/standing-law.md` — the status vocabulary every claim uses.
- `.claude/rules/ecosystem-boundary.md` — why a planner result is never an actuation.
