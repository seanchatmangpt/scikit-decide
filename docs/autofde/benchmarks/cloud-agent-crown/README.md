# AutoFDE Cloud Agent Benchmark Crown Campaign

**Status:** `PLAN / UNKNOWN`  
**Research snapshot:** 2026-08-07  
**Repository surface:** `EXPLORE`

This directory contains one falsifiable SOTA-crown plan per cloud-agent benchmark. It deliberately separates benchmark planning from consequential execution and from marketing claims.

## Campaign thesis

The benchmark portfolio should be attacked as a family of typed transition systems:

```text
raw observation → admitted state → planner/policy selection → manufactured intent
                                               ↓
                                  external authorized execution
                                               ↓
                              native verifier → receipt → replay
```

The cross-benchmark planning accelerator is the reverse-world construction:

```text
W* = ggen-legacy(task specification, ontology, constraints)
Δ  = discrepancy(O*, W*)
π* = lowest-cost admitted plan that closes the required part of Δ
```

This makes `ggen-legacy` a benchmark **world factory**: it can generate what the environment should be, healthy counterfactuals, lawful fault variants, and adjacent self-play worlds. AutoFDE then plans over the delta rather than asking an LLM to discover the goal topology by trial-and-error.

## Documents

| Benchmark | Crown focus |
|---|---|
| [aws-bench](aws-bench.md) | AWS investigation, troubleshooting, creation |
| [SREGym](sregym.md) | live SRE diagnosis + mitigation under noise |
| [ITBench-AA](itbench-aa.md) | minimal root-cause entity sets |
| [ITBench Core](itbench-core.md) | SRE + CISO + FinOps |
| [AIOpsLab](aiopslab.md) | detection → localization → diagnosis → mitigation |
| [Cloud-OpsBench](cloud-opsbench.md) | deterministic RCA + process compilation |
| [OpenRCA 2.0](openrca-2.md) | causal paths over heterogeneous telemetry |
| [CUJBench](cujbench.md) | browser-to-backend causal synthesis |
| [IaC-Eval v2](iac-eval-v2.md) | graph→Terraform verifier closure |
| [Secure Text-to-Terraform](secure-text-to-terraform.md) | policy-by-construction |
| [Multi-IaC-Eval](multi-iac-eval.md) | graph mutation across IaC formats |
| [Sola-Visibility-ISPM](sola-visibility-ispm.md) | deterministic identity graph queries |
| [Aliyun Cloud Console](aliyun-console.md) | compiled UI procedures + backend verification |

## Recommended attack order

1. **Deterministic leverage:** Cloud-OpsBench, ITBench-AA, IaC-Eval v2, Multi-IaC-Eval, Sola-Visibility-ISPM.
2. **Live operations:** SREGym, AIOpsLab, aws-bench.
3. **Cross-modal causality:** OpenRCA 2.0, CUJBench.
4. **UI actuation:** Aliyun Cloud Console.
5. **Cross-cutting security rail:** Secure Text-to-Terraform.
6. **Portfolio transfer test:** ITBench Core.

The order is intentionally compositional: early work manufactures the graph, world-factory, planner-routing, verifier, process-mining, and receipt primitives reused by later benchmarks.

## Repository fence

`autofde-lab` is the exploration, falsification, and planning substrate. Candidate plans are not authority. Consequential mutation must remain outside this repository and return independent verifier evidence/receipts.

`docs/autofde/EXPLORE.md` also excludes press-release/marketing copy from this tree. Each benchmark document therefore contains a **victory-claim evidence contract**, not publishable marketing prose. Once a benchmark becomes `ALIVE`, the external release can be generated from the receipt without weakening this repository boundary.
