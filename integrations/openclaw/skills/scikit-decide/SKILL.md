---
name: scikit-decide
description: Select, inspect, match, and execute registered scikit-decide planning, scheduling, and reinforcement-learning capabilities through receipted OpenClaw tools.
---

# scikit-decide

Use this skill when a task requires automated planning, scheduling, reinforcement learning, domain/solver compatibility analysis, or a bounded policy rollout.

## Lawful workflow

1. Call `skdecide_catalog` to observe the registered domains and solvers in the active Python environment.
2. Call `skdecide_describe` before constructing an unfamiliar subject. Never invent constructor arguments.
3. Call `skdecide_match` when a concrete domain can be constructed and solver compatibility is not already established.
4. Call `skdecide_run` only with registered domain and solver names. Set explicit `max_steps`, `num_episodes`, and `timeout_seconds` bounds.
5. Preserve the returned receipt. Treat `ALIVE` as execution evidence for that exact call only; do not promote a catalog listing, manifest, or successful import into rollout standing.

## Refusals and failure states

- `REFUSED:UNREGISTERED_SUBJECT`: use the catalog; do not bypass registration with an arbitrary import path.
- `REFUSED:INVALID_ARGUMENT`: inspect the subject and repair the argument shape.
- `REFUSED:BOUND_EXCEEDED`: reduce episodes, steps, timeout, or output size.
- `BUILD_BROKEN`: preserve the receipt and error, identify the first failed domain/solver transition, then repair the narrowest cause.

`skdecide_run` is optional because it performs compute and may initialize native solver dependencies. The catalog and description tools are read-only. MCP is configured explicitly through OpenClaw, and MCP and native plugin calls share the same Python bridge and receipt semantics.
