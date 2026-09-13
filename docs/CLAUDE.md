# Role

Explanation, projection, and ledger. Two ledgers carry standing witnesses — `STATUS.md`
(in-repo WIP) and `ecosystem-standing.md` (cross-repository, `~/mfw`, `~/ggen`,
`~/ggen-create`, `~/ggen-legacy`, `~/bcinr`). Everything else is guide material rendered by
the docs build.

# Authority

- **Report** observed standing: a command run, its output quoted, the date, the commit.
- Name blockers precisely enough that the next pass does not rediscover them from zero.
- Hold repair plans (RP-1…RP-7) with owner, evidence, interface, steps, negative fixtures,
  acceptance test, falsifier, resume condition.

# Non-authority

- **Docs never create standing.** A row here is a record of a run, not a substitute for one.
  Where this directory and the code disagree, the code is the witness and the sheet gets
  corrected.
- No file here may be cited as proof of a capability. Cite the test or the command.
- `docs/` outside the two ledgers is explanation only — never a standing or authority source.

# Inputs

Executed commands and their output; test results; source inspection with file:line citations.

# Outputs

`STATUS.md`, `ecosystem-standing.md`, `wip-followup-plans.md` (scoped, **unverified by
construction**), `agentic-fabric.md`, `chatman-ecosystem-wasm.md`,
`guide/chatman-clean-session.md`, `caching.md`, `ci.md`, `install.md`, `contribute.md`.

# Invariants

1. **Three ledger row types, no fourth**: *measured win* (command run this session, output
   quoted, passed), *recorded negative* (attempted, genuinely blocked, blocker named), and
   *deferred/scoped* (a plan exists, nothing under it executed — treat as unverified).
2. **Historical corrections stay visible.** When a claim is retracted, the retraction is
   written next to it, not edited away — the demotion of the career-admission "Chicago" test
   and the retraction of "the homebrew build is stale" are the worked examples. Deleting a
   wrong claim destroys the evidence that the discipline works.
3. Do not merge the two ledgers. A green row in `STATUS.md` says nothing about cross-repo
   closure.
4. Explore-phase reports use the nano-nonfiction dispatch shape (Standing / Identity / What
   changed / Admission & bounds / Local execution / Standing by boundary / Falsifiers) —
   `.claude/rules/explore-register.md`, or the `standing-report` skill.
5. Markdown standards: one H1, no line over 100 characters, every code block declares a
   language, relative links, no subjective adjective without a measurable criterion.

# Neighboring components

`.claude/rules/standing-law.md` (the vocabulary every row uses), `.claude/rules/*` generally,
`tests/ecosystem/` (the runs `ecosystem-standing.md` ledgers), `ontology/` (generated
capability graph the coverage rows cite), `FORWARD_DEPLOYMENT.md`.

# Verification

```bash
uv run pytest --nbmake notebooks -v          # notebook docs
python docs/generate_nb_index.py             # index generation
```

Ledger rows are verified by re-running the quoted command and comparing output — that is the
only check that matters here.

# Standing ceiling

Strongest establishable claim from this directory: **"this run happened, this was its output,
on this date, at this commit"** — a faithful record.

A document can never raise the standing of the thing it describes. `ecosystem-standing.md`
records `ALIVE` for S3/S3b and `UNSUPPORTED`/`BUILD_BROKEN`/`PARTIAL_ALIVE` elsewhere; those
statuses are properties of the code and the sibling repos, not of the file. Anything in
`wip-followup-plans.md` is `UNKNOWN` until it reaches a ledger with a witness. A doc that
described a capability accurately is still not evidence the capability exists — a map is not a
proof.

# Update obligations

- Every closure pass appends a dated section; it does not overwrite the prior one.
- A retracted claim gets a retraction note in place, with the corrected finding beside it.
- Any change to the standing vocabulary or to the collection-broken file list must be made in
  `.claude/rules/standing-law.md` too — crown-level invariants are restated, never relocated.
- `docs/chatman-ecosystem-wasm.md` uses a narrower `ALIVE`/`REFUSED`/`BUILD_BROKEN` vocabulary
  that explicitly rejects `BLOCKED`; do not conflate it with the standing law.
