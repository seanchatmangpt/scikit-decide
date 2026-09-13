# IaC-Eval v2 — AutoFDE SOTA Crown Plan

**Status:** `PLAN / UNKNOWN`  
**Research snapshot:** 2026-08-07  
**Surface:** `EXPLORE`  
**Class:** AWS Terraform generation with validate/plan/OPA verification

## Observed frontier

IaC-Eval v2 contains 186 AWS/Terraform tasks with deterministic Terraform + OPA/Rego verification. A 2026 verifier-first study reports GPT-4o iterative refinement at 84.4% pass@1.

Sources:
- https://arxiv.org/abs/2607.20478
- https://huggingface.co/datasets/iac-eval-v2/iac-eval-v2

## Crown objective

≥96% pass@1 across the complete verifier chain, ≥90% zero-retry success, ≤1.15 mean generation attempts, with no hidden verifier-policy manipulation.

**Scorecard:** overall pass@1; validate/plan/OPA stage pass; retries; latency; intent failures; security/policy violations; token cost.

## Shared AutoFDE calculus

The benchmark is modeled as a typed transition system, not a free-form agent loop:

`O → O* → Π → μ → I`

`autofde-lab` ends at candidate plan/intent manufacture. Consequential execution is external and must return benchmark-native verifier evidence plus a replayable receipt.

The planning accelerator is the reverse-world construction:

`W* = ggen-legacy(task specification, ontology, constraints)`

AutoFDE plans the smallest admitted morphism `π: O* → W*`. For RCA, `W*` is the healthy counterfactual and `Δ(O*,W*)` narrows causes. For construction, `W*` is desired infrastructure/identity/process state. Public self-play uses ggen-legacy to manufacture lawful variants; held-out answers are never inputs.

Reusable path: **ontology → world factory → planner portfolio → POWL/process mining → wasm4pm compilation where closed → typed gymact intent → external DO → native verifier → receipt/replay**.

## Why AutoFDE can win

This is a ggen crown. Parse the request into an admitted infrastructure graph constrained by the AWS provider schema and Rego policy; ggen renders Terraform as a projection. On verifier failure, repair the graph cause and regenerate instead of patching HCL strings. ggen-legacy can manufacture the target world `W*`, making generation a graph-delta problem rather than next-token code synthesis.

## Experiment campaign

1. Pin IaC-Eval v2 dataset, Terraform 1.15+, AWS provider ~6, OPA 1.16.1 and Rego v1 semantics.
2. Reproduce the 84.4% GPT-4o iterative baseline.
3. Build intent→resource graph parsing and provider-schema admission.
4. Project graph→Terraform with ggen; validate graph constraints before rendering.
5. Repair failed graph constraints, not output text; preserve typed failure classes.
6. Headline run disables retries; report a separate repair-allowed ceiling.

## Falsifiers

- Pass@1 hides retries.
- Terraform validates but violates intent.
- OPA policy is weakened or altered.
- Provider-version drift collapses results.

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
