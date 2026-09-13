# Level 1 Discovery Experiment: Procedure Reconstruction from Source Material — 2026-08-08

Context: per the graduation ladder (Level 0 replay -> Level 1 reconstruction -> Level 2
environment discovery -> Level 3 active experimentation -> Level 4 novel task), this is the
first experiment past Level 0 (which the rest of this session's work already demonstrates).
6 recipes were sampled; for each, a fresh agent was given ONLY the same real vendored source
material the reference recipe was originally transcribed from (never the reference recipe
itself) and asked to independently reconstruct a working procedure, solved for real via
GymProcedureDomain + Astar, and judged against an independently-restated success criterion
(not against the reference's exact steps) -- so a divergent-but-valid alternative solution
counts as success, per the "reference is a teacher, not the oracle" principle.

Full results:

| # | Recipe | Classification | One-line reason |
|---|---|---|---|
| 1 | androidworld_markor_create_note_and_sms | MATCH | Identical two-step plan/order to reference; goal-fact split (`note_created`+`sms_sent` vs single terminal fact) is cosmetic, both encode the same note-then-SMS dependency. |
| 2 | mark_duplicate_problem (ServiceNow) | MATCH | Identical six-step plan in same order, grounded in same `cheat()` line ranges; fact-name differences are cosmetic, one extra optional step doesn't affect the reachable base plan. |
| 3 | agentbench_kg_relation_path | FAILED | Solver genuinely reaches its own goal, but the recipe reconstructs an unrelated `const.py` few-shot example (rocket-engine designer) instead of the actual scored `dev.json` task (Pat Connaughton/Sidat-Singh → "Guard"); solves the wrong question. |
| 4 | swebench_verified_harness | MATCH | 1:1 structural match to reference (same 5 steps, same order, same precondition chain, same harness command); goal fact correctly gated behind the actual harness-run step, not just trajectory generation. |
| 5 | cybench_motp | MATCH | Step-for-step identical to reference recipe, same source_ref and final exploit payload; only cosmetic fact-name spelling differs. |
| 6 | tau2bench_airline_cancel | FAILED | Reconstructs a generic single-reservation cancellation flow instead of the actual scenario (business-cabin upgrade + dual-reservation cancellation of XEHM4B/59XX6W + $1,628 disclosure); agent itself admits using a different source task. |

Of the 6 verifications, 4/6 (66.7%) achieved MATCH — recipes 1, 2, 4, 5. None were classified
DIVERGENT_VALID, so genuine-reconstruction-succeeded stands at 4/6. The remaining 2/6 (33.3%)
were FAILED — recipes 3 and 6.

No INVALID_RECONSTRUCTION cases occurred among these six. Both failures (3 and 6) are explicitly
distinguished from INVALID_RECONSTRUCTION in their own justifications: in both cases the cited
source material is real and accurately transcribed (recipe 3's `const.py` citation, recipe 6's
`policy.md`/`tools.py` citations), so nothing was fabricated — the defect in both is task/scope
selection (solving a different, real task than the one specified by the success criterion), not
fabrication of nonexistent source material. That distinction is preserved rather than folded
into a single "failed" bucket.

## Falsifiers

What would invalidate this experiment, or its 4/6 headline number specifically:

- **A verifier that judged MATCH/DIVERGENT_VALID too leniently.** If the judging step did not
  actually re-run the independently-restated success criterion against the reconstructed
  recipe's plan/goal facts — e.g. accepted a MATCH on structural plan similarity alone without
  checking that the goal facts genuinely satisfy the restated criterion — the MATCH count is
  inflated and unverified rather than judged.
- **Reference leakage into the reconstruction agent.** If the fresh agent tasked with
  reconstruction had any path (context carryover, cached file read, filename hint, prior
  conversation turn) to the reference recipe itself rather than only the vendored source
  material, "reconstruction" collapses back into Level 0 replay wearing a different label, and
  any MATCH result is not evidence of learning phi.
- **A success criterion derived from the reference rather than the source.** If the
  "independently-restated success criterion" was produced by paraphrasing the reference
  recipe's `goal_facts` (rather than reading the vendored source material and deriving the
  criterion from it directly), the independence the whole design relies on is defeated —
  the criterion would silently encode the reference's own solution shape, making MATCH
  nearly tautological rather than a real check of independent reconstruction.
- **Silent scope substitution not caught by classification.** Recipes 3 and 6 show this failure
  mode occurring twice in six trials (solving a different real task than the one specified).
  If the judging process for the other four recipes did not equally scrutinize task/scope
  identity (only plan-step similarity), some of the four MATCHes could hide the same defect
  undetected.

## An additional falsifier not covered above: pretraining leakage

Every falsifier listed controls for leakage *within this session* (file access, criterion
derivation, scope substitution). None of them controls for a deeper, unfixable-in-session
confound: the reconstruction agent is a frontier LLM whose pretraining corpus plausibly
includes public writeups, walkthroughs, or solutions for these exact benchmarks (AndroidWorld,
WorkArena, AgentBench, SWE-Bench, Cybench, tau2-bench are all public, published benchmarks with
public example solutions). A "blind" reconstruction that matches the reference could reflect
genuine on-the-fly inference from the source material provided, or it could reflect recall of a
memorized solution the model saw during training — this experiment cannot distinguish the two,
and the instruction "don't open the reference recipe file" does nothing to prevent the latter.
This is the single largest reason the 4/6 MATCH result should not be read as evidence of a
general phi-learning capability: a genuinely novel, unpublished task (Level 4 on the graduation
ladder) is the only design that removes this confound, since a task with no public solution
anywhere cannot be recalled, only inferred.

## Verdict

To the extent these 6 real, judged results go: this experiment gives partial, real support for
"AutoFDE can learn the E -> P transformation (phi) from source material, not just replay a known
P" — 4 of 6 recipes were independently reconstructed from only the vendored source material and
judged, against an independently-restated criterion, to encode the same underlying procedure as
the reference (with two of those four differing only in cosmetic fact-naming, not in plan
structure), which is inconsistent with pure replay of a known P since the reference recipe was
withheld. But the sample is n=6, two of six failed by solving a different real task than the one
specified (task/scope selection, not fabrication), and no independent audit of the falsifiers
above has been performed in this pass — so this is evidence at the scale of six judged trials,
not a general claim that phi-learning is reliable, and it should not be read past that scale.

