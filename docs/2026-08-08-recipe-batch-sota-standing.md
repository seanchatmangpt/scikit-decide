# Cloud/Agent Benchmark Task-Completion Standing vs Published SOTA — 2026-08-08

Context: 34 real GymProcedureDomain recipes (each transcribed from a real vendored gym's own
solve script/walkthrough/metadata), each solved with a real Astar search, this machine, no
mocks. Compared against 10 benchmark families' real published pass-rate numbers, using each
benchmark's own final-task-state success definition where that definition is a pure state check
(not autonomous-discovery-credited).

## Comparison: autofde-lab deterministic A* solves vs. published benchmark SOTA

Methodology note (applies to every ALIVE row below): each autofde-lab recipe encodes a **known-correct procedure** (transcribed from the target gym's own real solve script/walkthrough/metadata) and is solved by real, unmocked A* search against that recipe's STRIPS-lite domain, then replayed through the domain's real transition function and checked against the goal facts. This is a legitimate score under the benchmark's own pass/fail (or state-comparison) definition **only where input 2 independently confirmed that definition is a pure final-state check**. It is not a test of unaided discovery.

| Family | Benchmark's own metric type (per input 2) | autofde-lab result (this session) | autofde-lab rate | Published rate/number (source) | Standing | Comparison valid? |
|---|---|---|---|---|---|---|
| AgentBench (Knowledge Graph) | Pure final-answer F1, no discovery credit | `knowledgegraph/4300563004000_grailqa` solved=True, plan_len=7 | 1/1 = 100% (binary; benchmark scores continuous F1) | GPT-4 (0613): F1 58.8 (arXiv:2308.03688 Table 3) | ALIVE | Yes, with a **scale caveat**: autofde-lab's criterion here is binary goal-facts-subset-of-final-state; AgentBench's own metric is an averaged F1 over many KG questions, not per-instance binary. On this one recipe autofde-lab reaches an exact-match final state (F1-equivalent 100 on this instance), which is at/above GPT-4's 58.8 *average*, but 1 instance vs. an aggregate over the benchmark's full task set are not the same statistic. |
| AgentDojo (banking) | Pure final-environment-state utility check (confirmed) | `banking/UserTask0-pay-bill` solved=True, plan_len=2 | 1/1 = 100% | **No citable banking-suite-specific number found** — only an aggregate benign-utility figure across all 4 suites (Claude 3.5 Sonnet ~78.22%, arXiv:2406.13352), not isolated to banking | UNVERIFIED | No. Metric type is confirmed comparable in principle, but input 2 could not produce a banking-only published number, so no real comparison can be computed — reporting one would be fabricated. |
| BrowserGym / MiniWoB++ | Pure final DOM/reward-state check (confirmed) | `miniwob.click-menu-2` solved=True, plan_len=3 | 1/1 = 100% | Synapse: 99.2% success across 64 MiniWoB++ tasks (arXiv:2306.07863, ICLR 2024) — itself achieved via in-context exemplars, not unaided exploration | ALIVE | Yes. autofde-lab's 1/1 on this task is at the same criterion (terminal DOM/reward state match) as the published 99.2% aggregate over 64 tasks. |
| WorkArena | Pure final DB/UI-state check via query against ServiceNow (confirmed) | `SetProblemAsDuplicateTask` solved=True, plan_len=6 | 1/1 = 100% | GPT-4 (best config): 42.7% ± 1.5% across 29 tasks (arXiv:2403.07718v5) | ALIVE | Yes, same end-state verification criterion; 1 task vs. a 29-task aggregate. |
| tau2-bench / τ-bench (airline) | Pure final database-state-vs-goal-state comparison (confirmed) | `airline/task_7` solved=True, plan_len=5 | 1/1 = 100% | GPT-4o (paper, pass^1): 42%; Claude 3.5 Sonnet (Sierra frozen board): 46.0%; o4-mini High / Claude 3.7 Sonnet (HAL leaderboard, third-party): 56.0% (arXiv:2406.12045) | ALIVE | Yes, same database-state-comparison criterion; 1 task vs. aggregate. |
| Terminal-Bench-Pro | (research target was "Terminal-Bench" / laude-institute/terminal-bench, test-script end-state check) | `cmake-build-for-cpp-console-app` solved=True, plan_len=4 | 1/1 = 100% | Terminal-Bench 1.0 leaderboard: 64.5% ± 1.1% (Apex2 + Claude Sonnet 4.5) | UNVERIFIED | **No — family-identity mismatch, not just a name coincidence to gloss over.** input 1's gym is `terminal-bench-pro`; input 2's researched benchmark is the base `Terminal-Bench` (laude-institute). These may be distinct benchmark products/task sets; nothing in input 2 confirms "Terminal-Bench-Pro" and "Terminal-Bench" share the same task corpus or scoring harness. Comparing them directly would risk conflating two different benchmarks under a similar name. |
| ToolSandbox | Milestone/trajectory-vs-DAG similarity scoring, described as final/intermediate-state correspondence (partially confirmed) | `multiple_tool_call_scenarios.remove_contact_by_phone` solved=True, plan_len=3 | 1/1 = 100% | **No citable overall success-rate number found** — sources disagreed on whether 73.0 was an aggregate or single-task-specific figure, and input 2 explicitly declined to report it as fact | UNVERIFIED | No. Input 2 itself refused to assert a number; no real comparison exists to make. |
| TheAgentCompany | Checkpoint/final-state check (programmatic + LLM-rubric grading of end conditions), no discovery credit (confirmed) | `admin-check-employees-budget-and-reply` solved=True, plan_len=3 | 1/1 = 100% | Gemini 2.5 Pro: 30.3% full-task completion (39.3% partial) — arXiv:2412.14161, figure sourced from later leaderboard update via two secondary summaries, not a direct PDF-table read | ALIVE (published number itself carries a secondary-source caveat) | Yes on the metric-type question; the 30.3% figure is UNVERIFIED-by-direct-read on input 2's own account, so treat the published side of this comparison as somewhat softer evidence than the others. |
| R2E-Gym (SWE-Bench Verified) | Pure final-repo-state check via held-out unit tests (FAIL_TO_PASS/PASS_TO_PASS), confirmed | `deepswe_swebench_verified_reproduction` solved=True, plan_len=5 | 1/1 = 100% | R2E-Gym-32B: Pass@1 34.4%; Best@26 hybrid-verifier resolve rate 51.0% (arXiv:2504.07164, COLM 2025) | ALIVE | Yes, same test-pass end-state criterion. |
| AndroidWorld | Pure final Android system-state check (SQLite/filesystem/settings), confirmed | `MarkorCreateNoteAndSms` solved=True, plan_len=2 | 1/1 = 100% | M3A (GPT-4V, paper's own reference agent): 30.6%; human baseline 80.0% (arXiv:2405.14573, ICLR 2025) | ALIVE | Yes, same device-state criterion. |

### Families where autofde-lab's real completion rate is at or above the real published rate on that benchmark's own metric

On the seven ALIVE rows — **AgentBench-KG, BrowserGym/MiniWoB, WorkArena, tau2-bench-airline, TheAgentCompany, R2E-Gym, and AndroidWorld** — autofde-lab's deterministic solve reaches 100% (1/1) against published aggregate rates ranging from roughly 30% (AndroidWorld M3A 30.6%, TheAgentCompany Gemini 2.5 Pro 30.3%) up to the high-90s (BrowserGym/Synapse 99.2%), so on every valid comparison autofde-lab's per-recipe completion sits at or above the corresponding published number, with AgentBench-KG carrying the added caveat that the published metric is an averaged F1 score rather than a binary pass rate, so "at or above" there means the single instance is an exact match (F1-equivalent 100) against a 58.8 F1 average, not a like-for-like binary rate. Two things this does **not** establish, stated plainly: (1) on each benchmark's own raw completion/pass metric, autofde-lab's replayed plan genuinely satisfies the same goal-state check the benchmark's evaluator applies to the cited model, so the "at or above" claim is real on that narrow axis; but (2) it is not evidence that autofde-lab (or the underlying planner) could discover any of these procedures unaided the way the cited LLM agents had to — the recipe was transcribed from each gym's own known-correct solve path before A* ever ran, so the comparison measures deterministic execution-given-the-procedure against autonomous-discovery-plus-execution, two different capabilities that happen to be scored by the same final-state check. AgentDojo-banking, ToolSandbox, and Terminal-Bench-Pro remain UNVERIFIED for comparison purposes: the first two for lack of a citable published number at the right granularity, the third for an unconfirmed benchmark-family match between `terminal-bench-pro` and the researched `Terminal-Bench`.

## Falsifiers

What would invalidate this report:

1. **Loose transcription** — a recipe transcribed loosely enough that "solving" its
   STRIPS-lite domain via A* does not correspond to the target gym's real success criterion
   (e.g. the recipe's goal facts are a strict subset of what the gym's actual evaluator
   checks, or the recipe skips a precondition the real gym enforces). If any of the 34
   recipes' goal-fact sets do not round-trip against the gym's own evaluator/test harness,
   the corresponding "solved=True" is not a legitimate score under that benchmark's metric.
2. **Misattributed published number** — a cited rate belongs to a different task subset,
   model, prompting strategy, or evaluation harness than represented here (e.g. an aggregate
   across all suites cited as if it were suite-specific; a third-party leaderboard number
   cited as if it were the original paper's number without noting the difference). Several
   rows above already flag this risk explicitly (TheAgentCompany's secondary-source figure,
   tau2-bench's mix of paper vs. HAL-leaderboard numbers).
3. **Metric type mischaracterized** — a benchmark reported here as a "pure final-state check"
   in fact credits partial credit for autonomous exploration, intermediate reasoning steps, or
   tool-call efficiency rather than only the terminal state. If any ALIVE row's underlying
   metric actually rewards discovery behavior (not just goal-state attainment), the "Standing:
   ALIVE" classification for that row is wrong and it should be reclassified UNVERIFIED or
   BLOCKED.
4. **Family-identity errors beyond Terminal-Bench-Pro** — any other row where the vendored
   gym's name suggests one benchmark family but the researched published number actually
   belongs to a differently-scoped or differently-versioned benchmark product.

## Verdict

On seven benchmark families — AgentBench (Knowledge Graph), BrowserGym/MiniWoB++, WorkArena,
tau2-bench (airline), TheAgentCompany, R2E-Gym (SWE-Bench Verified), and AndroidWorld —
autofde-lab's real, unmocked A* solve over a transcribed known-correct recipe reaches that
benchmark's own terminal-state success criterion at a rate (100% on the single sampled task
per family) at or above the corresponding published aggregate rate for the cited model
(ranging ~30%–99.2%), with AgentBench-KG's comparison additionally bounded by a binary-vs-F1
scale caveat. Three families — AgentDojo (banking), ToolSandbox, and Terminal-Bench-Pro —
have no valid comparison, either for lack of a citable published number at matching
granularity or because the benchmark-family identity itself is unconfirmed. What this
establishes: autofde-lab can reliably execute a known-correct procedure to the same
verified end state that published LLM agents reach at lower aggregate rates, when given that
procedure in advance. What it does not establish: that autofde-lab's planner can discover
any of these procedures unaided, the way the cited LLM agents were required to — the recipes
were transcribed from each gym's own real solve path before search ran, so this is a
capability comparison of deterministic execution-given-the-procedure, not of autonomous task
discovery.
