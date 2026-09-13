# 7. Run the Automation-Exposure Audit

Most automation assessments ask whether a task can be automated.

That is too shallow.

A model may be capable of producing an output while the surrounding system remains unable to admit, validate, authorize, or use it. Conversely, a task that appears highly variable may become automatable once the problem is represented correctly.

The Automation-Exposure Audit evaluates the full path from observation to consequence.

## The audit dimensions

Score each recurring task from 1 to 5 on the following dimensions.

### Representation

Can the relevant state be expressed in a machine-readable form?

A scheduling problem with explicit resources, durations, and constraints is highly representable. A tense interpersonal conflict may not be.

### Data availability

Are the required observations accessible, current, and trustworthy?

The model cannot compensate for missing source data without increasing uncertainty.

### Repeatability

Do similar situations recur?

Repeated structures support examples, policy learning, templates, caching, and deterministic handling.

### Evaluation

Can a result be checked?

The strongest automation candidates have executable tests, constraints, reconciliations, simulations, or clear rubrics.

### Reversibility

Can mistakes be corrected before harm occurs?

Drafting an email is more reversible than sending it. Creating a proposed schedule is more reversible than canceling appointments.

### Consequence

What is the cost of error?

High consequence does not prohibit automation, but it raises the burden of evidence and authority.

### Authority

Can the task be performed by the system, or does it require a person or institution with standing?

Separate technical capability from legitimate permission.

### Reuse potential

Can the solution be preserved as a reusable policy, cache entry, workflow, or component?

High reuse potential makes investment more valuable.

## Four exposure classes

After scoring, classify the task.

### Class A: Deterministic conversion

The task has clear inputs, clear rules, and clear evaluation.

Convert it to ordinary software or a bounded workflow. An LLM may help build the system but should not remain in the runtime without need.

Examples:

- validating file structure;
- calculating a known formula;
- checking required fields;
- enforcing a naming convention.

### Class B: Agent-assisted production

The task benefits from generation or retrieval, but a person or validator remains responsible for acceptance.

Examples:

- drafting proposals;
- comparing role descriptions;
- preparing meeting briefs;
- generating initial code.

### Class C: Policy manufacturing

The task involves repeated decisions under explicit constraints. Use planning, optimization, simulation, or learned policy, then preserve successful decisions for reuse.

Examples:

- workforce scheduling;
- inventory allocation;
- multi-step incident response;
- probabilistic planning;
- resource-constrained project sequencing.

### Class D: Human-standing work

The task may be supported by AI but should remain human-owned because authority, relationship, contested values, or consequence dominate.

Examples:

- terminating an employee;
- accepting a legal settlement;
- delivering a serious diagnosis;
- making a public moral commitment;
- deciding which harms an institution will risk.

## Exposure is not destiny

A high automation score does not mean the person performing the task lacks value.

It means the task's manufacturing method is likely to change.

The professional can respond in several ways:

- own the automation;
- become the evaluator;
- redesign the larger workflow;
- move toward exceptions and relationships;
- encode domain knowledge into tests and policy;
- become responsible for system governance;
- eliminate the task and own a better outcome.

The least defensible position is to continue performing a highly repeatable, easily evaluated task while refusing to understand the system replacing it.

## Calculate review burden

Automation creates value only when it reduces total system cost.

Track:

- generation time;
- review time;
- correction time;
- exception handling;
- model cost;
- infrastructure cost;
- failure cost;
- coordination cost.

An agent that produces work in one minute but requires forty minutes of expert review may not be an improvement. It may still be useful if the expert previously spent two hours creating the first draft, but the comparison must include the entire path.

This is why evaluation design is a career skill. The person who can determine whether automation actually works is more valuable than the person who merely demonstrates that it runs.

## Identify the 80/20 policy layer

Many domains contain a small number of recurring patterns responsible for most activity.

Find them.

For the common cases:

- normalize the observation;
- encode constraints;
- manufacture the response;
- validate it;
- cache the result with identity and expiration conditions;
- preserve a receipt;
- route novel cases to a more expensive reasoning path.

This reduces cost and increases consistency. It also changes the professional role from repeated performer to policy owner.


## Exposure is not a binary score

A task can be exposed along several dimensions:

