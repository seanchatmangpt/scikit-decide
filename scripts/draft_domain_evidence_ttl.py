#!/usr/bin/env python3
"""Draft an afl:DomainEvidenceSpec + afl:Capability Turtle snippet for one
real DeterministicPlanningDomain subclass that is NOT yet registered in
ontology/domain-evidence.ttl.

This is an authoring-cost-reduction tool, not a fact-admission tool: it
inspects the real target class's source (via `inspect`) to draft plausible
field guesses, but it NEVER writes to ontology/domain-evidence.ttl itself,
and it marks every field it could not confidently infer with a
"# REVIEW REQUIRED" comment so a human confirms before anything is
committed to the graph.

Usage:
    python scripts/draft_domain_evidence_ttl.py \
        --module autofde_lab.hub.domain.azuregoat_privesc.azuregoat_privesc \
        --class AzureGoatPrivilegeEscalation
"""

from __future__ import annotations

import argparse
import importlib
import inspect
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ONTOLOGY_PATH = REPO_ROOT / "ontology" / "domain-evidence.ttl"

REVIEW = "REVIEW REQUIRED"


def slugify(name: str) -> str:
    """Turn a domain module's dotted tail into a safe TTL local-name slug."""
    return re.sub(r"[^a-zA-Z0-9_]", "_", name)


def load_class(module_path: str, class_name: str):
    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    return cls


def get_method_source(cls, name: str) -> str | None:
    """Return the real source text of a method (including inherited), or None."""
    method = getattr(cls, name, None)
    if method is None:
        return None
    try:
        return inspect.getsource(method)
    except (OSError, TypeError):
        return None


def draft_goal_check_expr(cls) -> tuple[str, bool]:
    """Inspect _get_goals_ (and _is_terminal as a fallback) to guess a
    goalCheckExpr. Returns (expr, confident)."""
    src = get_method_source(cls, "_get_goals_")
    fallback_src = get_method_source(cls, "_is_terminal")
    text = src or fallback_src or ""

    # Look for a module-level GOAL_* constant referenced inside an
    # ImplicitSpace lambda, e.g. `GOAL_FACT in state.facts`.
    m = re.search(r"lambda\s+\w+\s*:\s*(.+?)\)\s*$", text.strip(), re.MULTILINE)
    if m:
        expr = m.group(1).strip()
        # Strip a single trailing ')' left over from `ImplicitSpace(lambda ...)`.
        if expr.endswith(")") and expr.count("(") < expr.count(")"):
            expr = expr[:-1].strip()
        return expr, True

    if text:
        return text.strip().splitlines()[-1].strip(), False

    return "<unknown>", False


def draft_capabilities(cls) -> tuple[list[dict], bool]:
    """Inspect _get_applicable_actions_from (and any module-level action/step
    table it draws from) to guess capability name/precondition pairs.
    Returns (capabilities, confident)."""
    src = get_method_source(cls, "_get_applicable_actions_from") or ""

    # Pattern used by table-driven fact/step domains (e.g. AttackStep-style):
    # `s.id for s in self.steps if s.preconditions <= memory.facts and ...`
    caps: list[dict] = []
    module = sys.modules[cls.__module__]

    # Try to find a module-level tuple/list of dataclass-like step/action
    # records with `.id`/`.establishes`/`.preconditions`-style fields, by
    # walking module globals for a tuple of objects exposing those attrs.
    for gname, gval in vars(module).items():
        if isinstance(gval, (tuple, list)) and gval:
            first = gval[0]
            if hasattr(first, "__dataclass_fields__"):
                fields = set(first.__dataclass_fields__.keys())
                if {"id", "preconditions", "establishes"} <= fields:
                    for item in gval:
                        caps.append(
                            {
                                "name": getattr(item, "id"),
                                "precondition": " and ".join(
                                    sorted(
                                        f"'{p}' in memory.facts"
                                        for p in getattr(item, "preconditions")
                                    )
                                )
                                or "True",
                                "consequence": "DO",
                            }
                        )
                    return caps, True

    # Fallback: no recognized table; surface the raw source for manual review.
    if src:
        return [
            {
                "name": f"<{REVIEW}: derive from _get_applicable_actions_from source below>",
                "precondition": f"<{REVIEW}>\n#   {src.strip()[:400]}",
                "consequence": "DO",
            }
        ], False

    return [
        {
            "name": f"<{REVIEW}: no _get_applicable_actions_from found>",
            "precondition": f"<{REVIEW}>",
            "consequence": "DO",
        }
    ], False


