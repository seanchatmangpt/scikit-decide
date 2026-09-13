# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Capability-coverage report, driven by the generated ontology.

The invariant this module exists to enforce:

    Every ontology-declared capability must be selected, compared, or
    explicitly excluded with a machine-readable reason. A capability that is
    applicable and available must never be silently omitted.

Applicability is **derived, not asserted**: the ontology records each
solver's required domain characteristics (from
``Solver.get_domain_requirements()``, itself derived from the solver's
``T_domain`` MRO), and this module evaluates those requirements against a
concrete domain instance with ``isinstance``. That is the same rule
``Solver.check_domain`` (``src/autofde_lab/solvers.py:123``) applies, but sourced
from the ontology file so the ontology genuinely drives the classification.

Comparison is **measured, not delegated**: ``match_solvers(..., ranked=True)``
accepts the flag and ignores it (``src/autofde_lab/utils.py:126`` carries
``# TODO: implement ranking heuristic``), so a "dominated" verdict is only
honest if the alternatives were actually run and their costs compared. This
module runs them.

Buckets are exhaustive and mutually exclusive:

``applicable_selected``   applicable, ran, and won the comparison
``applicable_dominated``  applicable, ran, lost -- with the measured margin
``applicable_failed``     applicable but errored/timed out when run -- recorded,
                          never quietly dropped
``inapplicable``          unmet precondition, naming the exact characteristic
``unavailable``           standing is UNSUPPORTED/BLOCKED/BUILD_BROKEN
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional, Tuple

from autofde_lab.fabric.bounded_exec import run_callable_bounded
from autofde_lab.fabric.ontology import SKD, parse_turtle

MAX_ROLLOUT_STEPS = 200
#: Wall-clock bound per solver, via `run_callable_bounded` (signal.alarm).
#: No timeout existed here before this session: an RL-training solver
#: (RayRLlib, StableBaseline, AugmentedRandomSearch, MaxentIRL, ...) could
#: hang `_run_solver` indefinitely, confirmed as a real (not hypothetical)
#: risk by a full-catalog MCP sweep that needed a timeout for 15/117 real
#: domain x solver pairs (notebooks/18_mcp_user_simulation_ocel.ipynb).
SOLVER_TIMEOUT_S = 60

#: Machine-readable exclusion causes. A free-text reason alone would not be
#: machine-readable, and "it failed" is not an actionable exclusion.
CAUSE_REQUIRES_CONFIGURATION = "REQUIRES_CONFIGURATION"
CAUSE_REQUIRES_OTHER_DOMAIN_TYPE = "REQUIRES_OTHER_DOMAIN_TYPE"
CAUSE_DID_NOT_CONVERGE = "DID_NOT_CONVERGE"
CAUSE_TIMEOUT = "TIMEOUT"
CAUSE_RUNTIME_ERROR = "RUNTIME_ERROR"
CAUSE_UNMET_CHARACTERISTICS = "UNMET_DOMAIN_CHARACTERISTICS"
CAUSE_UNAVAILABLE = "CAPABILITY_UNAVAILABLE"
CAUSE_NONE = ""


def classify_failure(evidence: str) -> str:
    """Map a raw failure string to a machine-readable cause.

    Encodes a real limitation discovered by running this report: a solver's
    ``get_domain_requirements()`` describes the *domain characteristics* it
    needs, but says nothing about the *constructor arguments* it requires
    (a heuristic, a hyperparameter, an inner solver). So a capability can be
    ontology-applicable and still not runnable with defaults. That is a
    distinct, actionable category -- not the same as "inapplicable".
    """
    if "required positional argument" in evidence or "unexpected keyword" in evidence:
        return CAUSE_REQUIRES_CONFIGURATION
    if "requires a" in evidence and "Domain" in evidence:
        return CAUSE_REQUIRES_OTHER_DOMAIN_TYPE
    if "needs python" in evidence:
        return CAUSE_REQUIRES_OTHER_DOMAIN_TYPE
    if "rollout steps" in evidence or "off-goal" in evidence:
        return CAUSE_DID_NOT_CONVERGE
    if evidence.startswith("TimeoutError:") or "wall-clock bound" in evidence:
        return CAUSE_TIMEOUT
    return CAUSE_RUNTIME_ERROR


@dataclass
class CoverageRow:
    """One machine-readable row of the coverage report."""

    capability: str
    ontology_id: str
    owner: str
    applicability: str
    standing: str
    disposition: str  # selected | tied_optimal | dominated | failed | excluded
    cause: str  # machine-readable; "" when the capability was used
    reason: str
    execution_evidence: str
    falsifier: str


def _characteristic_classes() -> Dict[str, type]:
    """Map characteristic names to classes for isinstance evaluation."""
    import autofde_lab.builders.domain as builders

    return {
        name: obj
        for name, obj in vars(builders).items()
        if isinstance(obj, type)
    }


def load_ontology(path: str) -> Tuple[Dict[str, dict], Dict[str, dict]]:
    """Return (solvers, domains) keyed by identifier, from the Turtle file."""
    with open(path, encoding="utf-8") as handle:
        graph = parse_turtle(handle.read())

    solvers: Dict[str, dict] = {}
    domains: Dict[str, dict] = {}
    for subject, predicates in graph.items():
        types = predicates.get("a", [])
        identifier = (predicates.get("skdt:identifier") or [None])[0]
        if identifier is None:
            continue
        record = {
            "iri": subject,
            "identifier": identifier,
            "standing": (predicates.get("skdt:standing") or ["UNKNOWN"])[0],
            "evidence": (predicates.get("skdt:evidence") or [""])[0],
            "owning_module": (predicates.get("skdt:owningModule") or [""])[0],
            "requirements": [
                iri.rsplit("/", 1)[-1]
                for iri in predicates.get("skdt:requiresCharacteristic", [])
            ],
        }
        if "skdt:Solver" in types:
            solvers[identifier] = record
        elif "skdt:Domain" in types:
            domains[identifier] = record
    return solvers, domains


def _unmet_requirements(domain, requirements: List[str]) -> List[str]:
    classes = _characteristic_classes()
    unmet = []
    for requirement in requirements:
        klass = classes.get(requirement)
        if klass is None:
            unmet.append(f"{requirement}(unresolvable)")
        elif not isinstance(domain, klass):
            unmet.append(requirement)
    return unmet


def _run_solver(solver_name: str, domain_factory) -> Tuple[Optional[float], str]:
    """Run one solver; return (total_cost, evidence). Never raises.

    Bounded by `SOLVER_TIMEOUT_S` via `run_callable_bounded` (`signal.alarm`) --
    `domain_factory` is an arbitrary caller-supplied closure (e.g.
    ``lambda: CareerAdmission()``), not a registry name a subprocess could
    reconstruct on its own, so subprocess isolation (used for the simpler
    registry-name case in `scripts/mcp_solve_one_pair.py`) does not fit this
    call site -- see `bounded_exec.py`'s module docstring for why these are
    two different mechanisms, not one.
    """
    from autofde_lab import utils

    solver_class = utils.load_registered_solver(solver_name)
    if solver_class is None:
        return None, "load_registered_solver returned None"

    def _solve_and_rollout() -> Tuple[Optional[float], str]:
        domain = domain_factory()
        with solver_class(domain_factory=domain_factory) as solver:
            solver.solve()
            observation = domain.reset()
            total_cost = 0.0
            steps = 0
            for _ in range(MAX_ROLLOUT_STEPS):
                if domain._is_terminal(observation):
                    break
                action = solver.sample_action(observation)
                outcome = domain.step(action)
                total_cost += float(outcome.value.cost)
                observation = outcome.observation
                steps += 1
            else:
                return None, f"exceeded {MAX_ROLLOUT_STEPS} rollout steps"

            if not domain._is_goal(observation):
                return None, f"rollout ended off-goal after {steps} step(s)"
            return total_cost, f"solved, {steps} step(s), cost {total_cost:g}"

    try:
        return run_callable_bounded(_solve_and_rollout, timeout_s=SOLVER_TIMEOUT_S)
    except Exception as exc:  # noqa: BLE001 - failure is evidence, not a crash
        return None, f"{type(exc).__name__}: {exc}"


def build_report(
    domain_factory,
    ontology_path: str,
    run_applicable: bool = True,
) -> List[CoverageRow]:
    """Classify EVERY ontology-declared solver against a concrete domain."""
    solvers, _ = load_ontology(ontology_path)
    domain = domain_factory()
    rows: List[CoverageRow] = []

    applicable: List[str] = []
    for name, record in sorted(solvers.items()):
        if record["standing"] not in ("ALIVE", "PARTIAL_ALIVE"):
            rows.append(
                CoverageRow(
                    capability=name,
                    ontology_id=record["iri"],
                    owner=record["owning_module"] or "scikit-decide",
                    applicability="unavailable",
                    standing=record["standing"],
                    disposition="excluded",
                    cause=CAUSE_UNAVAILABLE,
                    reason=record["evidence"] or "capability did not load",
                    execution_evidence="not run: unavailable",
                    falsifier="would run if its dependency became importable",
                )
            )
            continue

        unmet = _unmet_requirements(domain, record["requirements"])
        if unmet:
            rows.append(
                CoverageRow(
                    capability=name,
                    ontology_id=record["iri"],
                    owner=record["owning_module"] or "scikit-decide",
                    applicability="inapplicable",
                    standing=record["standing"],
                    disposition="excluded",
                    cause=CAUSE_UNMET_CHARACTERISTICS,
                    reason=f"unmet domain characteristics: {','.join(unmet)}",
                    execution_evidence="not run: preconditions unmet",
                    falsifier=(
                        "would become applicable if the domain provided: "
                        f"{','.join(unmet)}"
                    ),
                )
            )
            continue
        applicable.append(name)

    results: Dict[str, Tuple[Optional[float], str]] = {}
    if run_applicable:
        for name in applicable:
            results[name] = _run_solver(name, domain_factory)
    else:
        results = {name: (None, "not run: execution disabled") for name in applicable}

    solved = {n: c for n, (c, _) in results.items() if c is not None}
    best_cost = min(solved.values()) if solved else None

    for name in applicable:
        record = solvers[name]
        cost, evidence = results[name]
        winners = [n for n, c in solved.items() if c == best_cost]

        if cost is None:
            applicability, disposition = "applicable", "failed"
            cause = classify_failure(evidence)
            reason = f"applicable but produced no verified plan [{cause}]: {evidence}"
            falsifier = "a fix making this solver return a goal-reaching plan"
        elif best_cost is not None and cost == best_cost:
            applicability = "applicable"
            # A tie is not a win. Reporting every tied solver as "selected"
            # would overstate the comparison; the honest statement is that
            # several capabilities reached the same measured optimum.
            disposition = "selected" if len(winners) == 1 else "tied_optimal"
            cause = CAUSE_NONE
            reason = (
                f"achieved best measured cost {cost:g}"
                if len(winners) == 1
                else (
                    f"tied at best measured cost {cost:g} with "
                    f"{len(winners) - 1} other capabilit"
                    f"{'y' if len(winners) == 2 else 'ies'}"
                )
            )
            falsifier = f"any solver returning a verified cost < {cost:g}"
        else:
            applicability, disposition = "applicable", "dominated"
            cause = CAUSE_NONE
            reason = (
                f"measured cost {cost:g} exceeds best {best_cost:g} "
                f"(margin {cost - best_cost:g})"
            )
            falsifier = "a cheaper run by this solver on the same domain"

        rows.append(
            CoverageRow(
                capability=name,
                ontology_id=record["iri"],
                owner=record["owning_module"] or "scikit-decide",
                applicability=applicability,
                standing=record["standing"],
                disposition=disposition,
                cause=cause,
                reason=reason,
                execution_evidence=evidence,
                falsifier=falsifier,
            )
        )

    return sorted(rows, key=lambda row: row.capability)


def report_to_json(rows: List[CoverageRow]) -> str:
    return json.dumps([asdict(row) for row in rows], indent=2, sort_keys=True)


def coverage_is_complete(
    rows: List[CoverageRow], ontology_path: str
) -> Tuple[bool, List[str]]:
    """Every ontology solver must appear exactly once. Returns (ok, problems)."""
    solvers, _ = load_ontology(ontology_path)
    covered = [row.capability for row in rows]
    problems: List[str] = []

    missing = sorted(set(solvers) - set(covered))
    if missing:
        problems.append(
            "capabilities declared in the ontology but silently omitted from "
            f"the coverage report: {missing}"
        )

    extra = sorted(set(covered) - set(solvers))
    if extra:
        problems.append(
            f"coverage report contains capabilities absent from the ontology "
            f"(stale ontology?): {extra}"
        )

    duplicates = sorted({name for name in covered if covered.count(name) > 1})
    if duplicates:
        problems.append(f"capabilities classified more than once: {duplicates}")

    unreasoned = sorted(row.capability for row in rows if not row.reason.strip())
    if unreasoned:
        problems.append(f"exclusions without a reason: {unreasoned}")

    return (not problems), problems
