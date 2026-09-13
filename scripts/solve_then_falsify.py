#!/usr/bin/env python3
# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Thin CLI wrapper over `autofde_lab.fabric.solve_and_falsify.solve_and_falsify`.

The real solve+falsify logic now lives in `src/autofde_lab/fabric/
solve_and_falsify.py`, shared with `fabric/phase_h_trigger.py`'s real,
automatic, drift-triggered path -- this script is kept only as a manual,
standalone invocation for a human/CI to run one real cycle by hand
(`./.venv/bin/python scripts/solve_then_falsify.py <domain> [solver]
[max_steps]`), not because the logic itself is unique to it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from autofde_lab.fabric.solve_and_falsify import solve_and_falsify


def main() -> None:
    domain = sys.argv[1] if len(sys.argv) > 1 else "Maze"
    solver = sys.argv[2] if len(sys.argv) > 2 else "Astar"
    max_steps = int(sys.argv[3]) if len(sys.argv) > 3 else 100
    result, falsification = solve_and_falsify(domain, solver=solver, max_steps=max_steps)
    print(
        json.dumps(
            {
                "fabric_solve": {
                    "domain": domain,
                    "standing": result.standing.value,
                    "terminal": result.terminal,
                    "steps": len(result.steps),
                    "receipt_sha256": result.receipt_sha256,
                },
                "falsification": {
                    "candidate_id": falsification.candidate_id,
                    "standing": falsification.standing.value,
                    "rationale": falsification.rationale,
                    "receipt_refs": falsification.receipt_refs,
                    "violated_constraints": falsification.violated_constraints,
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
