# Sola-Visibility-ISPM — AutoFDE SOTA Crown Plan

**Status:** `PLAN / UNKNOWN`  
**Research snapshot:** 2026-08-07  
**Surface:** `EXPLORE`  
**Class:** AWS + Okta + Google Workspace identity security visibility

## Observed frontier

The benchmark evaluates 77 questions in a live production-grade identity environment. The Sola AI Agent reports expert accuracy 0.84, strict success 0.77, and AWS hygiene expert accuracy 0.94.

Sources:
- https://arxiv.org/abs/2601.07880

## Crown objective

expert accuracy ≥0.96, strict success ≥0.92, AWS hygiene ≥0.98, Okta/Google Workspace hygiene ≥0.93, with 100% evidence-linked answers and zero unsupported identity joins.

**Scorecard:** expert accuracy; strict success; per-platform hygiene; evidence completeness; false joins; query count; latency; cost.

## Shared AutoFDE calculus

The benchmark is modeled as a typed transition system, not a free-form agent loop:

`O → O* → Π → μ → I`

`autofde-lab` ends at candidate plan/intent manufacture. Consequential execution is external and must return benchmark-native verifier evidence plus a replayable receipt.

The planning accelerator is the reverse-world construction:

`W* = ggen-legacy(task specification, ontology, constraints)`

AutoFDE plans the smallest admitted morphism `π: O* → W*`. For RCA, `W*` is the healthy counterfactual and `Δ(O*,W*)` narrows causes. For construction, `W*` is desired infrastructure/identity/process state. Public self-play uses ggen-legacy to manufacture lawful variants; held-out answers are never inputs.

Reusable path: **ontology → world factory → planner portfolio → POWL/process mining → wasm4pm compilation where closed → typed gymact intent → external DO → native verifier → receipt/replay**.

## Why AutoFDE can win

Identity posture is primarily a graph-query problem. Normalize principals, groups, roles, policies, resources, entitlements and SaaS identities into a provenance-preserving identity graph; compile questions into graph queries plus evidence requirements. Models interpret language and explain results, but joins, counts, enumerations and hygiene predicates are deterministic.

## Experiment campaign

1. Pin benchmark schema and reproduce public methodology where possible.
2. Build canonical identity adapters for AWS, Okta and Google Workspace with source provenance.
3. Compile benchmark questions into explicit query/evidence plans.
4. Implement hygiene as deterministic graph predicates.
5. Self-play aliases, nested groups, stale accounts, inherited permissions, cross-account roles and conflicting metadata.
6. Run counterfactual query tests to expose false joins and incomplete populations.

## Falsifiers

- Answers require unsupported identity joins.
- Correct answers lack replayable evidence.
- Normalization merges distinct principals or misses aliases.
- Strong AWS results hide weak Okta/Workspace performance.

## Validation ladder

1. Contract/action/verifier tests + refusal fixtures.
2. Deterministic fixture replay.
3. Exact incumbent reproduction.
4. Public benchmark run.
5. Generated perturbation/noise/topology adversaries.
6. Held-out or official submission.
7. Economics + clean replay receipt.

## Contamination law

Public semantics and public training cases may support process mining, planner tuning, and generated variants. Private/held-out cases may not enter prompts, retrieval, procedures, demonstrations, or target-world generation. Generated worlds must carry lineage to public semantics. Native benchmark verification outranks generated verification.

## Victory-claim gate

This repository's `docs/autofde/EXPLORE.md` excludes press-release copy. The external release may say **“AutoFDE defeated the prior state of the art”** only after the exact benchmark subject is pinned and executed, the strongest same-semantics comparator is established, hidden-task contamination is excluded, benchmark-native verifier output and repeated-run statistics are retained, model/toolchain/config/cost/latency/actions/refusals are disclosed, and the result replays from a clean environment or official submission path. Until then: `UNKNOWN` or `PARTIAL_ALIVE`, never a crown claim.

## Required crown receipt

`benchmark SHA/dataset hash → comparator identity/score → AutoFDE repo SHA + planner/world-factory/adapter/model/toolchain identities → exact execution subject/repeats/native verifier → score/cost/latency/tokens-actions/refusals → replay command/exit/receipt → scoped standing`
