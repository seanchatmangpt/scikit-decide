---
name: standing-report
description: Report on this repo's state using the nano-nonfiction dispatch format from CLAUDE.md §2 — a bounded, evidence-only status shape instead of prose or a capability survey.
---

# standing-report

Use this skill whenever asked for the status of a change, an investigation,
or "what's the state of X" in this repo — the default answer to a grounding
question is a run or a precisely named blocker, never a survey (see
`~/.claude/rules/no-overclaiming-conversational.md`). This skill is the
repo-specific template for that answer.

## Format

Emit exactly these seven lines/sections, each grounded in a command actually
run this session or a precisely named blocker — never a self-graded claim:

```text
Standing            — one line, scoped per boundary (CLAUDE.md §1 vocabulary:
                       ALIVE / PARTIAL_ALIVE / BLOCKED:<reason> /
                       BUILD_BROKEN / UNKNOWN / UNSUPPORTED)
Identity            — repo, branch, base, head, commit count, drift
What changed        — files touched, surfaces added, in plain terms
Admission & bounds  — what's admitted, what's refused, execution limits
Local execution     — command / exit code / observation, one row each
Standing by boundary— ALIVE / PARTIAL_ALIVE / UNKNOWN, broken out per
                       boundary touched (a change is rarely one status
                       end to end)
Falsifiers          — named conditions that would overturn this standing
```

## Rules

- Bounded length — this is a dispatch, not a report. If a section has
  nothing to say, say "none" rather than padding.
- Every "Local execution" row must be a command genuinely run this session
  with output observed — not "should pass," not a description of what the
  command would do.
- Don't promote a broader claim than the narrowest evidence supports: a
  passing `--collect-only` is not a passing test run; a merged PR is not an
  executed deployment; a catalog listing is not a rollout.
- If a known standing exception already exists (e.g. the recorded
  `BUILD_BROKEN` test-collection state in `CLAUDE.md` §1), re-verify it is
  still current before repeating it — don't cite it from memory.
- Reference `docs/STATUS.md` for a worked example of this same discipline
  applied to a completed change.
