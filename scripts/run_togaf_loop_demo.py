#!/usr/bin/env python3
# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Run the real, full 10-phase TOGAF ADM loop and print the resulting real
OCEL 2.0 log, the real per-phase computed results, and the real
independent object-centric conformance verdict -- the artifact requested
directly, not a description of it.
"""

from __future__ import annotations

import json

from autofde_lab.reasoning.togaf_loop_demo import run_full_togaf_loop_with_ocel


def main() -> int:
    log, phase_results, conformance = run_full_togaf_loop_with_ocel()

    print("=" * 80)
    print("PHASE-BY-PHASE REAL COMPUTED RESULTS")
    print("=" * 80)
    for label, result in phase_results.items():
        if label.startswith("_"):
            continue
        print(f"  {label}: {result}")

    print()
    print("=" * 80)
    print("REAL OCEL 2.0 LOG (to_ocel2_json)")
    print("=" * 80)
    print(json.dumps(log.to_ocel2_json(), indent=2, default=str))

    print()
    print("=" * 80)
    print("REAL INDEPENDENT OBJECT-CENTRIC CONFORMANCE VERDICT")
    print("=" * 80)
    print(f"  all_conform: {conformance.all_conform}")
    print(f"  overall_fitness: {conformance.overall_fitness}")
    for obj in conformance.per_object:
        print(f"  object={obj.object_id!r} type={obj.object_type!r} conforms={obj.conforms} fitness={obj.fitness}")
        print(f"    observed: {obj.observed_trace}")
        print(f"    intended: {obj.intended_trace}")

    return 0 if conformance.all_conform else 1


if __name__ == "__main__":
    raise SystemExit(main())
