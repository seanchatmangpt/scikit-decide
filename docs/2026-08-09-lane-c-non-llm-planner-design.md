# Lane C — a real, non-LLM planner-driven attempt against sregym

**Status at time of writing: build complete, real live trial in flight.** This document
covers the investigation and design; the trial's real terminal result is appended once it
lands (see "Real trial result" below — filled in after the run completes, never
pre-written).

## Why this exists

Direct instruction this session, mid-investigation of the `stratus`/LiteLLM tool-calling
crash (`docs/2026-08-09-sregym-stratus-llm-attempt-terminal-result.md`): "you should not
default to LLM always. use all the planning available." This repo's own `fabric catalog`
(run live this session) already registers real, non-LLM planners (`Astar`, `BFWS`, `IW`,
`RIW`, `MCTS`, `POMCP`) and a bounded-structured solver (`DSPyPolicy`) — none of them had
ever been pointed at a real external benchmark task.

## Investigation, real and cited (4 parallel Explore agents, this session)

1. **sregym's real MCP tool server** (`vendor/gyms/sregym/mcp_server/*.py`) is a genuine
   SSE-over-HTTP server; every tool implementation (`get_traces`, `get_services`,
   `get_metrics`, `exec_kubectl_cmd_safely`, `submit`, ...) is a plain, LLM-free Python
   function — zero `litellm`/LLM code in any server-side implementation, confirmed by direct
   grep. `exec_kubectl_cmd_safely` is real (AST-parsed via `bashlex`, single-command-only,
   no pipes/redirects) with an optional whitelist gate that is **off** in the real deployed
   config.
2. **sregym's fault-type space**: 60 real `recover_<fault_type>` methods across 10 injector
   classes; 123 real registered `problem_id`s (this repo's own prior "~90/~34-Ported" figures
   were undercounts, corrected here). Mitigation grading is **mechanical/LLM-free for all
   123** active problems (`kubectl`/Prometheus state comparison). Diagnosis grading is
   **LLM-judged free text for 96/97** active diagnosis-graded problems
   (`LLMAsAJudgeOracle`) — the fault itself is mechanically detectable (deterministic image-
   string/status-reason signals), but the *scoring* of the diagnosis submission is not.
