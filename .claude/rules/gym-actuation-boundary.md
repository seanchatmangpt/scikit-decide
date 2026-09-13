---
paths:
  - "vendor/gyms/**"
  - "src/autofde_lab/gymact/**"
  - "src/autofde_lab/reasoning/**"
  - "src/autofde_lab/sota/**"
  - "src/autofde_lab/fabric/vendor_materialization.py"
  - "src/autofde_lab/fabric/forwardbench_fleet.py"
---

# Gym actuation boundary — vendor is reference, gymact is the only surface

This repo vendors real, exact-pinned gym checkouts under `vendor/gyms/`
(`sregym`, `devops-gym`, `enterprisebench`, ...) as real git submodules.
That vendoring exists for **reference, never for direct use**:

- Reading the real source (protocols, oracles, fault taxonomies, agent
  driver contracts) to ground design decisions correctly — this session's
  own extensive reading of `vendor/gyms/sregym/sregym/conductor/oracles/*`,
  `clients/*/driver.py`, `agents.yaml`, `main.py` is the intended use.
  Citing real file:line evidence in a docstring or comment
  (`materialize_sregym.py`'s `#: cited: vendor/gyms/sregym/...` comments
  are the correct pattern) is encouraged.
- Git-level pin auditing and materialization — `fabric/vendor_materialization.py`'s
  `audit_vendor`/`materialize_vendor` and `fabric/forwardbench_fleet.py`'s
  fleet-wide wrappers over them check/initialize the pinned revision. This
  is submodule bookkeeping, not actuation, and stays in scope here.

What is **never** in scope, from any file in `src/autofde_lab/`:

- `import` of anything under `vendor/gyms/` (no `sys.path` insertion into
  that tree, no `from vendor.gyms... import ...`, no relative import
  reaching into it).
- Directly launching a vendored gym's own subprocess (`main.py`,
  `clients/*/driver.py`) from autofde-lab code.
- Any other path that reads a vendored gym's live state or drives its live
  behavior without going through the one real, standalone `gymact`
  package.

## `gymact` is the only real actuation surface

`gymact` (`/Users/sac/gymact`, installed as a real editable dependency —
`pyproject.toml`'s `[tool.uv.sources]`) is the one, real, standalone
package that owns actual interaction with any gym: authority gating,
idempotency, RFC8785/BLAKE3 evidence, and the real
materialize/observe/act/verify/teardown lifecycle
(`gymact.models.Operation`). Every real diagnosis/mitigation trial this
session ran against sregym went through `gymact.gyms.sregym.SregymVendorProvider`
/ `SregymEnvironment` — never a hand-rolled subprocess or direct import of
the vendored checkout. That is the required pattern, not an incidental
one:

```python
# Correct — the pattern every real trial this session used
from gymact.gyms.sregym import SREGYM_CAPABILITIES, SregymVendorProvider
provider = SregymVendorProvider()
env = await provider.materialize(scenario=problem_id, config={...})

# Never — direct vendor access, regardless of how it's spelled
import sys; sys.path.insert(0, "vendor/gyms/sregym")
from clients.autofde_lab_dspy import driver  # NEVER
subprocess.run(["vendor/gyms/sregym/.venv/bin/python", "main.py", ...])  # NEVER
```

`src/autofde_lab/gymact/` (this repo's own internal sub-package —
`kernel.py`/`models.py`/`process.py`/`eventlog.py`) is a **thin adapter
over the real sibling package**, and must stay that way. Its own module
docstring is explicit: "This kernel no longer re-implements any of that
[authority gating, idempotency, evidence]... every one of these operations
builds a real `gymact.models` request, drives it through a real
`gymact.runtime.GymAct` instance." Never let this local sub-package grow
its own parallel semantics for something the real `gymact` package already
owns — that is exactly the dual-bookkeeping failure
`.claude/rules/no-dual-bookkeeping.md` names for evidence, applied here to
actuation authority instead.

## Where the real diagnosis/actuation path lives

`src/autofde_lab/reasoning/gymact_diagnosis_driver.py` (the POWL v2 -\>
gymact -\> sregym pipeline, `run_gymact_mediated_diagnosis`) and its
siblings (`gymact_dspy_react.py`, `gymact_dspy_signatures.py`) are the
real, current, correctly-scoped entry points — all import `gymact.gyms.sregym`,
none import `vendor.gyms.sregym`. `docs/2026-08-09-powl-actuation-sregym-progress.md`
is the living ledger of every real trial run through this path; read it
first for current state before starting new work here.

## Why this matters enough to be a standing rule

An earlier investigation this session found a real, working, 1080-line
SREGym-native agent driver (`vendor/gyms/sregym/clients/autofde_lab_planner/driver.py`)
orphaned in git history — real, substantial work, genuinely tempting to
"just recover and run directly." The correct call (made explicitly this
session, not assumed) was that recovering and *running* that driver
in-process, bypassing `gymact` entirely, is out of scope even though the
file itself is legitimate — because it re-opens exactly the direct-vendor-access
surface this rule closes. Mining its real domain logic (fault
detectors/remediators) into `gymact`-mediated `action_bindings` is in
scope; resurrecting it as a second, parallel actuation path is not.

## See also

- `.claude/rules/autonomic-loop-doctrine.md` — this same boundary restated
  as a four-stage loop with four boxed invariants, each traced to real
  code or named absent; `docs/2026-08-11-autonomic-loop-gap-ledger.md` is
  its evidence table.
- `CLAUDE.md` — the top-level project law this repo's rules restate; **"It
  computes candidate plans. It does not actuate."** — that applies to gyms
  exactly as it applies to everything else this repo touches.
- `.claude/rules/actuation-boundary.md` — the sibling boundary for the
  OpenClaw bridge; same principle (real actuation lives in one named,
  audited surface), different subsystem.
- `.claude/rules/no-dual-bookkeeping.md` — why `src/autofde_lab/gymact/`
  may never grow parallel semantics to the real `gymact` package.
- `docs/2026-08-09-powl-actuation-sregym-progress.md` — the living,
  append-only ledger of every real gymact-mediated sregym trial.
