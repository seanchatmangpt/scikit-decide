# scikit-decide Agentic Decision Fabric

## Purpose

This bounded layer projects the existing scikit-decide decision authority through modern human and agent interfaces:

```text
registered domain + solver catalog
→ DecisionFabric
→ Typer CLI
→ FastMCP tools
→ A2A Agent Card + JSON-RPC
→ optional DSPy job compiler
→ 80/20 ERRC cache
→ receipt-addressed trajectory
```

The interfaces do not reimplement planning, scheduling, reinforcement learning, PDDL, PPDDL, MDP, or POMDP algorithms. They call the existing scikit-decide registry and solver contracts.

## Installation

Install the repository's normal dependencies and the optional fabric surfaces:

```bash
python -m pip install -r requirements-agentic.txt
```

The first crown deliberately avoids changing the upstream package extras or default dependency footprint. Packaging entry points can be admitted after the focused protocol crown is stable.

## CLI

```bash
PYTHONPATH=src python -m autofde_lab.fabric catalog
PYTHONPATH=src python -m autofde_lab.fabric match Maze
PYTHONPATH=src python -m autofde_lab.fabric solve Maze --solver Astar --max-steps 100
PYTHONPATH=src python -m autofde_lab.fabric cache-stats
PYTHONPATH=src python -m autofde_lab.fabric cache-hotset
```

Constructor arguments are JSON objects:

```bash
PYTHONPATH=src python -m autofde_lab.fabric solve DOMAIN \
  --domain-arguments '{"width":10}' \
  --solver-arguments '{"quiet":true}'
```

Exact solve-cache reuse additionally requires bound identities:

```bash
PYTHONPATH=src python -m autofde_lab.fabric solve DOMAIN \
  --subject-digest 'subject:sha256:...' \
  --policy-digest 'policy:sha256:...' \
  --environment-digest 'environment:sha256:...' \
  --randomness-digest 'seed:42'
```

Without all four identities, planning still executes but solve-result reuse is reported as `BYPASS`.

## MCP

```bash
PYTHONPATH=src python -m autofde_lab.fabric.mcp
```

Tools:

- `decision_catalog`
- `decision_match`
- `decision_solve`
- `decision_cache_stats`
- `decision_cache_hotset`
- `decision_compile` when a configured DSPy compiler is explicitly supplied

MCP exposes schema-bound tool use. It does not own solver semantics.

## A2A

```bash
PYTHONPATH=src python -m autofde_lab.fabric.a2a
```

The A2A 1.0 server publishes a discoverable Agent Card and accepts either:

1. a strict JSON `DecisionRequest`; or
2. natural language only when a DSPy compiler has been explicitly configured.

External Agent Cards and messages remain untrusted observations. A2A discovery does not grant execution authority.

## DSPy frontier

The DSPy compiler is intentionally outside the normal execution path:

```text
strict JSON request        → no LLM
exact process-cache hit    → no LLM
solver matching            → no LLM
formal planning            → no LLM
bounded rollout            → no LLM
unmodeled natural language → DSPy compiler
```

The compiler may select only registered domains and solvers, and its JSON constructor arguments are validated before use.

## 80/20 ERRC cache

ERRC means:

- **Eliminate** exact repeated solves.
- **Reduce** repeated registry matching and construction.
- **Raise** evidence by binding domain, solver, implementation, runtime, subject, policy, environment, and randomness identities.
- **Create** a measured hot set and deterministic refusal memory.

The cache stores canonical JSON artifacts. It never stores live solver objects, credentials, approvals, or actuation authority.

Match-cache identity includes:

```text
domain
× domain arguments
× domain implementation digest
× registry digest
× scikit-decide runtime identity
```

Solve-cache identity includes:

```text
domain
× exact selected solver
× domain arguments
× solver arguments
× rollout bound
× domain implementation digest
× solver implementation digest
× subject digest
× policy digest
× environment digest
× randomness digest
× runtime identity
× fabric schema
```

Changing any material identity produces a miss. A request with an unbound subject, policy, environment, or randomness identity bypasses solve-result caching. Deterministic refusals are cached for five minutes only when the same exact reuse identity is admitted; transient execution failures are never cached.

The cache reports whether its highest-frequency 20% of artifacts account for at least 80% of reuse. That measurement identifies the scenario classes that should be preplanned, prevalidated, and retained as the operational hot set.

## Standing

The exact claim ceiling is:

```text
REGISTERED_DOMAIN_SOLVER_MATCH_AND_BOUNDED_ROLLOUT_ONLY
```

This crown does not establish:

- universal default constructors for every registered domain;
- universal solver compatibility or global optimality;
- authorization to actuate external systems;
- safety of arbitrary remote agents or MCP clients;
- aggregate scikit-decide release standing;
- package-level entry-point stability.
