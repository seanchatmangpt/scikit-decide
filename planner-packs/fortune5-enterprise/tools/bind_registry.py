#!/usr/bin/env python3
"""Discover live AutoFDE-Lab domains/solvers without inventing compatibility."""

import argparse
import json
from pathlib import Path

from autofde_lab.fabric.backend import ScikitDecideBackend


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="planner-bindings.generated.json")
    a = ap.parse_args()
    b = ScikitDecideBackend()
    payload = {
        "schema": "urn:autofde:live-registry-bindings:v1",
        "domains": b.list_domains(),
        "solvers": b.list_solvers(),
        "compatibility": {},
        "standing": "CANDIDATE",
        "claim_ceiling": "REGISTRY_DISCOVERY_ONLY_NO_COMPATIBILITY_CLAIM",
    }
    Path(a.out).write_text(json.dumps(payload, indent=2) + "\n")
    print(
        f"{len(payload['domains'])} domains; {len(payload['solvers'])} solvers -> {a.out}"
    )


if __name__ == "__main__":
    main()
