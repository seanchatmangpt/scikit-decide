# 27. The Economics of Reusable Intelligence

The first generation of LLM products treats intelligence as a metered utility.

Every request reconstructs context, generates alternatives, selects tools, and produces an answer. The model is paid repeatedly to rediscover the same structure.

This can be rational for novel work. It is wasteful for recurring work.

The post-LLM organization must learn to manufacture reusable intelligence.

## The total cost equation

Model cost is only one component.

A useful total includes:

- retrieval;
- prompt and context construction;
- inference;
- tool calls;
- latency;
- human review;
- correction;
- retries;
- failure impact;
- coordination;
- security and compliance;
- storage and observability.

A cheap model call can be part of an expensive workflow. An expensive model call can be economical if it replaces substantial expert labor and produces a reusable policy.

Measure the outcome path.

## The hierarchy of reuse

### Token reuse

Prompt caching avoids retransmitting stable context.

Useful, but shallow.

### Response reuse

A prior answer is returned for a matching request.

Efficient when wording and context are stable, risky when identity or freshness differs.

### Artifact reuse

A validated document, code component, test, or plan is reused.

This preserves more value.

### Semantic reuse

A normalized problem representation, example, rule, or ontology is reused across surface variations.

### Policy reuse

A validated mapping from admitted state to action is reused.

This can remove repeated reasoning from the common path.

### System reuse

The entire observation, admission, construction, validation, actuation, and receipt path becomes reusable infrastructure.

This is the highest leverage.

## The 80/20 architecture

Most operational domains contain common cases and long tails.

Use expensive flexible reasoning to discover and handle the tail. Use validated reusable policies for the common path.

```text
Incoming situation
    ↓
Normalize and identify
    ↓
Does an admitted policy match?
    ├── Yes → validate freshness → execute through broker → receipt
    └── No  → reason/plan → validate → preserve candidate policy → execute → receipt
```

Over time, the expensive branch should shrink for stable domains.

## Identity before reuse

Reuse is lawful only when the relevant identity matches.

Check:

- subject;
- observation version;
- policy version;
- model or solver version;
- toolchain;
- configuration;
- environment;
- authority;
- expiration;
- consequence class.

A cached answer for one customer cannot silently apply to another. A validated plan under one resource constraint may fail under another. A software receipt on one commit does not prove a different head.

Cache invalidation is an authority problem as well as a technical problem.

## Self-play accelerates policy coverage

You do not need to wait for every common case to occur naturally.

Use domain models and avatars to generate realistic scenarios. Run candidate policies. Validate outcomes. Preserve accepted cases and refusals.

This creates an 80/20 corpus before full deployment.

Synthetic coverage must remain labeled. Real-world evidence should update confidence.

## Economic roles emerge

Organizations will need people who own:

- inference accounting;
- semantic cache design;
- policy identity;
- evaluation amortization;
- reusable agent capabilities;
- scenario corpora;
- stale-context detection;
- cost-performance tradeoffs.

This is more strategic than selecting the cheapest model.

## Career implication

A professional who repeatedly produces one artifact is selling labor.

A professional who creates a reusable system is manufacturing capital.

The capital may belong to the employer, customer, community, or open-source ecosystem. The key is that the work changes future production capacity.

Ask after every project:

> What can the next person or next run do that was impossible or expensive before?

That answer belongs in your résumé and compensation conversation.


## Most agent cost is organizational, not only computational

Token price is visible. The larger cost often includes:

- reconstructing context;
- searching for the same facts;
- regenerating familiar plans;
- reviewing inconsistent output;
- correcting repeated failures;
- coordinating tools;
- explaining decisions;
- recovering from unreceipted actions.

A cheaper model does not solve these costs if the operating system remains stateless and improvisational.

## The reusable-intelligence ladder

Intelligence can be preserved at several levels.

### Raw transcript

Cheap to store, expensive to interpret, and vulnerable to irrelevant context.

### Summary

More compact, but may lose provenance and constraints.

### Structured observation

Facts are normalized into explicit fields with source and time.

### Admitted knowledge

The system records which observations are trusted for which purpose.

### Validated artifact

A response, template, mapping, or plan has passed acceptance criteria.

### Policy

The system can select or construct the correct response for a class of cases.

### Compiled execution path

The common case can run with minimal semantic interpretation while preserving authority and receipts.

Economic leverage increases as reuse moves down the ladder.

## The 80/20 ERRC cache

Start with the demand distribution.

Which twenty percent of scenarios account for eighty percent of requests, cost, delay, or review?

Then apply:

### Eliminate

Remove unnecessary model turns, duplicated retrieval, and status generation.

### Reduce

Compress context, narrow tools, and reuse admitted domain objects.

### Raise

Improve the common-case solution with stronger fixtures, policies, and evaluation.

### Create

Manufacture missing assets: canonical graphs, policy libraries, exception taxonomies, and replay receipts.

The cache is an operating redesign, not a key-value optimization.

## Cache identity must be exact enough

A cached answer is dangerous when it applies to the wrong subject or stale conditions.

Identity may include:

- domain version;
- subject identifier;
- policy version;
- tool version;
- model or semantic module version;
- configuration;
- environment;
- relevant observation hashes;
- authority scope.

Reuse requires correspondence, not resemblance.

## Cache failure too

Repeated unsupported cases should not repeatedly consume full reasoning cycles.

Cache typed outcomes such as:

- missing required observation;
- unsupported jurisdiction;
- authority unavailable;
- policy conflict;
- tool incompatibility;
- cost threshold exceeded.

The cache can return the known blocker and the evidence required to reopen the case.

This converts failure into topology.

## Self-play manufactures the cache

Ontology-driven self-play can generate the 80/20 scenario corpus before all cases arrive in production.

The process is:

1. define the domain objects and transitions;
2. generate representative and adversarial scenarios;
3. solve or construct candidate policies;
4. validate against acceptance criteria;
5. retain the admitted policies and negative fixtures;
6. test new cases against the library;
7. escalate novel edges.

This reduces runtime intelligence expense and improves coverage.

## The economics of the common path

Compare two systems.

### Improvisational agent

Every request reconstructs context, plans with an LLM, invokes tools, reflects, and retries.

### Policy-backed agent

The request is classified, matched to an admitted scenario, executed through a known path, and receipted. The LLM is used only for novel interpretation or exception handling.

The second system may have higher initial construction cost. Its marginal cost and variance can be dramatically lower.

This is the same economic logic through which software replaces repeated manual reasoning.

## Reuse changes career value

A professional who completes one task creates one unit of output.

A professional who manufactures a validated reusable policy creates future capacity.

Employers should ask:

- What intelligence remains after the person finishes the project?
- Can the next team replay it?
- Does the system become cheaper or more reliable with use?
- Are failures encoded?
- Is the knowledge portable?

Your portfolio should show not only what you produced, but what can now be produced repeatedly because of the system you built.

## Avoid stale intelligence

Every reusable asset needs invalidation rules.

Record:

- source freshness;
- policy version;
- domain assumptions;
- expiration conditions;
- monitoring signals;
- revalidation method.

A cache without invalidation is accumulated confidence in the past.

## Field exercise: Find one repeated intelligence expense

Choose a process that uses an LLM repeatedly.

Measure ten runs:

- request similarity;
- inference cost;
- human review;
- repeated context;
- repeated decisions;
- variation;
- failure.

Identify the highest lawful reusable layer: token, response, artifact, semantic structure, policy, or system.

Design a cache identity and one falsifier that would force recomputation.

The objective is not to eliminate models.

It is to stop paying for intelligence you have already admitted.
