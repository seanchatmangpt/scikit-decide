# Signature-driven SREGym SOTA rail

This rail treats source-controlled DSPy signatures as falsifiable cognition contracts.
The loop is deliberately manual: benchmark evidence changes the next signature revision;
there is no prompt optimizer or prompt-compilation stage.

```text
signature revision
  -> exact SREGym revision
  -> disposable kind cluster
  -> public MCP capability + input-schema discovery
  -> deterministic fact compiler
  -> hypothesis portfolio
  -> admitted evidence relationships
  -> mechanically computed epistemic standing
  -> capability-bound POWL discrimination process
  -> causal closure
  -> identity-bound diagnosis
  -> capability-bound POWL mitigation + verification process
  -> SREGym grader
  -> exact-subject receipt
```

## Invariants

- No GEPA execution or prompt compilation.
- No benchmark fault taxonomy in cognition.
- The LM proposes evidence relationships; it never owns epistemic standing.
- An evidence link is inert unless both its hypothesis ID and fact ID are admitted.
- Multiple `SUPPORTED` hypotheses are **not terminal**.
- `DIAGNOSIS_READY` iff exactly one hypothesis is supported and none is unknown.
- A committed diagnosis may reference only that supported hypothesis and admitted fact IDs.
- Repeated zero-information discrimination re-hypothesizes and then refuses.
- Observation and mitigation structures are represented as POWL v2.
- MCP capabilities and their input schemas are discovered at runtime.
- Every LM-manufactured process step binds one exact discovered `capability_id`; surface and
  tool names are deterministic consequences of that identity, not LM outputs.
- Unknown capability identities and invalid argument shapes refuse before POWL dispatch.
- A bounded kernel-owned retry may feed typed process refusals back to the same signature.
- Kubectl command semantics are authority-classified independently of LM READ/DO labels.
- Consequential activity requires explicit DO, reversibility, and verification.
- SREGym owns injection, hidden grading, stage transition, and reset.

## Signature revisions

### SRE-SIG-001

Established the seven-signature epistemic pipeline and reached the first legitimate live
SREGym cognition episode on GitHub-hosted kind. The episode proved the full infrastructure
rail but falsified the process contract: the discriminator emitted a POWL step that the
capability driver refused, so no diagnosis was submitted. SREGym graded diagnosis and
mitigation false. This is a cognition/process falsifier, not a cluster blocker.

### SRE-SIG-002

Closes that falsifier by replacing free-form `surface` + `tool` process fields with exact
runtime-discovered `capability_id` references, exposing MCP input schemas to the signatures,
validating capability identity/arguments/authority before runner dispatch, allowing up to
three bounded kernel-owned candidate retries with typed rejection feedback, and receipting
all terminal cognition/process refusals instead of crashing without evidence.

## Cost boundary

The deterministic `sregym-signature-court.yml` runs on PRs and makes no model calls.
The single-problem kind/Groq rail is manual or explicitly opted-in on a same-repository PR
with `/run-sregym-live`; absent that marker its paid job is skipped. Before kind creation it
imports the exact copied agent capsule, so packaging/import defects fail before cluster/model
spend. The 21-problem SREGym-Lite matrix is manual-only.

## Campaign structure

`SREGym-Lite.md` from the pinned upstream revision is the population authority for the Lite
campaign. The workflow derives exactly 21 unique problem IDs from that artifact, executes each
in an isolated disposable cluster job, normalizes SREGym's grader fields, and refuses a
scorecard unless all 21 exact-subject episode summaries are present.

## Exact upstream subject

The court pins `SREGym/SREGym@ba07faf1a322f9b6d4a279643bb796aa2f36f64b`.
Changing this revision changes the benchmark subject and requires new evidence.
