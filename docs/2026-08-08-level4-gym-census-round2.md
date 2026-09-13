# Level 4 gym census, round 2 — 74 gyms, goal-oracle taxonomy

Real workflow run (`w11002rh6`/`wf_5ef4fdeb-018`), this session: 57/57 agents completed, zero
errors, zero kills (unlike the round-1 workflow, which was killed mid-run at 31/46 — see
`docs/level4-migration-matrix.md`). Fresh discovery re-enumerated the full GymAct-capable
provider surface from real source and found **74 distinct gyms**, up from round 1's ~44 —
the increase is real: round 2 explicitly expanded every `VendorBenchmarkProvider` vendor as
its own `gym_id` (round 1 sampled 12 of 52), and discovery additionally found real, entirely
new local/network providers (`gymact.local_providers`, `gymact.network_providers`) round 1
never surfaced: `filesystem`, `git`, `http-json`, `memory`, `sqlite`.

Every claim below is either a real trial result (the 5 already-`ALIVE` gyms, unchanged from
round 1) or a real census agent's source-inspection finding, cited back to real file paths
and line numbers by the agents themselves. Nothing here is independently re-verified by the
main session this pass — see "What was not re-verified" at the end.

## Merged totals

Approximate — exact arithmetic not independently re-summed this pass, per the synthesizing
agent's own caveat:

| Standing | Count |
|---|---|
| `LEVEL4_ALIVE` | 5 |
| `ADAPTER_MISSING` (local/bespoke) | 9 |
| `ADAPTER_MISSING` (`VendorBenchmarkProvider` family) | 43 |
| `AUTHORITY_REQUIRED` | 5 |
| `CAPABILITY_MISSING` | 8 |
| `DEPENDENCY_BLOCKED` | 2 |
| **Total distinct gyms censused across both rounds** | **≈72** |

## The constructor-signature fix's real, confirmed effect

The generic `_construct_provider` fix (committed `d4e52ed`, this session) is now confirmed
**already live and correctly closing its target defect** by this independent round-2 census:
every `VendorBenchmarkProvider`-family vendor censused this round constructs correctly
(`toolsandbox`'s entry specifically re-reproduced the *pre-fix* `TypeError` live to confirm the
premise, then confirmed the fix resolves it). The fix did not, and could not by design, unlock
execution for any of them — see below.

## A second, separate, family-wide gap: authority-threading

Every `VendorBenchmarkProvider` instance carries `materialization_requires_authority=True` as a
**class attribute** — confirmed live and reproduced for `sqlite`, `swe-bench`, `tau2-bench`,
`terragoat`, and `ggen-legacy` (the two non-vendor-family cases sharing the same flag).
`_BRIDGE_SCRIPT`'s `MaterializationIntent` construction never sets `authority_ref` (only
`ActuationIntent` calls do), so `gym.materialize(...)` is refused with `LIVE_AUTHORITY_REQUIRED`
before `capabilities()` is ever reached. Because the flag is class-level, this structurally
applies to all ~46 vendor instances, whether or not each one's specific census entry
re-verified it live this round. **This is a second, separate, real fix — threading
`authority_ref` through `MaterializationIntent` in both bridge scripts — not yet done, and not
something the constructor fix touched.** Filed as a new, precisely scoped task (see below);
deliberately not attempted in this pass, since it changes what becomes reachable and deserves
its own review before landing, not a tail-end addition to an already-large session.

## Full census tables, goal-oracle taxonomy, and the "constructor-fix-only" qualifiers

