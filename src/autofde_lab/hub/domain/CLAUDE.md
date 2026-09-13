# Role

Concrete domains: the decision problems solvers search. Each subpackage composes builder mixins
from `src/autofde_lab/builders/domain/` into one class, usually via a preset in
`src/autofde_lab/domains.py` (`RLDomain`, `MDPDomain`, `GoalMDPDomain`,
`DeterministicPlanningDomain`, `POMDPDomain`, …).

# Authority

- Define state, observation, action/event, and transition semantics.
- Declare characteristics (agent, concurrency, dynamics, events, memory, observability, value,
  initialization) by choosing mixins — this is what makes a solver applicable.
- Wrap external problem formats: `pddl/`, `rddl/`, `up/`, `plado/`, `gym/`, `rcpsp/`.

# Non-authority

- A domain does not select a plan, admit one, or cause any effect in the world. `step()`
  advances a **model**, not a system.
- Domains named after ecosystem concepts (`chatman_clean_session/`, `career_admission/`,
  `tai_v30_1_1/`) model those concepts. They carry no admission or actuation semantics —
  BRCE is the portfolio's actuation DO-boundary and has no role in this repo.

# Inputs

Problem files (PDDL/RDDL/UP), Gym environments, scheduling data, constructor parameters.

# Outputs

`Domain` subclasses registered under the `autofde_lab.domains` entry-point group, reachable via
`load_registered_domain(name)`.

# Invariants

1. **Three-tier method naming.** Implement `_get_X_()`; never override the public `get_X()`
   autocast wrapper or the `_get_X()` LRU-cached layer. Same for
   `_state_step()` / `_state_reset()`.
2. Mixin chains are single-inheritance per dimension. Adding a characteristic changes which
   solvers `check_domain()` admits — a silent widening of applicability, so regenerate the
   ontology.
3. Registration is by entry point in `pyproject.toml`, not by import side effect. An
   unregistered domain is invisible to `fabric`, `coverage`, and the OpenClaw bridge (which
   refuses it as `REFUSED:UNREGISTERED_SUBJECT`).
4. `ChatmanCleanSession` is the only registered domain with no extras marker (pure core);
   others may be `UNSUPPORTED` in an environment lacking their extra (e.g. `TPDDLDomain` needs
   the `pddl` extra / `z3`).
5. Nearest working example first: `maze/` for a plain deterministic domain, `rcpsp/` for
   scheduling, `pddl/` for a wrapped external format. Do not re-derive the pattern from prose.

# Neighboring components

`src/autofde_lab/builders/domain/` (the mixins), `src/autofde_lab/domains.py` (presets),
`hub/solver/` (consumers), `hub/space/gym/` (spaces), `fabric/ontology.py` (derives
requirements from these classes), `tests/domains/`.

# Verification

A domain claim is `ALIVE` only with a Chicago-style test that constructs the real domain and
runs a real solver's `solve()` against it, executed this session:

```bash
uv run pytest tests/domains/python/test_<name>.py -v
```

The `chicago-domain-solver` skill automates the domain + fixture + test loop.

# Standing ceiling

Strongest establishable claim: **`ALIVE` for "this domain, constructed with these parameters,
admits solver S and S reached goal/cost C"**, with the run quoted.

Not establishable here: that the modelled process is faithful to any real-world system, that
any resulting plan is admissible, or that anything downstream would execute it. A domain named
after a real workflow is a model of it, and modelling fidelity is `UNKNOWN` unless separately
measured.

# Update obligations

- New or removed domain → update `pyproject.toml` entry points **and** regenerate
  `ontology/autofde-lab-capabilities.ttl`; `tests/ecosystem/` fails on drift.
- Changed mixin chain → re-run the coverage report; solver applicability moved.
- Close the loop in the same change (fixture + test), not a follow-up.
