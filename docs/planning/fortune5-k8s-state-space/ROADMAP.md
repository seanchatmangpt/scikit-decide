# Fortune-500-scale k8s state-space modeling — candidate plan

Last updated: 2026-08-10.

## Standing

**This is a candidate plan, not completed work or a standing claim.** Per
`CLAUDE.md`: "It computes candidate plans. It does not actuate." None of the
eight actions below have been executed — this document only records the real,
solved task order a registered planner (`Astar`) produced for the real
dependency graph in `domain.pddl`/`problem.pddl` in this directory.

## Why this exists

A 2026-08-10 review of the actual current source of `~/ggen-marketplace` and
`~/wasm4pm` found that neither repo can currently represent or reason over a
Fortune-500/Global-2000-scale Kubernetes deployment's state space. Four
concrete gaps were named:

1. No typed, hierarchical k8s object schema (CRD-aware) exists in either repo.
2. `ggen-marketplace`'s `dspy-pack` gate-caps field types to `str`/`int`/`float`/`bool`
   and explicitly excludes nested `PydanticModel` composition
   (`packs/dspy-pack/gates/010_admission.rq:47-51` — citation corrected 2026-08-11; the
   gate file grew since this was originally cited, and the restriction itself still
   holds, only the pinpoint line range had drifted).
3. No schema-to-ontology generator exists in the 94-pack marketplace.
4. `wasm4pm`'s Hearsay-II blackboard (`crates/wasm4pm-cognition/src/breeds/hearsay.rs`)
   is the structurally right *pattern* for multi-hypothesis reasoning over
   partial cluster observations — this session separately confirmed its core
   selection/STOP logic is genuinely correct against the 1980 source paper —
   but its concrete artifacts (a flat `BTreeMap<String,f32>`, an O(rules)
   linear KS-trigger scan, a firing-cap formula sized for a 13-rule fixture)
   are toy-scale, and `wasm4pm-dspy`'s own orchestrator explicitly declined to
   build a generic state encoder ("there is no lossless shared representation").

## The solved plan

Modeled as a real STRIPS domain (`domain.pddl`), solved by a real, registered
`Astar` solver (`tests/planning/test_fortune5_k8s_state_space_plan_chicago.py`,
mirroring `tests/domains/python/test_pddl_domain.py`'s own
`test_astar_solve_blocks` pattern) — same solver, same rollout shape, applied
to this problem instead of the toy `blocks` domain.

| Order | Action | Real target repo | What it produces |
|---|---|---|---|
| 1 | `loosen-dspy-pack-nesting-gate` | `ggen-marketplace` | nested Pydantic support |
| 2 | `build-typed-k8s-object-schema` | (shared/new) | typed k8s ontology |
| 3 | `index-hearsay-blackboard` | `wasm4pm` | indexed blackboard |
| 4 | `build-schema-to-ontology-generator` | `ggen-marketplace` | schema→ontology generator |
| 5 | `author-k8s-pack` | `ggen-marketplace` | a real `k8s-pack` |
| 6 | `rescale-firing-budget` | `wasm4pm` | scalable blackboard |
| 7 | `build-k8s-state-encoder` | `wasm4pm-dspy` | k8s state encoder |
| 8 | `integrate-with-autofde-cognition` | **autofde-lab** | wires `SreTroubleshootingPipeline`'s evidence inputs to the real encoder |

Every dependency the domain declares (e.g. `author-k8s-pack` requires both the
generator and the loosened gate; `integrate-with-autofde-cognition` requires
both the encoder and the pack) is independently re-checked against this exact
solved order in the test file — not merely trusted from the solver's own
success signal.

## What this repo can and cannot do next

Steps 1, 3, 4, 5, 6, 7 are real engineering work in **separate repos**
(`ggen-marketplace`, `wasm4pm`) that autofde-lab cannot execute directly, per
`.claude/rules/gym-actuation-boundary.md`'s governing principle applied to
sibling repos generally: this repo computes candidate plans, it does not
modify other repositories. Step 2 (a shared typed k8s ontology) is a design
decision about where it should live — plausibly a new, small, standalone
artifact rather than owned by any one of the three repos.

Step 8 is the one action genuinely in-scope for autofde-lab alone, and only
once steps 5 and 7 exist upstream.

## Machine-readable projection

`plan.powl.ttl` in this directory is a real POWL2 projection of this same
solved plan (via `autofde_lab.fabric.powl.project_plan_to_powl`, the same
projector this repo uses elsewhere) — a document, not an execution, per
`CLAUDE.md` rule 2 ("Projection is not execution").

## Sources

- `docs/planning/fortune5-k8s-state-space/domain.pddl` / `problem.pddl` — the real PDDL.
- `tests/planning/test_fortune5_k8s_state_space_plan_chicago.py` — the real,
  passing Chicago-style solve + dependency-order verification.
- This session's two review passes of `~/ggen-marketplace` and `~/wasm4pm`
  (2026-08-10) — the source of every gap named above.
