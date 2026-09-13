# CUJBench — AutoFDE SOTA Crown Plan

**Status:** `PLAN / UNKNOWN`  
**Research snapshot:** 2026-08-07  
**Surface:** `EXPLORE`  
**Class:** cross-modal browser-to-backend failure diagnosis

## Observed frontier

CUJBench provides 87 deterministic scenarios across five fault families. The paper reports 19.7% overall accuracy across evaluated conditions and a best-model ceiling of 52%; browser-only agents can outperform full-tool agents because extra telemetry induces unfocused exploration.

Sources:
- https://arxiv.org/abs/2604.23455

## Crown objective

≥65% exact diagnosis accuracy, ≥75% on cross-modal synthesis cases, ≤12 evidence actions/task, and no regression versus AutoFDE's own browser-only ablation.

**Scorecard:** exact accuracy; fault-family/modality score; evidence actions; decisive-evidence retrieval; synthesis given retrieval; time; tokens.

## Shared AutoFDE calculus

The benchmark is modeled as a typed transition system, not a free-form agent loop:

`O → O* → Π → μ → I`

`autofde-lab` ends at candidate plan/intent manufacture. Consequential execution is external and must return benchmark-native verifier evidence plus a replayable receipt.

The planning accelerator is the reverse-world construction:

`W* = ggen-legacy(task specification, ontology, constraints)`

AutoFDE plans the smallest admitted morphism `π: O* → W*`. For RCA, `W*` is the healthy counterfactual and `Δ(O*,W*)` narrows causes. For construction, `W*` is desired infrastructure/identity/process state. Public self-play uses ggen-legacy to manufacture lawful variants; held-out answers are never inputs.

Reusable path: **ontology → world factory → planner portfolio → POWL/process mining → wasm4pm compilation where closed → typed gymact intent → external DO → native verifier → receipt/replay**.

## Why AutoFDE can win

Represent the Critical User Journey as one graph: browser event/session → request/trace → service → dependency → infrastructure. The browser symptom constrains the backend causal frontier. Additional telemetry is admitted only if its expected information gain can discriminate live hypotheses.

## Experiment campaign

1. Reproduce retrieval, browser-only, and full-toolset baselines.
2. Build a typed CUJ graph with session/request/trace correlation.
3. Gate modality changes on expected information gain rather than tool availability.
4. Use modality-specific reducers to emit compact evidence claims.
5. Self-play time skew, duplicated requests, irrelevant backend anomalies, UI wording changes and missing modalities.
6. Compile recurring cross-modal motifs; retain graph search for unseen topologies.

## Falsifiers

- Full-tool AutoFDE remains below browser-only.
- Decisive evidence is retrieved but attributed to the wrong causal node.
- Results depend on exact UI strings/screens.
- Time alignment produces false causal links.

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