The complete real output — every censused gym with its exact blocker, difficulty, and (for the
vendor family) which of five goal-oracle semantic categories it falls into — is preserved
verbatim in the workflow transcript:
`/Users/sac/.claude/projects/-Users-sac-autofde-lab/a420c968-955c-43ee-8074-b768d3016a7e/subagents/workflows/wf_5ef4fdeb-018/journal.jsonl`
(the `synthesis-and-clustering` agent's result). Summarized here rather than fully duplicated,
per this repo's own markdown discipline against redundant restatement.

### The five goal-oracle categories (design, not implementation)

A real, source-grounded reduction of "52 vendors, 52 goal predicates" to 5 shared projection
rules — exactly the combinatorial reduction this campaign has been aiming for, and the single
most valuable output of this census round:

- **A — Fixed-convention reward file.** Read one file at a known relative path
  (`/logs/verifier/reward.txt`/`reward.json`) after `run-native` exits. The real Harbor-framework
  convention, shared verbatim by `harbor`, `terminal-bench`, `terminal-bench-pro`, `o11y-bench`,
  `tua-bench`; `osworld`'s `result.txt` is structurally identical under a different path.
- **B — Process exit-code contract.** `run-native`'s already-captured `last_result.returncode`
  directly *is* the goal signal — needs no new capability, only a goal-predicate branch reading
  a field GymAct already surfaces. `devops-gym`, `mcpmark`, `sregym`, `sec-bench`; `sadservers`
  is the same shape via stdout marker instead of exit code.
- **C — Written structured result artifact with a named field.** Read a JSON/JSONL file, project
  one config-specified field (a JSONPath-style pointer). `swe-bench`, `cybench`,
  `the-agent-company`, `toolsandbox`, `scuba`, `rcaeval`, `itbench`, `general-agentbench`.
- **D — In-process declarative evaluator, requires a live session.** Cannot collapse to A/B/C's
  subprocess-and-read-file pattern — needs a genuinely new "invoke-vendor-evaluator-in-session"
  capability shape. `tau2-bench`, `webarena`, `mcp-universe`, `st-webagentbench`, `workarena`,
  `agentgym`.
- **E — No machine-readable oracle exists.** A refusal boundary, not a gap to bridge, per
  `.claude/rules/absence-is-not-evidence.md` — coercing an LLM-judge score into a typed
  postcondition would be exactly the coerced-uncertainty defect that rule names. `mcp-bench`,
  `enterprisebench`, `sre-bench`, `gcpgoat`, `kubernetes-goat`, most of `wonderbread`.

### Gyms qualifying for `SAFE_EXECUTABLE` with only the constructor fix + a registry entry

**Zero `VendorBenchmarkProvider`-family gyms qualify** — all carry the authority-threading gap
above. Among local/bespoke providers, real, source-confirmed "yes" answers:

| gym_id | Confidence | Real caveat |
|---|---|---|
| `git` | High | Registry gap only; no authority flag; zero-arg constructible. Weakest link: `GitEnvironment.checkpoint()` requires a clean work tree as a real precondition trial-isolation would need to guarantee. |
| `http-json` | High | Registry gap only; authority already generically handled by the bridge's existing static `authority_ref`. `set`/`delete`'s open payload has no `_ACTION_PARAMS` entry, so default empty-payload probing wouldn't meaningfully exercise it without further design. |
| `memory` | High | Same shape as `http-json`. |
| `terraform-docker-apply` | Medium | No authority flag stated; not independently reconfirmed live this round; needs a reachable Docker daemon. |
| `mcp-client-session` | Medium | No authority flag *named* as a blocker, which is weaker evidence than a live-confirmed `False`. |
| `kubernetes-reconciliation` | Qualifies at code level, blocked by infra today | The local `kind-gymact-test` control-plane container is `Exited(137)`, consistent with the colima restart this session. |

None of these were migrated live this pass — real, careful goal-predicate and
`_ACTION_PARAMS` design is real work each one deserves on its own, not something to rush at the
tail of an already-large session (see `mcp-client-session`'s and `filesystem`'s census entries:
"no natural numeric/boolean goal dimension exists to found a predicate on" / "no declared
mechanism to bound candidate path/text values" — real, unstarted design, not mechanical wiring).

## What was not re-verified this pass

- The merged totals table's arithmetic (counts are the synthesizing agent's own tally, not
  independently re-summed).
- Every individual census claim below the ones this document quotes directly (dependency
  availability, exact file paths/line numbers) — trust the same standard round 1's entries
  carry: a real agent's source-grounded finding, not independently spot-checked by the main
  session for every row.
- No new `run_real_trial` was executed this pass. The 5 `LEVEL4_ALIVE` gyms are unchanged from
  round 1; the "migration attempts" phase of this workflow re-confirmed them from already-
  recorded evidence rather than re-running (the agents correctly recognized the conflict
  between their generic task prompt and the launch context's explicit "already done" list, and
  resolved it by citing existing evidence rather than fabricating a new run).

## New tasks filed

- **Authority-threading through `MaterializationIntent`** in both `_BRIDGE_SCRIPT` and
  `_EXECUTE_SCRIPT`, generalizing the same pattern `ActuationIntent` already uses
  (`AllowListAuthorityResolver({_AUTHORITY_REF})`). Real, scoped, additive — but deliberately
  not done this pass, since threading authority through materialize is a bigger behavioral
  change (it's what actually unlocks the ~46-vendor family, not just fixes construction) and
  deserves review on its own.
- **`git` gym integration** (goal predicate + `_ACTION_PARAMS` design) — the single best-scoped
  next real gym, per the table above.
- **Goal-oracle category A/B implementation** (reward-file contract, exit-code contract) — the
  two categories needing no new capability shape, only a goal-predicate projection rule each,
  covering ~9 vendors once authority-threading lands.

## See also

- `docs/level4-migration-matrix.md` — round 1's census (30 real entries) and the 5 real
  `LEVEL4_ALIVE` tracer bullets with full trial identities.
- `docs/STATUS.md` — the ledger row for this pass.
- `docs/2026-08-08-level4-shacl-tracer-bullet.md` — the evidence-kernel design these 5 gyms
  validate.
