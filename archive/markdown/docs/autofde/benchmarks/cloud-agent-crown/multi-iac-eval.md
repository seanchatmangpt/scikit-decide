# Multi-IaC-Eval / Multi-IaC-Bench — AutoFDE SOTA Crown Plan

**Status:** `PLAN / UNKNOWN`
**Research snapshot:** 2026-08-07
**Surface:** `EXPLORE`
**Class:** CloudFormation, Terraform, CDK Python, and CDK TypeScript mutation

## Observed frontier

The public dataset contains 709 examples (263 CloudFormation, 446 Terraform) plus CDK repositories (64 Python and 64 TypeScript examples noted in the dataset card). The paper reports >95% syntactic validity for modern models but persistent semantic-alignment gaps. This research snapshot did not verify a single current official SOTA row, so the crown comparator must be resolved against the exact scoring implementation before a win claim.

Sources:
- https://arxiv.org/abs/2509.05303
- https://huggingface.co/datasets/AmazonScience/Multi-IaC-Eval

## Crown objective

Beat the strongest verified per-format semantic-alignment baseline by ≥0.25 on its native scale while holding native lint/synth/validate ≥99%, security checks ≥99% where defined, first-attempt success ≥95%, and faithful-change rate ≥98%.

**Scorecard:** native lint/validate/synth; security; semantic judge/native alignment; unrelated semantic delta; retries; calls; cross-format graph equivalence.

## Shared AutoFDE calculus

The benchmark is modeled as a typed transition system, not a free-form agent loop:

`O → O* → Π → μ → I`

`autofde-lab` ends at candidate plan/intent manufacture. Consequential execution is external and must return benchmark-native verifier evidence plus a replayable receipt.

The planning accelerator is the reverse-world construction:

`W* = ggen-legacy(task specification, ontology, constraints)`

AutoFDE plans the smallest admitted morphism `π: O* → W*`. For RCA, `W*` is the healthy counterfactual and `Δ(O*,W*)` narrows causes. For construction, `W*` is desired infrastructure/identity/process state. Public self-play uses ggen-legacy to manufacture lawful variants; held-out answers are never inputs.

Reusable path: **ontology → world factory → planner portfolio → POWL/process mining → wasm4pm compilation where closed → typed gymact intent → external DO → native verifier → receipt/replay**.

## Why AutoFDE can win

Solve one graph mutation, not four language-generation problems. Parse each initial IaC artifact into a canonical resource/dependency/property graph, apply the admitted natural-language delta once, then render the same changed graph into the requested IaC representation. Round-trip projection proves cross-format semantic invariance.

## Experiment campaign

1. Pin exact dataset/repo versions and resolve the current official scoring scale/leader by format.
2. Build parsers from each IaC language to the canonical graph.
3. Translate utterance→bounded graph delta; reject ambiguous destructive edits.
4. Render with ggen, run native validation and security checks, then round-trip output back to the graph.
5. Prove intended delta + no unrelated semantic drift.
6. Self-play equivalent mutations across all formats to force projection invariance.

## Falsifiers

- High score includes unrelated changes.
- One projection silently drops graph semantics.
- CDK synthesis differs from Terraform/CloudFormation world graph.
- Retry cost remains no better than prompt baselines.

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
