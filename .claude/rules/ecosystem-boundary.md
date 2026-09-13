---
paths:
  - "src/autofde_lab/fabric/**"
  - "src/autofde_lab/openclaw_*.py"
  - "tests/ecosystem/**"
  - "ontology/**"
  - "docs/ecosystem-standing.md"
---

# Ecosystem boundary — this repo is the search graph, nothing more

The portfolio divides labour so that no component infers a spec, generates the
implementation, evaluates it, *and* certifies itself — that circularity is
self-attestation, and the separation exists to prevent it. Verified in source
2026-08-06 across `~/mfw`, `~/ggen`, `~/ggen-create`, `~/ggen-legacy`, `~/bcinr`:

```
ggen-create   exemplar → candidate authority   (reverse compiler: 0 lines today)
ggen          admitted authority → artifacts + BLAKE3 receipt   (works)
autofde-lab   candidate-plan computation       (THIS REPO — search graph only)
bcinr-powl    POWL scheduling / tick loop      (works, but SYMBOLIC — no world effect)
mfw           admission, broker, receipts, replay   (actuates, but has no plan driver)
ggen-legacy   independent verification, replay, sunset
```

**What this repo may claim.** It computes candidate plans and projects them into
POWL. That is it. A planner selects; the broker authorizes; the executor
performs; the verifier evaluates. Do not attach receipt, admission, or actuation
semantics to anything here — `tests/ecosystem/` contains assertions that fail if
someone does, deliberately, because that boundary erodes quietly.

**Projection is not execution.** `fabric/powl.py` writes `plan.powl.ttl`. That
manufactures a document; it does not run a workflow. An earlier pass in this
repo let the projector stand in for an executor and had to be retracted — see
`docs/ecosystem-standing.md`. As of 2026-08-06 **no component executes a POWL
plan end to end**: bcinr has the driver but no actuation, mfw has actuation but
no driver, and three POWL representations (mfw Turtle, runtime JSON, bcinr
`Pddl8Tape`) have zero converters between them.

**Two engineering rules that follow.**

1. `python -m autofde_lab.fabric.pddl_engine <domain> <problem> <plan>` satisfies
   `~/mfw`'s existing `classical` engine contract (`mfw-planner/src/config.rs`).
   Its `--help` banner must keep starting with `usage:` — that string is pinned
   as `pddl:versionWitnessPrefix` in a `PlannerProfile`, so changing it silently
   invalidates admission.
2. The engine **refuses** `:derived-predicates`, `:constraints` and
   `:preferences`. The C++ backend parses all three and implements none (`grep
   -rn "derived" cpp/src/hub/domain/pddl/semantics/` → zero hits), so planning
   would return a confident, plausible, *wrong* plan with no error. A wrong plan
   that can be admitted downstream is strictly worse than a refusal. Never
   "fix" this by removing the gate.

**Capability claims must be ontology-backed.** `ontology/autofde-lab-capabilities.ttl`
is generated from entry points + a live import probe + `get_domain_requirements()`
MRO derivation — regenerate it with `python -m autofde_lab.fabric.ontology
ontology/autofde-lab-capabilities.ttl`, never hand-edit. `tests/ecosystem/` fails if
it drifts from the registry. This is an epistemic control, not documentation: a
false ecosystem claim was made this session ("no POWL executor exists") from a
search that had never looked at `~/bcinr`, which contains one. Any conclusion
drawn from "whichever repos got inspected" is unsound by construction.

Note `match_solvers(..., ranked=True)` accepts the flag and ignores it
(`utils.py:126`, `# TODO: implement ranking heuristic`) — so any claim that one
capability dominates another must be *measured*, not delegated.

## See also

- `CLAUDE.md` — the index and routing table that points here.
- `.claude/rules/standing-law.md` — the status vocabulary every claim uses.
- `docs/ecosystem-standing.md` — the evidence and repair plans behind every claim in this file.