3. **`DSPyPolicy`** (`src/autofde_lab/hub/solver/dspy_policy/dspy_policy.py`) is already
   wired to the same local server (`default_lm()`, line 56-62) and is architecturally immune
   to the crash that killed `stratus`: it drives the model via `dspy.Predict` over a typed
   `dspy.Signature` (DSPy's own text-completion/structured-parsing layer), never OpenAI-
   native `tool_calls`/`bind_tools`. Not used in this build (see "Scope" below) but confirmed
   as a real, available escalation path if a future sregym problem's decision complexity
   ever warrants search/generation rather than a closed-form rule.
4. **`k8s_goat_rbac_escalation`** (this repo's own in-repo gym) is confirmed synthetic
   (in-memory, no live cluster), Astar-solved (real, re-run this session, 1 passed in
   0.20s) — real evidence planning works on this problem *shape* in principle, not evidence
   against a live cluster. `GymProcedureDomain` is the real, reusable Recipe-based pattern
   all 5 existing gym domains converged on.

## Design: what was actually built

`vendor/gyms/sregym/clients/autofde_lab_planner/driver.py` (committed locally within the
submodule, never pushed to `origin/SREGym-SREGym`) — a new sregym agent, registered in
`agents.yaml` as `autofde_lab_planner` (`container_isolation: false`, matching the vendored
`tierzero` agent's precedent, no container image build needed).

**It makes zero LLM calls.** The `misconfig_app` fault class has a closed-form correct
answer — one deployment's running image diverges from its own app's canonical baseline — so
it is solved by a real, typed, observation-driven decision procedure, not by LLM generation:

- **Diagnosis stage** (read-only, matching `diagnosis_agent_config.yaml`'s own
  `exec_read_only_kubectl_cmd` tool restriction): lists the real, live hotel-reservation
  deployments (`kubectl get deployments`), observes each one's real running image, and
  mechanically flags whichever diverge from
  `sregym.service.apps.hotel_reservation.HOTEL_RESERVATION_APPLICATION_IMAGE` (the app's own
  canonical config). Submits a diagnosis built only from those observations.
- **Mitigation stage** (matching `mitigation_agent_config.yaml`'s mutating
  `exec_kubectl_cmd_safely`): for each mismatched deployment, observes its real container
  name and executes `kubectl set image deployment/<name> <container>=<canonical> -n
  hotel-reservation`, then submits.

**Integrity constraint, load-bearing and checked by `tests/sota/
test_sregym_autofde_planner_decision_chicago.py`**: this driver never reads any
fault-injector's precomputed fault target (`inject_app.py`'s `service` parameter) or any
oracle's precomputed answer (`root_cause`, `expect()`, `actual_images`). Every decision comes
only from tool calls a real competing agent could make — the real, live deployment list, each
deployment's real running image, and the app's own *public* canonical baseline. Concretely
this means the driver never hardcodes "geo" as the affected service (even though this
session's own earlier debugging incidentally observed that fact in a log) — it scans **every**
real hotel-reservation deployment and lets the real, live evidence decide. This generalizes,
unmodified, to all 4 sregym problems sharing this exact oracle class (`misconfig_app`,
`incorrect_image`, `faulty_image_correlated`, `update_incompatible_correlated`), not just
`misconfig_app_hotel_res`.

Real conductor-orchestration mechanics (agent registry via `agents.yaml`, the `/get_app`,
`/status`, `/submit` HTTP surface, the kubectl/submit MCP tool SSE endpoints) were read
directly from `main.py`, `sregym/conductor/conductor_api.py`, and the real precedent drivers
`clients/autosubmit/autosubmit_agent.py` (simplest real example) and `clients/demo/driver.py`
(real MCP SSE call pattern) — not guessed.

## Verified this session, before the live trial

- `tests/sota/test_sregym_autofde_planner_decision_chicago.py`: **10/10 passing** under
  `vendor/gyms/sregym/.venv/bin/python` (the real runtime this driver actually executes
  under); **9/10 passing + 1 typed `UNSUPPORTED` skip** under this repo's own `.venv` (one
  test needs the real `kubernetes` package, which lives only in sregym's own venv — named
  precisely, not silently xfailed). Zero mocks.
- The judge preflight/grading call path (`run_judge_preflight_check()`,
  `DiagnosisJudge.judge_detailed()`) was confirmed, by direct source read, to call
  `.inference(messages)` with **no `tools=` argument** — meaning it never reaches
  `ChatLiteLLM.bind_tools(...)`, the exact code path that crashed for `stratus`. This is why
  diagnosis grading is expected to work against the local server even though `stratus`'s
  tool-calling agent loop did not.
- Both the kind cluster (4 nodes, all `Ready`) and the real `mcp-server` pod in the `sregym`
  namespace survived the earlier crash's teardown — only the `hotel-reservation`/`observe`
  app namespaces needed redeployment, which `main.py`'s own driver does automatically on
  launch.

## Scope — what this explicitly does not do yet

- No search-based planner (`Astar`/`BFWS`/`DSPyPolicy`) is actually invoked. This task's
  decision complexity is a single closed-form rule, not a search problem — reaching for
  search machinery here would be an unsupported abstraction, contradicting this session's own
  "extract existing choices before inventing new choices" discipline. `DSPyPolicy` remains
  the real, available escalation path (item 3 above) for a future sregym problem whose
  decision complexity actually warrants it.
- Diagnosis text is optimized to be honest and evidence-grounded, not to game the LLM judge's
  scoring checklist — no attempt was made to reverse-engineer what phrasing the judge scores
  highest.

## See also

- `docs/2026-08-09-sregym-stratus-llm-attempt-terminal-result.md` — the LLM-driven attempt
  this pivot replaces for the decision-making role (the judge LLM call is still used, for
  grading only, per the analysis above).
- `docs/2026-08-08-decision-basis-lane-b.md` — the `DecisionBasis` vocabulary this new
  `Planner` point (`sregym:autofde_lab_planner`, non-LLM) will attach to.
- `.claude/rules/absence-is-not-evidence.md` / `no-dual-bookkeeping.md` — the integrity
  disciplines this driver's "never read the answer key" constraint instantiates.

## Real trial result

**Run 1** (`results/0809_0123/`): real, honest, recorded negative — a launcher-level defect,
not a defect in the planner logic. `agents.yaml`'s `kickoff_command: python -m
clients.autofde_lab_planner.driver` resolved `python` against `agent_launcher.py`'s inherited
`os.environ.copy()` (no venv activation applied by the launcher), and bare `python` was not on
that `PATH`: `/bin/sh: python: command not found`, agent process exit code 127, empty result.
**Fixed**: `kickoff_command` now uses the absolute interpreter path
(`/Users/sac/autofde-lab/vendor/gyms/sregym/.venv/bin/python -m
clients.autofde_lab_planner.driver`), matching how `main.py` itself was invoked. The real
kind cluster and deploy/fault-injection sequence worked correctly up to that point (fault
injected, "Deployment complete. Ready for submission. Current stage is: diagnosis" — real,
observed) — only the agent process launch itself failed.

**Run 2** (`results/0809_0128/`): real PASS on the benchmark's own terminal scoring
(`Diagnosis.success=True`, composite 0.89; `Mitigation.success=True`), but a real, second
defect surfaced by the same run: the mismatch scan compared *every* real k8s Deployment's
image against the single canonical baseline, without first restricting to genuine
application microservices. It correctly found `geo` (the real injected fault) but also
incorrectly flagged and "fixed" 11 real infrastructure/dependency sidecars (`consul`,
`jaeger`, three `memcached-*`, six `mongodb-*`) — mutating their images too, since
`exec_kubectl_cmd_safely`'s optional whitelist gate is off in the real deployed config. The
benchmark's own **independent LLM judge caught this convergently**: `D3 Scope Precision`
scored 0.67/1.00 — "The agent lists many other deployments (consul, jaeger, mongodb, etc.) as
being part of the mismatch/fault." Since the whole `hotel-reservation` app namespace is torn
down at the end of every run regardless of outcome, the mutations never persisted beyond the
trial and the mechanical mitigation oracle's own narrow scope (`geo` only) was unaffected —
but the defect was real, not merely cosmetic, and is fixed below, not excused.

**Fix, attempt 1** (`filter_traced_application_deployments`, Jaeger-`get_services()`-based
ALLOW-list): real logic, real regression tests (12/12 passing) — but **Run 3**
(`results/0809_0137/`) exposed a *third* real defect: immediately after a fresh deployment,
before the workload generator has produced enough traffic, Jaeger had traced only 1 of 8 real
microservices (`['reservation']`, observed live). Gating solely on "has this been traced"
excluded `geo` — the actual injected fault — from scope entirely, producing a false "no
mismatch" diagnosis. Real, honest result: `Diagnosis.success=False`,
`Mitigation.success=False`.

**Fix, attempt 2** (final): a deterministic deny-list of well-known, generic OSS
infra/datastore product name tokens (`consul`, `jaeger`, `mongodb`, `memcached`, ...) as the
**primary** signal — available immediately, no traffic-timing dependency — with the real
traced-service signal retained only as a supplementary ALLOW override, never a gate. 3
regression tests added, one per defect found (14/14 total, all real, zero mocks, run against
both this repo's own `.venv` and `vendor/gyms/sregym/.venv`).

**Run 4** (`results/0809_0143/`, final): **real, clean, complete PASS.**
`Diagnosis.composite_score = 1.00` (D1 Fault Localization 1.00, D2 Fault Characterization
1.00, D3 Scope Precision 1.00 — the exact dimension the earlier defect broke, now clean),
`Diagnosis.success = True`, `Mitigation.success = True`, `TTL = 49.8s`, `TTM = 51.2s`. Real,
on-disk CSV:
`vendor/gyms/sregym/results/0809_0143/autofde_lab_planner/misconfig_app_hotel_res/
misconfig_app_hotel_res_autofde_lab_planner_results.csv`. A genuine, real, non-LLM-decided
solve of a real, live, unmodified external benchmark task, scored by the benchmark's own real
evaluators — zero paid credential, zero LLM call anywhere in the decision-making loop.

## Extension: `faulty_image_correlated` — real evidence of generalization

Per task #53 (running the same, unmodified driver across sregym's other real problems
sharing `misconfig_app_hotel_res`'s exact `IncorrectImageMitigationOracle` class): ran
`faulty_image_correlated` — same real `HotelReservation` app, same real canonical baseline
image, but the injected fault hits **all 8** real microservices simultaneously (a correlated
bad rollout, `jackcuii/hotel-reservation:latest`), not just `geo`. **Zero driver code
changes.** Real, clean, complete PASS: `Diagnosis.composite_score = 1.00`,
`Diagnosis.success = True`, `Mitigation.success = True`, `TTL = 59.7s`, `TTM = 65.9s`. Real
CSV: `vendor/gyms/sregym/results/0809_0155/autofde_lab_planner/faulty_image_correlated/
faulty_image_correlated_autofde_lab_planner_results.csv`.

This is the real, direct evidence the driver generalizes across an oracle class rather than
being secretly specialized to `misconfig_app_hotel_res` alone — it correctly scanned, in one
pass, all 8 real microservices and fixed all 8, with the same deny-list scope filter and the
same canonical-image comparison, unmodified.

**Two of the four same-oracle-class problems remain honestly out of scope, not attempted
without real, tested support** — named precisely rather than silently skipped:

- **`incorrect_image`** targets `AstronomyShop`, not `HotelReservation`. Checked this
  session: `sregym/service/apps/astronomy_shop.py` has no single canonical-image constant
  analogous to `HOTEL_RESERVATION_APPLICATION_IMAGE` (it deploys via an external Helm chart,
  `Helm.install(**self.helm_configs)`, with no local manifest checked out in this vendored
  tree — `SREGym-applications/astronomy-shop/` is empty). Astronomy-shop's real convention is
  almost certainly per-service distinct images (consistent with its OpenTelemetry Demo
  origin), which this driver's "one shared canonical image" comparison cannot handle without
  new, real, tested per-service image discovery — not built tonight.
- **`update_incompatible_correlated`** injects its fault onto the `mongodb-*` deployments —
  exactly the tier this driver's `_KNOWN_INFRA_PRODUCT_TOKENS` deny-list deliberately
  excludes as "not application code, don't touch." This driver would report a false "no
  mismatch" on this problem **by design**, not by bug. A real fix path was identified but not
  built or tested this session: `kubectl rollout undo` (confirmed real and permitted —
  `kubectl_server_helper/cmd_category.py:74`, in `kubectl_dry_run_commands`) reverts a
  Deployment to its prior ReplicaSet revision without needing this driver to know any
  "correct" image value in advance — a more general mitigation primitive than
  compare-against-one-canonical-image, but real detection (e.g. via `kubectl rollout
  history`'s revision count, or pod-health signals) was not implemented or verified live,
  and is not claimed as working.

## General architecture rebuild — per real fault-catalog survey + explicit user correction

Mid-session, explicit user correction: "why are you not building the general planner out of
the 50+?" — accurate. The pattern to that point (patch one narrow case, live-verify, patch
the next) converges on a perfect score on an ever-narrower slice, never on breadth. Response:
a 5-agent real workflow survey of sregym's real fault-injector source (`~60 real fault
types` across 10 injector classes) plus a real registry cross-reference against all 123
active registrations, then a rebuild from a hotel-reservation-only script into an
app-agnostic detector/remediator architecture.

**Real, quantified survey result** (compact synthesis, full 5-agent output ~1M tokens):

| Category | Real active registrations | Mechanism |
|---|---|---|
| A (already built) | 21 | image-mismatch / elevated-revision / rollout-undo, canonical-image comparison |
| B (17 distinct real mechanisms) | 63 | e.g. flagd-config public-default diff (+11), probe-value heuristic (+9), `Pending`+`FailedScheduling`/nodeSelector removal (+8), missing-object-vs-Helm-manifest reconstruction (+5), operator canonical-manifest reapply (+5), ... |
| C (no real generic signal found) | 13 | named honestly, e.g. `scale_pods_to_zero` (no externally-knowable target replica count) |
| D (kubectl-only tool can't reach) | 2 | real node-level SSH/exec faults, outside `exec_kubectl_cmd_safely`'s reach |
| Outside the 4 injector-source reports | 24 | ad-hoc per-problem implementations, unclassified this session |

**Built this session, from that real data**: (1) dynamic namespace/app discovery via the
conductor's own real `GET /get_app` (replacing the hardcoded `hotel-reservation` constant);
(2) `canonical_image_for_app(app_name)`, honestly `None` for apps with no known single-image
convention rather than a wrong guess; (3) the Category-B1 scheduling-constraint
detector/remediator (`find_deployments_with_unschedulable_pods` +
`decide_remove_node_selector_commands`) — the largest fully-deterministic Category-B
mechanism (8 real problems), requiring both an unready-replica signal AND a real
`nodeSelector` before flagging, to avoid false positives.

**Real live verification, three real bugs found and fixed in sequence** (each a genuine live
result, not a hypothetical):

1. **Regression check** (`misconfig_app_hotel_res`, re-run post-refactor): real, clean PASS
   — the app-agnostic rewrite did not break the already-proven case; dynamic discovery
   correctly resolved `namespace=hotel-reservation`, `canonical_image=ghcr.io/sregym/
   hotel-reservation:latest` via the new `/get_app`-based path.
2. **New capability, run 1** (`assign_to_non_existent_node`, `SocialNetwork`): dynamic
   discovery correctly resolved `namespace=social-network`; the new detector correctly
   flagged `user-service` (the real injected fault, found mechanically, never hardcoded);
   diagnosis scored 100/100. **Mitigation Failed**, though the applied fix
   (`kubectl patch ... remove nodeSelector`) was byte-for-byte identical to the benchmark's
   own real fault-recovery action (confirmed in the same log: "Removed nodeSelector for
   service user-service and redeployed") — a real timing defect: the oracle evaluated before
   the resulting rollout finished (pod still `Pending`). Fixed: wait for `kubectl rollout
   status` on every mutated deployment before submitting.
3. **New capability, run 2**: the rollout-status wait itself exposed a second real defect —
   `kubectl rollout status --timeout=90s` outlived fastmcp's own default SSE read timeout,
   closing the connection mid-command (`mcp.shared.exceptions.McpError: Connection closed`).
   Fixed by matching sregym's own established convention (`SSE_READ_TIMEOUT` env var, default
   3600s, same as `clients/stratus/stratus_utils/str_to_tool.py`'s real `get_client()`).
4. **New capability, run 3** (final): real, clean, complete PASS —
   `Diagnosis.composite_score = 1.00`, `Diagnosis.success = True`,
   `Mitigation.success = True`, `TTL = 53.4s`, `TTM = 488.9s`. Real CSV:
   `vendor/gyms/sregym/results/0809_0303/autofde_lab_planner/assign_to_non_existent_node/
   assign_to_non_existent_node_autofde_lab_planner_results.csv`.

**Real coverage after this pass: 3 complete, real, live-verified wins, spanning 2 real fault
categories (image-mismatch, node-scheduling) and 2 real apps (HotelReservation,
SocialNetwork)**, all fully general — zero hardcoding of app, service, or fault target in
either category. 44/46 real tests (2 typed environment skips), zero mocks, cross-venv
verified.

**What remains real, honest, unbuilt work, not silently claimed**: 62 of the 63 real
Category-B problems (only B1's 8 are built; B6-OTel's 11, B9's 9, and 14 other mechanisms
remain unbuilt), all 13 Category-C problems (no real generic signal exists — would need
answer-key access to solve, deliberately not pursued), both Category-D problems (tool-policy
unreachable), and all 24 problems outside the 4 injector-source reports (unclassified this
session). This is now a real, general architecture with a real, quantified map of what it
covers and doesn't — not a claim that it covers sregym broadly.

## Broadening the elevated-revision check + a real, honest 4th trial FAIL

The elevated-revision fallback only ever checked infra-excluded deployments -- a real gap
found by inspection: any app-tier fault that mutates a deployment's spec WITHOUT changing its
image (env var, ConfigMap mount, DNS policy, rollout strategy) was silently invisible to the
scan. Broadened to check every deployment not already flagged by the image comparison,
covering both infra tiers and app tiers with one mechanism. 29/29 tests still pass.

Live-verified against `configmap_drift_hotel_reservation` (real Category-A problem, targets
`geo`, ConfigMap-based, not image-based) -- two more real defects found and fixed along the
way:

- **Run 1**: the 3 flagged deployments' `kubectl rollout undo` commands all succeeded
  instantly, then the whole agent **hung for the full 600s harness timeout** with zero further
  output -- `kubectl rollout status --timeout=90s` was not honored somewhere in the real
  MCP/subprocess stack. Strictly worse than the premature-evaluation defect the wait was built
  to fix (a total loss vs. a real but wrong submission). Fixed: a hard `asyncio.wait_for`
  backstop that does not trust kubectl's own timeout flag alone -- a real timeout is now caught,
  logged, and execution proceeds to submit regardless.
- **Run 2** (with the backstop): confirmed the fix works -- all 3 rollout-status calls hit the
  real timeout cleanly (logged as `TIMEOUT: rollout status did not confirm convergence...`),
  execution continued, `main.py` exited cleanly (return code 0) instead of hanging. Real,
  complete, honest FAIL: `Diagnosis.success=False` (composite 0.0), `Mitigation.success=False`,
  `TTL=102.6s`, `TTM=329.4s`.

**Root cause, not a mystery -- already named in the original fault-catalog survey table**:
`recover_configmap_drift`'s own real entry noted "rollout undo removes the injected volume
mount; doesn't restore ConfigMap content -- a real but minor gap." `kubectl rollout undo`
reverts the Deployment's pod-template spec; it does not (and cannot) restore a ConfigMap
object's own data if the fault corrupted that separately. If the pod keeps failing readiness
because the ConfigMap content is still wrong, the rollout genuinely never converges -- which
is exactly why all 3 real rollout-status waits timed out, not a new bug. A real, honest
mechanism boundary of "rollback the Deployment spec," not a defect to keep chasing.

## Real, honest 4-trial aggregate (not yet a valid SOTA sample)

| Problem | App | Fault category | Diagnosis | Mitigation |
|---|---|---|---|---|
| `misconfig_app_hotel_res` | HotelReservation | image-mismatch | 1.00 / True | True |
| `faulty_image_correlated` | HotelReservation | image-mismatch (8 services) | 1.00 / True | True |
| `assign_to_non_existent_node` | SocialNetwork | node-scheduling | 1.00 / True | True |
| `configmap_drift_hotel_reservation` | HotelReservation | ConfigMap drift | 0.0 / False | False |

**Real, measured rate on this 4-trial sample: Diagnosis 3/4 = 75%, Mitigation 3/4 = 75%** --
both, numerically, at or above the top of sregym's real published aggregate ranges
(diagnosis 38.9-72.6%, mitigation 57.3-78.5%). **This is explicitly not yet a valid SOTA
claim**: n=4 is a hand-picked sample, not a representative draw from the full 90-problem
distribution; 3 of the 4 problems were specifically the ones this architecture was built to
solve; and the survey's own Category-C/D findings (15 real problems with no generic solvable
signal, 2 structurally unreachable) mean the full-suite rate is certain to be lower once a
representative sample is run. Reporting 75% > 72.6% as "SOTA beaten" from this sample would
be a real, precise violation of `.claude/rules/no-overclaiming-conversational.md` --
named here explicitly so it is not asserted elsewhere.

## Real, unbiased, representative-sample measurement — in progress

Per the standing goal's own precise objection to the 4-trial result: a hand-picked sample
cannot be compared against an aggregate rate measured on a representative sample. Response:
a real, programmatically-generated, unbiased systematic sample — every 5th `problem_id` from
the real, full, alphabetically-sorted list of all 123 active `ProblemRegistry` registrations
(computed once via `ProblemRegistry().get_problem_ids(all=True)`, never hand-edited to add or
remove a favorable/unfavorable case) — 25 problems, run sequentially against the real,
unmodified benchmark.

**A first batch attempt (stride-5, `--agent-timeout 200`/outer `timeout 240`) was discarded
as invalid, not reported**: even `misconfig_app_hotel_res` — the one case with the most real,
repeated, successful verification this session — timed out under those limits. Real cause,
confirmed by inspection of the batch log: deploying sregym's observability stack (Loki,
Promtail, MCP server) alone can take 3-5+ real minutes before the target app namespace is
even created, and legitimate driver work (multiple rollout waits) has been observed taking up
to 488.9s in this session's own prior real trials. A 240s ceiling was tight enough to produce
false timeouts on cases this driver can genuinely solve — mixing that data into an aggregate
would have been exactly the kind of manufactured-from-absence error
`.claude/rules/absence-is-not-evidence.md` forbids (a timeout is evidence the ceiling was too
low, not evidence the planner failed). Corrected to `--agent-timeout 600`/outer `timeout 750`
(evidence-based, not guessed) and restarted from scratch.

**Real, structural environment finding surfaced during the discarded run, still valid**:
`astronomy_shop_*`-targeted problems fail at deploy time, before this driver's own logic ever
runs -- `Helm chart_path does not exist: .../SREGym-applications/astronomy-shop/charts/
opentelemetry-demo`. The real OpenTelemetry Demo Helm chart was never vendored into this
checkout (confirmed: the local directory is empty). This is a real, honest `BLOCKED:
ENVIRONMENT` reason distinct from a planner defect -- fetching the missing chart would mean
downloading a file, which this session did not have standing authorization to do
unilaterally, so it was not attempted. ~7 of the 25 sampled problems target `astronomy_shop_*`
and will hit this same wall; the final aggregate accounts for them as a separate,
named category, never silently folded into either PASS or FAIL.

## Real, unbiased, representative-sample result — complete

The corrected 25-problem batch (real `--agent-timeout 600`/outer `timeout 750`, evidence-based)
ran to completion. Raw results: `docs/2026-08-09-representative-sample-batch-results.tsv`.

**Real, critical finding surfaced by classifying every result**: 10 of the 25 sampled problems
are structurally undeployable in this environment — confirmed by direct inspection of
`SREGym-applications/`'s real file counts: `astronomy-shop` (0 files), `FleetCast` (0 files),
`train-ticket` (0 files), vs. `hotelReservation` (776 files) and `socialNetwork` (699 files).
Every problem targeting AstronomyShop, FleetCast/TiDB, or TrainTicket fails at deploy time
with `Helm chart_path does not exist` — before this driver's own logic ever runs. This is a
real environment gap (missing vendored charts), not a planner defect, and is excluded from
the comparable denominator, named precisely rather than silently counted either way:

| | Count |
|---|---|
| `BLOCKED:ENVIRONMENT` (chart never vendored) | 10 |
| Real, comparable attempts (deployed, real oracle verdict reached) | 15 |
| — of which real PASS | 1 (`misconfig_app_hotel_res`) |
| — of which real FAIL | 14 |

**Real rate on the 15 environment-comparable, unbiased attempts: Diagnosis 1/15 = 6.7%,
Mitigation 1/15 = 6.7%.** This is the honest, representative-sample answer the standing goal
required, and it is decisive: **far below sregym's published aggregate range** (diagnosis
38.9-72.6%, mitigation 57.3-78.5%) **and far below the earlier, hand-picked 4-trial 75%/75%**
— confirming precisely what that earlier result's own caveat predicted ("the survey's own
Category-C/D findings guarantee a lower full-suite rate"). Four of the 14 real FAILs were
genuine timeouts (the driver made no detectable progress within 600s — fault types this
planner has no detector for at all: `admission_webhook_outage`, `cfs_cpu_throttling`,
`ephemeral_port_range`, `finalizer_deadlock_controller`); the other 10 reached a real
diagnosis submission (mostly a mechanical "no image mismatch / no anomaly detected" report,
scoring partial credit around 0.11 from the judge for correctly describing a clean scan, but
failing to identify the real fault) and a real, correctly-failed mitigation.

**Conclusion, stated plainly**: this session's non-LLM planner is a real, working, generalizing
architecture on the ~2 fault categories (13 of 60 real fault types) it was deliberately built
for, verified with 5 complete live wins across those categories. On an unbiased, representative
draw from sregym's actual problem diversity, its real success rate is 6.7%/6.7% — **AutoFDE
Lab does not beat sregym's published SOTA on a representative sample.** Reaching that would
require building out most of the remaining 15 real Category-B mechanisms (62 more problems)
identified in the original fault-catalog survey, not further testing of what already exists.
That is real, scoped, unbuilt work, named as such.

## Precision on the "beats SOTA" question — not yet established, named honestly

A real, cited WebSearch this session found sregym's real published numbers
([SREGym leaderboard](https://sregym.com/leaderboard),
[arXiv:2605.07161](https://arxiv.org/abs/2605.07161)): diagnosis success rates of **38.9% to
72.6%** and mitigation success rates of **57.3% to 78.5%**, reported as **aggregate rates
across the full 90-problem suite**, from frontier paid models (Sonnet-4.6, GPT-5.4, Kimi
K2.5) driving the real `stratus`/Claude Code/Codex agents.

**This session's real result is 3 complete wins across 2 real fault categories and 2 real
apps (21 + 8 = 29 of 123 real active problems now structurally in scope, per the survey
table above), not an aggregate rate on a sample commensurate with the published figures.**
Reporting "100% > 72.6%, SOTA beaten" would compare a small, favorable slice against a
90-problem aggregate — exactly the register mismatch
`.claude/rules/no-overclaiming-conversational.md` and `criticism-discipline.md` (rule 2,
register parity) forbid. What IS established, precisely: a genuine, non-LLM, general,
app-agnostic planner can reach perfect scores on real, structurally-diverse sregym tasks
using this repo's own architecture — a real, broadening existence proof, not yet a SOTA
comparison. The real next step, already scoped and not yet executed: run this driver across
the remaining real problems already known to be in scope (the other 20 Category-A problems,
the other 7 Category-B1 problems) to get a genuine aggregate rate over the 29-problem
in-scope set — and, beyond that, build out the highest-value remaining Category-B mechanisms
(B6-OTel, B9, B4, B13) for a comparison that
would actually be commensurate with the published figures.
