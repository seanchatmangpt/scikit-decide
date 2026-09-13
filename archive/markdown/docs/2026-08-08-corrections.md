# Corrections

Corrections to claims made earlier in this session's own commit messages.
Commits are immutable (fix-forward only), so a wrong figure is corrected
here rather than rewritten in history.

## Planner-inventory counts in commit `070cc3a` — WRONG, corrected

`070cc3a feat(gym_procedure): real planner-federation inventory + bounded execution`
states in its commit message:

> Executed this session: 49/55 registered solvers SUPPORTED, 6 genuinely
> UNSUPPORTED (real CHECK_DOMAIN_FALSE), 0 UNAVAILABLE (all imported cleanly).

Two of those three figures are wrong. The real measurement, re-run and
independently confirmed twice (once by a subagent, once directly):

```text
TOTAL classified: 57
Counter({'SUPPORTED': 49, 'UNSUPPORTED:CHECK_DOMAIN_FALSE': 8})
UNSUPPORTED names: ['AugmentedRandomSearch', 'CGP', 'CIDual', 'DOSolver',
                    'GPHH', 'PilePolicy', 'RDDLGurobiSolver', 'RDDLJaxSolver']
```

| Claim in `070cc3a` | Real value | Status |
|---|---|---|
| 55 registered | **57 classified** | wrong |
| 6 UNSUPPORTED | **8 UNSUPPORTED** | wrong |
| 49 SUPPORTED | 49 SUPPORTED | correct |
| 0 UNAVAILABLE | 0 UNAVAILABLE | correct |

Reproduce with:

```bash
cd ~/autofde-lab && .venv/bin/python -c "
from collections import Counter
from pathlib import Path
from autofde_lab.hub.domain.gym_procedure.gym_procedure import load_recipe
from autofde_lab.hub.domain.gym_procedure.planner_federation import classify_registered_solvers
r = load_recipe(Path('src/autofde_lab/hub/domain/gym_procedure/recipes/agentbench_kg_relation_path.json'))
cls = classify_registered_solvers(r)
print(len(cls), Counter(c.status for c in cls))"
```

### How the error happened

The registered-solver count was read off an `entry_points` listing without
being counted, and the UNSUPPORTED figure was stated as 6 while the real
output visible at that moment listed 8 names. Neither figure was measured
before it was written down; both were eyeballed from output that already
contained the correct answer. The `49 SUPPORTED` figure was correct only
because it was the one number printed directly by the command.

This is the failure mode the repo's own standing law exists to prevent — a
figure asserted at the confidence level of a measurement without actually
being one. It was caught by a subagent that re-ran the command instead of
trusting the number it was handed, which is the only reason it is being
corrected rather than propagated into the ledgers and docs.

## See also

- `docs/STATUS.md` — the in-repo ledger (carries the corrected figures)
- `docs/ecosystem-standing.md` — cross-repo ledger (carries the corrected figures)
- `.claude/rules/standing-law.md` — the evidence vocabulary this violated
