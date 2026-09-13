# AutoFDE Lab Crown Requirements

**Version:** 26.8.7

AutoFDE Lab is the experimental, falsification, self-play, benchmarking, planning, process-mining, and manufacturing environment for systems whose production invariant is:

\[
O \rightarrow O^* \rightarrow \Pi \rightarrow \mu \rightarrow E \rightarrow O' \rightarrow V \rightarrow R
\]

where `O` is observation, `O*` admitted observation, `Pi` selected plan/policy, `mu` lawful manufacture, `E` authorized execution, `O'` independently observed consequence, `V` verification, and `R` replayable receipt.

The primary optimization target is **Verified Consequential Throughput (VCT)**:

\[
VCT = \frac{\text{independently verified valuable state transitions}}{\text{wall time} \times \text{cost} \times \text{human attention}}
\]

The design goal is **maximum lawful verified consequence with minimum repeated cognition**.

## Non-negotiable laws

1. **Zero unreceipted actuation.** No production-capable operation may alter external state outside the admitted BRCE authority boundary.
2. **Candidate is not authority.** Planner, optimizer, workflow, agent, or model output is only a candidate.
3. **Acknowledgement is not effect.** Command accepted, action performed, physical/organizational effect, desired postcondition, and verified objective are distinct states.
4. **Independent verification.** Executor self-report alone does not establish a consequential postcondition when independent observation is possible.
5. **Refusal is positive evidence.** Typed refusal preserves more standing than unverifiable success.
6. **Importability is not execution.** Import, compile, mock, or structural applicability cannot establish runtime `ALIVE`.
7. **No Crown without evidence.** Standing may never exceed its evidence.

## Standing

Positive ladder:

`UNKNOWN < CANDIDATE < STRUCTURAL < PARTIAL_ALIVE < ALIVE < ADOPTED`

Typed outcomes include `BLOCKED`, `UNSUPPORTED`, `REQUIRES_CONFIGURATION`, `REFUSED`, `UNCERTAIN`, and `STALE`.

`ADOPTED` requires real external operational/customer evidence. Internal fixtures cannot establish adoption.

## Planner maximalism

AutoFDE Lab preserves heterogeneous planning and decision machinery rather than collapsing every decision into frontier-model inference. The registered solver ecology and delegated engines may include deterministic search, width search, stochastic shortest path, MDP, POMDP, belief-space planning, VI/PI, MCTS, RL/IRL, scheduling, mathematical optimization, RDDL, PDDL, PPDDL, temporal planning, Unified Planning engines, and learned policies.

Every admitted problem may expose a structural signature `sigma(O*)`. Applicability is resolved before empirical preference. An untested applicable competitor prevents a false `HOT` crown.

## QLever / simdjson selection architecture

Choosing mature machinery must converge from deliberation toward indexed retrieval:

\[
I:(\sigma, objective, scale, hardware, environment) \rightarrow \text{Pareto planner candidates}
\]

Cheap structural classification precedes expensive interpretation. Large semantic possibility must not imply full possibility-space traversal per decision. Experimental planner receipts accumulate durably and feed a Pareto selector; ties remain ties.

### Three-speed intelligence

- **COLD:** novel topology; models + planners + self-play + falsification generate evidence.
- **WARM:** indexed evidence narrows execution to a bounded Pareto candidate set.
- **HOT:** an exact, sufficiently repeated, fully covered signature routes directly to admitted specialized machinery. Frontier-model tokens may be zero.

**Cold discovery manufactures future hot paths.**

## Cognition compilation

Repeated verified `HOT` executions that still consume frontier-model tokens are candidate technical debt. Successful expensive cognition should be examined for admission, deterministic manufacture, caching, and reuse. A compilation finding is never itself authority to rewrite or actuate.

## Durable empirical evidence

Planner evidence is append-only and distinct from artifact caching. Exact replay may be idempotent, but distinct repeated runs must remain visible because repetition is evidence. Process restart must not erase the receipts that justified a selection regime.

## Closed-loop metrics

Every flagship should expose at least:

- verified transitions and verified value;
- wall time;
- monetary cost;
- human attention/interventions;
- frontier-model tokens;
- warm/hot reuse ratio;
- causal diameter;
- uncertain/reconciliation outcomes;
- replay success;
- Little's Law quantities when meaningful.

For workflow flow control:

\[
L = \lambda W
\]

WIP with zero throughput is infinite wait, not zero wait.

