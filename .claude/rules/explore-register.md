---
paths:
  - "docs/**"
  - "tests/ecosystem/**"
---

# Explore register — nano-nonfiction dispatch

Default reasoning mode for investigating a transition, a template, a fixture,
or an OpenClaw boundary is **Explore**: trace where the current design
actually leads before declaring it wrong. Switch to **Exploit** only to
assert current truth about repo state, or when a premise's own internal
parts contradict each other — never because the premise contradicts some
external expectation.

Any Explore-phase report to the user takes the **nano-nonfiction dispatch**
shape already in production use in this repo (see the OpenClaw interop
receipts in PR #8/#9/#10 history for the reference instance; also available
as the invocable `standing-report` skill, see `.claude/rules/project-tooling.md`):

```text
Standing            — one line, scoped per boundary (standing-law.md vocabulary)
Identity            — repo, branch, base, head, commit count, drift
What changed        — files touched, surfaces added, in plain terms
Admission & bounds  — what's admitted, what's refused, execution limits
Local execution     — command / exit code / observation, one row each
Standing by boundary— ALIVE / PARTIAL_ALIVE / UNKNOWN, broken out
Falsifiers          — named conditions that would overturn this standing
```

Bounded length. Every line is either a command actually run this session
with output observed, or a precisely named blocker — never a self-graded
claim, never hype framing, never a capability survey when a run was asked
for. This is the same discipline as `~/.claude/rules/no-overclaiming-conversational.md`
and `criticism-discipline.md` rules 1–4, restated in this repo's own
vocabulary: don't dismiss an existing mixin/domain/solver design without
checking its actual tests first; a status claim earns a run, not a survey.

## See also

- `CLAUDE.md` — the index and routing table that points here.
- `.claude/rules/standing-law.md` — the status vocabulary every claim uses.
- `docs/STATUS.md` — where a finished dispatch gets filed as a ledger row.
