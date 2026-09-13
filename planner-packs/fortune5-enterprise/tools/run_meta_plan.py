#!/usr/bin/env python3
"""Run a supplied meta-planning problem through AutoFDE-Lab's PDDL engine."""

import argparse
from pathlib import Path

from autofde_lab.fabric.pddl_engine import solve_to_plan_file


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("problem")
    ap.add_argument(
        "--domain",
        default=str(
            Path(__file__).parents[1] / "pddl/autofde-meta-planning-domain.pddl"
        ),
    )
    ap.add_argument("--plan", default="candidate.plan")
    ap.add_argument("--powl", default="candidate.powl.ttl")
    a = ap.parse_args()
    raise SystemExit(solve_to_plan_file(a.domain, a.problem, a.plan, powl_path=a.powl))


if __name__ == "__main__":
    main()
