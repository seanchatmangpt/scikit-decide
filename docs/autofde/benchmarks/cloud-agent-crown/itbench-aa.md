# ITBench-AA — AutoFDE SOTA Crown Plan

**Status:** `PLAN / UNKNOWN`  
**Research snapshot:** 2026-08-07  
**Surface:** `EXPLORE`  
**Class:** offline Kubernetes root-cause entity identification

## Observed frontier

Artificial Analysis currently evaluates 59 incident tasks (40 public + 19 private), three repeats per task. GPT-5.6 Sol (max) leads at 56.2% average precision at full recall. Missing any true root-cause entity makes the repeat score zero; once full recall is reached, extra false positives reduce precision.

Sources:
- https://artificialanalysis.ai/evaluations/itbench-aa
- https://github.com/itbench-hub/ITBench

## Crown objective

≥68% average precision at full recall, ≤20 average turns, fewer false-positive root-cause entities than the incumbent, and a favorable score/cost frontier.

**Scorecard:** average precision at full recall; exact root-cause set; false positives/task; turns; tokens; cost; causal path coverage.

## Shared AutoFDE calculus

The benchmark is modeled as a typed transition system, not a free-form agent loop:

`O → O* → Π → μ → I`

`autofde-lab` ends at candidate plan/intent manufacture. Consequential execution is external and must return benchmark-native verifier evidence plus a replayable receipt.

The planning accelerator is the reverse-world construction:

`W* = ggen-legacy(task specification, ontology, constraints)`

AutoFDE plans the smallest admitted morphism `π: O* → W*`. For RCA, `W*` is the healthy counterfactual and `Δ(O*,W*)` narrows causes. For construction, `W*` is desired infrastructure/identity/process state. Public self-play uses ggen-legacy to manufacture lawful variants; held-out answers are never inputs.

Reusable path: **ontology → world factory → planner portfolio → POWL/process mining → wasm4pm compilation where closed → typed gymact intent → external DO → native verifier → receipt/replay**.

## Why AutoFDE can win

Turn the benchmark into minimal causal abduction. Build a Kubernetes evidence graph and a generated healthy reference world; identify the smallest independent root-cause entity set whose forward causal paths cover all symptoms. The LLM proposes uncertain semantics, while the final entity set is selected by a constrained minimum-hitting-set / causal-closure solver.

## Experiment campaign

1. Pin ITBench-AA/Stirrup and reproduce the current leader where accessible.
2. Normalize alerts, events, metrics, traces, manifests and topology into one graph.
3. Generate candidate causes from temporal order, topology, anomaly propagation, configuration constraints, and healthy-world deltas.
4. Solve for the minimal entity set covering all symptoms; reject unsupported entities.
5. Use only public tasks for process mining and self-play; never expose the 19 private tasks to training/retrieval.
6. Run the prescribed three repeats and report uncertainty, false-positive distribution, turns and cost.

## Falsifiers

- The result depends on public answer/resource-name memorization.
- Minimal-set search drops multiple independent causes.
- Low turns come from premature convergence.
- Held-out/private performance collapses.

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
