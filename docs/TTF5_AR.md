# TTF5-AR — Time to Fortune-5-Class Architecture Readiness

TTF5-AR is the Fortune-5 architecture-readiness measurement contract for AutoFDE Lab.
It is a **technicalStanding** metric. It does not manufacture customer adoption,
organizational standing, enterprise standing, or execution authority.

## Metric

For verifier `V`, admitted subject `O*`, architecture/evidence submission `A`, and
reference predicate `P_F5`:

```text
TTF5-AR = inf { t >= 0 | V(O*, A, P_F5) = ALIVE }
```

The benchmark clock starts at the submission's admitted start boundary and stops at
**external verification**, not artifact generation or submission time.

The default `P_F5` is conjunctive across twelve mandatory gates:

1. identity
2. strategy
3. business
4. information
5. application
6. technology
7. governance
8. security
9. transition
10. production
11. actuation
12. evidence

No weighted average exists. One `FAIL`, `UNKNOWN`, or missing gate prevents `ALIVE`.

## Identity

A readiness subject is digest-bound to:

```text
benchmark id
× benchmark version
× Fortune-5 scenario digest
× admitted observation digest
× reference-profile digest
```

Every gate-evidence record must bind the same subject digest. Evidence presence never
implies `PASS`; the decision is an explicit admitted input to the verifier.

## F5Verify

`autofde_lab.fortune5.f5verify` is a read-only independent verifier surface. It consumes
one JSON submission and emits a deterministic `ReadinessWitness`.

Example execution shape:

```bash
PYTHONPATH=src python -m autofde_lab.fortune5.f5verify \
  submission.json \
  --verified-at-ns 175 \
  --output witness.json
```

Exit `0` means the exact supplied subject satisfied every mandatory gate. Exit `3`
means the submission was structurally valid but did not reach readiness.

A `ReadinessWitness` is **verification evidence, not an authority receipt**. AutoFDE Lab
remains SELECT/CONSTRUCT only.

## Replay

`F5ReadinessVerifier.replay()` recomputes the witness at its recorded verification time
and refuses if either the submission identity or deterministic witness diverges.

```text
REFUSED:READINESS_REPLAY_SUBMISSION_MISMATCH
REFUSED:READINESS_REPLAY_DIVERGENCE
```

## TTΔEA — architecture resynchronization

`BenchmarkMutation` observes an external enterprise mutation. It cannot perform one.
A mutation binds:

```text
pre-subject × post-subject × mutation kind × observed time × mutation evidence
```

For a previously `ALIVE` architecture:

```text
TTΔEA = verified(post-subject) - observed(mutation)
```

The resynchronization submission must start exactly at the observed mutation time; this
prevents moving the benchmark clock after work has already begun. Subject substitution
fails closed.

For the binary readiness predicate, Architecture Synchronization Debt over one mutation
is the same unresolved interval as `TTΔEA`. Richer distance-weighted debt can be added
later without changing the first-passage contract.

## Derived metrics

The implemented bounded metric family currently includes:

- `TTF5-AR` — first verified Fortune-5-class technical readiness.
- `TTΔEA` — first verified readiness after an observed mutation.
- binary Architecture Synchronization Debt — unresolved mutation interval.
- Evidence Coverage Ratio — fraction of mandatory gates carrying explicit evidence.
- Readiness Failure Rate — fraction of submitted attempts not reaching `ALIVE`.
- Architecture Optionality Density — `lawful_verified_alternatives / (1 + irreversible_decisions)`.

The existing Fortune-5 CMD state-space remains the option-manufacturing substrate. Its
raw symbolic space, pairwise construction, ggen correspondence, replay identity, and
`authority=NONE` fence are unchanged by this metric layer.

## Standing boundary

A successful TTF5-AR witness establishes only:

```text
technicalStanding = ALIVE
```

for the exact bounded benchmark subject and verifier profile. Existing customer adoption
logic remains the separate authority surface for organizational and enterprise standing.
No benchmark, diagram, generated file, verifier witness, or green CI job may self-certify
customer acceptance.

## Qualification

The dedicated exact-head court is `.github/workflows/ttf5-readiness.yml`. It:

1. checks out the exact PR head;
2. refuses an identity mismatch;
3. refuses mockist readiness tests;
4. compiles the Fortune-5 verifier package;
5. executes the real TTF5-AR Chicago court and the existing Fortune-5 state-space court.

Local narrow verifier:

```bash
PYTHONPATH=src python -m pytest -q tests/fortune5/test_readiness.py
```

Repository standing must still follow `.claude/rules/standing-law.md`: a published or
queued workflow is not `ALIVE` until execution against the exact candidate head has been
observed.
