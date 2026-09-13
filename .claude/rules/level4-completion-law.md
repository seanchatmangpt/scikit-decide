# Level 4 completion law — the crown is a witness, not a score

Loads unconditionally. Third of the evidence family, after
`absence-is-not-evidence.md` (how one claim is established) and
`no-dual-bookkeeping.md` (where claims may live). This one says what
completion *is*.

## The one law underneath everything

> Never manufacture semantics from absence, coincidence, prediction, or a
> secondary representation when the primary evidence can carry the relation
> itself.

Every correction this project has made is an instance of it:

```text
diagnostic       != defect
prediction       != observation
observation      != admission
co-reference     != relation
sequence         != conformance
edge existence   != causal identity
runtime verdict  != standing
absence          != success
```

These are not separate lessons. They are one law seen from eight angles.

## Two numbers, not peers

`3/10` (frozen crown) and `0/7` (independent reconstruction) are **not**
comparable results, and reporting them side by side as a status table is
itself the dual-bookkeeping error:

- `3/10` is a **runtime-derived projection**. It is presentation.
- `0/7` is the **independent evidence result**. Only this carries standing.

Under this architecture the crown score has no authority at all. Stop
optimizing it.

## The seven edges are schema, not score

The required relations define a **minimum causal topology**. They are not
seven points to accumulate.

A graph containing all seven relations with one wrong identity is not `6/7`
and is not "almost alive". It is a *different graph* that does not inhabit
`Level4AliveEvidence`. Never expose an edge count as standing.

This is not theoretical. The mutation suite caught the verifier accepting a
graph with the correct activity vocabulary, fully populated relationships,
and an `authorized_by` edge attached to the **wrong actuation**. Identity
mutation is therefore part of the crown, not merely a test of it.

**Mutation law**: for every required relation `R`, construct an
otherwise-complete episode, mutate exactly `R`'s identity, and require
admission to produce a typed non-ALIVE evidence object.

## One witness, not a bag of satisfied predicates

Never ask independently: *does a commitment exist? does authority exist? does
an actuation exist?* Carry identity **forward through the relation**:

```text
Task -> Goal -> PlanCandidate -> POWLCommitment -> AuthorityEnvelope
     -> Actuation -> PostconditionObservation -> Receipt -> ancestry -> Replay
```

An `AuthorityEnvelope` counts only if it authorizes THE SAME `Actuation` that
realizes THE SAME `POWLCommitment` derived from THE SAME `PlanCandidate` for
THE SAME admitted `Task`. A `PostconditionObservation` counts only if it
observes THAT actuation. A `Receipt` only if it derives from THAT actuation
and THAT independent observation. `Replay` only if it replays THAT receipt
DAG.

## Goal consequence must enter the evidence

Runtime `final_state` may not establish standing. The admitted `Goal` is a
first-class durable object, and the independent `PostconditionObservation`
must explicitly relate to that exact goal identity.

Consequence: a perfectly lawful execution that does **not** achieve the
admitted goal remains representable as conformant evidence, and still cannot
construct `Level4AliveEvidence`. Conformance and achievement are different
claims.

Never `goal_reached=True`. Never `final_state == target -> ALIVE`.

## Producer work dominates now

`standalone_verifier` is already strict enough to expose the gap. Do not keep
improving it while the producer stays at zero.

**The old artifact must remain 0/7 permanently** — it is a regression fixture
proving missing joins stay `UNKNOWN` rather than being guessed.

Change the **producer** so new execution emits each relationship at the causal
moment it becomes true. Never post-process a completed episode to manufacture
the missing topology: a relation backfilled from a summary is a claim about a
claim, not an observation.

## Branchless, precisely scoped

Move laws out of imperative branches **where they are declarative graph
constraints**. Prefer OCEL objects/relations, RDF, SHACL, POWL conformance,
and typed evidence constructors over nested `if` chains that re-derive
semantics already expressible in data.

But: **implementation branching is fine.** The target is not "no branches" —
it is *no parallel semantic truth*. Eliminate decision logic that duplicates
meaning the data already carries; leave ordinary control flow alone.

## Constructibility is data too

The planner federation shows the same principle. Applicability is not one
boolean. Preserve separately, as typed observations:

```text
ontology_applicable        representation_supported
constructible              runtime_available
candidate_produced         candidate_independently_validated
```

A planner can be semantically applicable while requiring configuration;
constructible while failing to solve; produce a candidate that fails
independent validation. Collapsing these loses exactly the information that
distinguishes them.

## Definition of done

For **each** identity in the frozen manifest:

1. execute through the real producer
2. emit complete OCEL 2.0 object-centric evidence
3. emit exact commitment identity
4. emit exact authority identity
5. emit exact actuation identity
6. emit independent consequence observation bound to the admitted Goal
7. emit the receipt causal DAG
8. emit replay bound to the exact source receipt DAG
9. persist all artifacts
10. terminate/discard execution state
11. launch a fresh standalone verifier
12. assert the execution runtime is absent from `sys.modules`
13. admit intended POWL × observed OCEL
14. run every identity-mutation falsifier
15. construct `Level4AliveEvidence` from durable artifacts alone

**No score is required.** The crown is the frozen manifest whose every episode
independently inhabits `Level4AliveEvidence`. Counting those objects afterwards
is presentation, not standing.

## See also

- `.claude/rules/absence-is-not-evidence.md` — how a single claim is established
- `.claude/rules/no-dual-bookkeeping.md` — where claims may live
- `.claude/rules/standing-law.md` — the status vocabulary
