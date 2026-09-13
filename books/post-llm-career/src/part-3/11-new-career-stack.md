# 11. MCP, A2A, DSPy, Planning, and the New Career Stack

The agent economy is often presented as a list of frameworks. That is useful for installation and poor for understanding.

A career stack should be organized by the function each layer performs.

## Language models: candidate intelligence

LLMs generate interpretations, plans, code, messages, classifications, and alternatives.

Their strength is flexible semantic construction. Their weakness is that plausible generation does not guarantee truth, authority, consistency, or fitness for a particular consequence.

Use models where language and ambiguity matter. Do not leave them in a runtime merely because they helped create it.

## MCP: agent-to-tool capability

The Model Context Protocol gives agents a structured way to discover and invoke tools or retrieve resources.

In career terms, MCP matters because professional capability no longer resides only inside one application. A person can expose bounded functions—search, analysis, scheduling, validation, simulation, repository operations—to many compatible clients.

The durable skill is not "knows MCP syntax." It is:

> Can define a safe, typed, observable capability surface that agents can use without gaining unnecessary authority.

## A2A: agent-to-agent coordination

Agent-to-Agent protocols allow independent agents to discover capabilities, exchange tasks, report state, and collaborate across organizational or platform boundaries.

This creates roles involving:

- capability discovery;
- task contracts;
- identity;
- trust;
- delegation;
- asynchronous coordination;
- result verification.

A2A is important because an enterprise agent ecosystem will not be one monolith. Specialized systems will need to cooperate without exposing all internal state.

## DSPy: semantic program optimization

DSPy treats language-model behavior as a program that can be described through signatures, modules, examples, metrics, and optimizers.

The career implication is significant. Prompting moves from artisanal phrasing toward evaluated semantic programming.

Use DSPy to optimize:

- extracting a structured problem from natural language;
- classifying a request;
- selecting examples;
- producing a candidate plan;
- explaining a result;
- routing an exception.

DSPy should not grant execution authority. It improves construction before admission and actuation.

## Planning and optimization: choosing under constraints

Many professional problems are not primarily language problems.

They involve:

- states;
- actions;
- resources;
- durations;
- probabilities;
- partial observability;
- goals;
- costs;
- constraints.

Planning frameworks, scheduling solvers, MDPs, POMDPs, PDDL, PPDDL, and optimization systems can represent these structures explicitly.

A language model can help translate messy observations into a candidate domain. A planner can then choose actions according to formal constraints. Simulation can test policy before execution.

This is a more mature architecture than asking the model to improvise every next step.

## Caching: reusable intelligence

A cache is not merely a performance trick.

In the post-LLM economy, caching is a method for turning paid cognition into reusable organizational memory.

Cache at the highest lawful semantic level:

- admitted observations;
- normalized problem graphs;
- solver compatibility;
- validated plans;
- policies;
- examples;
- refusal reasons;
- receipts.

A response cache may reuse words. A policy cache reuses a decision structure.

Identity is essential. Reuse is valid only when subject, version, constraints, toolchain, and environment match the original standing conditions.

## BRCE: bounded receipted actuation

The Brokered Receipted Capability Execution pattern enforces a simple invariant:

> Zero unreceipted actuation.

Construction systems produce intents. A broker admits or refuses those intents, checks authority, invokes the capability, and issues a receipt.

This separates intelligence from power.

The career opportunity is not limited to implementing one broker. It includes designing systems in which:

- raw input has no ambient execution authority;
- model output is a candidate, not a command;
- hooks manufacture intents but do not actuate;
- every external change has a traceable identity;
- replay and repair are possible.

## The complete stack

```text
Human objective and standing
        ↓
Observation and retrieval
        ↓
LLM/DSPy semantic construction
        ↓
Formal domain and admission
        ↓
Planner, optimizer, or deterministic workflow
        ↓
MCP/A2A capability coordination
        ↓
Brokered actuation
        ↓
Receipt, cache, and learning
```

No individual layer is the career.

The valuable professional understands where a problem belongs, where authority stops, and how evidence moves through the stack.

## Build role language from the stack

Possible descriptions include:

- Agentic AI Architect: designs the full capability and authority topology.
- Agent Systems Engineer: implements orchestration, tools, state, and integration.
- Decision Systems Architect: formalizes planning, optimization, and policy.
- Agent Reliability Engineer: designs evaluation, observability, refusal, and recovery.
- AI Governance Engineer: encodes policy, authority, evidence, and audit boundaries.
- Semantic Systems Engineer: optimizes structured model behavior and ontology alignment.

These roles overlap. The stack helps a company decide where its gap actually lies.


## Protocols are career primitives

