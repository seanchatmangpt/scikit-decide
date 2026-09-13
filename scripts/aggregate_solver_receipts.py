#!/usr/bin/env python3
"""Aggregate solver/verify signal across all real OCEL logs in docs/evidence.

Turns 22+ unread per-episode OCEL JSON files into one ranked table of
(strategy | verify_mode) rows: attempts, successes, refusals, mean elapsed
seconds on success. This is the "learned prior" precursor described in the
2030 discussion -- a real, queryable signal instead of static receipts.

Two genuinely different kinds of row are produced, and are NOT blended:

  - MULTI-CANDIDATE domains (planner-of-planners: currently rcpsp,
    flight_planning) emit solver_refused / solver_selected events with a
    `strategy` attribute. Each candidate strategy tried becomes its own row,
    sourced from real solver_refused/solver_selected event counts and
    elapsed_seconds.

  - SINGLE-MECHANISM domains (every other domain in this evidence pack) have
    no solver_candidates history at all -- there is exactly one mechanism,
    selected unconditionally. For these, the equivalent signal is the
    `verify_mode` attribute on the `verify` event, and success/failure is
    read from `standing == ALIVE` on that same event.

Run: python3 scripts/aggregate_solver_receipts.py
"""

from __future__ import annotations

import glob
import json
import os
import statistics
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVIDENCE_GLOB = os.path.join(ROOT, "docs", "evidence", "**", "*.ocel.json")


def attrs_to_dict(event: dict) -> dict:
    out = {}
    for a in event.get("attributes", []):
        out[a["name"]] = a["value"]
    return out


def domain_for(path: str) -> str:
    rel = os.path.relpath(path, os.path.join(ROOT, "docs", "evidence"))
    parts = rel.split(os.sep)
    return parts[0]


def load_events(path: str) -> list[dict]:
    with open(path, "r") as f:
        data = json.load(f)
    return data.get("events", [])


class Stats:
    def __init__(self):
        self.attempts = 0
        self.successes = 0
        self.refusals = 0
        self.success_elapsed: list[float] = []

    def mean_elapsed(self):
        if not self.success_elapsed:
            return None
        return statistics.mean(self.success_elapsed)


def main() -> None:
    files = sorted(glob.glob(EVIDENCE_GLOB, recursive=True))
    if not files:
        print(f"No OCEL logs found at {EVIDENCE_GLOB}")
        return

    # key: (kind, row_label) -> Stats ; kind in {"multi-candidate", "single-mechanism"}
    rows: dict[tuple[str, str], Stats] = defaultdict(Stats)
    domains_multi = set()
    domains_single = set()
    parse_errors = []
    domain_files = defaultdict(list)

    for path in files:
        dom = domain_for(path)
        domain_files[dom].append(path)
        try:
            events = load_events(path)
        except Exception as exc:  # real parse failures are reported, not swallowed
            parse_errors.append((path, str(exc)))
            continue

        event_names = {e.get("type") for e in events}
        has_solver_events = bool(event_names & {"solver_refused", "solver_selected"})

        if has_solver_events:
            domains_multi.add(dom)
            for e in events:
                etype = e.get("type")
                if etype not in ("solver_refused", "solver_selected"):
                    continue
                a = attrs_to_dict(e)
                strategy = a.get("strategy", "<unknown-strategy>")
                key = ("multi-candidate", strategy)
                st = rows[key]
                st.attempts += 1
                if etype == "solver_selected":
                    st.successes += 1
                    elapsed = a.get("elapsed_seconds")
                    if isinstance(elapsed, (int, float)):
                        st.success_elapsed.append(float(elapsed))
                else:
                    st.refusals += 1
        else:
            domains_single.add(dom)
            # equivalent single-mechanism signal: verify event's verify_mode + standing
            verify_events = [e for e in events if e.get("type") == "verify"]
            for e in verify_events:
                a = attrs_to_dict(e)
                if "verify_mode" in a:
                    mode = a["verify_mode"]
                else:
                    # actuation-replay logs (crown1/reconstruct-run1 trials) emit
                    # verify events with idempotency/state-digest attributes but no
                    # verify_mode at all -- a genuinely different schema, not a
                    # missing value, so it gets its own explicit label rather than
                    # being folded into a misleading "unknown" bucket.
                    mode = "<no verify_mode: actuation-replay schema>"
                key = ("single-mechanism", mode)
                st = rows[key]
                st.attempts += 1
                if a.get("standing") == "ALIVE":
                    st.successes += 1
                    # no elapsed_seconds is emitted on verify events; leave unmeasured
                else:
                    st.refusals += 1

    # ---- print ranked table ----
    header = (
        f"{'kind':<17}{'strategy / verify_mode':<28}{'attempts':>9}"
        f"{'successes':>11}{'refusals':>10}{'mean_elapsed_s(success)':>26}"
    )
    print(header)
    print("-" * len(header))

    def sort_key(item):
        (kind, label), st = item
        # rank by attempts desc within each kind; multi-candidate first
        return (0 if kind == "multi-candidate" else 1, -st.attempts, label)

    for (kind, label), st in sorted(rows.items(), key=sort_key):
        mean_e = st.mean_elapsed()
        mean_str = f"{mean_e:.3f}" if mean_e is not None else "n/a"
        print(
            f"{kind:<17}{label:<28}{st.attempts:>9}{st.successes:>11}"
            f"{st.refusals:>10}{mean_str:>26}"
        )

    print()
    print(f"Evidence root : {os.path.join('docs', 'evidence')}")
    print(f"OCEL files globbed : {len(files)}")
    print(f"Domains with real multi-candidate solver history "
          f"(solver_refused/solver_selected present): {len(domains_multi)} "
          f"-> {sorted(domains_multi)}")
    print(f"Domains on the single-mechanism path (verify_mode/standing only): "
          f"{len(domains_single)} -> {sorted(domains_single)}")
    if parse_errors:
        print(f"Parse errors ({len(parse_errors)}):")
        for p, err in parse_errors:
            print(f"  {p}: {err}")


if __name__ == "__main__":
    main()
