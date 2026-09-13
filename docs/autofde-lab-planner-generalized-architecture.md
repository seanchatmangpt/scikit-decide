# autofde_lab_planner: generalized architecture (target, not yet built)

**Status: design document, `UNKNOWN`/not-yet-alive per this repo's standing law.** None of the
containers/components below exist as code. This documents the target this session settled on
after abandoning a different, real, tested, but architecturally wrong direction — recorded here
so the reasoning isn't silently lost, not so the diagrams get mistaken for a status report.

## What was abandoned, and why

`src/autofde_lab_planner/{models,engine}.py` (as of commit `72c8dfa`, still on disk, still
passing its own tests) implements a **flat enumeration**: one dataclass, one `detect_X()`
function, one `decide_X()` function, and one wiring block per SREGym fault type, growing by one
of each every time a new fault mechanism gets built. By the last commit on this branch that's 14
mechanisms and a `run_diagnosis()` signature with 14 separate JSON-slice parameters
(`pvcs_json`, `resourcequotas_json`, `limitranges_json`, `service_accounts_json`, ...).

This is real, working code — 100+ real Chicago-style tests pass against it. It is also exactly
the failure mode named earlier in this session's ERRC discussion: **"ELIMINATE: Static Signature
Matching."** Each detector generalizes *within* its own narrow fault type (none of them hardcode
a benchmark app name — confirmed by grep before this document was written), but the
*architecture* does not generalize at all: it is capped by however many mechanisms get
hand-built, one at a time, forever chasing SREGym's ~60 injector methods without ever producing
a system that handles a fault type nobody has written a detector for yet.

**Decision: stop extending this pattern.** The already-merged commits stay on disk (real, tested,
not reverted per this repo's fix-forward git discipline) but are not the path forward. The four
diagrams in `docs/c4/autofde_lab_planner_*.mmd` describe what should replace it.

## The four diagrams

- `autofde_lab_planner_context.mmd` — the system in its environment (SREGym harness, the real
  cluster, Groq, the OCEL store).
- `autofde_lab_planner_container.mmd` — the major internal pieces: a Cluster State Fetcher that
  reads *any* object kind (not a fixed parameter list), a Generalized Structural Anomaly Scanner
  (one uniform diff pass, replacing the 14-function enumeration), a Symptom Signature Builder,
  the Case Library (already real and tested, `src/autofde_lab/case_library/`, though its
  abstraction layer has one confirmed real defect — see below), a DSPy Reasoning Fallback, a
  Remediation Dispatcher, and OCEL Telemetry.
- `autofde_lab_planner_component.mmd` — inside the scanner: an `ObjectKindAnalyzer` registry
  (one entry per Kubernetes *kind*, not per *fault type* — adding a new kind is O(1), never
  re-derived per injector method), a baseline/expected-shape model derived from each object's
  own spec (never a hardcoded app name), a uniform structural diff engine, and a fault-class
  taxonomy mapper that classifies an anomaly or honestly leaves it `UNCLASSIFIED`.
- `autofde_lab_planner_dynamic.mmd` — one full trial: fetch → scan → build symptom signature →
  check the case library → (hit: rebind a generalized template to this trial's real names) or
  (miss: grounded DSPy/Groq reasoning) → remediate → record OCEL telemetry → on a **confirmed**
  success, abstract and retain a new case.

## What's real right now, separate from this design

- **Case library** (`src/autofde_lab/case_library/`): real, tested, 12/12 passing. Its
  abstraction-on-write layer (`case_library/abstraction.py`, a different branch,
  `feat/case-library-abstraction`) has a confirmed real defect — service names given in the
  space-separated form (`"service billing-api"`, no slash) leak unabstracted into the stored
  template, found by adversarial testing this session. Not fixed yet.
- **DSPy + Groq reasoning path**: real, live-verified this session (judge pre-flight passes,
  real diagnosis text produced against a real cluster). Its own driver rewrite
  (`feat/autofde-lab-dspy-groq-only-structured-checklist`, in the `sregym` submodule) removed the
  local-model fallback and added a structured checklist + real fault taxonomy, verified at
  import/static level only — **never run against a live trial**.
- **OCEL 2.0 telemetry**: real, live-verified, real events captured during a real trial this
  session.
- **The generalized scanner itself**: does not exist. This document and its diagrams are the
  plan, not the artifact.

## See also

- `.claude/rules/standing-law.md` — the status vocabulary this document's own status line uses.
- `docs/c4/` — sibling C4 diagrams for the SOTA Lab/GymAct/ggen subsystems (different naming
  convention there, numbered `NN_*.mmd`; this set is named `autofde_lab_planner_*.mmd` to avoid
  colliding with that catalog's own sequence).
