# OpenRCA 2.0 — AutoFDE SOTA Crown Plan

**Status:** `PLAN / UNKNOWN`  
**Research snapshot:** 2026-08-07  
**Surface:** `EXPLORE`  
**Class:** causal RCA over logs, metrics, traces, and service topology

## Observed frontier

Current OpenRCA 2.0 leaderboard snapshot: DeepResearch + Claude Opus 5 leads with F1 61.37%, exact accuracy 46.40%, node-F1 80.15%, edge-F1 66.99%, any-hit 88.80%, all-hit 64.00%, path accuracy 68.80%, and type accuracy 77.36%.

Sources:
- https://microsoft.github.io/OpenRCA/

## Crown objective

F1 ≥72%, exact accuracy ≥60%, node-F1 ≥88%, edge-F1 ≥80%, path accuracy ≥80%, all-hit ≥75%, while reducing telemetry/model-token volume.

**Scorecard:** F1; exact accuracy; node/edge F1; any-hit/all-hit; path accuracy; type accuracy; telemetry bytes; tokens; wall time.

## Shared AutoFDE calculus

The benchmark is modeled as a typed transition system, not a free-form agent loop:

`O → O* → Π → μ → I`

`autofde-lab` ends at candidate plan/intent manufacture. Consequential execution is external and must return benchmark-native verifier evidence plus a replayable receipt.

The planning accelerator is the reverse-world construction:

`W* = ggen-legacy(task specification, ontology, constraints)`

AutoFDE plans the smallest admitted morphism `π: O* → W*`. For RCA, `W*` is the healthy counterfactual and `Δ(O*,W*)` narrows causes. For construction, `W*` is desired infrastructure/identity/process state. Public self-play uses ggen-legacy to manufacture lawful variants; held-out answers are never inputs.

Reusable path: **ontology → world factory → planner portfolio → POWL/process mining → wasm4pm compilation where closed → typed gymact intent → external DO → native verifier → receipt/replay**.

## Why AutoFDE can win

OpenRCA's path metrics align directly with a graph calculus. Specialized telemetry reducers emit typed anomalies; the planner searches for temporally valid forward causal paths from candidate root nodes to user-visible effects. ggen-legacy generates healthy and fault-propagation counterfactuals to score whether a proposed path explains the observed delta.

## Experiment campaign

1. Pin OpenRCA 2.0 and reproduce the standard-harness leader where possible.
2. Build compact metric/log/trace anomaly operators with provenance.
3. Create a temporal causal multigraph and generate candidate cause→effect paths.
4. Rank paths by evidence coverage, temporal consistency, fault constraints, and counterfactual plausibility.
5. Self-play telemetry density, irrelevant anomalies, renamed services, propagation depth and missing modalities.
6. Report outcome and process metrics together, with representative failed causal paths.

## Falsifiers

- Exact labels improve while path accuracy falls.
- Telemetry reduction discards decisive evidence.
- Rules are hand-coded from test instances.
- A correct service label cannot be causally connected to the symptom.

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
