---
paths:
  - "vendor/gyms/**"
  - "src/autofde_lab/gymact/**"
  - "src/autofde_lab/reasoning/**"
  - "src/autofde_lab/sota/**"
  - "src/autofde_lab/powl/**"
---

# The autonomic loop — four boxed invariants, each traced to real code or named absent

Companion to `.claude/rules/gym-actuation-boundary.md`, which states the
code-import-level half of this boundary (never import `vendor/gyms/`,
`gymact` is the one real actuation surface). This file states the same
boundary as a loop with named stages, and — the discipline
`absence-is-not-evidence.md` requires generally, applied here — marks
which stages are real in this repo today versus aspirational, rather than
asserting all four uniformly.

## The loop

```text
gymact: observe -> autofde-lab: infer/plan -> candidate
     -> gymact: consequence -> verify -> admit
     -> ggen: manufacture -> execute -> verify
```

## Four boxed invariants

1. **`gymact` does not plan.** `gymact`'s real `Environment`/
   `EnvironmentProvider` protocol (`~/gymact/src/gymact/providers.py`) is
   `materialize` -> `observe`/`actuate`/`verify`/`checkpoint`/`restore`/
   `teardown` — an execution and consequence surface, not a decision
   surface. No `gymact.gyms.*` provider chooses what to do next; every
   real trial this repo has run supplies the action from
   `src/autofde_lab/reasoning/gymact_diagnosis_driver.py`'s side, per
   `gym-actuation-boundary.md`'s own "where the real diagnosis/actuation
   path lives" section.
2. **`autofde-lab` does not own world truth.** This repo's planners
   (`src/autofde_lab/reasoning/planner_federation.py`,
   `sre_troubleshooting_pipeline.py`) and ensembles
   (`breed_ensemble.py`) produce *candidates* — `PartialOrder`/
   `ChoiceGraph` objects admitted via `autofde_lab.powl.validate.validate_model`
   — never a claim about what the observed world actually contains beyond
   what `gymact.observe()` (or, for reference-only design grounding, a
   vendored gym's *source*, never its live state) supplied. `CLAUDE.md`'s
   own law states this plainly: **"It computes candidate plans. It does
   not actuate."**
3. **`ggen` does not decide.** Every `ggen.toml` generation rule this
   repo has (constitution, `k8s-fault-universes`,
   `world-transformation-scenarios`) is `mode = "Create"`, deterministic,
   and re-derivable from its source `ontology/*.ttl` — confirmed
   independently this session by `scripts/verify_ggen_generation.py`
   recomputing every generated count from the ontology directly, never
   trusting `ggen`'s own self-report. `ggen` manufactures what was already
   admitted; it never selects among candidates itself.
4. **Governed production execution does not exist as a separate system on
   this machine, as of this session.** The doctrine names a fourth stage
   ("`autofde` executes") as distinct from `gymact`'s own trial-execution
   surface. **Checked directly this session: no `~/autofde` repository
   exists** (`find / -iname autofde -type d` finds only `autofde-lab`
   itself). The two real execution-adjacent surfaces that *do* exist here
   are (a) `gymact.actuate()`, real and already governed by invariant 1
   above, scoped to gym trials; and (b) this repo's own OpenClaw bridge
   (`src/autofde_lab/openclaw_bridge.py`/`openclaw_runtime.py`,
   `.claude/rules/actuation-boundary.md`), a **different, unrelated
   subsystem** for actuating this repo's own domains/solvers — not a
   governed-production-execution repo, and its own rule closes with the
   same law: "A planner result is a candidate, not an actuation." Do not
   conflate either of these with the doctrine's fourth stage; that stage
   is `UNKNOWN`/not-yet-built, not silently satisfied by an adjacent
   system. See `docs/2026-08-11-autonomic-loop-gap-ledger.md` for the full,
   per-stage standing.

## See also

- `.claude/rules/gym-actuation-boundary.md` — the code-import-level
  prohibition this file's loop framing sits on top of.
- `.claude/rules/actuation-boundary.md` — the OpenClaw bridge's own,
  separate boundary; explicitly not the same system as invariant 4 above.
- `docs/2026-08-11-autonomic-loop-gap-ledger.md` — real, evidence-backed
  standing per loop stage.
- `.claude/rules/absence-is-not-evidence.md` — the general law this file's
  "named absent, not assumed real" discipline for invariant 4 instantiates.
