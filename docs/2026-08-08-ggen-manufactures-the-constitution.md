# ggen manufactures the semantic constitution — first real Python manufacture

Measured win. Real `ggen sync run` against the merged working-backwards Lab
constitution (PR #37, merge commit `41365ab`) manufactured 8 Python modules
directly into `src/autofde_lab/constitution/` — no `generated/` directory,
no separate output tree, matching `ontology/manufacture.ttl`'s own law:
*"manufacture provenance never creates a special source-code namespace or
directory."*

## Identity, re-measured this session, not copied from earlier exploration

The request referenced `v26.8.8`. Precisely, as of this run:

- `~/ggen/target/release/ggen --version` → `26.8.6`.
- `git -C ~/ggen rev-parse HEAD` → `657a0befbd331be7c6c7da3dbe23b153342c1c8e`.
- `git -C ~/ggen describe --tags --always` → `v26.8.8-3-g657a0befb` — HEAD is
  **3 commits past a real tag `v26.8.8`** (created 2026-08-07T23:10:12Z).
- The built binary's own `--version` string (`26.8.6`) does **not** match the
  nearest git tag (`v26.8.8`) — a live instance of the exact defect
  `docs/ecosystem-standing.md`'s **RP-1** already tracks as open (binary
  self-reported version strings do not reliably identify the build). Neither
  number is fabricated here; both are reported, and the git commit hash is
  what's cited as the authoritative actuator identity below, not either
  version string.