def draft_ttl(module_path: str, class_name: str) -> str:
    cls = load_class(module_path, class_name)

    module_tail = module_path.rsplit(".", 1)[-1]
    domain_name_guess = module_tail
    slug = slugify(domain_name_guess)

    goal_expr, goal_confident = draft_goal_check_expr(cls)
    caps, caps_confident = draft_capabilities(cls)

    lines: list[str] = []
    lines.append(f"afl:domain_{slug} a afl:DomainEvidenceSpec ;")
    lines.append(f'    afl:domainName "{domain_name_guess}" ;  # {REVIEW}: confirm this matches the intended afl:domainName convention')
    lines.append(f'    afl:pythonModulePath "{module_path}" ;')
    lines.append(f'    afl:domainClassName "{class_name}" ;')
    lines.append(f'    afl:bridgeModulePath "" ;  # {REVIEW}: fill in only if a gymact bridge module applies')
    lines.append(f'    afl:bridgeClassName "" ;  # {REVIEW}: fill in only if a gymact bridge class applies')
    goal_line = f'    afl:goalCheckExpr "{goal_expr}" ;'
    if not goal_confident:
        goal_line += f"  # {REVIEW}: low-confidence extraction, verify against _get_goals_/_is_terminal source"
    lines.append(goal_line)
    lines.append(f'    afl:verifyMode "fresh-instance-replay" ;  # {REVIEW}: confirm this domain actually supports fresh-instance replay verification')
    lines.append(
        f'    afl:evidenceOutPath "docs/evidence/{domain_name_guess}/domain-evidence-episode.ocel.json" ;'
        f"  # {REVIEW}: confirm target evidence path"
    )
    if caps:
        cap_refs = " , ".join(f"afl:domain_{slug}_cap_{i+1}" for i in range(len(caps)))
        lines.append(f"    afl:hasCapability {cap_refs} .")
    else:
        lines.append(f"    afl:hasCapability afl:domain_{slug}_cap_1 .  # {REVIEW}: no capabilities drafted")
    lines.append("")

    for i, cap in enumerate(caps, start=1):
        lines.append(f"afl:domain_{slug}_cap_{i} a afl:Capability ;")
        lines.append(f"    afl:capabilityOrder {i} ;")
        lines.append(f'    afl:capabilityName "{cap["name"]}" ;')
        lines.append(f'    afl:capabilityConsequence "{cap["consequence"]}" ;')
        lines.append(f'    afl:capabilityPrecondition "{cap["precondition"]}" .')
        if not caps_confident:
            lines.append(f"    # {REVIEW}: capability extraction was low-confidence, verify against _get_applicable_actions_from source")
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module", required=True, help="Python module path, e.g. autofde_lab.hub.domain.azuregoat_privesc.azuregoat_privesc")
    parser.add_argument("--class", dest="class_name", required=True, help="Class name, e.g. AzureGoatPrivilegeEscalation")
    args = parser.parse_args()

    domain_name_guess = args.module.rsplit(".", 1)[-1]

    if ONTOLOGY_PATH.exists():
        existing = ONTOLOGY_PATH.read_text()
        if re.search(rf'afl:domainName\s+"{re.escape(domain_name_guess)}"', existing):
            print(
                f"WARNING: a domainName matching {domain_name_guess!r} already appears in "
                f"{ONTOLOGY_PATH} -- this class may already be registered. Proceeding to draft "
                f"anyway since domainName is a guess, but review carefully.",
                file=sys.stderr,
            )

    ttl = draft_ttl(args.module, args.class_name)

    print(f"# --- DRAFTED Turtle for {args.module}.{args.class_name} ---")
    print(f"# NOTE: this is a DRAFT ONLY. It was NOT written to {ONTOLOGY_PATH}.")
    print(f"# Every field flagged \"{REVIEW}\" must be confirmed by a human before")
    print("# this is added to the committed ontology.")
    print()
    print(ttl)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
