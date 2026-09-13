# Cloud-OpsBench — AutoFDE SOTA Crown Plan

**Status:** `PLAN / UNKNOWN`  
**Research snapshot:** 2026-08-07  
**Surface:** `EXPLORE`  
**Class:** reproducible Kubernetes root-cause analysis from state snapshots

## Observed frontier

The original 2026 benchmark paper reports DeepSeek-V3.2 at A@1 = 0.73 with approximately 10 average steps and coverage 0.88. The repository has evolved, so paper-v1 and current-repository results are distinct subjects and MUST NOT be mixed.

Sources:
- https://arxiv.org/abs/2603.00468
- https://www.alphaxiv.org/abs/2603.00468

## Crown objective

On pinned paper-v1: A@1 ≥0.88, A@3 ≥0.93, invalid-action count = 0, zero-tool diagnosis rate = 0, evidence coverage ≥0.90, and redundant-action rate ≤0.10. On current repo: beat the exact current leader by ≥5 pp under native metrics.

**Scorecard:** A@1/A@3 or pinned native score; coverage; steps; invalid actions; redundant actions; zero-tool diagnoses; evidence ordering.

## Shared AutoFDE calculus

The benchmark is modeled as a typed transition system, not a free-form agent loop:

`O → O* → Π → μ → I`

`autofde-lab` ends at candidate plan/intent manufacture. Consequential execution is external and must return benchmark-native verifier evidence plus a replayable receipt.

The planning accelerator is the reverse-world construction:

`W* = ggen-legacy(task specification, ontology, constraints)`

AutoFDE plans the smallest admitted morphism `π: O* → W*`. For RCA, `W*` is the healthy counterfactual and `Δ(O*,W*)` narrows causes. For construction, `W*` is desired infrastructure/identity/process state. Public self-play uses ggen-legacy to manufacture lawful variants; held-out answers are never inputs.

Reusable path: **ontology → world factory → planner portfolio → POWL/process mining → wasm4pm compilation where closed → typed gymact intent → external DO → native verifier → receipt/replay**.

## Why AutoFDE can win

Deterministic snapshots make this the best process-compilation benchmark. Mine state→probe→evidence→cause trajectories, cluster them by causal motif, generate equivalent faulty/healthy worlds, compile stable procedures to POWL/wasm4pm, and route only residual ambiguity to model reasoning.

## Experiment campaign

1. Pin paper-v1 and current-repo SHAs as separate benchmark subjects.
2. Reproduce DeepSeek-V3.2 on paper-v1 where executable.
3. Mine public diagnostic trajectories into causal motifs and evidence milestones.
4. Generate semantics-preserving snapshot variants without exposing gold labels at inference.
5. Compile stable procedures and mechanically validate action schemas.
6. Disallow zero-tool final diagnosis; stop only on causal/evidence closure.

## Falsifiers

- Paper-v1 score is mixed with the evolved evaluator.
- Compiled policies memorize case IDs/resource names.
- Accuracy is purchased with speculative or invalid actions.
- Self-play leaks gold labels into inference.

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