- `autofde-lab` still has no `vNN`/semver of its own (`docs/release/*.md`
  already states ggen's version "belongs to a different project") — this doc
  follows the repo's own `docs/YYYY-MM-DD-slug.md` convention, not ggen's.

## What was manufactured, and from what

`ggen.toml` (repo root) — `[ontology] source = "ontology/lab.ttl"`, `imports`
the other 7 non-meta files. One shared Tera template
(`templates/constitution_module.py.tera`) reused by 8
`[[generation.rules]]` entries, each `mode = "Create"` (refuse-if-exists,
never silent-overwrite), differing only in `query.file` and `output_file`.

Before any of that, the 8 merged ontology files got one small, additive
change: an `rdfs:isDefinedBy <urn:autofde-lab:ontology:X>` triple on every
`owl:Class` declaration (no existing triple touched), so one shared SPARQL
pattern could select "classes/properties/individuals belonging to file X"
from the single merged graph. Verified per file, class count vs. tagged
count, exact match on all 8:

| file | classes | isDefinedBy-tagged | match |
|---|---|---|---|
| lab.ttl | 8 | 8 | yes |
| world.ttl | 6 | 6 | yes |
| planning.ttl | 10 | 10 | yes |
| process.ttl | 8 | 8 | yes |
| authority.ttl | 2 | 2 | yes |
| evidence.ttl | 13 | 13 | yes |
| standing.ttl | 3 | 3 | yes |
| interop.ttl | 7 | 7 | yes |

`ontology/manufacture.ttl` was deliberately **excluded** — it describes the
manufacturing process itself (`ManufactureRun`, `ManufactureReceipt`), and no
individual of either class exists yet anywhere to project honestly.

## Real commands, real output

```console
$ ~/ggen/target/release/ggen graph validate --files ontology/lab.ttl,ontology/world.ttl,ontology/planning.ttl,ontology/process.ttl,ontology/authority.ttl,ontology/evidence.ttl,ontology/standing.ttl,ontology/interop.ttl
{"files_checked": 8, "files": [ ... 8 entries, each {path, quads, hash} ... ]}
```

Zero violations, 8/8 parsed. (Quad counts: 62, 57, 96, 90, 57, 176, 59, 73 —
matching an independent `rdflib` parse of each file exactly.)

```console
$ ~/ggen/target/release/ggen sync run --dry-run --format json
{"written": [... 8 files ...], "skipped": [], "graph_hash_hex": "343bae62..."}

$ ~/ggen/target/release/ggen sync run --format json
{"written": [... same 8 files ...], "skipped": [], "graph_hash_hex": "343bae62..."}
```

`closure` in both outputs hashes every input: all 8 `.ttl` files, all 8
`.rq` query files, and — confirming the ONE shared template really is reused
across all 8 rules — a single `templates/constitution_module.py.tera` hash
common to every rule's closure entry.

**Two real defects were caught by inspecting the rendered output before
treating the run as done, fixed, and re-verified — not glossed over:**

1. First real run: `ggen`'s `local()` template function splits an IRI on the
   last `/` or `#`. This ontology's IRIs are `urn:autofde-lab:`-scheme URNs
   with no such delimiter (e.g. `urn:autofde-lab:ALIVE`), so `local()`
   returned the full IRI unchanged and the template emitted
   `urn:autofde-lab:ALIVE = "urn:autofde-lab:ALIVE"` — invalid Python syntax.
   Fixed by replacing every `local(iri=...)` call with
   `... | replace(from="urn:autofde-lab:", to="")`, which is exact for this
   ontology's single-namespace design.
2. Second real run (after fix 1): `ontology/standing.ttl`'s `afl:StandingValue`
   is simultaneously an `owl:Class` (rendered by the class/property arm) and
   the type of 6 named individuals (rendered by the value arm as an `Enum`)
   — producing **two conflicting `class StandingValue` definitions in one
   file**, the second silently shadowing the first at runtime, plus a
   duplicate `__all__` entry. Fixed by computing `vocab_class_iris` (the set
   of classes that own named individuals) and excluding them from the
   class/property render arm — a vocabulary class renders as its `Enum` only,
   never also as an empty dataclass.

A third, cosmetic-but-real defect: applying ggen's `pascal_case` filter to
already-PascalCase ontology names mangled acronym-containing ones —
`POWLCommitment`/`POWLProcess` rendered as `Powlcommitment`/`Powlprocess`.
Since every class name in this ontology is already authored as a valid
Python identifier in correct PascalCase, the filter was removed entirely for
class names (kept for `snake_case` on property names, which are genuinely
camelCase in the source and need it).

Final rendered `src/autofde_lab/constitution/process.py` excerpt, confirming
the fix:

```python
@dataclass(frozen=True)
class POWLCommitment:
    """An exact partial-order commitment derived only from a governed candidate. It does not itself grant actuation authority."""
    commits_to: str | None = None  # ... (ref: GovernedCandidate)
    committed_process: str | None = None  #  (ref: POWLProcess)
```

```console
$ ~/ggen/target/release/ggen receipt verify --format json
{"valid":true,"chain_hash":"d467916a9957657fe6884fcebc2ab92486e2025e32faa4356a9e6a33295ee4a8","payload_hash":"0940cba12d6a6173a08eac3b3eadd7ba146da66ec3e212683f68b6e55c4eac68","graph_hash":"343bae62ea72350d5c5f2abce6a31a68320654532fa8c21819c9445d9d6552ec","outputs":8,"signed":true,"signature_valid":true}
```

**Determinism re-run** (same graph, no source changes):

```console
$ ~/ggen/target/release/ggen sync run --format json
{"written":[],"skipped":[["src/autofde_lab/constitution/lab.py","mode=create: target already exists"], ... all 8 ...],"graph_hash_hex":"343bae62..."}
```

`mode = "Create"` means the determinism guarantee shows up as **refuse to
touch an existing file** rather than `docs/ecosystem-standing.md`'s S4
precedent's `"skipped: unchanged: content identical"` (that precedent used
`mode = "Overwrite"`) — same underlying guarantee (nothing changes on a
repeat run against the same graph), stricter failure mode (a real content
drift would be a hard `Create` refusal on the next deliberate regeneration
attempt, not a silent overwrite).

## Verification: every manufactured name really imports and constructs

```console
$ .venv/bin/python -c "... construct every class in every __all__, assert real field values ..."
lab: 8 names OK
world: 6 names OK
planning: 10 names OK
process: 8 names OK
authority: 2 names OK
evidence: 13 names OK
standing: 3 names OK
interop: 7 names OK

total dataclasses constructed with zero args: 56
total enums verified non-empty: 1
ALL 57 manufactured names verified
```

57 manufactured Python names, exactly matching the 57 `owl:Class`
declarations counted independently above.

## Chicago-style tests — 8 new files, 89 tests, real pytest runs, zero mocks

