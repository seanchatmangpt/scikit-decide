# Forward Deployment Context

This repository is part of the **Chatman Ecosystem**, a portfolio built to make forward deployment repeatable, governed, and evidence-bearing.

Sean Chatman is publicly documenting the case for **The 2,001st Forward-Deployed Agentic Architect** while building the **operating system for forward deployment**: a path from incomplete operational observation to admitted context, lawful construction, authorized actuation, receipts, and replay.

## Local role

Within that portfolio, `autofde-lab` is the canonical decision, planning, hypothesis, and integration control plane. Its domain/solver capability model provides the lawful SELECT/CONSTRUCT surface between admitted operational state and candidate plans. It does not itself receive ambient authority to actuate customer systems.

The portfolio-level lifecycle is:

```text
parse → route → admit/refuse → diagnose/repair → construct
→ BRCE.DO → verify → receipt → replay/hook → standing
```

The governing formulation is:

```text
A = μ(O*)
R = receipt(A)
```

## Ownership boundaries

- `autofde-lab` owns candidate hypotheses, discriminating experiments, planning routes, possibility graphs, desired-state envelopes, and inert solution graphs.
- `wasm4pm` may supply process-model evidence and continuously maintained process hypotheses; that evidence remains input until admitted here.
- `gymact` owns executable benchmark-world truth and consequences. A gym result is not production authority.
- `ggen` owns deterministic manufacture and manufacturing provenance. A ggen receipt binds manufacture; it is not a production consequence receipt.
- `autofde` owns production authority, the exclusive `BRCE.DO` consequence path, re-observation, consequence receipts, and replay. Zero production actuation is valid without a receipt-bearing BRCE path.
- Hooks manufacture intents only. Planner/model output, proofs, semantic derivations, and hooks never acquire ambient execution authority.

## Canonical cross-repository contracts

The repository now exposes inert, versionable contracts for the previously implicit seams:

```text
DomainPack
  → world | reasoning | manufacture | runtime projections

BaselineSnapshot
  → WorldDelta
  → HypothesisPortfolio
  → ExperimentPortfolio
  → PossibilityGraph
  → DesiredStateEnvelope
  → SolutionGraph
```

`DomainPack` requires source provenance, ontology identity, state/desired-state laws, violation modes, observation and authority contracts, planner compatibility, remediation morphology, verification rules, and exactly one projection for each of `world`, `reasoning`, `manufacture`, and `runtime`.

`SolutionGraph` is intentionally inert. It binds preconditions, transformation reference, preservation laws, postconditions, verifier, recovery, and authority requirements. It does not execute them.

## Crown benchmark law

The general failure-to-fix crown is:

```text
Δ → process inference → hypothesis closure → planner ensemble
  → desired state → manufacture → verifier generation → recovery generation
```

A sub-second claim is admitted only when all required stages were observed for the same subject and run. Partial timing evidence is `PARTIAL_ALIVE`; cross-subject timing aggregation is `REFUSED`; a complete run over budget is not `ALIVE`.

## Boundaries

- This portfolio context does not replace the project’s existing Airbus provenance, purpose, license, documentation, or contributor history.
- Inclusion does not assert that every upstream capability is authored by Sean Chatman.
- A planner result is a candidate until admission, authority, actuation, and consequence evidence are separately established.
- Component maturity and full ecosystem integration must be reported from exact observed execution, not from branding.

The canonical portfolio narrative is maintained in `seanchatmangpt/chatman-ecosystem`.
