# EXPLORE — every AutoFDE surface in this repository is a testbed prototype

This file is a boundary, not an introduction. Read it before citing anything under the AutoFDE
surfaces as a capability.

## The claim this file exists to prevent

scikit-decide is a **laboratory**. The AutoFDE material that arrives here — Azure Breach Clock,
Terraform world factory, adapter contracts, work-graph projection — is written in product register
(*production*, *crown*, *release candidate*, *executive demonstration*). Running product register
inside a laboratory is precisely how a prototype gets cited as a shipped capability.

So, stated once and bindingly:

> **No standing row produced under an AutoFDE surface in this repository transfers to the AutoFDE
> product.** AutoFDE ships from a different repository. Everything here is a prototype until it is
> re-established there, with its own evidence.

This is narrower than "the code is unfinished." Some of it works and has witnesses. The point is
that *working here* and *being an AutoFDE capability* are different claims, and only the first is
available in this tree.

## Explore surfaces

| Path | Status |
|---|---|
| `src/autofde_lab/autofde/` | EXPLORE |
| `infra/azure/` | EXPLORE |
| `infra/github/` | EXPLORE |
| `docs/autofde/` | EXPLORE |
| `tests/autofde/` | EXPLORE |
| `demo/` | EXPLORE |

## Exploit surfaces

`src/autofde_lab/{powl,agent,ocel,fabric}/` and `src/autofde_lab/{core,domains,solvers,hub}/` are
standing-bearing. They carry witnesses, they are cited in `docs/STATUS.md`, and they are what a
clean checkout must exercise.

## The one mechanical control

Documentation does not hold a boundary; a test does.

`tests/autofde/test_explore_boundary.py` asserts that **no exploit module imports any explore
module**. It parses module-level imports with `ast`, mirroring the existing
`test_no_adapter_module_imports_a_sibling_at_module_level`
(`tests/adapters/test_adapters.py:126`).

The direction is deliberate and asymmetric. Explore code may depend on exploit code — that is the
point of a testbed. The reverse would mean the prototype had quietly become load-bearing, and the
extraction below would stop being a copy.

## Extraction manifest

When the AutoFDE repository is created, these paths move. Nothing else does:

```text
src/autofde_lab/autofde/     →  the work-graph projection and phase graph
infra/azure/              →  the Terraform world factory
infra/github/             →  project-management-as-code
docs/autofde/             →  this directory, minus this file
tests/autofde/            →  the projection and boundary tests
demo/                     →  the executive demonstration
ontology/autofde-*.ttl    →  hand-authored AutoFDE vocabulary
```

`src/autofde_lab/adapters/azure/` is the ambiguous one and stays here on purpose: it is an *optional
adapter of scikit-decide*, which is a scikit-decide concern, not an AutoFDE one. The AutoFDE repo
consumes it as a dependency rather than absorbing it.

Whether that manifest is honest is exactly what the boundary test measures. If an exploit module
ever imports an explore module, the manifest is a fiction and the test goes red before anyone has
to notice by reading.

## What is deliberately absent

Book and press-release copy — the *Enterprise Architecture as Agency* framing, the manual-FDE
contrast as marketing, category naming, availability claims. A marketing claim inside a laboratory
is the same category error this file exists to prevent, one register further out. That material
lives with the book, not in the tree.

## See also

- `docs/autofde/PRODUCT.md` — the operating-model definition, written as a laboratory document
- `.claude/rules/standing-law.md` — the `ALIVE` / `PARTIAL_ALIVE` / `BLOCKED` / `UNKNOWN` /
  `UNSUPPORTED` vocabulary every claim here must carry
- `docs/STATUS.md` — the in-repo ledger, and the measured-win / recorded-negative convention
- `docs/ecosystem-standing.md` — cross-repository standing; read before any cross-repo claim
