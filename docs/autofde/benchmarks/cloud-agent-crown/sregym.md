# SREGym — AutoFDE SOTA Crown Plan

**Status:** `PLAN / UNKNOWN`  
**Research snapshot:** 2026-08-07  
**Surface:** `EXPLORE`  
**Class:** live SRE diagnosis + mitigation under Kubernetes noise

**2026-08-10 update — architecture closed, no result yet:** the "Required crown
receipt" schema below is now a real, enforced type
(`autofde_lab.sota.crown_receipt.CrownReceipt`), not prose — `admit()` refuses any
receipt missing a required field, composing `gymact.sota.StandingEvidence`'s own
independent admission for the subject/experiment/receipt/verifier/replay-verified
portion. `sregym`/`swegym` are now wired into `level4_gymact_bridge.py`'s `_PROVIDERS`,
so the generic Level-4 discovery/trial harness can reach both real gymact providers.
Real Chicago-style tests prove the gate (`tests/sota/test_crown_receipt_chicago.py`)
and a real, `require_standing`-gated attempt at the actual `autofde_lab_planner`
episode (`tests/sota/test_crown_receipt_live_chicago.py`).

**Status stays `PLAN / UNKNOWN` — no result exists.** A real colima+k3s cluster and the
real vendored SREGym checkout were both stood up and exercised this session; the
concrete remaining blocker is external and named, not implied to be "almost done":
even the non-LLM `autofde_lab_planner` path's judge pre-flight check requires
`OPENAI_API_KEY`, which is not configured. Until real judge-model credentials exist,
`test_crown_receipt_live_chicago.py` correctly refuses (fails loudly, not silently) —
matching this doc's own Victory-claim gate below.

## Observed frontier

Current public leaderboard snapshot: Claude Code + Claude Sonnet 4.6 leads at 60.7% end-to-end without noise and 53.7% with noise. SREGym only counts E2E when diagnosis and mitigation both succeed on the same live run.

Sources:
- https://www.sregym.com/
- https://sregym.com/docs

## Crown objective

≥72% E2E without noise and ≥65% with noise; diagnosis ≥80%; mitigation ≥82%; materially lower TTD/TTM and tokens than the incumbent at comparable success.

**Scorecard:** E2E; diagnosis; mitigation; TTD; TTM; tokens; invalid actions; noise robustness; compound-fault score; refusal/rollback rate.

## Shared AutoFDE calculus

The benchmark is modeled as a typed transition system, not a free-form agent loop:

`O → O* → Π → μ → I`

`autofde-lab` ends at candidate plan/intent manufacture. Consequential execution is external and must return benchmark-native verifier evidence plus a replayable receipt.

The planning accelerator is the reverse-world construction:

`W* = ggen-legacy(task specification, ontology, constraints)`

AutoFDE plans the smallest admitted morphism `π: O* → W*`. For RCA, `W*` is the healthy counterfactual and `Δ(O*,W*)` narrows causes. For construction, `W*` is desired infrastructure/identity/process state. Public self-play uses ggen-legacy to manufacture lawful variants; held-out answers are never inputs.

Reusable path: **ontology → world factory → planner portfolio → POWL/process mining → wasm4pm compilation where closed → typed gymact intent → external DO → native verifier → receipt/replay**.

## Why AutoFDE can win

Model incident response as a POMDP/active-diagnosis problem. ggen-legacy generates the healthy counterfactual world and legal fault variants; the planner chooses probes by information gain over the discrepancy graph, then selects the smallest reversible mitigation whose postcondition returns the live world toward `W*`.

## Experiment campaign

1. Reproduce Claude Code, Stratus, and Codex leaderboard rows where accessible.
2. Create typed symptom/topology/fault/probe/mitigation/health state machines.
3. Maintain explicit hypothesis sets and causal-closure stopping rules rather than fixed ReAct turns.
4. Self-play benchmark-public faults plus generated noise, delayed telemetry, duplicate symptoms, compound faults, and tool failure.
5. Compile stable fault families into POWL/wasm4pm procedures; retain exploratory planning for residual unknowns.
6. Report noisy and non-noisy E2E together with TTD, TTM, tokens, action count, and failure classes.

## Falsifiers

- Noise robustness comes from ignoring telemetry.
- Mitigation raises a narrow health check while creating a new fault.
- Correct diagnosis still fails E2E due to bad execution plans.
- Performance depends on benchmark resource names rather than causal structure.

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
