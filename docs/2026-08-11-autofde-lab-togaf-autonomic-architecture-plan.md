# AutoFDE-Lab — Complete TOGAF Autonomic Architecture Plan

## Context

This plan is the user's own, fully-specified design (verbatim below,
adopted as this session's plan). It reframes the 10-phase TOGAF demo built
this session as a **checkpoint** proving the mechanism (phase semantics
representable, executable, OCEL-recorded, independently conformance-
checked) — not the target architecture. The target is
`autofde-lab` as an **autonomous engineering laboratory**: observe → infer
→ construct candidates → explore alternatives → falsify → compare →
admit → emit manufacturing intent. Explicitly scoped to this repo only —
GymAct, wasm4pm, ggen/ggen-marketplace, QLever, and cloud infrastructure
are external capability contracts, never reimplemented here.

Real, already-built pieces from this session are preserved and extended,
not rewritten: `world_transformation_orchestrator.py`,
`fortune5_architecture_signatures.py`/`fortune5_architecture_metrics.py`,
`object_centric_conformance.py`, `togaf_loop_demo.py`, the standing/
admission law files, `world_transformation_scenarios.py`, and
`docs/2026-08-11-autonomic-loop-gap-ledger.md`.

## Execution approach for this session

Section 26 ("First Implementation Sequence") is the concrete, ordered
build list. Given its scale (14 real components), this session executes
it incrementally, committing after each real, tested unit — matching this
session's established discipline (Chicago-style tests, real regression
runs, honest `UNSUPPORTED`/`BLOCKED`/`UNKNOWN` typing for anything
depending on an external contract that doesn't exist yet, per
`.claude/rules/absence-is-not-evidence.md`). Sections 1–25 and 27 are the
target-architecture reference this sequence is building toward — cited
inline as each numbered step is implemented, not re-derived.

---

[The full design document follows verbatim, as supplied — sections 1
through 27 — governing every subsequent implementation step this session
takes under this plan.]

## 1. Preserve What Is Already Real

Do not rewrite the working pieces created this session.

Keep and build upon:

* `world_transformation_orchestrator.py`
* DSPy Fortune-5 architecture Signatures
* independently computed architecture metrics
* POWL execution
* OCEL production
* object-centric conformance
* TOGAF loop demonstration
* existing capability/standing/admission laws
* existing deterministic scenario generation
* existing gap ledger/autonomic-loop doctrine

The current ten-phase TOGAF loop is a **checkpoint**, not the target architecture.

Its purpose is to establish that TOGAF phase semantics can be represented, executed, recorded as OCEL, and independently checked.

Do not keep expanding that demo manually phase-by-phase.

## 2. AutoFDE-Lab's Core Product

The product of `autofde-lab` is not a TOGAF workflow engine.

It is an **autonomous engineering laboratory**.

Given: admitted ontology; enterprise observations; objectives; constraints;
authority/capability descriptions; process evidence; available external
computational capabilities — it should manufacture and test a large
portfolio of possible explanations, desired states, architectures,
migrations, and interventions.

Formally: `O* + G + C + K → candidate hypothesis space H → candidate
transformation space T → experiments E → falsification results F →
admitted candidate A`, where `O*` = admitted observations, `G` =
goals/objectives, `C` = constraints, `K` = admitted domain/process
knowledge.

**AutoFDE-Lab proposes and tests. It does not grant itself DO authority.**

## 3. TOGAF Is the First Full Experimental Domain

Treat TOGAF as the first Fortune-5-scale test of this laboratory
architecture. Do not encode TOGAF merely as Preliminary → A → B → C → D →
E → F → G → H. TOGAF is iterative and combinatorial. The experiment graph
must support requirement changes, alternative visions, multiple baseline
interpretations, multiple candidate target architectures, rejected
candidates, multiple migration strategies, governance failure, incomplete
evidence, revisiting prior phases, Phase H change triggers, Requirements
Management feedback into every phase, multiple possible technology
consequences evaluated through GymAct.

The key question is not "which TOGAF phase comes next" but "given the
observed enterprise, admitted objectives and constraints, what are all
materially different lawful hypotheses and transformations worth testing?"

## 4. Phase A Inside AutoFDE-Lab

DSPy Signatures and Modules do **not** constitute external truth. They
specify typed reasoning procedures. Phase-A inputs should conceptually be
admitted ontology/public-standard facts, admitted enterprise evidence,
observed process state, objectives/constraints. DSPy then performs typed
inference over those inputs.