The names MCP, A2A, and DSPy can sound like a temporary technology stack. Their deeper importance is architectural.

They represent three separations:

- tools from agents;
- agents from other agents;
- semantic programs from ad hoc prompting.

Planning, caching, and receipts add three more:

- candidate generation from policy selection;
- repeated problems from repeated intelligence expense;
- action from evidence of action.

A professional who understands these separations can reason about many frameworks without becoming dependent on one.

## MCP: capability exposure

Model Context Protocol gives an agent a discoverable interface to tools and resources.

The career implication is that domain capabilities can be packaged once and used through many model surfaces. A scheduling engine, customer-data lookup, policy validator, or document generator does not need to be rebuilt for each assistant.

The important design questions are:

- What capability is exposed?
- What input schema is required?
- What authority does the tool possess?
- What evidence does it return?
- What failures are typed?
- What information is allowed to cross the boundary?

Knowing how to “make an MCP server” is less valuable than knowing how to expose a capability without accidentally granting ambient execution authority.

## A2A: organizational composition

Agent-to-agent protocols allow independently operated agents to discover capabilities, exchange tasks, and report state.

This resembles organizational design. One agent may specialize in research, another in planning, another in validation, and another in communication.

The danger is anthropomorphic theater: naming several prompts as agents without defining distinct contracts, authority, or evidence.

A meaningful agent boundary should have:

- a defined capability;
- an input and output contract;
- independent state;
- a failure model;
- a reason for separate authority or scaling;
- evidence returned to the caller.

A2A becomes valuable when the network preserves these boundaries.

## DSPy: semantic programs

DSPy treats model behavior as a program that can be specified, evaluated, and optimized rather than as a single hand-written prompt.

For careers, the lesson is that natural-language reasoning can become an engineered component.

You might define modules for:

- extracting a business problem from an interview transcript;
- mapping a job description to a role taxonomy;
- generating test scenarios;
- classifying objections;
- producing executive and technical projections of the same evidence.

The module should be evaluated against examples and metrics. This turns “I am good at prompting” into a reproducible system capability.

## Planning: choosing under constraints

LLMs are strong candidate generators. They are not automatically reliable planners for bounded, consequential domains.

Formal planning and decision frameworks provide representations for:

- states;
- actions;
- transitions;
- probabilities;
- costs;
- goals;
- constraints;
- partial observability.

The professional opportunity is to connect natural-language intent to these decision structures.

A model may interpret the request. A planner may select a policy. A validator may admit the result. A broker may execute it.

This division of labor is more defensible than asking one model turn to understand, plan, authorize, and act.

## Caching: stop rebuying intelligence

Most agent systems repeatedly pay to reconstruct context and solve familiar cases.

An 80/20 ERRC cache asks:

- Which cases account for most demand?
- Which repeated steps can be eliminated?
- Which context reconstruction can be reduced?
- Which solution quality can be raised through validated exemplars?
- Which reusable policies should be created?

The cache may store:

- admitted observations;
- canonical domain objects;
- solver compatibility results;
- plans and policies;
- validated responses;
- failure classifications;
- receipts.

This moves the system from generative improvisation toward reusable intelligence infrastructure.

## Receipts: bind action to standing

A log says something happened. A receipt establishes correspondence.

A useful receipt includes:

- the exact subject;
- the admitted inputs;
- the actor or system identity;
- the authority used;
- the constructed artifact;
- the action executed;
- the result;
- timestamps and hashes where appropriate;
- replay instructions;
- unresolved uncertainty.

Receipts matter to your career because they transform invisible orchestration into inspectable proof.

## The stack is not a permission hierarchy

No protocol or model component should gain authority merely because it can produce an intent.

A safe topology is:

```text
Natural-language observation
    → semantic interpretation
    → admitted domain object
    → planner or policy selection
    → candidate construction
    → validation
    → authorized actuation
    → receipt
```

MCP exposes capability. A2A routes work. DSPy constructs semantic programs. Planning selects. Caches reuse. Receipts prove.

None of these should silently become the only DO path.

## Career positions in the stack

The stack creates several durable positions:

- capability/tool builder;
- semantic program engineer;
- agent interoperability architect;
- planning and decision engineer;
- evaluation and reliability engineer;
- governance and authority architect;
- AI cost and reuse engineer;
- product leader integrating the complete system.

You do not need to occupy every position. You need to know which layer you own and how it corresponds to the others.

## Field exercise: Locate your stack position

For each layer—models, MCP, A2A, DSPy, planning, caching, actuation, receipts—mark:

- unaware;
- familiar;
- used;
- built;
- operated in production;
- taught to others.

Choose one adjacent layer that would increase the value of your current strengths.

Do not learn every framework at once. Build one complete path from observation to receipt.
