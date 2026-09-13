# ITBench Core — AutoFDE SOTA Crown Plan

**Status:** `PLAN / UNKNOWN`
**Research snapshot:** 2026-08-07
**Surface:** `EXPLORE`
**Class:** SRE + CISO + FinOps enterprise IT automation

## Observed frontier

The ICML 2025 paper reports 102 real-world scenarios and baseline resolution of 11.4% for SRE, 25.2% for CISO, and 25.8% for FinOps excluding anomaly detection; FinOps anomaly detection reaches F1 0.35. The current repository continues to evolve, so exact crown runs must pin the current subject.

Sources:
- https://proceedings.mlr.press/v267/jha25a.html
- https://github.com/itbench-hub/ITBench

## Crown objective

At crown time, beat the strongest same-subject official row in every evaluated domain by ≥5 pp. Planning floor: ≥60% SRE, ≥65% CISO, ≥60% FinOps non-AD, and anomaly F1 ≥0.70.

**Scorecard:** resolution by domain/scenario; anomaly F1; safety violations; cost-savings correctness; evidence coverage; action count; runtime.

## Shared AutoFDE calculus

The benchmark is modeled as a typed transition system, not a free-form agent loop:

`O → O* → Π → μ → I`

`autofde-lab` ends at candidate plan/intent manufacture. Consequential execution is external and must return benchmark-native verifier evidence plus a replayable receipt.

The planning accelerator is the reverse-world construction:

`W* = ggen-legacy(task specification, ontology, constraints)`

AutoFDE plans the smallest admitted morphism `π: O* → W*`. For RCA, `W*` is the healthy counterfactual and `Δ(O*,W*)` narrows causes. For construction, `W*` is desired infrastructure/identity/process state. Public self-play uses ggen-legacy to manufacture lawful variants; held-out answers are never inputs.

Reusable path: **ontology → world factory → planner portfolio → POWL/process mining → wasm4pm compilation where closed → typed gymact intent → external DO → native verifier → receipt/replay**.

## Why AutoFDE can win

Treat SRE, security/compliance, and FinOps as different objective functions over one admitted enterprise graph. ggen-legacy manufactures domain-valid target worlds and conflict cases; planners optimize reliability, policy, or cost while preserving cross-domain invariants.

## Experiment campaign

1. Pin the exact core benchmark revision, scenario set, and official evaluation semantics.
2. Build one enterprise graph spanning resources, identity, topology, telemetry, policy and cost.
3. Define separate domain objectives and refusal laws on the shared graph.
4. Route planner type by domain: active diagnosis, policy/constraint reasoning, or constrained cost optimization.
5. Self-play cross-domain conflicts such as cheap-but-noncompliant and secure-but-unavailable.
6. Publish per-domain Pareto fronts rather than hiding a domain loss inside one blended score.

## Falsifiers

- Shared ontology erases domain-specific constraints.
- FinOps savings violate reliability/security.
- CISO answers cannot name exact evidence/resources.
- Offline standing does not transfer to live scenarios.

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
