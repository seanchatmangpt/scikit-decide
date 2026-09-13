# AutoFDE Planner-League Planning Pack

Frozen against `seanchatmangpt/autofde-lab@d47ce62018fec51751b2b615ca300e44afe903ab`.

This is a **planning-subject pack**, not an agent prompt pack. It has two layers:

1. `pddl/` — executable causal/meta-plans for AutoFDE-Lab's classical PDDL engine.
2. `league/` + `plans/` — population, role, cross-play, curriculum, transition and ecosystem semantics that classical PDDL should not impersonate.

## Run

```bash
python tools/validate_pack.py
python tools/bind_registry.py --out planner-bindings.generated.json
python tools/run_meta_plan.py pddl/problems/00_ecosystem_full_crown.pddl --plan ecosystem.plan --powl ecosystem.powl.ttl
python tools/run_meta_plan.py pddl/problems/10_world_cyber_self_play.pddl --plan cyber.plan --powl cyber.powl.ttl
```

Equivalent direct engine invocation:

```bash
python -m autofde_lab.fabric.pddl_engine \
  pddl/autofde-meta-planning-domain.pddl \
  pddl/problems/00_ecosystem_full_crown.pddl \
  ecosystem.plan ecosystem.powl.ttl
```

## Safety / authority law

The PDDL domain has **no action that creates authority or an execution receipt**. It ends at `handoff-ready`. The post-receipt problem can only advance because `transition-receipted` is supplied as an external initial fact from the prior BRCE/runtime episode.

## Symbolic planner slots

`p01..p50` are symbolic league slots so the meta-planner can reason about a population. They are **not claims** that all concrete solvers support all roles. `tools/bind_registry.py` discovers the live AutoFDE solver/domain registry. A production league executor must replace fixture compatibility with a mechanically admitted matrix derived from concrete domains and `ScikitDecideBackend.match_solvers()`.

## What is plannable now

This pack treats more than action sequence as a planning problem: problem formulation, representation/formalism, planner selection, planner parameters, role assignment, information acquisition, hypothesis discrimination, counter-planning, world/curriculum selection, verifier construction, recovery construction, ggen projection choice, closure order, parallel cuts, next-edge selection, planner switching after real observation, and the decision to compile repeated cognition into deterministic semantics.


## Fortune 5 enterprise architecture extension

See `fortune5/README.md`. The extension adds enterprise principles, viewpoints, governance gates, NFR tiers, control domains, operating model, portfolio model, planner-role matrix, ten enterprise stress scenarios, a dedicated enterprise-architecture PDDL domain, and eight executable enterprise problem subjects.
