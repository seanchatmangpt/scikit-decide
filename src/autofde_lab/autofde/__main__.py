# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Render the four AutoFDE artifacts from the one admitted graph.

``python -m autofde_lab.autofde [outdir]`` — writes files only. It never calls
Terraform and never touches GitHub.
"""

from __future__ import annotations

import sys
from pathlib import Path

from autofde_lab.autofde.github_projection import (
    render_powl_json,
    render_project_plan_json,
    render_tfvars,
)
from autofde_lab.autofde.phase_graph import AUTOFDE_PHASE_GRAPH

DEFAULT_OUTDIR = (
    Path(__file__).resolve().parents[3] / "infra" / "github" / "project_management"
)


def main(argv: list[str]) -> int:
    outdir = Path(argv[1]) if len(argv) > 1 else DEFAULT_OUTDIR
    outdir.mkdir(parents=True, exist_ok=True)
    g = AUTOFDE_PHASE_GRAPH
    written = {
        outdir / "project_management.auto.tfvars": render_tfvars(g),
        outdir / "phase-graph.powl.json": render_powl_json(g),
        outdir / "github-project-plan.json": render_project_plan_json(g),
    }
    for path, text in written.items():
        path.write_text(text, encoding="utf-8")
        print(f"wrote {path} ({len(text)} bytes)")
    print("ontology/autofde-phase-graph.ttl is hand-authored, not generated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