- **generation exposure:** a model can produce the artifact;
- **decision exposure:** a system can select an action;
- **execution exposure:** a tool can change external state;
- **coordination exposure:** an agent can sequence the work;
- **evaluation exposure:** quality can be checked mechanically;
- **reuse exposure:** prior solutions can be cached or compiled into policy.

These dimensions matter because a task may be easy to generate but difficult to validate, or easy to validate but impossible to execute without human authority.

## Score the task, not the fantasy

For each task, score from 0 to 4:

| Dimension | 0 | 4 |
|---|---|---|
| Input clarity | Unbounded, tacit | Structured and complete |
| Output specification | Subjective | Explicit schema and criteria |
| Repeatability | Unique | Highly recurring |
| Evaluation | No reliable check | Deterministic or strong benchmark |
| Consequence | Severe/irreversible | Low/reversible |
| Tool availability | No access | Stable API/tooling |
| Domain stability | Rapidly changing | Stable rules |
| Exception rate | Dominant | Rare and classifiable |

A high score suggests the task is a strong candidate for automation or reusable policy. A low score does not mean “never automate.” It means the admission and review burden is higher.

## Reversibility changes the design

A reversible action can often be delegated more aggressively.

Drafting a response, creating a local branch, preparing a candidate schedule, or simulating a decision can be undone or discarded. Sending money, deleting records, publishing legal advice, changing production access, or contacting a customer may create immediate consequence.

Separate construction from actuation:

```text
Agent constructs candidate
    → validator checks candidate
    → authorized actor approves
    → broker executes
    → receipt records outcome
```

Many unsafe agent designs collapse these stages into one model turn.

Your audit should therefore identify not merely whether the task can be automated, but where the irreversible transition occurs.

## Look for hidden review cost

A generated artifact can appear cheap while transferring cost to review.

Suppose an agent generates fifty sales leads. If a salesperson must spend two hours eliminating irrelevant or risky targets, the system may not have created leverage. It created review inventory.

Track:

- generation time;
- human review time;
- correction rate;
- downstream failure rate;
- time to accepted outcome;
- cost of false positives and false negatives.

The relevant metric is not output per minute. It is **accepted outcome per unit of total system cost**.

## Audit the exceptions

Automation projects often prove the happy path and hide the exception distribution.

For each task, collect at least ten examples of failure or ambiguity:

- missing data;
- conflicting instructions;
- unusual customer state;
- tool timeout;
- stale policy;
- ambiguous identity;
- insufficient authority;
- adversarial input;
- cost threshold exceeded;
- validator disagreement.

A task becomes operationally mature when exceptions produce typed outcomes rather than silent improvisation.

Examples:

```text
NEEDS_HUMAN_JUDGMENT
INSUFFICIENT_EVIDENCE
AUTHORITY_REQUIRED
TOOL_UNAVAILABLE
POLICY_NOT_APPLICABLE
COST_LIMIT_EXCEEDED
```

Typed refusal is a capability. It prevents uncertainty from being converted into false confidence.

## Use ERRC to redesign the role

After scoring tasks, apply four moves.

### Eliminate

Remove tasks that exist only because systems are fragmented or status is invisible.

### Reduce

Automate or template recurring construction with strong review criteria.

### Raise

Use the saved capacity to improve judgment, customer understanding, experimentation, or architecture.

### Create

Add the missing work: evaluation, policy maintenance, exception design, evidence capture, and reuse.

The result should not be “the same job, faster.” It should be a new outcome system.

## Career exposure matrix

Classify each task into one of four quadrants:

| | Outcome ownership low | Outcome ownership high |
|---|---|---|
| Exposure low | Stable but possibly stagnant | Defensible specialist work |
| Exposure high | Immediate risk | Redesign opportunity |

The most promising quadrant is high exposure plus high outcome ownership. You have both urgency and permission to reshape the system.

High exposure plus low ownership is a warning. You may need to acquire broader responsibility, move closer to the buyer, or change markets.

## Field exercise: Audit ten tasks

Select ten recurring tasks from your role.

For each task, score the eight dimensions from 1 to 5. Then classify it as A, B, C, or D.

Choose:

- one Class A task to convert;
- one Class B task to augment;
- one Class C task to model;
- one Class D task whose human authority should be made explicit.

Write the expected reduction in total work—not just generation time.

That is your first automation portfolio.
