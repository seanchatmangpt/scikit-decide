# AIOpsLab — AutoFDE SOTA Crown Plan

**Status:** `PLAN / UNKNOWN`  
**Research snapshot:** 2026-08-07  
**Surface:** `EXPLORE`  
**Class:** autonomous-cloud detection, localization, diagnosis, mitigation

## Observed frontier

Current AIOpsLab leaderboard: OpsAgent (GPT-4) leads at 78.75 average accuracy: detection 100, localization 60, diagnosis 83.34, mitigation 66.67, average time 27.6.

Sources:
- https://microsoft.github.io/AIOpsLab/pages/leaderboard/

## Crown objective

≥90 average accuracy with detection ≥99, localization ≥85, diagnosis ≥90, mitigation ≥85, and mean time ≤25 seconds.

**Scorecard:** average; detection; localization; diagnosis; mitigation; runtime; invalid API calls; evidence coverage; reversibility.

## Shared AutoFDE calculus

The benchmark is modeled as a typed transition system, not a free-form agent loop:

`O → O* → Π → μ → I`

`autofde-lab` ends at candidate plan/intent manufacture. Consequential execution is external and must return benchmark-native verifier evidence plus a replayable receipt.

The planning accelerator is the reverse-world construction:

`W* = ggen-legacy(task specification, ontology, constraints)`

AutoFDE plans the smallest admitted morphism `π: O* → W*`. For RCA, `W*` is the healthy counterfactual and `Δ(O*,W*)` narrows causes. For construction, `W*` is desired infrastructure/identity/process state. Public self-play uses ggen-legacy to manufacture lawful variants; held-out answers are never inputs.

Reusable path: **ontology → world factory → planner portfolio → POWL/process mining → wasm4pm compilation where closed → typed gymact intent → external DO → native verifier → receipt/replay**.

## Why AutoFDE can win

Exploit the weak stages, not the saturated one. Detection is already near ceiling; AutoFDE should require a single evidence-linked causal chain from symptom → localization → mechanism → mitigation. ggen-legacy generates the healthy reference state and faulted variants, so localization is the smallest causal delta consistent with observed symptoms.

## Experiment campaign

1. Reproduce OpsAgent's stage-level row on the pinned harness.
2. Convert the action interface into typed gymact candidate-intent contracts.
3. Require evidence-linked localization before diagnosis can close.
4. Construct mitigation from diagnosed mechanism and generated target post-state.
5. Self-play public incidents and fault combinations; compile stable procedures.
6. Run ablations removing graph, verifier feedback, compiled procedures, and causal closure.

## Falsifiers

- Average rises while localization/mitigation remains below SOTA.
- Diagnosis uses hidden labels rather than observable evidence.
- Mitigation passes a narrow check but violates broader service health.
- Runtime drops only because evidence acquisition is skipped.

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
