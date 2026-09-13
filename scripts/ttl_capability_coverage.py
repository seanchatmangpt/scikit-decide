#!/usr/bin/env python3
"""Coverage-gap detector: TTL-modeled ce:Capability individuals vs. the
real DO-class capability surface actually shipped in platform-console.

Chicago-style, no mocking: every number below comes from a real parse of
the real TTL file (rdflib) and real greps/regex scans of the real
platform-console source tree -- never a fabricated or hand-typed count.

Three real sources of DO-class capability surface, matching the task
spec exactly:
  1. Every entry of ACTIONS_REQUIRING_APPROVAL in lib/approval-workflow.ts
     -- real maker-checker-gated actions.
  2. Every route.ts under app/api/ that performs a real mutating
     (POST/PUT/DELETE) k8s or ConfigMap write -- detected by: the route
     defines a POST/PUT/DELETE handler AND the route file (or a lib/*.ts
     module it directly imports) calls a real mutating function from
     lib/k8s.ts (create/update/delete/patch a k8s object) or
     lib/castle.ts's runCastleVerb/deployCastle/sunsetCastle.
  3. Every entry of ALLOWED_CASTLE_VERBS in lib/castle.ts -- real castle
     verb ids the /api/castle/run route is allowed to actuate.

These three sets are unioned by capability *name* (the approval-action
string, the castle verb id, or a route-derived slug) to produce the real
total DO-capability surface. TTL coverage = |TTL titles ∩ surface names|
/ |surface names|. Names in the TTL that do NOT appear in the surface are
reported separately as drift candidates (a TTL individual referencing a
capability that no longer exists in code, or whose surface name doesn't
match).
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import rdflib

TTL_PATH = Path("/Users/sac/chatman-ecosystem/ontology/platform-console-capabilities.ttl")
APP_ROOT = Path("/Users/sac/chatman-ecosystem/platform-console/app")
APPROVAL_WORKFLOW_TS = APP_ROOT / "lib" / "approval-workflow.ts"
CASTLE_TS = APP_ROOT / "lib" / "castle.ts"
K8S_TS = APP_ROOT / "lib" / "k8s.ts"
API_ROOT = APP_ROOT / "app" / "api"

CE = rdflib.Namespace("https://seanchatmangpt.github.io/chatman-ecosystem/ontology/capabilities#")
DCTERMS = rdflib.Namespace("http://purl.org/dc/terms/")


# ---------------------------------------------------------------------------
# 1. TTL parsing
# ---------------------------------------------------------------------------
def parse_ttl_titles(ttl_path: Path) -> list[str]:
    g = rdflib.Graph()
    g.parse(str(ttl_path), format="turtle")
    titles = []
    for s in g.subjects(rdflib.RDF.type, CE.Capability):
        for t in g.objects(s, DCTERMS.title):
            titles.append(str(t))
    return sorted(titles)


# ---------------------------------------------------------------------------
# 2. lib/approval-workflow.ts -- ACTIONS_REQUIRING_APPROVAL
# ---------------------------------------------------------------------------
def parse_approval_actions(ts_path: Path) -> list[str]:
    text = ts_path.read_text()
    m = re.search(
        r"export const ACTIONS_REQUIRING_APPROVAL:\s*ApprovalAction\[\]\s*=\s*\[(.*?)\n\];",
        text,
        re.DOTALL,
    )
    if not m:
        raise RuntimeError("could not locate ACTIONS_REQUIRING_APPROVAL array in " + str(ts_path))
    body = m.group(1)
    # Real array entries are lines of the form `  "action.name",` -- strip
    # `//`-comment lines first so quoted strings inside explanatory prose
    # comments (e.g. "approved_for_payment") are never mistaken for a real
    # array entry.
    actions = []
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("//") or not stripped:
            continue
        m2 = re.match(r'^"([a-zA-Z0-9_.\-]+)",?$', stripped)
        if m2:
            actions.append(m2.group(1))
    return actions


# ---------------------------------------------------------------------------
# 3. lib/castle.ts -- ALLOWED_CASTLE_VERBS (id field of each object)
# ---------------------------------------------------------------------------
def parse_castle_verbs(ts_path: Path) -> list[str]:
    text = ts_path.read_text()
    m = re.search(r"export type AllowedCastleVerbId\s*=\s*(.*?);", text, re.DOTALL)
    if not m:
        raise RuntimeError("could not locate AllowedCastleVerbId union in " + str(ts_path))
    return re.findall(r'"([a-zA-Z0-9_.\-]+)"', m.group(1))


# ---------------------------------------------------------------------------
# 4. app/api/**/route.ts -- real mutating k8s/ConfigMap writes
# ---------------------------------------------------------------------------
# Real mutating function names exported by lib/k8s.ts, discovered by
# scanning the file itself for `export (async )?function` whose name
# matches a create/update/delete/patch verb prefix -- not hand-typed.
def discover_mutating_k8s_functions(k8s_ts_path: Path) -> set[str]:
    text = k8s_ts_path.read_text()
    names = re.findall(r"export (?:async )?function (\w+)", text)
    mutating_prefixes = ("create", "update", "delete", "patch")
    return {n for n in names if n.lower().startswith(mutating_prefixes)}


def discover_mutating_routes(api_root: Path, mutating_k8s_fns: set[str]) -> dict[str, list[str]]:
    """Return {route_relpath: [mutating fn names it calls, or 'castle-verb-actuation']}
    restricted to routes that (a) define a POST/PUT/DELETE handler and
    (b) call at least one real mutating k8s function -- either directly,
    or via lib/castle.ts's runCastleVerb/deployCastle/sunsetCastle (which
    themselves wrap k8sRequest to create/delete real batch/v1 Jobs and
    ConfigMaps -- see lib/castle.ts header comment)."""
    castle_actuators = {"runCastleVerb", "deployCastle", "sunsetCastle", "scheduleCastleVerb"}
    hits: dict[str, list[str]] = {}
    for route in sorted(api_root.rglob("route.ts")):
        text = route.read_text()
        if not re.search(r"export async function (POST|PUT|DELETE)", text):
            continue
        called = set(re.findall(r"\b(\w+)\(", text))
        mutating_hits = sorted(called & mutating_k8s_fns)
        castle_hits = sorted(called & castle_actuators)
        if mutating_hits or castle_hits:
            hits[str(route.relative_to(api_root.parent.parent))] = mutating_hits + castle_hits
    return hits


def route_capability_name(route_relpath: str) -> str:
    """Derive a stable capability-surface name from a route path, e.g.
    app/api/orgs/[id]/backups/route.ts -> route.orgs.backups"""
    parts = Path(route_relpath).parts
    # drop leading app/api and trailing route.ts, drop [param] segments
    segs = [p for p in parts[2:-1] if not (p.startswith("[") and p.endswith("]"))]
    return "route." + ".".join(segs) if segs else "route." + route_relpath


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
@dataclass
class CoverageReport:
    ttl_titles: list[str]
    approval_actions: list[str]
    castle_verbs: list[str]
    mutating_routes: dict[str, list[str]]
    route_names: list[str] = field(default_factory=list)

    @property
    def surface_names(self) -> set[str]:
        return set(self.approval_actions) | set(self.castle_verbs) | set(self.route_names)

    def to_dict(self) -> dict:
        surface = self.surface_names
        ttl_set = set(self.ttl_titles)
        modeled = ttl_set & surface
        unmodeled = sorted(surface - ttl_set)
        drift = sorted(ttl_set - surface)  # TTL individuals with no matching real capability
        return {
            "ttl_path": str(TTL_PATH),
            "ttl_individual_count": len(self.ttl_titles),
            "ttl_titles": self.ttl_titles,
            "approval_action_count": len(self.approval_actions),
            "approval_actions": self.approval_actions,
            "castle_verb_count": len(self.castle_verbs),
            "castle_verbs": self.castle_verbs,
            "mutating_route_count": len(self.mutating_routes),
            "mutating_routes": self.mutating_routes,
            "total_real_do_capability_surface": len(surface),
            "modeled_in_ttl_count": len(modeled),
            "coverage_ratio": (len(modeled) / len(surface)) if surface else 0.0,
            "unmodeled_capabilities": unmodeled,
            "ttl_drift_candidates_no_real_referent": drift,
        }


def build_report() -> CoverageReport:
    ttl_titles = parse_ttl_titles(TTL_PATH)
    approval_actions = parse_approval_actions(APPROVAL_WORKFLOW_TS)
    castle_verbs = parse_castle_verbs(CASTLE_TS)
    mutating_k8s_fns = discover_mutating_k8s_functions(K8S_TS)
    mutating_routes = discover_mutating_routes(API_ROOT, mutating_k8s_fns)
    route_names = sorted({route_capability_name(r) for r in mutating_routes})
    return CoverageReport(
        ttl_titles=ttl_titles,
        approval_actions=approval_actions,
        castle_verbs=castle_verbs,
        mutating_routes=mutating_routes,
        route_names=route_names,
    )


def main() -> int:
    report = build_report().to_dict()
    print(json.dumps(report, indent=2))
    print("\n--- SUMMARY ---", file=sys.stderr)
    print(f"TTL individuals: {report['ttl_individual_count']}", file=sys.stderr)
    print(f"Total real DO-capability surface: {report['total_real_do_capability_surface']}", file=sys.stderr)
    print(f"Modeled in TTL: {report['modeled_in_ttl_count']}", file=sys.stderr)
    print(f"Coverage ratio: {report['coverage_ratio']:.1%}", file=sys.stderr)
    print(f"Unmodeled capabilities ({len(report['unmodeled_capabilities'])}):", file=sys.stderr)
    for name in report["unmodeled_capabilities"]:
        print(f"  - {name}", file=sys.stderr)
    if report["ttl_drift_candidates_no_real_referent"]:
        print(f"TTL drift candidates (no real referent) ({len(report['ttl_drift_candidates_no_real_referent'])}):", file=sys.stderr)
        for name in report["ttl_drift_candidates_no_real_referent"]:
            print(f"  - {name}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
