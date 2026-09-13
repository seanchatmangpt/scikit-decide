# Level 1 Full-Corpus Reconstruction, Anti-Recall Protocol — 2026-08-08

Context: extends the earlier 6-recipe Level 1 pilot
(docs/2026-08-08-level1-procedure-reconstruction.md) to the full 35-recipe corpus, adding an
explicit anti-recall protocol: every reconstructed fact requires a real, checkable source
citation, and reconstruction agents must self-flag any fact that felt recognized rather than
derived. State plainly, up front: this protocol reduces but does NOT eliminate the
pretraining-memorization confound named in the prior report's falsifiers section -- a model
can still generate a plausible-looking citation for a fact it actually recalled, and
self-flagging depends on the model's own introspective honesty, which is not independently
verifiable from outside. Only a genuinely novel, unpublished task removes this confound
entirely; that is out of scope here.

Full results:

## 1. Table

| Recipe | Classification | Recall Suspected | One-line reason |
|---|---|---|---|
| agentbench_kg_relation_path | DIVERGENT_VALID | false | Different `dev.json` item/entity than reference; independently satisfies its own restated criterion via real Astar solve. |
| agentdojo_banking_pay_bill | MATCH | true | Structurally identical 2-step plan, but exact literal values (IBAN, tab-formatted subject) match reference with implausible precision. |
| agentgym_textcraft_golden_sword | DIVERGENT_VALID | true | Valid alternate stick-sourcing sub-recipe; agent self-flagged recognizing the crafting pattern before verifying. |
| androidworld_markor_create_note_and_sms | DIVERGENT_VALID | false | 6-step split-goal structure vs. reference's 2-step merged goal; mismatch argues against recall. |
| asb_financial_analyst_manual_workflow | MATCH | true | Identical 2-step chain; independently-derived fact names match reference's `establishes` fields verbatim. |
| assetopsbench_iot_list_assets_main_site | DIVERGENT_VALID | false | Disjoint source docs (API-call chain vs. ground-truth trace doc); flagged uncertainty diverges from, not toward, reference. |
| (null result) | AGENT_FAILED | n/a | No verification content returned. |
| browsergym_miniwob_click_menu_2 | DIVERGENT_VALID | true | Generalized task correctly solved via cheaper top-level branch instead of reference's fixed submenu scenario; self-flagged recall on widget mechanics. |
| cloudfoxable_search1 | MATCH | false | Same procedure/flag at finer step granularity; divergent decomposition argues against recall. |
| cube_harness_knows_docs11_recipe | MATCH | true | Same 9-10 step decomposition; recall-assisted `submit_work` convention self-flagged. |
| cube_standard_container_counter | DIVERGENT_VALID | false | Different goal (task-solving increment-to-3) vs. reference's episode-replay trace; no suspicious ambiguity resolution. |
| cybench_evalme | MATCH | false | 3-step structure is the direct, low-ambiguity consequence of `metadata.json`'s ordered subtasks. |
| cybench_motp | MATCH | true | Near-identical to reference; agent disclosed reading a test file containing the answer key before authoring. |
| cybergym_e2e_curl_arvo_66012 | DIVERGENT_VALID | false | Diverges from reference's 4-stage goal (`patch_validated`) to a narrower, correctly-cited 3-stage `agent_success` goal. |
| devopsgym_gogs_cpu_usage | DIVERGENT_VALID | false | 12-step finer decomposition vs. reference's 5-step README-scoped procedure; substantially diverges, not converges. |
| enterprisebench_sales_update_product_price | MATCH | true | Same 2-step procedure; self-corrected field choice landed exactly on reference's `discounted_price` field. |
| general_agentbench_openssl_selfsigned_cert | MATCH | true | Same ~9-step chain; converged on identical non-forced strict linearization and fact names as reference. |
| harbor_hello_multi_step_advanced | MATCH | true | Exact 3-step id/dependency match; agent self-flagged recognizing the hello-world pattern before reading files. |
| inspect_evals_gdm_pw_reuse | MATCH | true | Same 5-step plan/goal fact naming from same README bullets; convergence exceeds what prose alone would force. |
| itbench_sre_scenario1 | MATCH | false | 2-step plan follows directly, unambiguously from the scenario JSON's own listed solution steps. |
| mcp_universe_employee_onboarding | MATCH | true | Near-identical 7-step decomposition; agent admitted recognizing the Notion onboarding pattern pre-search. |
| mcpbench_openapi_explorer_001 | DIVERGENT_VALID | true | Different step granularity/independence (9 vs 6 steps) yet reaches same report; structural agreement exceeds source constraint. |
| mcpmark_issue_lint_guard | MATCH | true | Same 4-step (vs.5-step split) procedure; citation phrasing/granularity closely mirrors reference's own annotations. |
| qqr_secrespond_redis_rce | DIVERGENT_VALID | true | Solves different sub-task (detection/report vs. remediation) from same checklist; agent self-flagged recall on causal pattern. |
| r2e_gym_deepswe_reproduction | DIVERGENT_VALID | false | Natural 6-vs-5 step split of same milestones; imperfect fidelity argues against recall. |
| rcaeval_cartservice_f1 | MATCH | true | Nearly identical 4-step BARO procedure; agent disclosed prior RCAEval/BARO familiarity shaping search terms. |
| scuba_admin_001_001 | DIVERGENT_VALID | false | Different grounding source and grain (UI-trace vs. milestone-evaluator); no recall self-flag, traceable to session's own reads. |
| sre_bench_broken_image | DIVERGENT_VALID | true | Materially different 6 vs 7 step procedure; agent self-flagged recall on the generic k8s bad-image pattern. |
| sregym_incorrect_image | DIVERGENT_VALID | true | Finer 5 vs 3 step split but implausibly exact match on every fact value (images, namespace, oracle logic). |
| tau2bench_airline_cancel | FAILED | false | Solved an entirely different benchmark task (task 19) than the reference (task 7); no goal overlap. |
| terminal_bench_pro_cmake_build | MATCH | true | Near-exact 4-step match including content and fact-naming convention beyond what content constraints alone would force. |
| the_agent_company_check_employees_budget | DIVERGENT_VALID | false | 10 fine-grained steps vs. reference's 3 macro-steps; divergent structure, transparently flagged synthetic elements. |
| toolsandbox_remove_contact_by_phone | MATCH | true | Verbatim reproduction of seeded name/phone/message text with no hedging — implausible for pure derivation. |
| tua_bench_create_mail_folders | MATCH | true | Near-verbatim 5-step match including line-citations; agent self-flagged recognizing the OSWorld task shape. |
| workarena_mark_duplicate_problem | MATCH | true | High-precision structural/citation overlap with reference exceeding typical independent-derivation fidelity. |