The causal loop is decomposed across observation, propagation, admission, decision, command propagation, actuation, consequence observation, and verification. Amdahl-style analysis must expose when further cognition acceleration cannot materially accelerate the full causal loop.

## Authority-narrowing handoffs

Agent or planner handoffs require an exact schema identity, evidence lineage, and delegated authority that is a subset of the parent's capability and resource scope. A handoff may narrow authority; it may never broaden it.

## Independent verifier composition

Multiple verifier identities may corroborate one exact content-bound subject and one exact postcondition. Repeating the same verifier does not create independence. Subject mismatch, postcondition mismatch, insufficient independence, or any verifier rejection is a typed refusal.

## Causal-local placement

Stable manufactured controllers may be placed closer to effectors only after authority and safety admission. Placement minimizes causal diameter among admitted candidates. A fast unauthorized or unsafe edge controller cannot outrank a slower lawful controller. Equal measured causal diameter remains a tie.

## ForwardBench vendor identity

For every pinned vendor, three identities must agree:

1. semantic lock pin;
2. superproject Git gitlink;
3. materialized vendor-owned Git worktree `HEAD`.

A directory beneath `vendor/gyms` may not impersonate a vendor merely because Git discovers the parent repository. Uninitialized gitlinks are `PINNED_UNMATERIALIZED`; populated parent-inheriting directories are refused; wrong vendor `HEAD` is `REFUSED:VENDOR_REVISION_MISMATCH`.

Fleet materialization may initialize only admitted unmaterialized gitlinks and must never overwrite an existing drifted/refused vendor to make a test green.

## Competitive benchmark court

AutoFDE may only claim a competitive crossover when baseline and challenger use:

- the exact same workload identity;
- the exact same verifier identity;
- identical repetition checkpoints;
- verified consequences rather than raw task attempts.

Canonical repetition checkpoints include `N = 1, 10, 100, 1000` and may extend to `10000`.

The target is a persistent crossover in cost per verified consequence, not a one-off win.

## Palantir parity gates

Palantir parity is the floor, not the differentiator. `P1` through `P7` are:

- **P1:** operational ontology objects, links, functions/actions;
- **P2:** fine-grained identity-bound governance and audit;
- **P3:** natural-language and programmatic FDE operation;
- **P4:** safe branch -> validation -> review -> merge/deploy;
- **P5:** real heterogeneous enterprise integrations;
- **P6:** repeatable local/cloud/edge deployment;
- **P7:** end-to-end traceability across planning, manufacture, and execution.

## Differentiator gates

`D1` through `D8` are:

- **D1:** formal planner breadth and measured specialization;
- **D2:** indexed empirical selection replacing generalized reasoning on mature paths;
- **D3:** independent postcondition verification as a universal consequential primitive where possible;
- **D4:** open semantic portability without proprietary ontology lock-in;
- **D5:** persistent repeated-task economic crossover against model-centric baselines;
- **D6:** measured causal-distance reduction from lawful local controllers;
- **D7:** reproducible content-bound receipts and replay across the causal chain;
- **D8:** successful cold-path cognition becoming durable indexed/manufactured capability.

A claim of “beyond Palantir” is mechanically closed until all `P1-P7` and `D1-D8` have evidence-backed `SATISFIED` standing.

## Cloud-first validation law

Implementation work must exhaust the available local/cloud execution environment before moving failures to CI. CI is an admission layer, not the first debugger.

For the current branch, cloud-local validation can execute Python, SQLite, and real local Git/submodule fixtures. The current cloud image does **not** contain Docker, kind, kubectl, QLever, or Rust; work requiring those runtimes must remain `BLOCKED`/`PARTIAL` until executed in an environment that actually provides them.

## Crown experiment

The canonical end-to-end experiment is:

\[
\text{admit} \rightarrow \text{manufacture} \rightarrow \text{select} \rightarrow \text{plan} \rightarrow \text{authorize} \rightarrow \text{actuate} \rightarrow \text{observe} \rightarrow \text{verify} \rightarrow \text{receipt} \rightarrow \text{mine} \rightarrow \text{replay} \rightarrow \text{reuse}
\]

Repeated equivalent executions must show whether the system migrates `COLD -> WARM -> HOT` while retaining identical or stronger authority and verification guarantees.

AutoFDE Lab therefore targets an **experimental compiler for turning intelligence into indexed, authority-bounded, locally executable, independently verifiable causal machinery**.
