# 14. Receipts, Not Claims

The labor market runs on claims.

Candidates claim expertise. Companies claim culture. Portfolios claim impact. Job descriptions claim scope. Interviews claim to measure ability.

Claims are unavoidable, but they are weak evidence.

The post-LLM economy makes them weaker because high-quality language is cheap. Anyone can generate a persuasive résumé, a confident case study, a polished architecture diagram, or a plausible explanation. The appearance of competence is abundant.

The response is not suspicion toward every AI-assisted artifact. It is a higher standard of proof.

Replace unsupported claims with receipts.

## What a receipt is

A receipt is evidence that binds an action or artifact to its identity, context, authority, result, and verification.

A useful receipt answers:

- What exact subject was acted upon?
- What observation and version were admitted?
- What method or toolchain produced the result?
- What changed?
- Who or what had authority?
- Which checks ran?
- What passed, failed, or remained unknown?
- Can another person replay or inspect the process?

A screenshot is evidence. It is not necessarily a receipt. A green check is evidence. It may not prove that the exact subject requested was executed. A repository is evidence. It may not show that the software runs.

The strength comes from the binding.

## The proof ladder

Use a proof ladder to classify evidence.

### Level 0: Assertion

> I can build agent systems.

No inspectable support.

### Level 1: Artifact

A repository, document, diagram, or video exists.

This proves construction, not execution.

### Level 2: Static verification

The artifact passes lint, type checks, schema validation, theorem checks, or policy gates.

This proves selected properties.

### Level 3: Observed execution

The exact artifact runs against an admitted subject.

This establishes local operational life.

### Level 4: Behavioral verification

Tests or evaluation show that the observed behavior satisfies acceptance criteria.

### Level 5: Reproduction

Another environment or person can replay the result using preserved instructions and identities.

### Level 6: Outcome evidence

The system produces the intended real-world change over time.

Do not call Level 1 evidence Level 6 evidence. Precision creates trust.

## Career receipts

A career receipt may be:

- a commit tied to a specific issue and verification command;
- a benchmark with source, configuration, hardware, and raw results;
- a case study with baseline, intervention, and measured outcome;
- a customer reference;
- a recorded demonstration against a realistic scenario;
- a public article whose claims are sourced and later validated;
- a hiring workflow that records roles found, applications sent, responses, and conversion;
- an architecture decision record linked to the resulting system.

The best portfolio is a receipt graph, not a gallery.

## Receipts for AI-assisted work

AI-assisted production creates a new evidentiary question:

> What did the person actually contribute?

The wrong response is to pretend the work was manually produced.

The right response is to describe the manufacturing system:

- the outcome definition;
- the admitted context;
- the architecture;
- the prompts or semantic programs;
- the tools and models;
- the validation method;
- the repairs;
- the final decision;
- the result.

A person who can reliably direct and verify a high-throughput system demonstrates a valuable capability. Hiding the system makes extraordinary throughput look implausible.

## Refusals are evidence

A trustworthy system does not merely show successful runs.

It also shows what it refuses:

- unsupported input;
- missing authority;
- stale context;
- failed validation;
- identity mismatch;
- unsafe actuation;
- unavailable toolchain;
- unbounded cost.

Typed refusal is stronger than vague failure because it establishes the boundary of standing.

A candidate can use the same discipline:

> I have not operated this exact platform at your production scale. I have operated adjacent distributed systems, built the relevant architecture, and can demonstrate the capability against a bounded scenario. Production-scale standing remains to be established in your environment.

This answer is stronger than either false certainty or self-disqualification.

## Build the evidence index

Create a table with these columns:

| Claim | Subject | Artifact | Execution | Verification | Outcome | Boundary |
|---|---|---|---|---|---|---|

For every important career claim, fill the row.

If execution is missing, do not infer it from the artifact. If outcome evidence is missing, state the bounded standing you do have.

The index becomes the source for résumés, interviews, posts, and proposals.


## The evidence ladder

Not all evidence carries the same standing.

A useful ladder is:

