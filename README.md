
                    _  __    _  __              __             _      __
       _____ _____ (_)/ /__ (_)/ /_        ____/ /___   _____ (_)____/ /___
      / ___// ___// // //_// // __/______ / __  // _ \ / ___// // __  // _ \
     (__  )/ /__ / // ,<  / // /_ /_____// /_/ //  __// /__ / // /_/ //  __/
    /____/ \___//_//_/|_|/_/ \__/        \__,_/ \___/ \___//_/ \__,_/ \___/

<br>
<p align="center">
  <a href="https://github.com/seanchatmangpt/autofde-lab/actions/workflows/ci.yml?query=branch%3Amaster">
    <img src="https://img.shields.io/github/actions/workflow/status/seanchatmangpt/autofde-lab/ci.yml?branch=master&logo=github&label=CI%20status" alt="actions status">
  </a>
  <a href="https://github.com/seanchatmangpt/autofde-lab/tags">
    <img src="https://img.shields.io/github/tag/seanchatmangpt/autofde-lab.svg?label=current%20version" alt="version">
  </a>
  <a href="https://github.com/seanchatmangpt/autofde-lab/stargazers">
    <img src="https://img.shields.io/github/stars/seanchatmangpt/autofde-lab.svg" alt="stars">
  </a>
  <a href="https://github.com/seanchatmangpt/autofde-lab/network">
    <img src="https://img.shields.io/github/forks/seanchatmangpt/autofde-lab.svg" alt="forks">
  </a>
</p>
<br>

# AutoFDE Lab

AutoFDE Lab is the foundation layer of the **Chatman Ecosystem**'s Forward Deployment OS: the
canonical decision, planning, hypothesis, and integration control plane between admitted
operational state and candidate plans. See `FORWARD_DEPLOYMENT.md` for the portfolio role and
ownership boundaries this repository operates inside.

**It computes candidate plans. It does not actuate.** A planner selects; a broker authorizes;
an executor performs; a verifier evaluates. Nothing here carries ambient authority to change
the world, and nothing here is given receipt, admission, or actuation semantics — that path
runs through OpenClaw and the portfolio's `BRCE.DO` boundary, never directly from this repo.

