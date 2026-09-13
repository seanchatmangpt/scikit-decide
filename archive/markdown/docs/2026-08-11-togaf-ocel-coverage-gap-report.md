# TOGAF ADM OCEL Coverage Gap Report — 2026-08-11

4 parallel validation agents each researched one TOGAF phase-group's real,
officially-documented sub-steps (WebSearch, cited sources per agent) and
compared them against `togaf_loop_demo.py`'s iteration-1 single-atom-per-
phase representation. This is the synthesized findings record.

## Agent 1 — Preliminary, Requirements Management, Phase A

Sources: Open Group TOGAF 9.2 official docs (Preliminary Phase, Req Mgmt
chap13/chap17, Phase A chap03/chap07).

High-priority real fixes identified and **implemented in iteration 2**:
- `preliminary_identify_architecture_principles` — real `.claude/rules/*.md`
  glob (13 real principle files) replacing a single-file boolean check.
- `requirements_document_specification` — real plural `DesiredStateHypothesis`
  via `infer_desired_state_hypotheses` replacing a flat count-dict.
- `phase_a_confirm_constraints` — real `metadata.constraints` read at the
  TOGAF-correct phase (previously only read in Phase B).
- `phase_a_architecture_vision_artifact` — real `ArchitectureCandidate`
  construction from `DesiredStateEnvelope.targets`.

Remaining real gaps, no mechanism exists — recorded in
`UNSUPPORTED_TOGAF_SUBSTEPS`: enterprise-scope/capability definition,
governance framework/EA team, framework tailoring, requirements
baselining/impact assessment, stakeholder identification, business-
capability-readiness assessment, Statement of Architecture Work approval.

## Agent 2 — Phase B, Phase C

Sources: TOGAF 9.2 Phase B/C 9-step template (Visual Paradigm, cross-
verified secondary sources reproducing the official standard's step
titles).

High-priority real fix implemented: `phase_b_gap_analysis` — real
`compute_delta` reuse (previously computed only inside the Phase E atom),
attributed to Phase B where TOGAF documents gap analysis as a B-phase step.

Remaining real gaps, no mechanism exists: reference-model/viewpoint/tool
selection, cross-landscape impact resolution, formal stakeholder review,
Architecture Definition Document authoring (both B and C).

## Agent 3 — Phase D, E, F

Sources: TOGAF 9.1/9.2 Phase D/E/F step documentation (QualiWare,
cross-referenced).

**Strongest finding**: `laboratory.py`'s `ArchitectureCandidate`/
`ExperimentIntent`/`FalsificationResult`/`falsify_candidate` machinery was
real, typed, and already built — but completely unwired into
`togaf_loop_demo.py`. High-priority real fixes implemented:
- `phase_d_delegated_to_gymact_boundary_refusal` — now enumerates the real
  9 documented TOGAF 9.2 §12.4 decision points being refused, not a bare
  boolean.
- `phase_e_consolidate_gap_analysis` — exposes the full per-item
  `DeltaItem` list (kind + violated-or-UNKNOWN), previously computed but
  discarded down to aggregate ints.
- `phase_e_business_constraints` — re-surfaces `metadata.constraints` at
  the TOGAF-correct phase.
- `phase_f_prioritize_via_falsification` — wires `ArchitectureCandidate`
  through the real `falsify_candidate`, using the real, honest
  `UnsupportedWorldExperimentProvider` (no gymact connector exists yet) —
  produces a real, correctly-typed `UNSUPPORTED` standing, never a
  fabricated verdict.
- `phase_f_powl_migration_plan` — now includes the real phase sequence and
  selected transformation label, not only graph node/edge counts.

Remaining real gaps: transition-architecture staging, business-value
assignment (real typed `cost_bound` slot exists, unpopulated), resource/
timing estimation.

## Agent 4 — Phase G, H

Sources: TOGAF 9.2 Phase G/H step documentation (Visual Paradigm,
referencing official Open Group ADM chapters).

Key finding: `check_object_centric_conformance`'s order-fitness signal is
real evidence but **not sufficient** to claim TOGAF G4 ("Perform
Architecture Compliance Reviews") is implemented — it measures activity
order, not conformance to an Architecture Contract (which this repo has no
object for). Iteration 2 makes this explicit:
`phase_g_admission_and_conformance` now records
`"compliance_review_scope": "PARTIAL -- order-fitness only, no
Architecture Contract object exists"` rather than silently implying full
coverage. Similarly, `phase_h_gap_ledger_reference` now records the real
`unsupported_togaf_substep_count`, making the scope of Phase H's real
coverage (a document-existence check) explicit rather than implied-complete.

Remaining real gaps: deployment-resource/skill coverage (a real partial
mechanism exists — `fabric/coverage.py` — not yet wired), Architecture
Contract object, post-implementation review, value realization, risk
management, change-request objects, governance-process/board record,
change-activation object. Correctly-excluded-by-design: "Implement
Business and IT Operations" (G5) — actuation is out of scope for this
repo per `CLAUDE.md`'s own law.

## Result

`PHASE_SEQUENCE` grew from 10 to 15 real, independently-computed atoms.
`UNSUPPORTED_TOGAF_SUBSTEPS` records 26 real, documented TOGAF sub-steps
this repo genuinely has no mechanism for — named explicitly, per
`.claude/rules/absence-is-not-evidence.md`, rather than silently omitted.
Re-run `scripts/run_togaf_loop_demo.py`: 15 real events, `all_conform:
True`, `overall_fitness: 1.0`.

## See also

- `src/autofde_lab/reasoning/togaf_loop_demo.py` — the implementation.
- `docs/2026-08-11-autofde-lab-togaf-autonomic-architecture-plan.md` — the
  larger design this iteration operates inside.
- `docs/2026-08-11-autonomic-loop-gap-ledger.md` — the broader autonomic-
  loop standing ledger this file is scoped narrower than.
