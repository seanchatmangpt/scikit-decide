# aws-bench — AutoFDE SOTA Crown Plan

**Status:** `PLAN / UNKNOWN`  
**Research snapshot:** 2026-08-07  
**Surface:** `EXPLORE`  
**Class:** AWS control-plane investigation, troubleshooting, and infrastructure creation

## Observed frontier

AWS launched aws-bench as a research preview on 2026-07-24. It provides reproducible real-AWS tasks with a CLI that instantiates, executes, scores, and resets environments. No stable public SOTA leaderboard was verified in this research snapshot, so the first campaign step is to manufacture the baseline frontier rather than invent one.

Sources:
- https://aws.amazon.com/about-aws/whats-new/2026/07/aws-bench/
- https://github.com/aws-bench/aws-bench

## Crown objective

Establish the same-harness frontier, then achieve ≥95% on the basic/public suite and ≥85% on the advanced suite, while exceeding the strongest reproduced agent by ≥5 percentage points and reducing cost per verified success by ≥50%.

**Scorecard:** pass rate split by investigation/troubleshooting/creation; basic vs advanced; AWS API calls; invalid/denied actions; cost per success; time-to-verified-state; rollback/replay success.

## Shared AutoFDE calculus

The benchmark is modeled as a typed transition system, not a free-form agent loop:

`O → O* → Π → μ → I`

`autofde-lab` ends at candidate plan/intent manufacture. Consequential execution is external and must return benchmark-native verifier evidence plus a replayable receipt.

The planning accelerator is the reverse-world construction:

`W* = ggen-legacy(task specification, ontology, constraints)`

AutoFDE plans the smallest admitted morphism `π: O* → W*`. For RCA, `W*` is the healthy counterfactual and `Δ(O*,W*)` narrows causes. For construction, `W*` is desired infrastructure/identity/process state. Public self-play uses ggen-legacy to manufacture lawful variants; held-out answers are never inputs.

Reusable path: **ontology → world factory → planner portfolio → POWL/process mining → wasm4pm compilation where closed → typed gymact intent → external DO → native verifier → receipt/replay**.

## Why AutoFDE can win

Generate the expected AWS resource graph `W*` from the task contract, compare it with admitted live state `O*`, and plan the minimal resource/relationship delta. Investigation tasks use the same graph in reverse: discrepancies between observed and healthy/generated worlds become causal hypotheses. This converts open-ended AWS exploration into resource-graph search.

## Experiment campaign

1. Pin aws-bench and dataset SHAs plus AWS service/provider versions.
2. Reproduce multiple frontier harnesses before optimization; publish separate mutation and introspection rows.
3. Materialize AWS resources, IAM, region, dependencies, health and quotas into the common evidence graph.
4. Use ggen-legacy to generate healthy/target AWS worlds and semantics-preserving perturbations: names, regions, irrelevant resources, quota pressure, extra healthy dependencies.
5. Plan minimal deltas and bounded diagnostic probes; compile stable public task motifs into POWL/wasm4pm.
6. Run public/basic, advanced, perturbation, then official/held-out submission with receipt bundles.

## Falsifiers

- The score advantage requires broader IAM or manual intervention.
- Basic performance does not transfer to advanced tasks.
- A live-state success cannot be replayed or rolled back.
- Cost/action count grows faster than scenario complexity.

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
