# Aliyun Cloud Console 278-task benchmark — AutoFDE SOTA Crown Plan

**Status:** `PLAN / UNKNOWN`
**Research snapshot:** 2026-08-07
**Surface:** `EXPLORE`
**Class:** real-world cloud-console web-agent execution

## Observed frontier

The AliyunConsoleAgent paper evaluates 278 real-cloud console/documentation tasks. The best frontier proprietary model reaches 65.34% mean success; AliyunConsoleAgent-32B reaches 63.52% and is reported at 92% lower inference cost.

Sources:
- https://arxiv.org/abs/2606.09447

## Crown objective

≥76% mean success, ≥70% on held-out/new-console variants, ≥95% valid-action rate, and ≥50% lower cost per verified success than the lowest-cost comparator within 5 pp of AutoFDE.

**Scorecard:** mean success; cost per task/success; valid actions; steps; UI recovery; drift robustness; backend audit verification.

## Shared AutoFDE calculus

The benchmark is modeled as a typed transition system, not a free-form agent loop:

`O → O* → Π → μ → I`

`autofde-lab` ends at candidate plan/intent manufacture. Consequential execution is external and must return benchmark-native verifier evidence plus a replayable receipt.

The planning accelerator is the reverse-world construction:

`W* = ggen-legacy(task specification, ontology, constraints)`

AutoFDE plans the smallest admitted morphism `π: O* → W*`. For RCA, `W*` is the healthy counterfactual and `Δ(O*,W*)` narrows causes. For construction, `W*` is desired infrastructure/identity/process state. Public self-play uses ggen-legacy to manufacture lawful variants; held-out answers are never inputs.

Reusable path: **ontology → world factory → planner portfolio → POWL/process mining → wasm4pm compilation where closed → typed gymact intent → external DO → native verifier → receipt/replay**.

## Why AutoFDE can win

Represent console work as a UI process backed by backend-state postconditions. ggen-legacy generates the desired backend world and a semantic navigation/process model; POWL procedures use stable semantic anchors rather than coordinates. Browser appearance is never proof of completion—the backend audit/resource state closes the result.

## Experiment campaign

1. Pin the 278-task environment and reproduce frontier/32B baselines where available.
2. Represent each task as desired backend state plus a UI process graph.
3. Express browser actions as typed candidate intents with pre/postconditions and recovery edges.
4. Mine and compile stable public procedures; fall back to DOM/visual reasoning only when process state is unmatched.
5. Verify completion from backend audit/resource state rather than page text.
6. Self-play menu reordering, label changes, latency, dialogs, pagination, permissions and stale documentation.

## Falsifiers

- Success is inferred from UI appearance only.
- Procedures depend on brittle coordinates/exact labels.
- Cost reduction sacrifices frontier-level success.
- Held-out procedures leak into training.

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
