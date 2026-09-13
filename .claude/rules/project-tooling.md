---
paths:
  - ".claude/skills/**"
  - ".claude/agents/**"
---

# Project-scoped Claude Code tooling

`.claude/skills/` and `.claude/agents/` in this repo operationalize the
workflows above as invocable tooling rather than prose to re-derive each
session:

- `chicago-domain-solver` skill — the domain/solver + fixture + test loop
  from `architecture.md`, encoding the `standing-law.md` rule that a solver/domain claim is `ALIVE` only
  with an executed test this session.
- `openclaw-lawful-call` skill — the catalog → describe → match → run
  workflow and refusal vocabulary from `actuation-boundary.md`, for invoking a domain/solver
  through the bridge during a session.
- `standing-report` skill — the `explore-register.md` nano-nonfiction dispatch template.
- `fabric-runner` agent — narrow agent scoped to `python -m autofde_lab.fabric`
  and `openclaw_bridge` invocations, for when something should actually run
  through the registry rather than be read about.

## See also

- `CLAUDE.md` — the index and routing table that points here.
- `.claude/rules/standing-law.md` — the status vocabulary every claim uses.
- `.claude/rules/architecture.md` — the workflows these skills operationalize.