It is forked from [Airbus scikit-decide](https://github.com/airbus/scikit-decide), an AI
framework for Reinforcement Learning, Automated Planning and Scheduling, and inherits its full
domain/solver catalog, C++ solver core, and API surface unchanged (`autofde_lab.*`, with a
deprecated `skdecide` compatibility alias — see `docs/migration/from-scikit-decide.md`).

This repository establishes **AutoFDE Lab technical standing only** — what the code in this
tree demonstrably does, evidenced by a test run in the current session (see
`.claude/rules/standing-law.md`). It establishes none of: AutoFDE product standing (a separate,
future repository — see `docs/autofde/EXPLORE.md`), organizational standing (accountable
customer acceptance), or legal standing (this repository confers none; see `NOTICE` and
`LICENSE`).

The original framework was initiated at [Airbus](https://www.airbus.com) AI Research and
notably received contributions through the [ANITI](https://aniti.univ-toulouse.fr/en/) and
[TUPLES](https://tuples.ai/) projects, and also from [ANU](https://www.anu.edu.au/). Renaming
this fork does not transfer that copyright — see `NOTICE`.

## What's new in v26.9.1

Two additive capabilities merged this cycle, per `docs/jira/v26.9.1/PLAN.md` (that plan's own
"Last Updated" section carries the full merge closure record):

- **Fortune-5 SAFe DfCM digital twin simulation** — a simulatable full SAFe backlog hierarchy
  (portfolios, value streams, ARTs, teams, epics/features/stories) for validating DfCM
  decision-making at Fortune-5 SAFe-portfolio scale. `src/autofde_lab/simulation/fortune5_safe/`,
  `docs/fortune5-safe-simulation.md`.
  PR [#94](https://github.com/seanchatmangpt/autofde-lab/pull/94), merge `2bf2871f`.
- **APS AutoFDE protocol semantic profile** — an RDF/OWL ontology profile with SHACL shape
  constraints giving cross-agent planning artifacts a verifiable, SHACL-constrained semantic
  contract, plus a PR-qualifying CI gate. `ontology/aps-autofde-profile.ttl`,
  `ontology/shapes/aps-autofde-profile.shacl.ttl`,
  `.github/workflows/aps-protocol-profile.yml`. PR
  [#95](https://github.com/seanchatmangpt/autofde-lab/pull/95), merge `d2242c39`.

Both verified this session with real, currently-passing commands (Chicago-style — real
collaborators, no mocks): `.venv/bin/python -m pytest tests/simulation/
tests/test_aps_protocol_profile_chicago.py -v` → 11 passed; independent `pyshacl.validate()`
of the new ontology profile against its own shapes → `Conforms: True`.

## Documentation map

- `FORWARD_DEPLOYMENT.md` — this repository's role and ownership boundaries in the portfolio.
- `docs/STATUS.md` — the in-repo standing ledger (measured wins / recorded negatives / scoped
  work, per `.claude/rules/standing-law.md`).
- `docs/ecosystem-standing.md` — the cross-repository standing ledger.
- `docs/diataxis/README.md` — Diataxis-framework documentation (tutorial / how-to / reference /
  explanation) for individual capabilities, starting with the autonomic life-planning case
  study.
- `docs/jira/v26.9.1/PLAN.md` — the DMEDI plan and merge record for this cycle's two additive
  capabilities above.
- `docs/migration/from-scikit-decide.md` — what changed / didn't for anyone with existing code
  against `pip install scikit-decide`.
- `NOTICE` / `LICENSE` — provenance and legal terms; renaming this fork did not transfer
  upstream Airbus copyright.

Docs never establish standing on their own (`docs/CLAUDE.md`) — every "works" claim above
points at a real command and its real output, not prose alone.

## Main features

<!--features-list-start-->

- **Problem solving:** describe your decision-making problem once and auto-match compatible solvers.\
  _For instance planning/scheduling problems can be solved by RL solvers using GNNs._
- **Growing catalog:** enjoy a growing list of domains & solvers catalog, supported by the community.
- **Open & Extensible:** scikit-decide is open source and is able to wrap existing state-of-the-art domains/solvers.
- **Domains available:**
  - [Gym(nasium)](https://gymnasium.farama.org/) environments for reinforcement learning (RL)
  - [PDDL](https://planning.wiki/) (Planning Domain Definition Language) via [unified-planning](https://github.com/aiplan4eu/unified-planning) and [plado](https://github.com/massle/plado) libraries
    - encoding in gym(nasium) spaces compatible with RL
    - graph representations for RL (inspired by [Lifted Learning Graph](https://doi.org/10.1609/aaai.v38i18.29986)) :new:
  - [RDDL](https://users.cecs.anu.edu.au/~ssanner/IPPC_2011/RDDL.pdf) (Relational Dynamic Influence Diagram Language) using [pyrddl-gym](https://github.com/pyrddlgym-project) library.
  - Flight planning, based on [openap](https://openap.dev/) or in-house Poll-Schumann for performance model
  - Scheduling, based on rcpsp problem from [discrete-optimization](https://airbus.github.io/discrete-optimization) library
  - Toy domains like: maze, mastermind, rock-paper-scissors
- **Solvers available:**
  - RL solvers from ray.rllib and stable-baselines3
    - existing algos with action masking
    - adaptation of RL algos for graph observation, based on GNNs from [pytorch-geometric](https://pytorch-geometric.readthedocs.io/) :new:
    - autoregressive models with action masking component by component for parametric actions :new:
  - Planning solvers from [unified-planning](https://github.com/aiplan4eu/unified-planning) library
  - RDDL solvers jax and gurobi-based based on pyRDDLGym-jax and pyRDDLGym-gurobi from [pyrddl-gym project](https://github.com/pyrddlgym-project)
  - Search solvers coded in scikit-decide library:
    - A*, AO*, Improved-LAO*
    - Value Iteration (VI), Policy Iteration (PI)
    - Labeled RTDP, Learning Real-Time A*
    - LDFS (Label-correcting Depth-First Search), Iterative Deepening A*
    - SSiPP (Short-Sighted Planning), FRET (Find, Revise, Eliminate Traps)
    - iDual (LP-based SSP solver), Goal Probability and Cost Iteration (GPCI)
    - Best First Width Search, Iterated Width (IW), Rollout IW (RIW)
    - Monte Carlo Tree Search (MCTS), POMCP
    - DESPOT, SARSOP, Witness (POMDP solvers)
    - RTDP-Bel (belief-space RTDP), HSVI / GoalHSVI
    - SSPReplan, SSPDetHindsight, SSPPlanMerger (determinization approaches)
    - Multi-Agent RTDP, Multi-Agent Heuristic meta-solver (MAHD)
  - (Probabilistic) PDDL (PPDDL) solvers:
    - FF planner
    - FFReplan / PPDDLReplan (replanning with pluggable inner solvers)
    - FFDetHindsight / PPDDLDetHindsight (determinization in hindsight)
    - RFF / PPDDLPlanMerger (plan aggregation into a policy)
  - PDDL heuristics (with their probabilistic extensions):
    - Delete-Relaxation heuristics
    - FF Heuristic
  - PDDL+ parser and simulators with Probabilistic PDDL extensions
    - Lifted applicable action filtering using Clingo
    - Z3-based event synchronization in python using [z3-solver](https://pypi.org/project/z3-solver/)
  - Evolution strategy: Cartesian Genetic Programming (CGP)
  - Scheduling solvers from [discrete-optimization](https://airbus.github.io/discrete-optimization),
    - itself wrapping [ortools](https://developers.google.com/optimization), [gurobi](https://www.gurobi.com/),
    [toulbar](https://toulbar2.github.io/toulbar2/#), [minizinc](https://www.minizinc.org/),
    [deap](https://deap.readthedocs.io/) (genetic algorithm), [didppy](https://didppy.readthedocs.io/) (dynamic programming),
    - and coding local search (hill climber, simulated annealing), Large Neighborhood Search (LNS), and
    genetic programming based hyper-heuristic (GPHH)
- **Tuning solvers hyperparameters**
  - hyperparameters definition
  - automated study with optuna

<!--features-list-end-->

## Installation

Quick version:
```shell
pip install autofde-lab[all]
```
For more details, see the [online documentation](https://seanchatmangpt.github.io/autofde-lab/install).

## Documentation

The latest documentation is available [online](https://seanchatmangpt.github.io/autofde-lab).

## Examples

Some educational notebooks are available in `notebooks/` folder.
Links to launch them online with [binder](https://mybinder.org/) are provided in the
[Notebooks section](https://seanchatmangpt.github.io/autofde-lab/notebooks) of the online documentation.

More examples can be found as Python scripts in the `examples/` folder, showing how to import or define a domain,
and how to run or solve it. Most of the examples rely on scikit-decide Hub, an extensible catalog of domains/solvers.

## Contributing

See more about how to contribute in the [online documentation](https://seanchatmangpt.github.io/autofde-lab/contribute).
