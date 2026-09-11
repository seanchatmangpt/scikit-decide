# Explanation: Why an Autonomic Life Planning Case Study

Continuous planning in AutoFDE Lab needed a worked example that exercises real
admission, reuse, repair, and refusal semantics under load. This document explains
the reasoning behind `src/autofde_lab/agent/life_autonomic_case_study.py`, not how
to run it — see
[`docs/case-studies/life-autonomic-controller.md`](case-studies/life-autonomic-controller.md)
for the replay commands and falsifiers.

## 1. Why "life as a planning world" at all

This is not a new direction for the repo. Branch names already in this repo's
history — `plan/life-20260827-dfcm`, `tps/daily-production-planning`,
`agent/postagi-k10-xai-hyperdimensional` — show the planning machinery has
repeatedly been pointed at "an ordinary week" as a bounded planning world, as a
recurring idea rather than a one-off experiment. What none of those branches did
was land an executable, tested instance of the idea. `life_autonomic_case_study.py`
is that first instance: it does not introduce a new concept, it closes the loop on
one the repo had already tried several times, with `tests/agent/test_life_autonomic_case_study.py`
(3 passed, verified this session — see the pytest command in
[`docs/case-studies/life-autonomic-controller.md`](case-studies/life-autonomic-controller.md))
as the evidence that distinguishes it from its predecessors.

## 2. Why the subject is deliberately generic

`GOAL = "stabilize-week"` decomposes into four abstract workstreams — preserve an
income option, protect a career window, advance an education option, publish a
household brief — not the user's actual calendar, inbox, or task list. This is a
constraint, not a limitation of scope.

The top-level `CLAUDE.md`'s root law is: *"It computes candidate plans. It does not
actuate."* A case study that ingested real PII, a real calendar feed, or a real
inbox would put actuation-shaped material inside a SELECT/CONSTRUCT-only
demonstration, and the boundary between "this is a planning artifact" and "this is
personal operational data" would blur exactly where the repo most needs it sharp.
`admit_life_observations` only ever sees synthetic `LifeObservation` fact strings
(`"income-option-open"`, `"career-window-open"`, …) with a `source_ref` that names a
fixture, never a real document, message, or calendar entry.

This also connects to a house rule that predates this case study: docs never create
standing. A case study is itself a kind of documentation-by-demonstration, and if it
had claimed to plan over live personal data, the claim of harmlessness would have
had to live in prose next to the code rather than in the code's own admitted inputs.
Keeping the subject synthetic means the non-actuation claim is structural, not
asserted.

## 3. Why a frontier of three plans, not one winner

`build_candidate_frontier()` returns three `PlanArtifact` instances — `balanced`,
`income-protect`, `career-window` — over the same four activities, each a
differently-ordered `PartialOrder`. `run_case_study()` never ranks them and never
discards two in favor of "the best one." All three are remembered in the
`PlanCache` and their `frontier_keys` all appear in the receipt.

This is a direct instance of the combinatorial-maximalism framing in
`~/.claude/rules/local-dfcm-manufacturing-engine.md`: "maximize CONSTRUCT
concurrency; serialize only consequential shared-state transitions." Three lawful,
reversible candidate plans is combinatorial width preserved; picking one "winning"
ordering this early would be exactly the kind of premature serialization that rule
warns against when there is no consequential shared-state transition (an actuation,
a commitment) forcing a choice yet.

It is also the same discipline `.claude/rules/absence-is-not-evidence.md` states for
observations, applied here to plans instead of facts: that file's core claim is "not
observed to be inapplicable ≠ known applicable" — uncertainty must survive until
evidence discharges it, never get coerced into a convenient value. A frontier
collapsed to one plan asserts that plan is uniquely correct without evidence that
the other two are worse. Preserving three candidates instead of selecting one is the
planning-time analog of refusing to collapse `UNKNOWN` into a convenient `True`.

## 4. Why these four transitions, and no fewer

`ContinuousPlanner.decide` classifies every context change into one of
`PlanDisposition.EXACT_REUSE`, `REPAIR`, `CONTINUE`, or `FRESH_PLAN` (a `CACHED_REUSE`
branch also exists in the kernel but the case study does not exercise it). The case
study exercises all four reachable dispositions in sequence, and each exists to rule
out one specific failure mode:

- **EXACT_REUSE** — reusing the exact admitted `balanced` plan via `exact_key`
  proves that unchanged state does not trigger a fresh plan. Replanning on no change
  would be pure wasted cost.
- **REPAIR** — closing only `career-window-open` produces
  `repair_affected_paths == ("1", "3")`. This is the concrete proof, not a claim in
  prose, that `affected_paths` computes a delta-local repair cone: node `1`
  (`prepare-career-window`) is the changed dependency, node `3`
  (`publish-household-brief`) is its sole downstream successor per
  `dependency_keys`/`downstream`, and nodes `0` and `2` (income, education) are
  untouched. A repair that invalidated the whole plan on one closed fact would
  defeat the purpose of tracking a dependency graph at all.
- **CONTINUE** — adding the irrelevant fact `weather-noted` does not trigger repair
  or replanning. This proves the system does not "flinch" on noise: an admitted
  delta that touches no dependency key of the active plan must be classified
  `CONTINUE`, not `REPAIR`.
