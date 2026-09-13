#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from autofde_lab.forwardbench import ForwardBenchRegistry

p = argparse.ArgumentParser()
p.add_argument("--registry", default="docs/papers/generated/forwardbench/registry.json")
sub = p.add_subparsers(dest="cmd", required=True)
sub.add_parser("list")
plan = sub.add_parser("plan")
plan.add_argument("subject")
a = p.parse_args()
r = ForwardBenchRegistry(a.registry)
if a.cmd == "list":
    print(json.dumps([s.__dict__ | {"observed_standing": s.observed_standing} for s in r.list()], indent=2, sort_keys=True))
else:
    print(json.dumps(r.plan(a.subject).__dict__, indent=2, sort_keys=True))
