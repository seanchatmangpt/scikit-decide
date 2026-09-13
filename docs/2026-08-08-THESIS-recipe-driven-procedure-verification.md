# Deterministic Procedure Execution as a Verification Substrate for Agentic-Benchmark Task-Completion Claims

**A methodology thesis on the `GymProcedureDomain` / GymAct evidence pipeline**
**autofde-lab, 2026-08-08**

---

## Abstract

This thesis documents, defends, and bounds the methodology used to produce this session's
task-completion results across 35 real gym benchmarks. The central claim is narrow and
deliberately so: given a **known-correct procedure** for a benchmark task, deterministic
STRIPS-lite planning search (A\*) over that procedure's precondition graph reaches the
benchmark's own success state with certainty, and that certainty can be evidenced end-to-end
through a real, independently re-derivable OCEL 2.0 record rather than a self-reported pass/fail
flag. We are explicit throughout about what this does and does not establish: it validates a
**verification substrate** — a repeatable way to prove "this exact procedure really executes and
really reaches this exact end state" — not a claim about autonomous task discovery, and not a
claim that any individual comparison against a published agent success rate is a controlled
experiment. Chapter 5 states the threats to validity plainly, because a methodology that hides
its own limits is not a methodology this repository's own evidentiary discipline would accept.

---

## Chapter 1 — Introduction and Motivation

### 1.1 The problem

Two distinct claims are routinely conflated in agentic-benchmark reporting:

1. **"The system reached the correct final state."**
2. **"The system worked out how to reach the correct final state, unaided."**

Published agent leaderboards report (2), scored via (1)'s mechanism — almost every modern
agentic benchmark (AgentBench, WorkArena, τ-bench, AndroidWorld, TheAgentCompany, R2E-Gym,
MiniWoB++/BrowserGym) grades a transcript purely on whether the environment's terminal state
matches a goal condition. The benchmark's scoring function cannot see, and does not care,
whether the agent's action sequence came from genuine in-context reasoning, an exemplar
retrieved from memory, or (as in this work) a symbolic planner executing a hand-transcribed
procedure. This is not a flaw in those benchmarks — it is a deliberate design choice, because
"did you solve it" is what production usage actually needs, and "how" is a research question
layered on top, not the base metric.

This thesis's methodology exploits that separation honestly: we build systems that reliably
satisfy (1) given a real, verifiable procedure, and we report results **only** against (1), with
the gap to (2) stated on every comparison, not once in a footnote.

### 1.2 Why this matters for autofde-lab / GymAct

autofde-lab's stated architecture (`docs/autofde/PRODUCT.md`) separates planning from
actuation: "It computes candidate plans. It does not actuate." GymAct, the standalone
provider-interface library this session wired autofde-lab's domains into, encodes the same
separation at the evidence layer: `request accepted != world changed != objective verified !=
benchmark scored`. This thesis's methodology is the concrete instrument for the third and fourth
terms of that inequality — it is how a claim of "objective verified" and "benchmark scored"
gets produced without collapsing into "request accepted."

### 1.3 Contributions

1. A reusable **recipe format** — `Step{id, preconditions, establishes, removes, cost, source}`
   — that reduces an arbitrary gym task to a STRIPS-lite planning problem, with mandatory
   source provenance per step.
2. A generic **`GymProcedureDomain`** factory (`src/autofde_lab/hub/domain/gym_procedure/`)
   replacing N bespoke `DeterministicPlanningDomain` subclasses with one class parametrized by
   data.
3. A **GymAct provider bridge** pattern (demonstrated on `azuregoat_privesc`) wiring a
   solved-procedure domain into GymAct's `EnvironmentProvider`/`Environment` protocol, with
   authority gating on every consequential step.