`ontology/evidence = knowledge substrate`; `DSPy Signature = reasoning
contract`; `DSPy Module = candidate inference implementation`; `DSPy
Optimizer = search over inference implementations`; `independent metric =
falsifier`. Never `DSPy output = truth`.

The existing Fortune-5 architecture Signatures and metrics should become
components of a more general `ArchitectureInferenceProgram`.

## 5. Create an Explicit Observation Model

Build/consolidate one canonical admitted observation carrier,
`EnterpriseObservation`, containing references to evidence, not
duplicated world truth: ontology graph identity; source/provenance
identity; enterprise/world identity; current observations; OCEL evidence
references; discovered-process references; conformance findings; metrics;
objectives; constraints; capability inventory; authority envelopes;
evidence receipts; observation timestamp/version.

Do not copy external GymAct or wasm4pm state into a second unofficial
source of truth — references + digests + typed projections. This object is
`O*`, not merely `O`. `UNKNOWN` data remains `UNKNOWN` until admitted.

## 6. Introduce Process Inference as a First-Class Stage

Insert a distinct process-inference stage: `EnterpriseObservation →
ProcessEvidenceRequest → wasm4pm external computation → ProcessObservation`.

`ProcessObservation` may contain: discovered model reference; DFG;
object-centric relations; conformance deviations; alignments; performance
metrics; bottlenecks; drift indicators; predictions;
uncertainty/evidence standing; receipts for the computations.

AutoFDE-Lab defines the request/result contracts and consumes receipted
results — never implements wasm4pm algorithms itself. This establishes
`world observation ≠ process interpretation` and lets multiple process
interpretations coexist.

## 7. Generalize the Current Desired-State Pipeline

Refactor conceptually from `infer_desired_state → compute_delta →
select_transformation` toward `infer_desired_states → manufacture
candidate deltas → manufacture transformation portfolio → falsify
portfolio → admit surviving candidate`. Plural matters — combinatorial
maximalism requires preserving lawful alternatives; output should be a
portfolio, not a winner: `DesiredStateHypothesis[]`, each carrying exact
admitted evidence used, assumptions, objective coverage, constraint
interpretation, process interpretation reference, uncertainty, falsifiers,
provenance. Do not collapse the list until evidence justifies selection.

## 8. Build the Candidate Architecture Portfolio

`ArchitectureCandidate` — not merely an LLM response — a typed candidate
graph: target-state assertions; requirement satisfaction claims;
assumptions; dependencies; migration actions; required capabilities;
expected effects; expected risks; cost/resource bounds; authority needs;
verification criteria; rollback/recovery requirements; provenance;
generator/reasoner identities.

Candidates may come from deterministic rules; DSPy modules; planning
algorithms; constraint solvers; wasm4pm cognition breeds; OR algorithms;
prior cases; mixed compositions — all feed the same representation.

## 9. Create the Computational Portfolio Router

Determine which external computational operators are lawful for a
problem — never hardcode "run all N breeds." Derive applicable operator
classes from the admitted problem representation (hard constraints →
SAT/CDCL; state+operators+goals → STRIPS/GPS; hierarchical decomposition →
HTN; temporal event semantics → event calculus; precedents → CBR;
contradictions → TRIZ; uncertainty → probabilistic methods; OCEL/event
evidence → process discovery/conformance; resource optimization →
OR/optimization).

`OperatorApplicability` with statuses `ADMITTED | UNSUPPORTED | REFUSED |
UNKNOWN`. Absence of necessary semantics is `UNSUPPORTED`, never
permission to fabricate input.

## 10. Create the Experiment Portfolio

For each promising `ArchitectureCandidate`, manufacture an
`ExperimentIntent`: candidate identity; target GymAct world/profile;
initial-state/evidence identity; proposed action set; required
capabilities; expected postconditions; constraints; authority
requirements; verifier expectations; rollback expectations.

AutoFDE-Lab sends the intent outward; GymAct executes or refuses it;
AutoFDE-Lab receives `ExperimentReceipt` with observed consequence
evidence. Never equate "candidate says it works" with "GymAct observed it
work."

## 11. Falsification Must Be First-Class

A falsification engine around experiment receipts actively seeks: violated
constraints; failure states; counterexamples; process-conformance
degradation; security regressions; cost regressions; migration
infeasibility; authority failure; non-replayable evidence; contradiction
between predicted and observed effects.

A candidate survives because attempts to kill it failed under the
admitted test envelope, not because an LLM ranked it highly.
`Candidate × ExperimentReceipt[] → FalsificationResult`, standings:
`SURVIVES | FALSIFIED | PARTIAL | UNSUPPORTED | REFUSED | UNKNOWN`.

