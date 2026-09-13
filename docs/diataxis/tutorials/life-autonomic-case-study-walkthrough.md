# Run the Autonomic Life Planning Case Study

In this tutorial you run a real, already-merged planning experiment, read its
deterministic evidence receipt field by field, prove it replays identically, and
make one small hands-on edit to see the evidence change in response.

## Prerequisites

- A checked-out copy of this repository, with dependencies installed
  (`uv sync --extra=all -v`, per the root `CLAUDE.md`).
- A working `.venv` for the repo.
- You will run commands with `PYTHONPATH=src`, the convention this repo's own
  case-study docs use so `autofde_lab` resolves without an editable install.

No prior knowledge of planning theory, PDDL, or this repo's architecture is
assumed. Everything you need is explained as you go.

## Step 1: run the test and see it pass

The case study ships with a Chicago-style test that exercises the real
planning kernel — no mocks. Run it:

```bash
PYTHONPATH=src .venv/bin/python -m pytest -vv tests/agent/test_life_autonomic_case_study.py
```

You should see all three tests pass (test IDs wrapped below for line width;
your terminal will show each on one line):

```text
tests/agent/test_life_autonomic_case_study.py::
  test_case_study_executes_real_planning_kernel_and_replays PASSED
tests/agent/test_life_autonomic_case_study.py::
  test_unknown_observation_is_not_silently_admitted PASSED
tests/agent/test_life_autonomic_case_study.py::
  test_frontier_is_candidate_only_and_non_actuating PASSED

3 passed
```

That `3 passed` line is your evidence, not a claim in this document — if your
run doesn't say that, stop here and diagnose before continuing.

## Step 2: run the CLI and read the receipt

The same case study has a CLI entry point that prints its evidence as JSON.
Run it:

```bash
PYTHONPATH=src .venv/bin/python -m autofde_lab.agent.life_autonomic_case_study
```

You'll see canonical, sorted-key JSON similar to:

```json
{
  "authority": "NONE",
  "continue_disposition": "CONTINUE",
  "do_authority": false,
  "evidence_kind": "PLANNING_EVIDENCE_ONLY",
  "exact_reuse_disposition": "EXACT_REUSE",
  "fresh_goal_disposition": "FRESH_PLAN",
  "frontier_keys": ["...", "...", "..."],
  "observation_digest": "...",
  "receipt_sha256": "...",
  "repair_affected_paths": ["1", "3"],
  "repair_disposition": "REPAIR",
  "schema": "urn:autofde-lab:life-autonomic-case-study-receipt:1",
  "subject": "stabilize-week"
}
```

This JSON is produced by `LifeCaseStudyReceipt.as_dict()` in
`src/autofde_lab/agent/life_autonomic_case_study.py`. Confirm these six
fields in your own output — they are the load-bearing claims of the case
study, each corresponding to one real transition of the `ContinuousPlanner`:

- `"exact_reuse_disposition": "EXACT_REUSE"` — the admitted `balanced` plan
  was reused exactly, by content-addressed key, with no replanning.
- `"repair_disposition": "REPAIR"` — closing the career-window fact forced a
  local repair.
- `"repair_affected_paths": ["1", "3"]` — the repair touched exactly node
  path `1` (`prepare-career-window`) and its downstream node `3`
  (`publish-household-brief`). Nodes `0` and `2` are untouched.
- `"continue_disposition": "CONTINUE"` — adding an irrelevant fact
  (`weather-noted`) did not trigger any replanning.
- `"fresh_goal_disposition": "FRESH_PLAN"` — asking for a different goal
  (`different-weekly-goal`) did not reuse the stale plan.
- `"authority": "NONE"` and `"do_authority": false` — this experiment never
  claims authority to actuate anything.

If any of those six values differs from what's shown above, the case study
is not behaving as documented — do not proceed past this point without
resolving that first.

## Step 3: prove it replays identically

Run the CLI a second time and compare the digest:

