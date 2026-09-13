---
name: openclaw-lawful-call
description: Invoke a registered scikit-decide domain/solver through the OpenClaw bridge during a Claude Code session, using the catalog-describe-match-run workflow and typed refusal vocabulary instead of calling internals directly.
---

# openclaw-lawful-call

Use this skill when a task in this repo asks to actually run a domain/solver
during the session (not just read about it), and going through the bridge is
appropriate — e.g. verifying an OpenClaw-facing change, or exercising a
domain the same way the bridge's own contract test does. This mirrors
`integrations/openclaw/skills/scikit-decide/SKILL.md` (the OpenClaw-side
skill), scoped here for in-session Claude Code use.

## Lawful workflow

1. `python -m autofde_lab.openclaw_bridge inspect` (or `skdecide_catalog` if
   working through MCP) — observe registered domains/solvers before
   constructing anything. Never invent a class path outside the registry;
   the bridge refuses unregistered subjects (see below).
2. `python -m autofde_lab.openclaw_bridge call describe --name <subject>` before
   constructing an unfamiliar domain/solver — don't guess constructor args.
3. `... call match` when compatibility between a concrete domain and a
   solver isn't already established.
4. `... call run` only with registered names, and set explicit
   `max_steps`, `num_episodes`, `timeout_seconds` bounds — the bridge caps
   these anyway (`MAX_EPISODES=100`, `MAX_STEPS=10_000`,
   `MAX_TIMEOUT_SECONDS=600.0`, `MAX_RESULT_BYTES=4MiB`; see `CLAUDE.md` §3),
   but naming them explicitly makes the intended bound legible in the
   command itself.
5. Preserve the returned receipt (`input_sha256`/`output_sha256`). Treat a
   successful run as evidence for that exact call only — a catalog listing
   or successful `describe` is not rollout evidence.

## Refusal and failure vocabulary

- `REFUSED:UNREGISTERED_SUBJECT` — use the catalog; don't bypass
  registration with an arbitrary import path.
- `REFUSED:INVALID_ARGUMENT` — re-run `describe`, repair the argument shape.
- `REFUSED:BOUND_EXCEEDED` — reduce episodes, steps, timeout, or output
  size; don't retry unchanged.
- `REFUSED:UNKNOWN_TOOL` — the tool name itself isn't in `TOOL_DEFINITIONS`;
  check `python -m autofde_lab.openclaw_bridge inspect` for the actual set.
- `BUILD_BROKEN` — preserve the receipt and error, identify the first
  failed transition, repair the narrowest cause — don't broaden the fix
  past what the receipt implicates.

## Notes

- `catalog`/`describe` are read-only and replay-safe; `match`/`run` perform
  real compute and are not replay-safe — don't call `run` speculatively.
- The bridge enforces isolation via a subprocess worker
  (`openclaw_bridge.py::_worker`) independent of whatever process invokes
  it — this holds whether the call came from the TS plugin, MCP, or the CLI
  directly.
- This is Explore-territory per `CLAUDE.md` §3 for local/read-only calls;
  anything that would install/enable the OpenClaw plugin on a real host, or
  restart a gateway, is actuation and needs explicit confirmation.
