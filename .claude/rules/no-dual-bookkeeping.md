# No dual bookkeeping — the evidence graph is the record

Loads unconditionally. Companion to `absence-is-not-evidence.md`: that file
governs how an *individual* claim may be established; this one governs where
claims may **live at all**.

## The diagnosis

The recurring defect in this repo was never "bad booleans". It was **two
parallel structures recording the same thing**:

```text
execution reality                 derived Python summary state
    -> OCEL / receipts /              -> step_standings
       commitment artifacts           -> replay_valid
                                      -> ocel_valid
                                      -> independently_verified
                                      -> is_alive / alive_count
```

The second is free to drift from the first, and it demonstrably did — three
separate times, each found only by adversarial audit:

| Defect | The drift |
|---|---|
| REPLAY never verified | summary said clean; no replay had run |
| `step_standings` ALIVE for a refused step | summary said ALIVE; the receipt said REFUSED |
| `authority_ref` NULL in 100% of receipts | summary claimed authority; no receipt carried one |

Each was fixed individually. The *class* is only fixed by deleting the second
structure.

## The rule

> Standing is a query over one joined evidence graph. It is never a field.

A summary field may exist **only** as a non-authoritative reporting projection
derived *from* admitted evidence. It may never participate in computing
standing. Where the two disagree, the graph is right by construction, because
the field has no independent claim to truth.

## Identity, not adjacency

Two artifacts in the same directory are not joined. Measured: a real ALIVE
trial's `commitment.ttl` carries `planDigest 220f81bf978fe490`; its
`episode.ocel.json` carries episode `4b1d493441504091a6fb082b49d87937`; grep
counts **both ways are zero**. The only relation was filesystem adjacency.

So these questions were literally unanswerable from evidence:

- Was this exact actuation authorized by this exact authority envelope?
- Was this exact actuation the realization of this exact commitment?
- Did this exact receipt derive from this actuation and this independent
  observation?
- Did this replay bind the exact source receipt DAG?

Exact object identity only. Never reconstruct a relation afterwards from
timestamps, ordering, or string similarity — a relation inferred post hoc is a
guess wearing the costume of a join.

## Object-centric conformance

A correct activity **order** with broken object **identity** is
non-conformant. Sequence fitness alone cannot see this, which is why
token-replay fitness is one layer and never the verdict:

- `ActuationClosed` must reference the *same* `Actuation` that was opened.
- The `AuthorityEnvelope` admitted must be the *same* one the `Actuation` used.
- `ReceiptEmitted` must reference the *same* `Actuation` and
  `PostconditionObservation`.
- `ReplayCompleted` must reference the *same* source `Receipt` graph.
- `POWLCommitted` must reference the *same* `PlanCandidate` later actuated.

`SELF_CERTIFIED_POSTCONDITION` becomes a graph violation — the verifier
identity is not the actuator identity — rather than a boolean anyone can set.

## The intended/observed boundary

Two independently produced artifacts, joined only by explicit identity:

```text
INTENDED   POWL / process commitment
OBSERVED   OCEL 2.0
```

Never derive observed events from the intended model. Never derive the
commitment from the observed trace after execution. Conformance is the
*relation* between them; deriving either from the other makes that relation
vacuous — the same tautology as mining a process model from the log you then
check against it.

## Identity is explicit or it does not exist

An identity join may be established ONLY by an explicit typed edge. Never by:

```text
timestamps          filename similarity     token overlap
activity ordering   matching labels         matching counts
```

Each of those is a correlation that happens to hold. None is a statement the
producer committed to. Co-reference is not relationship: an event naming two
objects does not assert that those two objects are related to each other.

**Tightening a join may lower the count.** Measured: a checker accepting token
co-occurrence read 2/5; the same trial under explicit-typed-edge-only reads
0/7. If the earlier join was incidental, the lower number is the more honest
one and the drop is a correct regression. Never optimize a verifier toward a
green result — optimize toward every required identity being explicit in
durable evidence.

## The threshold — standing external to the actor

The crown is not a score. It is this property:

> Delete the Python runtime state entirely. Load only the durable OCEL +
> commitment/provenance artifacts. Recompute the same standing.

If that recomputation is impossible, standing still depends on the
implementation that produced it — the system is attesting to itself, and its
verdict is worth exactly what a self-report is worth. If it is possible,
standing becomes **external to the actor**, and can be checked by someone who
does not trust the runtime and did not run it.

That is the threshold to target, and it is testable: the recomputation either
reproduces the verdict from artifacts alone, or it names precisely which
identity is missing.

## See also

- `.claude/rules/absence-is-not-evidence.md` — how a single claim is
  established; this file is where claims may live.
- `.claude/rules/standing-law.md` — the status vocabulary.
- `docs/2026-08-08-level4-crown-run1.md` — the FALSE_GREEN record that
  motivated both files.
