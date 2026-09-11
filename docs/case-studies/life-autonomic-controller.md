# Autonomic Life Planning Case Study

## Purpose

This case study treats a generic personal operating week as a bounded planning
world for AutoFDE Lab. It composes existing continuous-planning machinery rather
than adding another planner:

`observations -> explicit admission -> reversible candidate frontier -> exact reuse / local repair / continuation / fresh-plan routing -> deterministic planning evidence`

The subject is intentionally generic. It models four ordinary workstreams:

- preserve an income option;
- protect a time-bounded career opportunity;
- advance an education option;
- publish a household brief.

It does not encode private account data, credentials, medical information, or
real-world authority.

## Preserve / fence

The repository remains SELECT/CONSTRUCT only.

- A fact enters the planning context only when the case fixture marks that
  observation explicitly admitted.
- A missing or non-admitted fact is not converted into a negative fact.
- Three lawful candidate plans are preserved; the experiment does not claim a
  globally optimal winner.
- Candidate plan authority is `NONE`.
- The receipt is `PLANNING_EVIDENCE_ONLY`, never an execution receipt.
- No message, application, calendar event, purchase, deployment, or other
  consequential action is performed.

## Experiment

The executable case study constructs three candidate partial orders:

1. `balanced` — preserve parallel optionality before the household brief;
2. `income-protect` — preserve income continuity before other workstreams;
3. `career-window` — protect the time-bounded career window first.

The exact experiment then exercises four real `ContinuousPlanner` transitions:

1. **EXACT_REUSE** — the exact admitted balanced plan is reused.
2. **REPAIR** — closing only the career window changes the career node and its
   downstream household-brief node; unrelated nodes remain untouched.
3. **CONTINUE** — adding an irrelevant observation does not trigger replanning.
4. **FRESH_PLAN** — a different goal does not inherit a stale plan.

The expected local repair cone is exactly node paths `1` and `3`.

## Replay

Run:

```bash
PYTHONPATH=src python -m pytest -vv tests/agent/test_life_autonomic_case_study.py
PYTHONPATH=src python -m autofde_lab.agent.life_autonomic_case_study
```

The CLI emits canonical JSON with a SHA-256 planning-evidence identity. Repeating
the same admitted subject must reproduce the same observation digest, candidate
frontier keys, transition classifications, and receipt digest.

## Falsifiers

Reject the bounded standing if any of the following occurs:

- a non-admitted observation enters the planning context;
- the same subject produces a different receipt on replay;
- the candidate frontier collapses to fewer than three preserved alternatives;
- the career-window delta repairs unrelated income or education nodes;
- an irrelevant observation forces repair/replanning;
- a different goal reuses the stale weekly plan;
- any case-study plan gains `execute`, `grant`, `actuate`, authority-token, or
  external side-effect semantics.

## Standing

Publication alone is not execution evidence. The focused exact-head GitHub
workflow is the owning court for this case study. `ALIVE` is scoped only to the
exact head on which that court executes successfully.