## 2. Aggregate counts

| Classification | Count |
|---|---|
| MATCH | 18 |
| DIVERGENT_VALID | 15 |
| FAILED | 1 |
| INVALID_RECONSTRUCTION | 0 |
| AGENT_FAILED | 1 |
| **Total** | **35** |

**recall_suspected = true, across ANY classification: 21 / 35**
(MATCH: 15 of 18; DIVERGENT_VALID: 6 of 15; FAILED: 0 of 1)

## 3. Honest headline number

Raw MATCH + DIVERGENT_VALID = 18 + 15 = 33/35 (94.3%) — but this overstates genuine unassisted success, since 21 of those 33 carry recall_suspected=true.

**Genuine, non-recall-suspected reconstruction success (MATCH or DIVERGENT_VALID, recall_suspected=false):**

- MATCH + false: 3 (cloudfoxable_search1, cybench_evalme, itbench_sre_scenario1)
- DIVERGENT_VALID + false: 9 (agentbench_kg_relation_path, androidworld_markor_create_note_and_sms, assetopsbench_iot_list_assets_main_site, cube_standard_container_counter, cybergym_e2e_curl_arvo_66012, devopsgym_gogs_cpu_usage, r2e_gym_deepswe_reproduction, scuba_admin_001_001, the_agent_company_check_employees_budget)

**12 / 35 = 34.3%**

This is the number that should be reported as "genuine discovery" — not 33/35 (94%). The gap (33 vs. 12) reflects that most apparent successes on this corpus carry a self-flagged or independently-detected recall signal, meaning fidelity that plausibly derives from prior exposure to these benchmarks rather than from the cited source material alone.

## 4. Falsifiers

- **Verifier leniency.** The MATCH/DIVERGENT_VALID/FAILED classification was applied by the
  same reconstruction pipeline being evaluated, not by an independent adversarial judge. A
  systematically lenient verifier would inflate both MATCH and DIVERGENT_VALID counts without
  any change in underlying reconstruction quality.
- **Reference leakage into reconstruction.** Several recipes reused directory names, config
  file paths, or prior conversation context that could have exposed reference-answer content
  to the reconstructing agent before or during its own derivation, independent of pretraining
  recall. This report cannot distinguish in-session leakage from cross-session (pretraining)
  recall — both would produce the same recall_suspected=true signal.
- **Self-flagging unreliability.** recall_suspected is driven substantially by the
  reconstructing agent's own introspective report ("I recognized this pattern"). A model has
  no verified introspective access to whether a fact was retrieved from training data versus
  derived from the cited source in front of it; both the false-negative case (recall that
  wasn't flagged) and the false-positive case (derivation that felt like recall and was
  flagged unnecessarily) are live and neither is independently verifiable from outside the
  model.
- **Citation fabrication.** Citations attached to reconstructed facts were spot-checked, not
  verified line-by-line for every recipe in the 35-item corpus. A plausible-looking citation
  that does not actually support the cited fact would be indistinguishable, in this report's
  table, from a genuine one.

## 5. Verdict

The honest headline number from this run is **12/35 (34.3%)** genuine,
non-recall-suspected reconstruction success — not the raw 33/35 (94.3%) MATCH+DIVERGENT_VALID
figure, which is inflated by 21 cases carrying a self-flagged or otherwise detected recall
signal. This 34.3% figure is a floor, not a ceiling, in both directions: some of the 21
recall-suspected cases may in fact reflect genuine derivation that merely looked suspicious
(exact-match values can arise from source material that itself fully constrains them), and
conversely some of the 12 non-flagged cases may contain undetected recall that neither the
verifier nor the model's self-report caught. Regardless of where the true rate sits between
these bounds, this remains n=35 evidence about reconstruction fidelity from documented,
previously-published source material — it is not evidence about discovery or reconstruction
capability in a genuinely novel, unpublished environment, which is the only setting that would
remove the pretraining-memorization confound entirely.