1. **Assertion:** You state that you can do something.
2. **Artifact:** You show a created object.
3. **Demonstration:** You show the object operating.
4. **Verification:** An independent check confirms defined properties.
5. **Observed outcome:** The system produces the intended result in the target context.
6. **Receipt and replay:** Identity, inputs, authority, execution, result, and reproduction are preserved.
7. **Repeated standing:** The result survives multiple relevant cases and counterexamples.

A repository is an artifact. A passing workflow is verification of a specific build path. Neither automatically proves customer value or production readiness.

Match your claim to the highest rung you actually possess.

## A receipt schema

A practical career receipt can contain:

```yaml
subject:
  project: customer-risk-triage
  version: 1.4.2
  environment: staging
observation:
  sources:
    - crm_snapshot_2026_08_01
    - support_cases_2026_w31
  admitted_at: 2026-08-02T09:00:00-07:00
objective:
  reduce_false_negative_risk: true
  max_review_minutes_per_account: 4
authority:
  constructor: agent-workflow-v3
  approver: customer-success-director
execution:
  command: triage run --week 31
  exit: 0
result:
  accounts_reviewed: 184
  escalations: 17
  false_negative_audit: 1
replay:
  fixture: fixtures/week-31.json
  command: triage replay receipt-2026-w31.json
limitations:
  - enterprise-segment only
```

The exact schema changes by domain. The principle remains: bind the claim to an exact subject and observed execution.

## Receipts protect ambitious builders

People with unusually high output encounter skepticism. The worst response is to escalate the claim without improving the evidence.

Receipts allow you to say:

- what was generated;
- what was reviewed;
- what was executed;
- what changed;
- what passed;
- what remains unsupported.

This makes high throughput believable without pretending every artifact has equal standing.

For example:

> I produced 3,000 commits across forty repositories. That number measures manufacturing activity, not equivalent production value. Here are the exact-head builds, test receipts, benchmark reports, and deployed outcomes that support the stronger claims.

Precision increases credibility.

## Build proof packs for buyers

Different buyers need different receipts.

### Recruiter proof pack

- one-page role definition;
- résumé;
- three concise case studies;
- searchable skill language;
- availability and target role.

### Technical-leader proof pack

- architecture diagram;
- repository and exact revision;
- test and build commands;
- failure cases;
- benchmark assumptions;
- design tradeoffs.

### Executive proof pack

- business problem;
- cost of current state;
- target operating model;
- measured or modeled impact;
- risks and controls;
- first-ninety-days plan.

The underlying graph is the same. The receipt projection changes.

## Negative evidence is valuable

A mature proof portfolio includes what failed.

Record:

- unsupported environments;
- rejected hypotheses;
- negative fixtures;
- incomplete integrations;
- cost thresholds;
- known edge cases;
- cases requiring human review.

Negative evidence establishes that the system can distinguish success from failure.

A demonstration that always reports success is not strong proof.

## Make replay cheap

The easier it is for another person to inspect your evidence, the more likely it will be used.

Provide:

- one command;
- one fixture;
- one short video;
- one machine-readable report;
- one explanation of expected output;
- one statement of limitations.

Do not require a hiring manager to reconstruct your environment, read an entire repository, or trust screenshots without context.

## The proof portfolio as career capital

A résumé decays when titles and keywords change. A proof portfolio can compound.

A test fixture becomes a benchmark. A benchmark becomes a public lesson. A public lesson attracts a collaborator. The collaboration creates a stronger case study. The case study supports a role brief. The role produces new authority and evidence.

Receipts are not merely defensive documentation. They are the memory through which a career learns.

## Field exercise: Upgrade one claim

Choose a claim from your profile.

Write the current evidence level from 0 to 6.

Then define the cheapest legitimate action that moves it one level higher.

Examples:

- turn an architecture diagram into a working slice;
- run the exact command and capture the result;
- add a behavioral test;
- provide a replay script;
- measure the user outcome;
- obtain an external reference.

Do not seek maximum proof for every claim.

Seek the strongest proof necessary for the consequence you want the market to grant.
