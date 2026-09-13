# AzureGoat Privilege Escalation — GymAct Bridge + SOTA Push — 2026-08-08

Context: what was built (real GymAct EnvironmentProvider bridge for AzureGoat), what was
measured (real OCEL 2.0 log, real ConformanceChecker replay, real solved=True evidence), and
what was researched/attempted (published cloud-privesc agent SOTA comparison, 3 bounded
improvement rounds).

## Bridge

All work is complete and verified. Summary below.

### Summary

**Confirmed real import**: `gymact` was not importable (`ModuleNotFoundError`), so I added it as a real path dependency in `/Users/sac/autofde-lab/pyproject.toml` (`[tool.uv.sources] gymact = { path = "/Users/sac/gymact", editable = true }` + a `gymact` entry in base `dependencies`) and installed it for real via `uv pip install --python .venv/bin/python -e /Users/sac/gymact`. Confirmed: `.venv/bin/python -c "import gymact; print(gymact.__file__)"` → `/Users/sac/gymact/src/gymact/__init__.py`.

**New file**: `/Users/sac/autofde-lab/src/autofde_lab/hub/domain/azuregoat_privesc/gymact_bridge.py` (209 lines) — `AzureGoatPrivescProvider`/`AzureGoatPrivescEnvironment` implementing `gymact.providers.EnvironmentProvider`/`Environment` for real:

- `materialize()`: builds a real `AzureGoatPrivilegeEscalation` domain + the real C++-backed `Astar` solver (`utils.load_registered_solver("Astar")`), runs `solver.solve()` for real, replays the policy from the real initial state to derive the real 10-step plan, stores it plus the initial state.
- `capabilities()`: one `Capability` per `ATTACK_STEPS` entry, all `Consequence.DO`.
- `observe()`: real current fact-set.
- `actuate()`: applies the real `get_next_state` transition only if the capability is both a real applicable step (via `get_applicable_actions`) **and** the real plan's next step; otherwise raises `ActuationRefused` — verified this refuses both an out-of-order-but-eventually-applicable step and a replay of an already-completed step.
- `verify()`: checks observed facts against `GOAL_FACT`/explicit expected facts.
- `checkpoint()`/`restore()`: real `(facts, plan_cursor)` snapshot/restore, verified round-tripped into a second materialized environment.
- `teardown()`: idempotent no-op, called twice without error.

**pyproject.toml diff** (also added the `gymact.providers` entry point):

```diff
 dependencies = [
     "pynng>=0.6.2",
     "pathos>=0.2.7",
     "discrete-optimization>=0.9.0",
     "wrapt>=2.2.1",
+    "gymact",
 ]
...
+[project.entry-points."gymact.providers"]
+azuregoat_privesc = "autofde_lab.hub.domain.azuregoat_privesc.gymact_bridge:AzureGoatPrivescProvider"
...
 [tool.uv.sources]
 wasm4pm-compat-py = { path = "/Users/sac/wasm4pm-compat/wasm4pm-compat-py", editable = true }
+gymact = { path = "/Users/sac/gymact", editable = true }
```

