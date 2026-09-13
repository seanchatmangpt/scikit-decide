# Fortune-5 SAFe simulation

`autofde_lab.simulation.fortune5_safe` reconstitutes the archived Agile Protocol Specification
Fortune-5 SAFe reference as an executable, deterministic AutoFDE-Lab digital twin. It is a
**model-only** surface: transitions change simulated enterprise state and receipts bind simulated
consequences; no result admits or actuates a real-world action.

## Preserved source identity

- APS source: `seanchatmangpt/agile-protocol-specification@b5916330905195b124409ca0e857f43b897ffc80`
- AutoFDE-Lab adaptation base: `seanchatmangpt/autofde-lab@61840ec86b05f5542267421d015f3f2d7c1c5ce9`
- APS reference scale: 4 portfolios, 20 value streams, 60 ARTs, 720 teams, 7,200 personnel,
  $1.2B annual budget.

The adaptation expands the topology to 10 Solution Trains, scoped SAFe role assignments,
dependency edges, explicit strategy/backlog hierarchy, and cadence-event volume while preserving the APS scale invariants above.

## DfCM calculus

The simulator does not optimize to one policy. Its lawful policy space is the Cartesian product
of six independent dimensions:

| Dimension | Alternatives |
|---|---:|
| priority | 5 |
| funding | 4 |
| capacity allocation | 4 |
| cadence | 3 |
| architecture | 3 |
| risk posture | 3 |

That yields **2,160 policy vectors**. They are evaluated across **10 disruption scenarios** for a
**21,600-episode** matrix. The result retains the feasible set, a non-dominated Pareto frontier,
and a normalized Hamming diversity score. There is intentionally no `winner` or
`selected_policy` field.

## Enterprise model

The topology models portfolio/LPM, development value streams, Solution Trains, ARTs, teams,
personnel seats, role assignments, cross-level dependencies, and an explicit work graph of
8 strategic themes → 40 epics → 160 capabilities → 960 features → 8,640 stories (9,808 work
items total, including enabler flags). Cadence buckets include
portfolio sync, Pre/Post-PI, PI Planning, ART Sync, System/Solution Demo, Inspect & Adapt,
iteration events, and team sync.

Each episode advances six planning intervals and measures throughput, lead time, WIP, business
value, predictability, reliability, compliance risk, architecture runway, coordination overhead,
budget variance, employee load, dependency age, and recovery time.

The scenario matrix covers baseline demand plus demand burst, funding shock, supplier delay,
compliance hold, reliability incident, attrition, dependency cascade, reorganization, and cyber
incident.

## Receipts and replay

Each episode emits a deterministic `SimulationReceipt` binding source SHA, target adaptation
base SHA, topology digest, policy digest, scenario, seed, input digest, output digest, trace
digest, and replay digest. Its authority is explicitly `NON_ACTUATING_MODEL_ONLY` and its
standing is `MODEL_EXECUTED`.

The same admitted subject + policy + scenario + seed must replay byte-for-byte to the same
receipt. Changing the seed or scenario is a falsifier and must change the consequence digest.

## Run

```bash
python -m autofde_lab.simulation.fortune5_safe
python -m autofde_lab.simulation.fortune5_safe --matrix
pytest tests/simulation/test_fortune5_safe.py -v
```

The full matrix output reports topology scale, policy/scenario/episode counts, feasible and
Pareto set sizes, diversity, and a matrix digest. It reports `selection: null` by construction.