```bash
PYTHONPATH=src .venv/bin/python -m autofde_lab.agent.life_autonomic_case_study \
  > /tmp/receipt-run-1.json
PYTHONPATH=src .venv/bin/python -m autofde_lab.agent.life_autonomic_case_study \
  > /tmp/receipt-run-2.json
diff /tmp/receipt-run-1.json /tmp/receipt-run-2.json
```

`diff` should print nothing — the two files are byte-identical, so
`receipt_sha256` matches across runs. This is exactly the property the test
asserts directly:

```python
assert first.receipt_sha256 == second.receipt_sha256
```

You've now confirmed by hand what the automated test already checks: this
case study's evidence is a pure, replayable function of the fixed admitted
observations, not a run that happens to look the same.

## Step 4: make one small edit and watch the evidence change

Open `src/autofde_lab/agent/life_autonomic_case_study.py` and find the
`observations` tuple inside `run_case_study()`:

```python
observations = (
    LifeObservation("income-option-open", "case:income-observation", True),
    LifeObservation("career-window-open", "case:career-observation", True),
    LifeObservation("education-option-open", "case:education-observation", True),
    LifeObservation("household-brief-due", "case:household-observation", True),
    LifeObservation("unverified-side-project", "case:unknown-observation", False),
)
```

Add a sixth, admitted observation right after the fourth one:

```python
    LifeObservation("household-brief-due", "case:household-observation", True),
    LifeObservation("morning-review-done", "case:review-observation", True),
    LifeObservation("unverified-side-project", "case:unknown-observation", False),
```

Save the file, then re-run the CLI:

```bash
PYTHONPATH=src .venv/bin/python -m autofde_lab.agent.life_autonomic_case_study
```

Compare `observation_digest` and `receipt_sha256` in this new output against
the two values you captured in Step 3. Both changed — because
`observation_digest` is `sha256(...)` of the exact observation payload
(`_observation_payload`), and `receipt_sha256` is `sha256(...)` of the whole
receipt payload, so any change to what's admitted changes both digests
deterministically.

Notice what did **not** change: `exact_reuse_disposition`,
`repair_disposition`, `repair_affected_paths`, `continue_disposition`, and
`fresh_goal_disposition` are still `EXACT_REUSE`, `REPAIR`, `["1", "3"]`,
`CONTINUE`, and `FRESH_PLAN` — your new fact was never referenced by any
plan's `dependency_keys`, so it changes the observation record without
touching any planning transition. This is the same "irrelevant delta"
behavior Step 2's `CONTINUE` case demonstrated, now shown as a direct
consequence of an edit you made yourself.

When you're done, you can revert the edit (`git checkout --
src/autofde_lab/agent/life_autonomic_case_study.py`) to leave the repo as you
found it.

## What you just observed

You ran a real planning kernel — `ContinuousPlanner.decide()` from
`src/autofde_lab/agent/continuous_planning.py` — against a bounded, fictional
personal-operating-system world, and watched it produce four distinct,
correctly-classified transitions (`EXACT_REUSE`, `REPAIR`, `CONTINUE`,
`FRESH_PLAN`) from one fixed set of admitted observations, all of it
replayable byte-for-byte and none of it carrying any authority to act in the
world (`authority: "NONE"`, `do_authority: false`,
`evidence_kind: "PLANNING_EVIDENCE_ONLY"`). Then you changed what was
admitted and watched exactly the digests that should change, change, and
nothing else.

For applying this same pattern to a bounded planning world of your own, see
the [how-to guide](../how-to/adapt-life-case-study-to-your-own-planning-world.md).
For why this design looks the way it does — why observations are explicitly
admitted rather than inferred, why three plans are preserved instead of one
winner, and why the receipt is evidence rather than an execution artifact —
see the [explanation doc](../explanation/why-a-bounded-life-planning-case-study.md)
and the [case study record](../case-studies/life-autonomic-controller.md).
For the exact API surface used above, see the
[reference doc](../reference/life-autonomic-case-study-api.md).
