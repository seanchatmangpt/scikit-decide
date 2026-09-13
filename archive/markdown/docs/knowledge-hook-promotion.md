# Knowledge Hook Promotion Court

AutoFDE Lab is the exploration and falsification factory that turns repeated cognition into evidence-bound candidate reflexes. It does not actuate production systems and does not grant production standing.

## Chesterton fence

The protected invariant is not “hooks can never cause actuation.” The protected invariants are:

1. zero unreceipted actuation;
2. no unadmitted cognition receives ambient DO authority;
3. BRCE remains the exclusive production DO boundary.

Therefore direct `Hook -> DO` is forbidden, while an independently promoted deterministic pattern may lawfully become `PromotedHook -> BRCE -> DO` in production after the production authority boundary independently admits the request.

## Three hook classes

- `CONSTRUCT`: manufactures intent only and can never enter the fast path.
- `ACTUATION`: deterministic known pattern eligible to manufacture a powerless BRCE request after promotion.
- `REFLEX`: tighter autonomic control rule; promotion additionally requires a bounded compensation identity.

Lab promotion is deliberately `CANDIDATE`, never `ALIVE` production standing.

## Promotion calculus

A candidate binds an exact implementation digest and an envelope:

`E_H = (subjects, predicate, action, scopes, policy, time, falsifiers, verifier)`.

The current bounded court requires at least two distinct positive `ALIVE` episode receipts plus at least one killed falsifier. Every positive receipt must bind the exact hook implementation/action/policy/verifier, stay inside subject/scope, independently verify the postcondition, and replay successfully. Receipt IDs are deduplicated; conflicting reuse of one evidence ID refuses.

The court refuses:

- CONSTRUCT hooks entering the fast path;
- direct DO authority;
- BRCE bypass;
- embedded authority tokens;
- insufficient independent positive evidence;
- missing/unproven falsifiers;
- evidence identity, implementation, action, policy, verifier, subject, or scope drift;
- unverified postconditions or replay;
- REFLEX hooks without compensation.

A successful Lab result is a deterministic `PromotionCandidate` digest suitable for later production admission. It carries `direct_do_authority=false` and `requires_brce=true`.

## Runtime routing model

For a promoted candidate, an observation inside the exact envelope yields `BRCE_ELIGIBLE` and a powerless `BrceRequest`. The request contains no authority grant and has `do_authority=false`.

Any mismatch in predicate, subject, scope, policy, or temporal bound yields `ESCALATE_TO_COGNITION`. This is the crucial autonomic boundary:

```text
known + admitted pattern -> deterministic BRCE request -> no cognition
unknown / drifted world  -> cognition -> Lab discovery/falsification
repeated unknown         -> candidate hook -> promotion court -> future reflex
```

Production AutoFDE or another BRCE implementation must independently intersect principal, action, subject, scope, policy, temporal authority, and current world state before DO.

## Cognition elimination metric

The Lab exposes the observational metric:

`CER = 1 - current_cognitive_episodes / initial_cognitive_episodes`.

CER is not standing by itself. A useful future crown should constrain CER by precision, verified postconditions, authority correctness, and replay so an unsafe shortcut cannot score highly.

## Provenance

The candidate schema pins the marketplace semantic source `ggen-marketplace:consequence-ir-pack@0.2.0`. That pack is semantic provenance, not production authority. A later ggen projection should manufacture production-specific hook bundles and verifiers from the admitted semantic graph.

## Falsifiers

Invalidate this Lab capability if it can execute an external consequence, produce a request containing an authority grant, promote an unverified or non-replayable positive episode, satisfy evidence thresholds by duplicating one receipt, accept authority/envelope drift, promote a REFLEX without compensation, or route an out-of-envelope observation to BRCE instead of cognition.
