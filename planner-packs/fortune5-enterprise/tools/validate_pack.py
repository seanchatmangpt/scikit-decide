#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]


def balanced_pddl(text: str) -> bool:
    stripped = "\n".join(line.split(";", 1)[0] for line in text.splitlines())
    return stripped.count("(") == stripped.count(")") and stripped.lstrip().startswith(
        "(define"
    )


def main() -> int:
    failures = []
    for path in sorted(ROOT.rglob("*.json")):
        try:
            json.loads(path.read_text())
        except Exception as exc:
            failures.append(f"{path}: JSON: {exc}")
    for path in sorted(ROOT.rglob("*.pddl")):
        text = path.read_text()
        if not balanced_pddl(text):
            failures.append(f"{path}: unbalanced/not define")
        active = "\n".join(line.split(";", 1)[0] for line in text.splitlines())
        for banned in (":derived-predicates", ":constraints", ":preferences"):
            if banned in active:
                failures.append(f"{path}: current AutoFDE PDDL engine refuses {banned}")
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print("planner pack structural validation: ALIVE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
