# Testing discipline: Chicago school, not London school

Loads unconditionally (no `paths:` gate) — this governs every test in the repo, not
one subsystem.

**Chicago school / classicist** (the required default here): exercise real
collaborators — a real domain + real solver (`solve()` on an actual instantiated
domain, per `CLAUDE.md`'s rule 1), a real subprocess, a real file on disk, a real
locally-running service — and assert on **final state**: real return values, real
file contents, real computed results. **London school / mockist** (rejected as a
default): replace collaborators with mocks/stubs and assert on interactions ("was
this called"). A mockist test can pass while the real integration is broken — exactly
the failure mode rule 2 in `CLAUDE.md` already names for projection-vs-execution.

## Banned by default

`unittest.mock` / `Mock()` / `MagicMock()` / `patch(...)` / pytest `monkeypatch`
faking any collaborator this repo owns or that is realistically runnable in-process
or locally. This is not new policy — it is what "Chicago-style test exercising
`solve()` on a real domain" in `CLAUDE.md` rule 1 has always required; this file
makes the *general* case (every subsystem, not just solver/domain claims) explicit
and names the banned mechanism directly.

## The one legitimate exception

A test double is allowed only when a real collaborator is genuinely infeasible
in-process (a paid external API, a destructive operation, unpinned nondeterminism) —
and even then: state why in the test/module docstring, prefer a real local/degraded
alternative first (e.g. a locally-running model server reached over real HTTP, with a
named `pytest.mark.skipif` if that server isn't up — never a silent mock
substitution), and keep any double a real simple implementation of the interface
(a fake), not an interaction-verifying mock.

## Verification, every time

"It works" / "not cutting corners" is not a description, it is:

```
grep -rn "unittest.mock\|Mock(\|MagicMock\|patch(\|monkeypatch" <test dirs>
pytest -v <test dirs>
```

both real, both run this session, both reported with actual output — matching the
`ALIVE` standard in `.claude/rules/standing-law.md` (a command actually run, output
observed), not a memory of a prior run.

## See also

- `~/.claude/rules/testing-chicago-style.md` — the same discipline at the global
  Claude Code config level (applies across all of this user's projects)
- `.claude/rules/standing-law.md` — the `ALIVE`/evidence vocabulary this file's
  verification requirement plugs into
- `CLAUDE.md` rule 1 — the solver/domain-specific instance this file generalizes