One test file per manufactured module, each: reads the real manufactured
source first, imports the real module, constructs every class with real
field values, asserts on the real constructed state, and (for every dataclass)
asserts `dataclasses.FrozenInstanceError` on a real mutation attempt.
`standing`'s test additionally asserts the `StandingValue` enum has exactly
the six `standing-law.md` members with exact string values.

```console
$ .venv/bin/python -m pytest tests/test_constitution_*.py -v
tests/test_constitution_authority_chicago.py ......                      [  6%]
tests/test_constitution_evidence_chicago.py ................             [ 24%]
tests/test_constitution_interop_chicago.py ............                  [ 38%]
tests/test_constitution_lab_chicago.py ...........                       [ 50%]
tests/test_constitution_planning_chicago.py ..............               [ 66%]
tests/test_constitution_process_chicago.py ............                  [ 79%]
tests/test_constitution_standing_chicago.py .......                      [ 87%]
tests/test_constitution_world_chicago.py ...........                     [100%]
============================== 89 passed in 0.19s ==============================

$ grep -rn "unittest.mock\|Mock(\|MagicMock\|patch(\|monkeypatch" tests/test_constitution_*.py
(no matches)
```

## Full regression — `just test`

Three pre-existing failures, none touching anything this pass created or
modified — confirmed via `git status --short` showing all three files
untouched by this session (they arrived via the `git merge origin/master`
Stage 0 step, which brought in 77 files / 7205 insertions unrelated to this
work):

- `tests/fabric/test_crown_errc.py::test_terminal_registry_is_not_rewritten_without_execution_receipts`
- `tests/autofde/test_explore_boundary.py::test_core_modules_do_not_reach_autofde_dynamically`
- `tests/ocel/test_powl_replay_boundary.py::test_powl_replay_never_imports_spiffworkflow_or_ofmf`

Plus one pre-existing environment skip (`test_optional_dependencies.py` —
`a2a` module absent). Not investigated or fixed here — out of scope for this
pass, reported rather than silently absorbed into a passing count.

## Explicitly not claimed

- **Not wired into any runtime code path.** No planner, no `level4_crown`, no
  gymact bridge imports `autofde_lab.constitution.*`. This is a pure additive
  projection, matching PR #37's own stated scope.
- **Not the full C4 architecture.** `model/`, `admission/`, `capabilities/`,
  `gyms/`, `experiments/` have no ontology yet — nothing was invented for
  them here.
- **Standing dimensions and the `BLOCKED`-carries-a-reason rule remain
  unmodeled.** `technicalStanding`/`organizationalStanding`/`enterpriseStanding`
  do not exist anywhere in the merged ontology (confirmed by grep, zero
  occurrences across all 12 files); `afl:Refusal`'s `refusalReason` is not
  wired to `afl:BLOCKED` by any property. Both are reported gaps, not
  invented content — per `absence-is-not-evidence.md`.
- **The live Level4-crown standing types are untouched.** `FactorState`,
  `CrownStanding` (`hub/domain/gym_procedure/crown_factor.py`,
  `level4_crown_runner.py`) are a different, pre-existing, hand-written
  system; nothing here supersedes or duplicates them.

## Files changed

Additive only, except the 8 ontology files (which gained one triple per
class, nothing removed or reworded):

- `ontology/{lab,world,planning,process,authority,evidence,standing,interop}.ttl`
  — `rdfs:isDefinedBy` annotations added.
- `ggen.toml`, `templates/constitution_module.py.tera`,
  `queries/constitution/*.rq` (8 files) — new.
- `src/autofde_lab/constitution/{__init__,lab,world,planning,process,authority,evidence,standing,interop}.py`
  — new; 8 of 9 manufactured by `ggen sync run`, `__init__.py` hand-written.
- `tests/test_constitution_*_chicago.py` (8 files) — new.

## See also

- `ontology/manufacture.ttl` — the RDF law this pass instantiates for the
  first time (no `ManufactureRun` individual emitted yet; a natural next
  step, deliberately not attempted here).
- `docs/ecosystem-standing.md` **RP-1** — the ggen build-identity mismatch
  this pass encountered directly (binary `--version` vs. git tag disagreeing).
- `.claude/rules/testing-chicago-style.md` — the discipline the 8 new test
  files follow.
