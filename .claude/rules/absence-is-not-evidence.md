# Absence of negative evidence is not positive evidence

Loads unconditionally. This is an **admission** law, not a planning heuristic:
it governs what may enter O* from O, and every learned-model surface in this
repo is bound by it.

## The rule

> Not observed to be inapplicable **≠** known applicable.

An experiment that never produced contrary evidence has not established a
fact. Coercing that gap into the value most convenient to a downstream
consumer hands the consumer a certainty the experiment never earned.

## The lattice that must survive every projection

For applicability:

```text
KNOWN_APPLICABLE
KNOWN_INAPPLICABLE
UNKNOWN
```

For effects:

```text
OBSERVED_EFFECT
OBSERVED_NO_EFFECT
CONDITIONAL_OR_CONTEXTUAL_EFFECT
UNKNOWN_EFFECT
```

`UNKNOWN` survives every projection until evidence discharges it. When a
target representation cannot carry an uncertainty that matters to soundness,
the projection returns:

```text
UNREPRESENTABLE:<typed_reason>
```

It never erases the uncertainty to fit the representation.

## The specific conflations, each of which really happened here

| Coerced | Into | Where it bit |
|---|---|---|
| absence of refusal evidence | proven applicability | `force_latch` learned repeatable; jams the rack forever |
| single observed effect | proven repeatable effect | `burn_catalyst` planned twice; second call refused |
| single observed delta | proven monotonic effect | `toggle_switch` `required_on +1`; second toggle turns it back off |
| model-predicted standing | observed standing | `step_standings` recorded ALIVE for a REFUSED actuation |
| planner-valid plan | environment-valid plan | 30 planners agreed on an unsound model |
| missing replay evidence | successful replay | every crown row scored a replay that never ran |
| zero DSPy calls | DSPy provenance | `source="dspy"` set on the strength of an import |

## Why this is an admission defect, not a planner defect

The `force_latch × depth` plan was **optimal** under the model it was given.
BFS prefers short plans, and it was handed an action promising a free,
repeatable gain. Blaming the planner mislocates the fault: the planner
faithfully executed against an O* that admitted an unproven permission. The
defect is upstream, at the point where an unknown was admitted as a known.

A model that cannot represent a constraint does not fail loudly — it plans
straight through it. That is why an honest `NO_TYPED_VALID_PLAN` is strictly
better than a confident wrong plan, and why a refusal is a result rather than
a gap to be filled.

## Consequence for scoring

A factor that cannot fail is a factor that is not being checked. Crown
attempts 1–3 scored 8/10, 5/10, 5/10 against a conjunction in which REPLAY
could not fail; re-scored against a conjunction that can, all three are
`UNKNOWN`. Those attempts remain permanently recorded as FALSE_GREEN and must
never be rehabilitated by weakening the corrected conjunction.

The objective is not a green scoreboard. It is a reality that satisfies a
scoreboard **capable of being red**.

## See also

- `.claude/rules/standing-law.md` — the status vocabulary; `UNKNOWN` there is
  the same refusal-to-coerce as `UNKNOWN` here.
- `docs/2026-08-08-level4-crown-run1.md` — the FALSE_GREEN correction record.
- `.claude/rules/testing-chicago-style.md` — real collaborators, so that an
  observation is an observation.
