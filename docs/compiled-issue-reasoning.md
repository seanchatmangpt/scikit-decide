# Compiled Issue Reasoning

AutoFDE Lab can route recurring troubleshooting through a finite diagnostic graph before spending open-ended cognition.

## Calculus

```text
OBSERVE
  -> NORMALIZE
  -> ROUTE
  -> HYPOTHESIZE
  -> ELIMINATE
  -> CONSTRUCT CANDIDATE REPAIR INTENT
  -> VERIFY EVIDENCE CONTRACT
  -> MATCHED | REFUSED_EVIDENCE | FALLBACK_NOVELTY
```

This package does not admit or actuate the repair intent. `mfw`/BRCE remains the authority boundary.

## Compilation criterion

A troubleshooting family belongs on the compiled path when it has all four properties:

1. structured observable evidence;
2. a finite causal/diagnostic graph;
3. bounded repair candidates;
4. a deterministic verifier.

Unknown or metastable causal topology is not forced through the graph. It returns `FALLBACK_NOVELTY`, so cognition can discover a new pattern. Once independently validated, that pattern can be added as another deterministic archetype.

```text
novel issue -> cognition -> validation -> admitted knowledge -> compiled recurrence
```

## MCP tools

`issue_reasoning_catalog` returns the finite archetype inventory and evidence contracts.

`issue_reason` accepts either a list of active evidence symbols or a mapping whose truthy values indicate observed evidence.

Example input:

```json
{"no_endpoints": true}
```

Example candidate result shape:

```json
{
  "route": "MATCHED",
  "archetype": "service_routing",
  "domain": "networking",
  "matched_evidence": ["no_endpoints"],
  "missing_evidence": [],
  "contradictory_evidence": [],
  "hypotheses_considered": [
    "selector_mismatch",
    "target_port_mismatch",
    "backend_unready",
    "endpoint_stale"
  ],
  "hypotheses_eliminated": 3,
  "repair_intent": "construct a service-routing repair candidate",
  "evidence_identity_sha256": "...",
  "candidate_identity_sha256": "...",
  "actuation": "REFUSED"
}
```

The SHA-256 fields are deterministic content identities for evidence and candidate replay. They are **not admission receipts**.

## Current generalized inventory

The initial compiler spans scheduling/capacity, probes/restart loops, service routing, DNS, authorization, resource exhaustion, storage, configuration drift, dependency failure, data/schema validation, software/version compatibility, queue/backpressure, build/toolchain failure, governance/policy, business-process stuck state, and explicit novel causal topology.

The inventory is intentionally extensible: the value proposition is not the first 16 patterns, but the ratchet that continually moves validated recurrence from expensive cognition into deterministic process reasoning.

## Challenger 8x8 value benchmark

`benchmarks/challenger_issue_reasoning.py` executes eight enterprise portfolios with eight reasoning uses per portfolio. At the CI setting of 100,000 repetitions this is 6,400,000 directly executed issue-reasoning calls.

Economic value is calculated only for `MATCHED` compiled episodes. `FALLBACK_NOVELTY` and `REFUSED_EVIDENCE` receive zero displaced-cognition value. In the benchmark's deliberately bounded 64-pattern portfolio, 60 patterns are compiled-known and four are novelty fallbacks, so the 100,000-repeat rail has 6,000,000 value-eligible matched executions.

The declared economic envelope is stored in `benchmarks/challenger_value_fibo.ttl` and uses ggen's vendored FIBO Currency Amount ontology at exact source snapshot `c37b46015b8e5ab40be771d61aafe3d7c7af084c`. Monetary outputs are typed as FIBO `MonetaryAmount` in USD.

The benchmark uses a declared loaded-engineering rate of $100/hour and reports three scenario translations:

| Matched compiled episodes | Minutes avoided per matched issue | Derived cognition-capacity value |
|---:|---:|---:|
| 6,000,000 | 5 | $50,000,000 |
| 6,000,000 | 15 | $150,000,000 |
| 6,000,000 | 30 | $300,000,000 |

These are **derived scenario values, not realized savings**. The benchmark proves the arithmetic correspondence between observed matched executions and a declared economic envelope. A realized enterprise savings claim additionally requires an observed enterprise issue corpus, measured human/LLM comparator cost and latency, and independent correctness verification.

The Challenger question is therefore measurable rather than rhetorical:

```text
Why purchase fresh cognition for an issue after its causal topology has been
validated, compiled, and deterministically replayed?
```