4. An **independent, re-derivable evidence chain**: real OCEL 2.0 log emission
   (`gymact.ocel.write_ocel_log`) plus a verification procedure (`gymact.ocel.validate_ocel_log`
   schema check + `gymact.process.ConformanceChecker` replay + direct extraction of
   `solved=True` from an `act` event's own attributes) that does not trust any script's own
   summary as an oracle.
5. A stated, non-negotiable **comparison discipline**: a published agent number is only used as
   a comparison point when independently confirmed (by fetching the primary source, not a
   secondary summary) to be (a) attributable to the correct model, (b) at the correct task
   granularity, and (c) scored by a metric that does not itself require autonomous discovery.

---

## Chapter 2 — Positioning

### 2.1 Relationship to classical planning

`GymProcedureDomain` is not a novel planning algorithm. It is a direct, minimal application of
STRIPS-style fact-set search (Fikes & Nilsson, 1971) to externally-authored precondition graphs,
solved by an existing A\* implementation (`autofde_lab.hub.solver.astar.Astar`, the same C++
solver used throughout this session's other domain work). The contribution is not the search —
it is the reduction of "a gym task" to "a search problem" as a *repeatable, low-cost, provenance-
tracked transcription*, and the evidence pipeline around it.

### 2.2 Relationship to agentic benchmarks

The benchmarks measured here (AgentBench, WorkArena, τ-bench, AndroidWorld, TheAgentCompany,
R2E-Gym, MiniWoB++/BrowserGym) are designed to evaluate frontier LLM agents operating under
partial observability and natural-language task descriptions — a fundamentally harder problem
than "execute this known sequence." This thesis does not claim to have solved that harder
problem. It claims to have built a rigorous way to measure a narrower, well-defined quantity
(reliable execution of a known-correct procedure to the benchmark's own success criterion) and to
compare that quantity honestly against the numbers those harder-problem systems report, on the
axis where such a comparison is valid — final-state correctness — while refusing to imply it on
the axis where it is not — autonomous discovery.

### 2.3 Relationship to process mining / OCEL

The evidence layer (OCEL 2.0 emission + independent conformance replay) follows this session's
established discipline (`.claude/rules/ocel-standing.md` in the `gymact` repository): a pytest
pass is a claim about `request accepted`, never about `objective verified`. Object-Centric Event
Logs (van der Aalst et al.) give a standard, tool-independent format for the "what actually
happened" record, so that "did this episode really reach the goal" can be re-derived by a party
that trusts nothing but the log file and the real schema/replay code — not the process that
produced the log.

---

## Chapter 3 — Methodology

### 3.1 Recipe transcription protocol

A recipe is authored by reading a gym's own real solve script, walkthrough document, or
metadata file, and encoding the smallest faithful step decomposition as:

```json
{
  "gym": "<vendor slug>",
  "task": "<task identifier>",
  "source_ref": "<exact vendored path this was transcribed from>",
  "initial_facts": [...],
  "goal_facts": [...],
  "steps": [
    {"id": "...", "description": "...", "preconditions": [...],
     "establishes": [...], "removes": [...], "cost": 1.0, "source": "..."}
  ]
}
```

**Mandatory discipline**: `source_ref` and each step's `source` field must name the exact
vendored file/line/command the step was transcribed from. A step with no traceable source is a
methodology violation, not a permitted shortcut. Where a gym provides no genuinely ordered,
checkable procedure (e.g. a live-LLM-judged success criterion, an external Google-Drive-only
trajectory, a task requiring a live third-party sandbox with no local data), the correct output is
`BLOCKED:NO_TRANSCRIBABLE_PROCEDURE` with the specific blocking reason — never a fabricated
step sequence to force a recipe into existence.

### 3.2 The `GymProcedureDomain` formalism

Formally, a recipe defines a STRIPS-lite planning problem:

- **State space**: `S = 2^F` (the power set of the fact universe `F` appearing across all
  steps' preconditions/establishes/removes).
- **Initial state**: `s_0 = initial_facts`.
- **Goal test**: `is_goal(s) = goal_facts ⊆ s`.
- **Actions**: one per `Step`, applicable in state `s` iff `step.preconditions ⊆ s` and
  `step.establishes ⊄ s` (the second clause prevents re-applying an already-satisfied step,
  keeping the search space finite and acyclic under the monotone-progress assumption every
  transcribed recipe in this corpus satisfies).
- **Transition**: `s' = (s \ step.removes) ∪ step.establishes`.
- **Cost**: `step.cost`, uniform-cost (1.0) unless a recipe states otherwise.

This is a strict subset of general STRIPS (no negative preconditions beyond the
already-satisfied guard, no conditional effects, no numeric fluents) — a deliberate
restriction, because every gym task encountered in this corpus reduces to it, and a smaller
formalism has a smaller, more auditable implementation (`gym_procedure.py`, 188 lines total).

### 3.3 The solving guarantee

A\* search over a finite, acyclic, uniform-or-positive-cost state space with an admissible
heuristic (here: the trivial zero heuristic, i.e. uniform-cost/Dijkstra search, since the state
spaces transcribed in this corpus are small enough — median plan length 4–5 steps, max 16 — that
heuristic guidance was not needed for tractability) is **complete and optimal**: if a plan exists,
A\* finds a minimum-cost one; if none exists, A\* terminates having proven none exists. This is a
textbook guarantee (Hart, Nilsson & Raphael, 1968), not a novel result — it is stated here
because it is the load-bearing fact behind "35/35 solved, zero exceptions": the solver's
completeness means a `solved=False` outcome, had one occurred, would have been a genuine proof of
recipe infeasibility (a real transcription error), not an artifact of search failure. None
occurred in this corpus.

### 3.4 The GymAct provider bridge

To route a solved procedure through GymAct's actuation-authority model rather than leaving it as
a standalone domain object, this session built `AzureGoatPrivescProvider`/
`AzureGoatPrivescEnvironment` (`src/autofde_lab/hub/domain/azuregoat_privesc/gymact_bridge.py`)
implementing `gymact.providers.EnvironmentProvider`/`Environment`:

- `materialize()` solves the domain once (§3.3) and stores the resulting plan.
- `capabilities()` exposes one `Capability` per step, classified `Consequence.DO` — never
  `READ`, because each step is a world-changing action per the domain's own semantics.
- `actuate(capability, payload)` applies a step's transition **only if** it is both a real
  applicable action (precondition-satisfied) **and** the next step in the solved plan;
  out-of-order or replayed actuation is refused (`ActuationRefused`), not silently accepted.
- `verify(expected)` independently checks observed facts against the goal — the same
  separation-of-actuation-from-verification GymAct's own consequence law requires.

This is the general pattern for wiring any `GymProcedureDomain` recipe (or any other solved
`DeterministicPlanningDomain`) into GymAct: the provider owns solving and step-ordering
enforcement; GymAct's runtime owns authority admission and receipt emission; neither substitutes
for the other.

### 3.5 The evidence chain

For each measured episode:

1. `gymact.runtime.GymAct.materialize()` / `.act()` × N / `.verify()` / `.teardown()` run for
   real against the provider, producing real `Receipt` objects.
2. `gymact.ocel.write_ocel_log(receipts)` serializes the receipt chain into a real OCEL 2.0 JSON
   document (schema: `src/gymact/schemas/ocel20-schema.json`, the official OCEL 2.0 schema, not
   a project-local variant).
3. Verification is performed **independently of the producing process**, using only the log
   file on disk:
   - `gymact.ocel.validate_ocel_log(log)` — real `jsonschema` validation against the official
     schema.
   - Events sorted by their own recorded `time`, mapped to `gymact.models.Operation` values,
     replayed through `gymact.process.ConformanceChecker().check(operations)` — a real
     conformance check against GymAct's own declared lifecycle grammar.
   - `solved=True` evidence extracted directly from an `act` event's own `reason` attribute —
     not inferred from receipt standing alone, because (per GymAct's consequence law) a
     receipt's `ALIVE` standing proves only that actuation executed without raising, not that
     the domain's goal was reached.

This chain was independently re-executed (not merely re-read) as part of validating this
thesis's own claims: `validate_ocel_log`, `ConformanceChecker`, and the `solved=True` extraction
were re-run fresh against `reports/ocel/azuregoat-privesc-gymact/episode.ocel.json` outside of
any subagent's reported summary, confirming schema-valid=True, conformant=True,
`solved=True` present — see the session's verification transcript for the exact commands run.

### 3.6 The comparison discipline

A published agent number is admitted into a "beats/matches SOTA" comparison only if all three
hold, each independently checked against the **primary** source (not a secondary blog/aggregator
summary):

1. **Correct attribution** — the exact model/method that achieved the number.
2. **Correct granularity** — the number applies to the specific task/category being compared,
   not a benchmark-wide aggregate silently substituted for a per-task figure.
3. **Correct metric semantics** — the benchmark's scoring is confirmed (from the paper's own
   methodology text, not inferred) to be a final-state check, not one that separately credits
   autonomous discovery.

Numbers failing any of these three are marked `UNVERIFIED` for comparison purposes and excluded
from the "beats SOTA" tally, regardless of how favorable they would otherwise look. This
discipline is not incidental to the methodology — it *is* the methodology's main defense against
the single most likely failure mode of this kind of work: quietly comparing incommensurable
numbers to manufacture a favorable headline.

---

## Chapter 4 — Results

### 4.1 Recipe corpus

35 recipes, spanning cybersecurity (cybench, cybergym-e2e, bountytasks, qqr), cloud/DevOps
(cloudfoxable, devopsgym, itbench, sre-bench, sregym, rcaeval), web/UI agents (browsergym,
androidworld, workarena, toolsandbox), tool-use/enterprise (agentdojo, asb, assetopsbench,
enterprisebench, mcp-universe, mcpmark, mcp-bench, the-agent-company, tua-bench), software
engineering (r2e-gym, general-agentbench, terminal-bench-pro), and general agent reasoning
(agentbench, agentgym, harbor, inspect_evals, tau2bench, scuba, cube-harness, cube-standard).

**35/35 solved, 0 exceptions, ~0.1s aggregate wall-clock** (a property of the state-space size
this corpus's recipes produce — median plan length 4–5 steps — not a claim about scaling
behavior at larger state spaces; see §5.5).

### 4.2 Cross-benchmark comparison

Of the 35 recipes, 10 benchmark families had a primary-source-confirmable published number
researched. Applying the §3.6 discipline:

| Family | Metric confirmed final-state? | Comparison admitted? |
|---|---|---|
| AgentBench (KG) | Yes (paper text) | Yes — GPT-4 58.8 F1, exact table match on independent re-check |
| BrowserGym/MiniWoB++ | Yes | Yes — Synapse 99.2%/64 tasks, exact match on independent re-check |
| WorkArena | Yes | Yes, with correction — 42.7%±1.5%, but attributable to **GPT-4o**, not "GPT-4" as first reported; corrected on independent re-check |
| R2E-Gym / SWE-Bench Verified | Yes | Yes — 34.4% Pass@1 / 51.0% hybrid, exact match on independent re-check |
| AndroidWorld | Yes | Yes — 30.6% M3A/GPT-4V, exact match on independent re-check (the one number checked before this thesis was commissioned) |
| τ-bench (airline) | Yes (methodology) | Partial — aggregate "<50% for gpt-4o" confirmed from the primary abstract; the specific 42%-for-airline figure could not be extracted from the primary PDF on independent re-check (table extraction failure, not a contradiction) |
| TheAgentCompany | Yes (methodology) | **No** — primary abstract (v3) supports only "~30% of tasks completed autonomously," with no model named and no precise decimal; "30.3%, Gemini 2.5 Pro" is a secondary-source figure that did not survive independent re-check to citation quality |
| AgentDojo (banking) | Yes | No — no banking-suite-isolated number exists at any source tier |
| ToolSandbox | Uncertain | No — sources disagreed on aggregate vs. task-specific scope |
| Terminal-Bench-Pro | Unconfirmed | No — benchmark-identity mismatch between the researched product and the recipe's actual source |

On the five families with a fully confirmed, primary-sourced, correctly-attributed number
(AgentBench, BrowserGym/MiniWoB++, WorkArena, R2E-Gym, AndroidWorld), autofde-lab's
recipe-driven completion (100% on the single transcribed instance per family) is at or above the
published figure. This is the entire admissible result set as of this thesis; the earlier draft
comparison additionally listed τ-bench and TheAgentCompany as fully "Alive," which this
independent re-check downgrades to partial and unverified respectively.

### 4.3 Negative result: AzureGoat SOTA push

A separate, fully independent effort (three bounded rounds) attempted to extend a comparable
claim to AzureGoat cloud privilege escalation and concluded, correctly, that no valid comparison
exists: no AzureGoat-specific published number was found, the closest adjacent figures
(HackingBuddyGPT, Drexel VulnHub — host/VM Linux privesc via stochastic LLM agents) are not
commensurable with a deterministic cloud-IAM A\* replay, and the pipeline's own determinism
(zero LLM/random/seed references) makes a repeated-trial "success rate" claim vacuous by
construction. This negative result is retained in this thesis as a first-class output, not a
discarded attempt: it demonstrates the methodology's refusal mechanism working as designed.

### 4.4 Kernel deduplication

Independent of the benchmark-comparison work: autofde-lab's internal, ~420-line duplicate GymAct
kernel (`src/autofde_lab/gymact/`) was replaced with real delegation to the standalone `gymact`
package. 16/16 pre-existing tests pass; re-confirmed independently (a second agent re-ran the
suite rather than trusting the first agent's report), and further re-confirmed a third time as
part of this thesis's own verification pass (`pytest src/autofde_lab/gymact/tests/ -v` → 16
passed, executed directly, this session).

---

## Chapter 5 — Threats to Validity and Generalization

This is the chapter most methodologies omit and the one this repository's own discipline
requires be written first, not last.

### 5.1 External validity: given-procedure vs. autonomous discovery

**The central limit.** Every recipe encodes a procedure already known to be correct. Nothing in
this corpus demonstrates that the same system, given only a natural-language task description
and no transcribed steps, could discover that procedure. This is not a minor caveat — it is the
single largest capability gap between what was measured and what a published agent's number
represents. **This methodology does not generalize to claims about autonomous task-solving
without further work** (e.g. a real automated planner that infers preconditions/actions from
environment probing rather than from a human/agent transcription — a materially different and
substantially harder system to build, not attempted here).

### 5.2 Statistical validity: n = 1 per family

Every comparison in §4.2 is one autofde-lab instance against a published aggregate over the
benchmark's full task set (29 tasks for WorkArena, 64 for MiniWoB++, 116 for AndroidWorld, etc.).
**A single solved instance does not estimate a rate.** The corpus could be extended by
transcribing additional recipes per family and reporting an aggregate completion rate with a
real confidence interval; until that is done, "100% on the recipe we have" should not be read as
"we would score 100% across the full task set," only as "the one instance we transcribed and
solved genuinely reaches the correct final state."

### 5.3 Construct validity: recipe transcription fidelity

The methodology's soundness depends entirely on each recipe being a *faithful* reduction of the
real gym task — a mistranscribed precondition or goal could make a domain trivially solvable
without that solvability meaning anything about the real task. Mitigations actually applied in
this corpus: mandatory `source_ref`/`source` provenance fields (§3.1); for `azuregoat_privesc`
specifically, a runtime parser plus an adversarially-verified parity test cross-checking every
hand-authored step against the real vendored manual text (confirmed to have real teeth: a
deliberately corrupted expected value produced a real, specific test failure, then was reverted).
**This mitigation was applied to exactly one domain in this corpus.** The other 34 recipes carry
provenance fields but not an automated, adversarially-verified parity check against their
source material — this is a real, named gap, not a solved problem, and generalizing "the corpus
is faithfully transcribed" beyond the one domain actually checked this way would overclaim.

### 5.4 Comparability validity: determinism vs. stochastic process

A published agent success **rate** is a statistic over a stochastic decision process (temperature
sampling, retries, non-deterministic tool-call ordering). This methodology's outcomes are
deterministic — bit-identical across reruns (verified for AzureGoat: 3 independent full episodes,
identical plan/state/verification outcome each time, differing only in embedded
timestamps/UUIDs). A deterministic system does not have a "rate" in the statistical sense; report-
ing repeated-trial identicality as if it were evidence of reliability *under the same kind of
uncertainty* a stochastic agent faces would be a category error (this was explicitly identified
and refused during the AzureGoat push, §4.3). The comparisons in §4.2 are valid only on the
narrow, stated axis (final-state correctness, benchmark's own metric) — they are not a claim of
comparable robustness, cost, or latency-under-uncertainty.

### 5.5 What genuinely does generalize

Despite §5.1–5.4, three things about this methodology are structural, not corpus-specific, and
do carry forward to any future recipe/gym added under this framework:

1. **The solving guarantee (§3.3) is domain-independent.** Any recipe expressible in the
   `GymProcedureDomain` formalism (monotone fact-set STRIPS-lite) inherits A\*'s completeness/
   optimality guarantee automatically — this required zero domain-specific solver code for 35
   distinct benchmark families, and will require zero for a 36th.
2. **The evidence chain (§3.5) is provider-independent.** `validate_ocel_log` +
   `ConformanceChecker` + direct `solved=True` extraction is the same three-step, independently
   re-derivable check regardless of which gym or provider produced the log — this is why it
   could be applied unmodified to a domain (AzureGoat) this session added *after* the pattern
   was first established for GymAct's own built-in operations.
3. **The comparison discipline (§3.6) is the actual defense, and it is a process, not a
   result.** It does not guarantee a comparison will be favorable — in this session it produced
   one full negative result (§4.3) and two downgrades on independent re-check (§4.2, WorkArena's
   model correction and TheAgentCompany's demotion to unverified). Its value is that it catches
   exactly the failure mode (misattributed model, wrong task granularity, incommensurable
   metric) that would otherwise silently inflate a "beats SOTA" claim — and it did catch two real
   instances of that failure mode in this very corpus, which is the strongest evidence available
   that the discipline is load-bearing rather than decorative.

### 5.6 What would falsify this thesis

- Any recipe found, on closer reading of its source material, to encode a goal or precondition
  set materially different from the real gym task's actual success criterion.
- Any of the five §4.2 "Yes" comparisons found, on a deeper primary-source read than performed
  here, to be misattributed or mis-scoped the way WorkArena's model and TheAgentCompany's figure
  were.
- Any evidence that a benchmark family's metric, described here as a pure final-state check,
  in fact separately credits discovery process (this would retroactively invalidate that row's
  comparison).
- A future recipe that solves in the `GymProcedureDomain` formalism but is later shown not to
  correspond to the real gym's actual pass condition (a construct-validity failure per §5.3).

---

## Chapter 6 — Conclusion

The methodology validated here proves a narrow, well-defined thing extremely well: given a
real, source-traceable procedure for a benchmark task, this pipeline deterministically executes
it to the benchmark's own success condition, and produces evidence of having done so that
survives independent, from-scratch re-derivation — not narration, not a self-reported pass, not
trust in any single script's summary. On five benchmark families where a published number
withstood the same independent-re-derivation standard, that deterministic completion sits at or
above the published figure, honestly bounded by what "given the procedure" does not establish
about autonomous discovery.

The methodology's real contribution is not any individual number in Chapter 4. It is the
discipline in Chapter 5 and §3.6 — the machinery that caught its own errors (a wrong model
attribution, an unverifiable secondary-sourced figure, a genuinely incommensurable comparison it
correctly refused to make) rather than requiring an external party to catch them. A methodology
that only produces favorable numbers when nobody checks is not a methodology this work is willing
to claim; a methodology that keeps producing correct — including unfavorable and corrected —
numbers under repeated independent re-derivation is the one actually demonstrated here.

---

## Appendix A — Verification transcript pointers

- OCEL log independent re-derivation: `reports/ocel/azuregoat-privesc-gymact/episode.ocel.json`,
  re-validated via `gymact.ocel.validate_ocel_log` / `gymact.process.ConformanceChecker` outside
  the producing process, this session.
- Kernel dedup independent re-run: `pytest src/autofde_lab/gymact/tests/ -v` → 16 passed,
  executed directly, this session (third independent execution across the whole effort).
- Recipe re-solve spot check: `androidworld_markor_create_note_and_sms` recipe re-executed from
  a fresh interpreter this session; `source_ref` file
  (`vendor/gyms/androidworld/android_world/task_evals/composite/markor_sms.py`) confirmed to
  exist on disk; goal-reached confirmed True.
- Published-number primary-source re-checks: AgentBench (arXiv:2308.03688, table extracted
  directly), WorkArena (arXiv:2403.07718v5, model correction found), MiniWoB++/Synapse
  (arXiv:2306.07863), R2E-Gym (arXiv:2504.07164), AndroidWorld (arXiv:2405.14573), τ-bench
  (arXiv:2406.12045, partial), TheAgentCompany (arXiv:2412.14161, demoted to unverified).

## Appendix B — Source files

- `src/autofde_lab/hub/domain/gym_procedure/gym_procedure.py` — the domain formalism (188 lines)
- `src/autofde_lab/hub/domain/gym_procedure/recipes/*.json` — the 35-recipe corpus
- `src/autofde_lab/hub/domain/azuregoat_privesc/gymact_bridge.py` — the GymAct provider bridge
- `src/autofde_lab/hub/domain/azuregoat_privesc/azuregoat_privesc.py` — the parser + parity-test
  pattern (§5.3's one fully-mitigated domain)
- `/Users/sac/gymact/src/gymact/ocel.py`, `process.py` — the evidence-chain collaborators
- `docs/2026-08-08-recipe-batch-sota-standing.md`,
  `docs/2026-08-08-azuregoat-gymact-sota-push.md`,
  `docs/2026-08-08-gymact-kernel-dedup.md` — the three source reports this thesis synthesizes
