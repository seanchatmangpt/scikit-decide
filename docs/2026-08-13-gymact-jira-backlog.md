# gymact Jira-style backlog — 2026-08-13

Synthesized from three real survey reports over `~/gymact`: (1) chatman-state vs
dev_portfolio duplication, (2) TODO/FIXME/BLOCKED scan, (3) docs-disclosed open items.
Every ticket below cites evidence actually reported by those surveys; nothing here is
speculative.

### GYMACT-1: dev_portfolio.py duplicates chatman_state's local/github-repo-state shape, unregistered and unreachable
- **Type**: Bug
- **Priority**: P0
- **Evidence**: `src/gymact/gyms/chatman_state_gym.py:36-46` (`list_local_repos`,
  `list_github_repos`) vs `src/gymact/gyms/dev_portfolio.py:121-140`
  (`snapshot_local_state`, `snapshot_github_state`); registration check via
  `registry.py:15,48`, `combinatorial_ocel.py:58,257-264`, and
  `grep -rln "dev_portfolio\|DevPortfolio" src/gymact/` returning only
  `dev_portfolio.py` itself.
- **Description**: Both gyms expose a local-repo-list-shaped read and a
  github-repo-list-shaped read over the user's own portfolio state, but answer
  different questions (chatman_state: open-ended recency discovery; dev_portfolio:
  bounded named-repo PR/issue/branch backlog) with no cross-import, shared capability
  namespace, or comment referencing the other. `dev_portfolio` is currently dead code
  from the registry's perspective — not in `_BUILTINS`, not in `GYM_FACTOR`/`_SCENARIOS`
  — so there is no live duplication defect today, but registering it as-is would create
  two independently-invokable, unreconciled answers to "what's the state of my local
  repos." dev_portfolio.py's own docstring (line 21-22) claims no other gym file calls
  `gh`/GitHub API, which is false — `chatman_state.py:164-179,198-205` both call `gh` —
  evidence the two were written without awareness of each other.
- **Definition of done**: A decision record (or code change) exists stating either (a)
  dev_portfolio.py is deleted/archived as superseded, or (b) it is registered under an
  explicitly distinct capability namespace with a doc comment in both files cross-
  referencing the other and stating the scope difference (discovery-and-recency vs.
  named-repo-backlog). `grep -rln "dev_portfolio\|DevPortfolio" src/gymact/` result is
  consistent with the chosen option (empty if deleted; includes `registry.py` and
  `combinatorial_ocel.py` if registered).

### GYMACT-2: dev_portfolio.py docstring makes a false grep-verifiable claim about gh/GitHub API usage
- **Type**: Bug
- **Priority**: P1
- **Evidence**: `src/gymact/gyms/dev_portfolio.py:21-22` (docstring: "nothing else in
  `gymact/src/gymact/gyms/*.py` calls the GitHub API or `gh` CLI today (confirmed by
  grep before writing this file)") contradicted by `src/gymact/gyms/chatman_state.py:164-179`
  and `chatman_state.py:198-205`.
- **Description**: The docstring asserts a grep-confirmed fact that is false as
  written — `chatman_state.py` already calls `gh` in two places. This is a documentation
  defect that misrepresents the codebase's actual state and is the one piece of hard
  evidence supporting that dev_portfolio.py was authored without visibility into
  chatman_state.py.
- **Definition of done**: `src/gymact/gyms/dev_portfolio.py`'s module docstring is
  corrected to acknowledge `chatman_state.py`'s existing `gh` usage, and
  `grep -n "gh CLI today\|nothing else" src/gymact/gyms/dev_portfolio.py` no longer
  matches the false claim.

### GYMACT-3: docs/STATUS.md referenced by ecosystem convention does not exist in gymact
- **Type**: Task
- **Priority**: P2
- **Evidence**: Survey 3 — `find`/`ls` over `~/gymact` confirm `~/gymact/docs/STATUS.md`
  is absent from the repository tree.
- **Description**: The sibling repo `autofde-lab` maintains `docs/STATUS.md` as its
  in-repo WIP ledger per its own `CLAUDE.md`. gymact has no equivalent file, even though
  closely-named documents exist (`sota-standing.md`,
  `docs/audits/2026-08-08-stubs-wip.md`, `2026-08-08-gymact-constitution.md`). Whether
  gymact is expected to carry a `docs/STATUS.md` at all is `UNKNOWN` from these surveys
  alone — this ticket records the disclosed gap, not a decision to create one.
- **Definition of done**: A decision is recorded (in an existing gymact doc or this
  ticket's resolution) on whether `docs/STATUS.md` is required for gymact; if yes, the
  file exists at `~/gymact/docs/STATUS.md` and follows the same ledger convention
  referenced by `autofde-lab/CLAUDE.md`.

### GYMACT-4: docs/ecosystem-standing.md referenced by ecosystem convention does not exist in gymact
- **Type**: Task
- **Priority**: P2
- **Evidence**: Survey 3 — `find`/`ls` over `~/gymact` confirm
  `~/gymact/docs/ecosystem-standing.md` is absent from the repository tree.
- **Description**: Same gap class as GYMACT-3, for the cross-repo standing ledger.
  Closest present analogues in `~/gymact/docs/` are `assurance.md`, `architecture.md`,
  `crown-compiled-reference.md`, `gymact-thesis.md`, `gymact-prd-ard.md`. Whether these
  are meant to supersede or feed an `ecosystem-standing.md` is `UNKNOWN` from the
  surveys.
- **Definition of done**: A decision is recorded on whether gymact needs its own
  `docs/ecosystem-standing.md` or whether standing is intentionally tracked only in
  `autofde-lab`'s copy; if the former, the file exists and cites the per-stage
  ALIVE/BLOCKED/UNSUPPORTED vocabulary it is meant to carry.

### GYMACT-5: confirm BLOCKED usages remain scoped to typed refusal vocabulary, not latent TODOs
- **Type**: Tech Debt
- **Priority**: P3
- **Evidence**: Survey 2 — `grep -rn "TODO|FIXME|XXX|BLOCKED|NotImplementedError" src/gymact/`
  (excluding vendor/, .venv/, node_modules/) returns 40 matches, all `BLOCKED`, all
  confirmed on inspection to be `Standing.BLOCKED` enum usages or
  `"BLOCKED:<REASON>"` string literals in `kernel.py`, `combinatorial.py`, `maximal.py`,
  `catalog.py`, `plugins.py`, `gyms/ggen.py`, `gyms/vendor_benchmarks.py`,
  `surfaces/fastapi.py`, `requirements.py`, `dcm_requirements.py`. Zero `TODO`/`FIXME`/
  `XXX`/`NotImplementedError` matches.
- **Description**: No unfinished-work markers were found; every `BLOCKED` hit is the
  intended runtime refusal taxonomy per this ecosystem's standing-law vocabulary, not a
  placeholder for missing code. This ticket exists only to record that the scan was run
  and came back empty of actionable TODOs, and to make the check re-runnable as the
  codebase changes.
- **Definition of done**: `grep -rnE "TODO|FIXME|XXX|NotImplementedError" src/gymact/`
  (excluding vendor/, .venv/, node_modules/) returns zero matches, or any new match is
  triaged into its own ticket rather than left unscanned.
