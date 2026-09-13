# Secure Text-to-Terraform — AutoFDE SOTA Crown Plan

**Status:** `PLAN / UNKNOWN`  
**Research snapshot:** 2026-08-07  
**Surface:** `EXPLORE`  
**Class:** security-first AWS Terraform generation

## Observed frontier

A paper published 2026-08-02 evaluates seven models across 17 AWS Terraform scenarios using Checkov and Trivy. Under detailed security prompting, Claude Opus 4 reaches 23.1% Checkov compliance and 92.5% Trivy pass rate (pass@5 study).

Sources:
- https://arxiv.org/abs/2608.02672

## Crown objective

100% terraform validate, ≥95% Checkov, ≥98% Trivy, ≥90% joint Checkov∩Trivy compliance on the first admitted artifact, plus ≥95% functional intent correctness.

**Scorecard:** validate; Checkov; Trivy; joint compliance; intent correctness; high-severity findings; retries; cost.

## Shared AutoFDE calculus

The benchmark is modeled as a typed transition system, not a free-form agent loop:

`O → O* → Π → μ → I`

`autofde-lab` ends at candidate plan/intent manufacture. Consequential execution is external and must return benchmark-native verifier evidence plus a replayable receipt.

The planning accelerator is the reverse-world construction:

`W* = ggen-legacy(task specification, ontology, constraints)`

AutoFDE plans the smallest admitted morphism `π: O* → W*`. For RCA, `W*` is the healthy counterfactual and `Δ(O*,W*)` narrows causes. For construction, `W*` is desired infrastructure/identity/process state. Public self-play uses ggen-legacy to manufacture lawful variants; held-out answers are never inputs.

Reusable path: **ontology → world factory → planner portfolio → POWL/process mining → wasm4pm compilation where closed → typed gymact intent → external DO → native verifier → receipt/replay**.

## Why AutoFDE can win

Move security ahead of generation. Convert scanner-relevant controls into constraints on the target infrastructure graph, so insecure states are inadmissible unless the task explicitly grants a bounded exception. Scanners remain independent verifiers; they do not become a post-hoc prompt repair loop.

## Experiment campaign

1. Pin paper artifacts, scanner/rule versions, Terraform/provider versions and 17 scenarios.
2. Reproduce frontier rows under the paper's prompt/security-level protocol.
3. Map findings into graph constraints and typed exception/refusal objects.
4. Generate only after security+intent admission; independently run validate/plan where applicable, Checkov and Trivy.
5. Use counterexample-guided graph repair for residual failures; forbid suppression-as-repair.
6. Self-play CIDR, encryption, IAM scope, public access, logging and KMS mutations.

## Falsifiers

- Security score rises by omitting requested functionality.
- One scanner passes while equivalent high-severity findings remain in another.
- Suppressions/skips are used without admitted justification.
- Security defaults make the intended deployment unusable.

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
