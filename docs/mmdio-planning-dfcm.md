# AutoFDE → mmdio with DFCM

The AutoFDE planning interchange uses `mmdio`'s Design for Combinatorial Maximalism (DFCM) layer as an independent projection-admission oracle.

```text
native AutoFDE planning semantics
        ↓
bounded PlanningGraph export
        ↓
mmdio PlanningGraph admission
        ↓
DFCM design-space enumeration
        ↓
┌───────────────────────┬────────────────────────┐
│ ADMITTED              │ REFUSED                │
│ Mermaid + receipt     │ typed refusal evidence │
└───────────────────────┴────────────────────────┘
```

For the five planning formalism families and eight Mermaid projection families, the exact-head cross-repository crown evaluates:

```text
5 × 8 = 40 candidate projection cells
```

Every cell must receive exactly one disposition. No candidate may disappear through a conditional branch without evidence.

## Why DFCM sits here

AutoFDE owns native planning semantics and bounded exploration. `mmdio` owns visual/document I/O. The DFCM seam asks a separate question for every possible projection:

> Does the admitted graph actually contain the semantics required to manufacture this view?

Examples:

- a PPDDL graph with probability-bearing edges may admit `value-flow`;
- a PDDL+ graph with time/duration evidence may admit `timeline` and `schedule`;
- a POWL graph without temporal evidence must refuse those projections rather than fabricate them;
- a graph without actor/target-actor evidence must refuse `interactions`.

The actual Mermaid generator must equal the DFCM admission set. Drift is a crown failure.

## Evidence law

For each planning subject:

```text
DFCM candidates = 8
receipts = admitted candidates
refusal artifacts = refused candidates
receipts + refusal artifacts = 8
```

Across the five-formalism AutoFDE crown:

```text
candidate cells = 40
admitted + refused = 40
```

The crown pins the exact proven `mmdio` DFCM contract commit and then passes every admitted Mermaid document through Mermaid 11.16.0.

## Authority

This remains a non-actuating construction boundary.

DFCM can:

- enumerate reversible projection alternatives;
- evaluate semantic preconditions;
- manufacture admitted documents;
- manufacture refusal evidence;
- bind results to exact planning digests.

DFCM cannot:

- run a consequential planner action;
- authorize production;
- mutate a GymAct world;
- bypass BRCE;
- treat a Mermaid edit as ambient execution authority.

The cross-repository claim ceiling is:

```text
NATIVE_PLANNING_SEMANTICS_TO_DFCM_MMDIO_PROJECTION_ONLY
```