(Note: a concurrent process was independently editing the same file's `gymact` extra block at the same time — this produced one duplicate `[tool.uv.sources]` key that broke `uv sync`; I removed the exact duplicate line, touching nothing else of theirs, verified TOML validity, and confirmed via `git diff` afterward that their concurrent edits and mine coexist cleanly with no more duplication.)

**Real end-to-end verification run** (`.venv/bin/python` against the real installed `gymact` + real `Astar` C++ solver), full output:

```
provider.name: azuregoat_privesc
provider.materialization_requires_authority: False
environment_id: urn:gymact:azuregoat-privesc:environment:705391520a9d4376878caa4768815ba3
requires_authority: True
real solved plan: ('ssh_login_vm', 'az_login_managed_identity', 'list_resources_for_principal_id', 'list_role_assignments', 'correlate_owner_principal_to_automation_account', 'list_runbooks', 'write_privesc_runbook_script', 'replace_and_publish_runbook', 'start_runbook', 'confirm_owner_role')
num capabilities: 10
all capabilities classified DO: OK
initial observe(): {'facts': []}
correctly refused out-of-order actuation: refused: 'az_login_managed_identity' is not applicable from the real current state [] ...
actuated 'ssh_login_vm' -> established 'has_vm_ssh_access'; ...
... (all 10 steps actuated in order) ...
actuated 'confirm_owner_role' -> established 'has_owner_role_on_resource_group'; observed facts: [...10 facts including has_owner_role_on_resource_group...]
correctly refused replayed actuation: refused: 'ssh_login_vm' is not applicable ...
verify({}) -> True {'facts': [...]}
verify(explicit expected facts) -> True: OK
checkpoint(): {'facts': [...10 facts...], 'plan_cursor': 10}
restored env2 observe(): {'facts': [...matches checkpoint...]}
teardown() completed; idempotency check (calling again):
teardown() called twice without error: OK
{"status": "ALL_REAL_CHECKS_PASSED", "plan": [...10 steps...]}
```

**Entry-point discovery verified real** (required a real `uv pip install -e . --no-deps` reinstall of autofde-lab itself to regenerate entry_points metadata, since editable-install metadata doesn't auto-refresh on pyproject.toml edits):

```
discovered: (ProviderPluginInfo(name='azuregoat_privesc', value='autofde_lab.hub.domain.azuregoat_privesc.gymact_bridge:AzureGoatPrivescProvider', group='gymact.providers'),)
loaded standing: ALIVE
provider.name: azuregoat_privesc
```

Confirmed no collateral damage: other `autofde_lab.domains`/`autofde_lab.solvers` entry points (`azuregoat_privesc` domain, `Astar` solver) still resolve after the reinstall, and `terragoat_remediation.py`/`tests/ecosystem/` were not touched.

**Standing**: `ALIVE` for the provider registration and the full real materialize→observe/actuate×10→verify→checkpoint/restore→teardown episode. Not run: `write_ocel_log`/OCEL-2.0 standing evidence (`consumer-setup.md` step 5) — this was scoped to provider implementation + registration + a real functional verification run, not OCEL log generation; that remains open if a future task asks for it.

## Verification (real OCEL evidence)

Digest matches independently (`sha256sum`-equivalent `shasum -a 256` gives the same `22545f9e...` reported by `write_ocel_log`). All verification steps complete.

### Summary

**Real end-to-end episode through the provider bridge** (not the old direct-domain path): wrote `/Users/sac/autofde-lab/scripts/run_azuregoat_gymact_ocel_episode.py`, which uses the real `gymact.runtime.GymAct` orchestrator — `gym.register_provider(AzureGoatPrivescProvider())`, then real `materialize()` → real `act()` × 10 (in the real solved-plan order, each requiring and passing a real `AllowListAuthorityResolver` authority check) → real `verify()` → real `teardown()`. Ran it with `.venv/bin/python`; the real C++ A* solver logged `"A* finished to solve ... in 0 seconds"`, all 10 real capabilities actuated with `standing=ALIVE`, and the real `verify({})` call returned `passed=True` with all 10 expected facts including `has_owner_role_on_resource_group`.

**Real solved=True evidence**, following the exact pattern in `~/gymact/scripts/discover_and_actuate.py`: `receipt.standing == ALIVE` on an `act` receipt only proves the actuation mechanism ran without raising, not that the domain's goal was reached, so the real `gym.verify()` outcome (`passed=True`) was attached onto the final `act` receipt's own `reason` field via `Receipt.model_copy` before conversion — the OCEL log itself carries `solved=True`, not just this script's stdout.

**OCEL log written**: `/Users/sac/autofde-lab/reports/ocel/azuregoat-privesc-gymact/episode.ocel.json`, via real `gymact.ocel.write_ocel_log` (12 events, 14 objects), sha256 `22545f9e1940e50e8043fae75048d2a0370b18c509aaff10869d98b68d841499` — independently reproduced via `shasum -a 256` on the file directly (not a re-serialization).

**Independent verification**, replicating `/Users/sac/gymact/tests/test_ocel_standing.py`'s exact steps against real collaborators (not trusting any summarizing script):

- Schema-valid: **True** (`gymact.ocel.validate_ocel_log` against the real official OCEL 2.0 JSON Schema — no exception raised)
- Conformant: **True**, no deviations (`gymact.process.ConformanceChecker().check()` over the real operation sequence extracted from the log's own `events`, sorted by real `time`)
- Real `solved=True` evidence: **True** — found on the log's own `act` event `reason` attribute (`'solved=True'`), read directly off the log file, not asserted from memory

**Domain-level pytest** (unmodified): `.venv/bin/python -m pytest tests/domains/test_azuregoat_privesc.py -v` → `2 passed in 0.16s`.

**Standing**: `ALIVE` for the full real episode (materialize → 10× act → verify → teardown) through `AzureGoatPrivescProvider` via `gymact.runtime.GymAct`, and the resulting OCEL log independently satisfies all three axes `test_ocel_standing.py` checks (schema-valid, conformant, real solved=True evidence). Not run: registering this new log against gymact's own `pytest tests/test_ocel_standing.py` glob-discovery (that test discovers `reports/ocel/*/` under the `gymact` repo root, not `autofde-lab`'s) — the same three checks were instead run directly, using the same real collaborators that test uses, against the log in its actual location as the task specified.

## Published SOTA research

Based on real web search, here are the findings.

**No published, citable AzureGoat-specific number exists.** I searched directly for "AzureGoat" combined with LLM/GPT/agent terms and found nothing — no paper, benchmark writeup, or blog post reporting LLM-agent success rates on AzureGoat specifically. AzureGoat (Ine/OWASP-style "vulnerable by design" Azure range) does not appear to have been used as an LLM-agent evaluation target in any indexed publication as of this search (2026-08-07).

Closest real, citable adjacent findings:

**1. HackingBuddyGPT — Linux privilege escalation (closest real "privesc + LLM agent" number, but Linux OS-level, not cloud/IAM)**

- Paper: "LLMs as Hackers: Autonomous Linux Privilege Escalation Attacks" — Happe, Kaplan, Cito
- URL: https://arxiv.org/abs/2310.11409 (also published in Empirical Software Engineering, Springer: https://link.springer.com/article/10.1007/s10664-025-10758-3)
- Numbers: GPT-4-Turbo successfully exploited 33–83% of vulnerabilities across benchmark VMs (described as comparable to human pentesters' ~75%); GPT-3.5-Turbo 16–50%; Llama3 0–33%.
- Note: this benchmark is single-vulnerability Linux VMs (local OS privilege escalation), not cloud IAM/privilege-escalation attack chains.

**2. Drexel University automated pentesting benchmark (has an explicit "Privilege Escalation" task category, VulnHub VMs — not cloud/IAM either)**

- Paper: "Towards Automated Penetration Testing: Introducing LLM Benchmark, Analysis, and Improvements" — Isozaki, Shrestha, Console, Kim (Drexel University)
- URL: https://arxiv.org/abs/2410.17141 (preprint dated Oct 22, 2024; adjunct-proceedings version at ACM UMAP 2025: https://dl.acm.org/doi/10.1145/3708319.3733804)
- Numbers on the "Privilege Escalation" task category specifically: GPT-4o 31.8%, Llama 3.1-405B 36.4% (compare: Reconnaissance 40.3%/44.4%, Exploitation 25.0%/38.6%, General Techniques 35.7%/57.1%).
- Note: benchmark is built on VulnHub VMs (general pentest CTF-style targets), not a cloud provider or IAM-specific range.

I did not locate any published number for a cloud-IAM-specific or cloud-privilege-escalation-attack-chain category in any benchmark (searched explicitly for "cloud penetration testing," "IAM privilege escalation," and "cloud CTF" combined with LLM agent success rates) — the two numbers above are the closest real, citable privilege-escalation results, but both are host/VM-level Linux privesc, not cloud-control-plane/IAM privesc. Everything reported above was pulled from the actual paper abstracts/text via WebFetch, not inferred.

## Push rounds

### Round 1 — Gap (a): manual-to-code transcription fidelity

**Gap targeted: (a)** — `ATTACK_STEPS` was hand-transcribed from the vendored manual with no runtime link back to the source, weaker evidence than TerraGoat's real regex parser that extracts findings directly from vendored `.tf` text at construction time. Verified this was real and true (not assumed) by reading both domain files directly: `terragoat_remediation.py` genuinely regex-parses `resource "type" "name" {` blocks and their `#` comments out of real vendored Terraform files (`_parse_findings_from_text`, line 56); `azuregoat_privesc.py`'s `ATTACK_STEPS` was a hand-written Python tuple whose only claim to fidelity was a docstring assertion ("transcribed directly from that manual's numbered steps") — no code checked it against the real vendored `05-Privilege Escalation.md`.

**What I did**: added a real runtime parser, `parse_manual_steps()` in `/Users/sac/autofde-lab/src/autofde_lab/hub/domain/azuregoat_privesc/azuregoat_privesc.py`, that regexes `**Step N:**` headers and their fenced code blocks directly out of the real vendored file at `vendor/gyms/azuregoat/attack-manuals/module-1/05-Privilege Escalation.md`. Added a new test, `test_attack_steps_match_real_manual_commands_parsed_at_runtime` in `/Users/sac/autofde-lab/tests/domains/test_azuregoat_privesc.py`, that cross-checks every hand-authored `AttackStep`'s claimed command substring against the real parsed manual text for its cited step number — a genuine, re-checkable link from the domain to its source, the honest AzureGoat analogue of TerraGoat's parser (full precondition/`establishes` extraction from unstructured prose isn't literally regex-parseable the way TerraGoat's structured HCL is, so the fix is a real parity check rather than full extraction — stated explicitly in the test's docstring, not glossed over).

**Real verification output**:

- `pytest tests/domains/test_azuregoat_privesc.py -v` → `3 passed in 0.18s` (includes the new test).
- Teeth check: temporarily replaced the real expected command substring (`ssh -i justin.pem justin@` → `ssh -i wrong.pem nobody@`) and reran — real failure: `AssertionError: 'ssh_login_vm' claims command 'ssh -i wrong.pem nobody@' from real 'Step 1', but the real manual's code block for Step 1 is: 'chmod +600 justin.pem\n\nssh -i justin.pem justin@40.85.170.40\n'`. Restored the original file, reran → `3 passed in 0.18s` again, confirming the test is load-bearing, not vacuously true.
- `grep -rn "unittest.mock|Mock(|MagicMock|patch(|monkeypatch" tests/domains/test_azuregoat_privesc.py src/.../azuregoat_privesc.py` → zero matches (exit code 1) — Chicago-style, real files, real regex, no mocking.
- Wider real run: `pytest tests/domains/test_azuregoat_privesc.py tests/ecosystem/ -k azuregoat -v` → `3 passed, 62 deselected`.

Gap (a) is closed for what's honestly closable: the domain's steps now have a real, automated, adversarially-verified runtime tie to the vendored source text, catching both manual drift and transcription error. Note this does not touch gaps (b) (single-trial OCEL evidence vs. a rate) or (c) (no citable AzureGoat-specific published number exists at all) — those remain open and, per the task's own instruction, were not fabricated closed in this round.

### Round 2 — Gap (b): single-trial evidence vs. a published reliability rate

Targeted gap **(b)**: "the OCEL log only proves ONE deterministic run, not repeated-trial reliability the way a published agent success RATE implies multiple trials."

**What I checked first (before writing anything):** whether repeated trials would even be meaningful evidence here. Grepped the entire domain + bridge for any source of stochasticity:

```
grep -n "random\|Random\|llm\|LLM\|openai\|anthropic\|temperature\|seed" \
  src/autofde_lab/hub/domain/azuregoat_privesc/*.py \
  src/autofde_lab/hub/domain/azuregoat_privesc/gymact_bridge.py
→ zero matches
```

There is no LLM, no sampling, no randomness anywhere in the pipeline: the plan comes from a deterministic C++ A* solve over a deterministic STRIPS-style domain, and `actuate()` deterministically applies `get_next_state`. This is the load-bearing fact for the whole gap: a published agent "success rate" (e.g. the HackingBuddyGPT/Drexel numbers in Research) is measuring variance across an LLM's non-deterministic choices, retries, and environment noise. This provider has none of those — it is a solved planning problem replayed once.

**Real evidence gathered anyway** (to not just assert this from reasoning): ran the actual episode script three independent times against the real installed `gymact`, real A* solver, real actuation:

```
=== run 1/2/3 ===
verify({}) -> passed=True observed={ ...same 10 facts, same order... }
events=12 objects=14   (identical count each run)
plan/order identical across all 3 runs
```

The only difference across the three OCEL logs' sha256 is from embedded timestamps/UUIDs (`008000e1...`, `85cb09d6...`, `59f271f8...`) — not from any difference in the solved plan, the actuation sequence, the facts reached, or the `passed=True` verification outcome. 3/3 trials are bit-identical in substance.

**Why this closes the investigation rather than "fixing" the gap:** running N trials of a fully deterministic pipeline produces a constant, vacuous 3/3 = 100% "rate" — it re-confirms determinism, not reliability under any real source of variance. Reporting that as if it were commensurable with a published stochastic agent-success-rate (which is exactly what gap (b) warns against) would itself be the overclaim. There is no honest way to manufacture a non-trivial reliability statistic here without introducing an artificial noise source that doesn't exist in the real system, which would be evidence about a system that isn't the one being claimed to work.

**Verdict:** Gap (b) is **not closable with real evidence in this round** — not because I couldn't run trials, but because the trials that can be run (and were run, 3/3, real output above) don't measure what a "beats/matches published SOTA agent success rate" claim requires: variance under a real decision-making process. The provider's true standing remains what it already was — `ALIVE` for one correct, now 3x-reconfirmed-deterministic, full episode (materialize → 10× act → verify → teardown) — and any "beats SOTA" framing stays unsupported, same as gap (c), because the two published numbers found in Research are host/VM Linux privesc rates from a genuinely stochastic LLM agent, not comparable to a deterministic A* replay regardless of how many times it's rerun.

No code changes were made this round; the three-run check and the grep for stochasticity sources are the full real evidence for this conclusion. Files referenced: `/Users/sac/autofde-lab/scripts/run_azuregoat_gymact_ocel_episode.py`, `/Users/sac/autofde-lab/src/autofde_lab/hub/domain/azuregoat_privesc/azuregoat_privesc.py`, `/Users/sac/autofde-lab/src/autofde_lab/hub/domain/azuregoat_privesc/gymact_bridge.py`.

### Round 3 — Re-verification pass, no new gap claimed

All checks reconfirmed real: 3/3 domain tests pass, zero mock hits in the domain+test files, entry-point discovery intact, and a fresh episode run reproduces the OCEL log (12 events/14 objects, new sha `59f271f8...` — timestamp/UUID-only diff from prior runs, same as before).

**Gap targeted this round**: none newly claimed — re-verified the terminal state of gaps (a), (b), (c) rather than re-litigating a settled verdict, since the task named no new gap and both prior rounds' closing arguments for (b)/(c) are still load-bearing.

**What I did**: reran the concrete evidence each prior round's verdict rests on, rather than trusting the prior summaries from memory:

- (a) real regex parser (`parse_manual_steps`) + parity test still present and passing (`tests/domains/test_azuregoat_privesc.py::test_attack_steps_match_real_manual_commands_parsed_at_runtime`) — 3 passed in 0.18s, `grep -n "unittest.mock|Mock(|MagicMock|patch(|monkeypatch"` over the domain + test files → zero matches.
- (b)/(c): no new evidence changes their standing. (b) remains genuinely unclosable with real evidence — the pipeline is proven deterministic (zero LLM/random/seed references in the domain + bridge), so any N-trial "rate" would be vacuous 3/3=100%, not a measurement of the variance a published agent-success-rate actually reports. (c) remains genuinely unclosable — no AzureGoat-specific published number exists to compare against (confirmed by direct web search in a prior round); the two adjacent numbers found (HackingBuddyGPT, Drexel VulnHub) are host/VM Linux privesc from a stochastic LLM agent, not commensurable with this domain's deterministic cloud-IAM A* solve regardless of category proximity.

**Real verification output**:

```
grep unittest.mock|Mock(|MagicMock|patch(|monkeypatch → no matches (exit 1)
pytest tests/domains/test_azuregoat_privesc.py -v → 3 passed in 0.18s
pytest tests/domains/test_azuregoat_privesc.py tests/ecosystem/ -k azuregoat -v → 3 passed, 62 deselected
reports/ocel/azuregoat-privesc-gymact/episode.ocel.json sha256 59f271f87d279103f07c97ea595b8aa4d041bcab3c7c0891421cebe3c60c22fc (fresh episode run this round, log regenerated, substance unchanged from prior runs)
```

**Verdict — stop condition met**: (a) is genuinely closed (real parser + adversarially-verified parity test, reconfirmed). (b) and (c) are genuinely not closable with real evidence available in this environment — not "not yet tried," but structurally unclosable: (b) because the system under test has no stochastic decision process to measure a rate over, and (c) because no comparable published number exists. Fabricating a repeated-trial "success rate" or a "beats SOTA" framing against a non-existent or incommensurable baseline would itself be the overclaim this task is designed to prevent. No code changes made this round — this was a re-verification pass confirming the prior rounds' closing arguments still hold under fresh, real execution, not new work.

Files referenced: `/Users/sac/autofde-lab/src/autofde_lab/hub/domain/azuregoat_privesc/azuregoat_privesc.py`, `/Users/sac/autofde-lab/tests/domains/test_azuregoat_privesc.py`, `/Users/sac/autofde-lab/src/autofde_lab/hub/domain/azuregoat_privesc/gymact_bridge.py`, `/Users/sac/autofde-lab/reports/ocel/azuregoat-privesc-gymact/episode.ocel.json`.

## Falsifiers

What would invalidate this report, if found:

- The OCEL log's `solved=True` evidence coming from a provider bug that always writes `passed=True` into the `act` receipt's `reason` field regardless of real facts reached (i.e. `verify()` not actually gating on observed state) — not independently re-derived from `AzureGoatPrivescEnvironment.verify()`'s real comparison logic in this report; the report trusts that logic's correctness rather than re-proving it from first principles.
- Either published number (HackingBuddyGPT 33–83% GPT-4-Turbo; Drexel GPT-4o 31.8%/Llama-3.1-405B 36.4% on "Privilege Escalation") being misattributed to a task category, model version, or benchmark scope different from what this report states — both were read from abstracts/text via WebFetch rather than independently reproduced by rerunning either paper's benchmark.
- `AzureGoatPrivescEnvironment.actuate()` silently permitting an out-of-order or already-completed step under some untested code path (e.g. a capability id collision, or a plan-cursor reset bug) — only the two specific negative cases described (out-of-order-but-eventually-applicable, and full replay) were exercised; the refusal logic was not exhaustively fuzzed against all 10×10 possible (attempted-step, plan-cursor) pairs.
- The `parse_manual_steps()` regex parser silently matching the wrong fenced code block for a given `Step N:` header on some other manual layout (only Module 1's `05-Privilege Escalation.md` was exercised; the parser's generality across other AzureGoat manual files/modules is unverified).
- The claim that the pipeline is fully deterministic (Round 2) depending on an unstated assumption in the real C++ A* solver (e.g. hidden priority-queue tie-breaking depending on memory layout or hash-map iteration order) that happened not to manifest across exactly 3 runs — 3 identical runs increases confidence but does not prove the solver is deterministic in the general case, only that it was reconfirmed for this specific domain instance 3 times.
- Any of the "not closable" verdicts for gaps (b) and (c) being falsified by a future published AzureGoat-specific benchmark number, or by a legitimate non-artificial source of variance in this pipeline being discovered later (e.g. if an LLM-driven planner is substituted for the deterministic A* solver in a future revision).

## Final standing

- **GymAct `EnvironmentProvider`/`Environment` bridge for AzureGoat privilege escalation (`gymact_bridge.py`), including entry-point registration and a full real materialize→observe/actuate×10→verify→checkpoint/restore→teardown episode**: **ALIVE**.
- **OCEL 2.0 log at `reports/ocel/azuregoat-privesc-gymact/episode.ocel.json`, schema-valid + conformant (`ConformanceChecker`) + carrying real `solved=True` evidence in the `act` event's `reason` attribute**: **ALIVE**.
- **Round 1 fix — runtime-parsed link (`parse_manual_steps`) from `ATTACK_STEPS` to the real vendored manual text, with an adversarially-verified parity test**: **ALIVE**.
- **Round 2/3 finding — the pipeline is deterministic (no LLM/random/seed sources), so no non-vacuous repeated-trial reliability rate can be produced**: **ALIVE** (as a verified negative finding — confirmed by grep + 3 real reruns, not merely asserted).
- **Published cloud-IAM/AzureGoat-specific agent success-rate baseline to compare against**: **UNSUPPORTED** — searched for directly, none found; only host/VM-level Linux privesc numbers exist (HackingBuddyGPT, Drexel), which are not commensurable with this domain.
- **"autofde-lab beats/matches SOTA on cloud-agent privilege escalation" as a general claim**: **UNSUPPORTED** — no citable SOTA number exists for this exact task category, so there is nothing to beat or match in a well-formed sense.

**Closing sentence**: this real work demonstrates one correct, independently reproducible, fully verified (schema-valid, conformant, goal-state-confirmed) deterministic solve of the AzureGoat privilege-escalation chain through a genuine GymAct provider bridge — not a claim of "beating SOTA," because no published AzureGoat-specific or cloud-IAM-specific agent success rate exists to be beaten, and the two adjacent published numbers that do exist (host-level Linux privesc from stochastic LLM agents) are not a valid comparison baseline for a deterministic A* replay of a solved planning problem.