## 12. Treat wasm4pm Results as Experimental Evidence

Two consumption points: before experimentation (`OCEL → discovery/
conformance/prediction → process observation`) and after experimentation
(`GymAct consequence OCEL → discovery/conformance/prediction → consequence
interpretation`). Compare before-process state vs. predicted-process state
vs. after-process state — a substantially stronger falsifier than state
equality alone.

## 13. Phase H Becomes the Outer AutoFDE-Lab Loop

Phase H is the actual autonomic trigger: `new observation/OCEL → process
inference → conformance/drift analysis → trigger evaluation`. If the
admitted trigger fires, start a new architecture experiment cycle,
producing `ArchitectureChangeTrigger` (evidence; detected drift; affected
requirements; confidence/standing; trigger policy; prior architecture
identity), returning control to Requirements Management / Phase A
reasoning. No human prompt required.

## 14. Requirements Management Is the Persistent Constraint Kernel

Not one event in a ten-phase demo — persistent state consulted by every
computation. Every candidate is evaluated against the active requirements
graph. Every new observation may support, violate, obsolete, or reveal a
gap/contradiction in a requirement. New requirements inferred by a model
remain **proposals** until the configured admission policy accepts them.

## 15. Add Capability Admission

Do not assume every planner/reasoner/tool is valid merely because it
exists. Experimentally establish capability standing:
`operator × representation class × scenario family × verifier → capability
evidence`, classified `UNKNOWN | PARTIAL_ALIVE | ALIVE | UNSUPPORTED |
BLOCKED | typed REFUSED`. A capability is reusable only inside the
envelope actually demonstrated ("HTN planning ALIVE for state
representation X under constraints Y" — legitimate; "HTN works for
enterprise architecture" — not).

## 16. Build an Experiment Knowledge Graph

Accumulate all exploration results into a graph, not logs: relationships
among observations, requirements, hypotheses, process models, candidates,
operators, experiments, GymAct worlds, receipts, falsifiers, admitted
plans, generated artifacts, resulting consequences — enabling questions
like which candidate families repeatedly fail, which operators work for
which problem shapes, which requirements are most constraining, which
candidate is Pareto-dominant, which experiment would reduce uncertainty
most.

## 17. Make Experiment Selection Information-Theoretic

Select the next experiment by expected information gain, cost, authority,
reversibility, and risk — maximize `expected uncertainty reduction ×
reversibility × consequence value` divided by `cost × execution risk ×
time`. The scoring function may start simple; the architecture must
support replacing it.

## 18. Preserve SELECT / CONSTRUCT / DO

SELECT: choose what hypothesis/candidate/experiment is worth considering.
CONSTRUCT: construct a typed candidate or experiment intent. DO: not owned
here — a candidate may become an admitted `ActuationIntent`, but it stays
powerless until an external authority-bearing runtime accepts it. This
boundary stays mechanical.

## 19. ggen Boundary

Output a formal `AdmittedArchitecture`: canonical graph identity;
candidate identity; evidence DAG; requirements; constraints; expected
capabilities; generation profile; verification obligations. ggen consumes
it. AutoFDE-Lab does not manually generate the final implementation when a
canonical ggen projection exists. The returned generated artifact is
treated as another evidenced object requiring verification before
execution.

## 20. Do Not Build Public-Ontology Ingestion Here

This session's audit found ggen/ggen-marketplace currently lack external
ontology ingestion. Record it as a capability dependency:
`PUBLIC_ONTOLOGY_INGESTION = UNSUPPORTED`. Do not implement QLever,
federation, quarantine, or public RDF crawling here — define a
`KnowledgeGraphProvider` interface whose implementation may eventually come
from ggen/ggen-marketplace; operate against already-admitted local graphs
for now.

## 21. Do Not Reimplement wasm4pm Here

Do not port DFG discovery, conformance, optimization, SAT, planning
breeds, or predictive ML into AutoFDE-Lab. Define
`ProcessScienceProvider`/`ComputationalOperatorProvider` adapters/contracts
instead of duplicate implementations. Provider responses must carry
identity/evidence establishing exactly what was executed.

## 22. Do Not Reimplement GymAct Here

Do not add simulated world mutation merely to make Phase D green. Keep the
current Phase-D refusal until a real GymAct connector exists. The next
correct implementation is an external `WorldExperimentProvider` contract
(materialize a world; inspect capabilities; submit an experiment; receive
authority/refusal standing; retrieve observations/verifier results/
receipts/OCEL; teardown/replay). AutoFDE-Lab consumes, never owns, those
results.

## 23. Refactor the TOGAF Demo Into a Generated Experiment

Separate TOGAF semantics from handwritten Python sequencing. Create a
canonical internal TOGAF experiment graph and drive orchestration from it.
The test should prove: changing the admitted graph changes the experiment
topology without editing Python orchestration code — the minimum evidence
that TOGAF has become data rather than application logic.

## 24. Fortune-5 Scenario Families

Not one giant scenario — generate families covering business units,
regions, clouds, application portfolios, dependency graphs, regulatory
domains, SLOs, cost limits, residency rules, availability requirements,
migration deadlines, legacy constraints, vendor dependencies, security
policies, authority models, incident/drift histories. Every synthetic
dimension needs an explicit generation rule and seed — experimental
coverage, not fake realism.

## 25. Benchmark the Laboratory, Not Just the Planner

Measure: candidate-space coverage; falsification efficiency; experiment
information gain; regret (vs. best experimentally observed candidate);
process improvement; constraint preservation; replay (independent
recomputation from evidence); human baseline (how many alternatives a
conventional process could evaluate under the same evidence/time
envelope). The point: demonstrate a phase change from
architecture-by-meeting to architecture-by-experiment.

## 26. First Implementation Sequence

Implement inside `autofde-lab` in this order:

1. Introduce/normalize `EnterpriseObservation`.
2. Introduce `ProcessObservation` and an external `ProcessScienceProvider` contract.
3. Generalize `infer_desired_state` into plural `DesiredStateHypothesis` manufacture.
4. Add typed `ArchitectureCandidate`.
5. Add operator-applicability/admission representation.
6. Add `ExperimentIntent`.
7. Add external `WorldExperimentProvider` contract for GymAct.
8. Add `ExperimentReceipt`.
9. Add explicit `FalsificationResult`.
10. Add candidate portfolio comparison/admission.
11. Add `ArchitectureChangeTrigger` driven from new evidence.
12. Refactor the TOGAF demo to traverse this generalized model.
13. Preserve current OCEL/object-centric-conformance tests as regression witnesses.
14. Add a multi-candidate TOGAF experiment that proves at least two candidate architectures are actually falsified against independently observed consequences before one survives.

Do not touch another repository as part of this plan. Missing external
capabilities remain explicitly typed `UNSUPPORTED`, `BLOCKED`, or
`REFUSED`.

## 27. The AutoFDE-Lab Crown

The crown is not production deployment. It is: given admitted enterprise
evidence and constraints, can AutoFDE-Lab autonomously conduct a
reproducible engineering experiment that discovers the process,
manufactures many lawful candidate architectures, chooses high-information
experiments, tests candidates against an external consequence-bearing
world, falsifies bad candidates, admits a survivor, and emits a formal
manufacturing intent whose entire derivation can be replayed?

The crown test demonstrates: ingest admitted ontology/evidence references;
construct `EnterpriseObservation`; obtain process-science evidence through
the wasm4pm provider; infer multiple desired-state hypotheses; generate
multiple candidate architectures; derive a lawful computational/operator
portfolio; construct several GymAct experiment intents; receive actual
consequence receipts; run process/conformance analysis over resulting
OCEL; falsify multiple candidates; preserve uncertainty where evidence is
insufficient; admit exactly the survivor(s) justified by evidence; emit an
`AdmittedArchitecture` for ggen manufacture; generate an
OCEL/provenance/receipt graph covering the complete laboratory cycle;
replay that cycle without trusting the LLM that proposed any candidate.

GymAct supplies reality. wasm4pm supplies process/computational science.
ggen supplies manufacture. AutoFDE-Lab conducts the experiment.

## Verification (for this session's first real slice of section 26)

1. Chicago-style tests for each new typed component (steps 1–11), reusing
   existing real fixtures (`world_transformation_scenarios.py`,
   `object_centric_conformance.py`) wherever the shape fits, per section 1's
   "preserve what is already real."
2. `.venv/bin/python -m pytest tests/reasoning/ tests/powl/ tests/ocel/ -v`
   after each step — zero regressions, real pass counts reported.
3. Repo-wide mock grep after each new test file.
4. Every external-contract-dependent path (`ProcessScienceProvider`,
   `WorldExperimentProvider`, `KnowledgeGraphProvider`) returns a real,
   typed `UNSUPPORTED` today — asserted by test, not left implicit — since
   no real `wasm4pm`/`gymact`/ggen-ingestion connector exists to call.
