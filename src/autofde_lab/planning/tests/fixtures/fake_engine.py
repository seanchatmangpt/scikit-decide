#!/usr/bin/env python3
"""A fake external solver/validator binary, used only to exercise
``autofde_lab.planning``'s outcome taxonomy deterministically, without depending on a
real installed planner (fast-downward, VAL, ...) being present in CI.

Usage: fake_engine.py --mode {success,no_candidate,tool_failed,bounded} [--plan-file PATH]
"""

from __future__ import annotations

import argparse
import sys
import time


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=["success", "no_candidate", "tool_failed", "bounded"],
        required=True,
    )
    parser.add_argument("--plan-file", default=None)
    # Swallow positional domain/problem args, they're unused by the fake.
    parser.add_argument("rest", nargs="*")
    args = parser.parse_args()

    if args.mode == "success":
        if args.plan_file:
            with open(args.plan_file, "w") as fh:
                fh.write("(pick-up a)\n(put-down a)\n")
        print("plan found", file=sys.stdout)
        return 0

    if args.mode == "no_candidate":
        # Exit success but write nothing — the "solver ran fine, no plan exists" case.
        print("no plan found", file=sys.stdout)
        return 0

    if args.mode == "tool_failed":
        print("boom", file=sys.stderr)
        return 1

    if args.mode == "bounded":
        time.sleep(5)
        return 0

    return 2  # unreachable


if __name__ == "__main__":
    raise SystemExit(main())