- **FRESH_PLAN** — switching to `goal="different-weekly-goal"` with no
  `active_plan` and no matching cached candidate returns `FRESH_PLAN` rather than
  silently reusing the `stabilize-week` plan. This is the transition with real
  safety content: reusing a plan built for one goal against a different goal is
  exactly the confident-wrong action `absence-is-not-evidence.md` warns against in
  its own context (the `force_latch` example) — an unproven permission admitted as
  proven. Here the analogous failure would be a plan admitted for the wrong goal.

Together these four are not an arbitrary sample of the state space; they are the
minimal set that rules out the two opposite failure modes (replanning too eagerly on
noise, and reusing a plan too eagerly across a goal change) plus the two boundary
cases in between (no change at all, and a change requiring only local repair).

## 5. Why the receipt carries `authority`, `do_authority`, and `evidence_kind` as fields

Every `LifeCaseStudyReceipt` sets `authority="NONE"`, `do_authority=False`, and
`evidence_kind="PLANNING_EVIDENCE_ONLY"` as literal fields returned from
`payload()` and hashed into `receipt_sha256`. `test_frontier_is_candidate_only_and_non_actuating`
asserts on exactly these three fields, plus that no candidate plan carries an
`execute`, `grant`, or `actuate` attribute.

This is the same point `.claude/rules/no-dual-bookkeeping.md` makes about standing
in general, applied to a single receipt: a claim of non-actuation is worthless
unless it is carried in the evidence object itself, not merely asserted in
surrounding prose. A docstring saying "this never actuates" next to a receipt object
that happened not to carry an `authority` field would be exactly the kind of
derived-summary claim that file warns can drift from the artifacts it describes. By
making `authority`, `do_authority`, and `evidence_kind` part of the hashed payload,
the non-actuation claim is bound into the same content-addressed digest as
everything else the receipt asserts — it cannot silently drift because there is
nothing else for it to drift from.

This is the concrete, receipt-level instance of the top-level `CLAUDE.md`'s root
law: "It computes candidate plans. It does not actuate." The law is stated once at
the repo root; this case study is one place where the law is also load-bearing data,
not only prose.

## 6. What this case study is not

Stated precisely, because the gap matters:

- **It is not a demonstration of autonomic event-driven scheduling.** The
  Observe → Encode → Bind → Compress → Predict → Select → Actuate → Receipt loop
  referenced elsewhere in this repo's autonomic-control vocabulary is not
  implemented here. `run_case_study()` calls `ContinuousPlanner.decide` four times
  against hand-constructed `PlanningContext` objects built directly in the function
  body — there is no Observe stage pulling from a live source, no Encode/Bind/Compress
  stage, and no Predict stage. Only the Select-time transition classification
  (`EXACT_REUSE`/`REPAIR`/`CONTINUE`/`FRESH_PLAN`) is exercised.
- **It is not a claim that this could safely run against a real personal calendar
  or inbox today.** There is no admitted authority envelope anywhere in this
  module — `required_authority_classes=()` on every plan, `authority="NONE"` on
  every receipt — and no receipt/replay chain wired to a real actuator. Per
  `.claude/rules/gym-actuation-boundary.md`'s separation of concerns, any real
  actuation surface in this portfolio runs through a dedicated actuation boundary,
  never through this module or through this repo directly. Binding real observation
  sources without also building that authority and actuation path would be an
  admission-boundary violation, not an extension of this case study.

## 7. Where this could go next (speculative — none of this is built)

The following are directions the existing structure suggests, not planned or
in-progress work:

- **Binding real observation sources through an explicit admission boundary.**
  `LifeObservation` already separates `admitted` from non-admitted facts
  (`test_unknown_observation_is_not_silently_admitted` proves a `False`-admitted
  fact never enters `PlanningContext.facts`). Extending the `source_ref` field to
  point at a real calendar delta or email thread would require a real admission
  gate deciding what counts as `admitted=True` — not built, and that gate is the
  hard part, not the wiring.
- **A fourth ordering over a genuinely different subject.** `_model()` currently
  raises `ValueError` on any ordering string outside `balanced`/`income-protect`/
  `career-window`. Adding a fourth candidate is mechanically straightforward inside
  the existing `_plan`/`_model` shape, but would still need its own falsifier (per
  the existing falsifiers list) before it could be trusted the way the current
  three are.
- **Wiring this into an actual event-driven Observe loop.** This would mean the
  Select-time classification demonstrated here becomes one stage inside a larger
  Observe → … → Actuate → Receipt pipeline elsewhere in the portfolio. That pipeline
  does not exist yet for this case study's subject, and building it is a materially
  different and larger undertaking than what this module does — connecting this
  case study to it is future work, not an extension of the current scope.

## See also

- [`docs/case-studies/life-autonomic-controller.md`](case-studies/life-autonomic-controller.md) —
  the how-to-shaped companion doc: replay commands, exact falsifiers, and standing.
- `src/autofde_lab/agent/continuous_planning.py` — the real kernel this case study
  composes rather than reimplements.
- `.claude/rules/absence-is-not-evidence.md`, `.claude/rules/no-dual-bookkeeping.md` —
  the admission and evidence-locality laws this case study's design follows.
- `.claude/rules/gym-actuation-boundary.md` — the actuation-boundary separation
  referenced in §6.
