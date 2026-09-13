"""Eight Challenger Enterprise Architecture value benchmarks.

Each case study executes the compiled issue-reasoning tool eight times against a
bounded evidence portfolio. The benchmark directly observes routing, hypothesis
elimination, fallback/refusal boundaries, zero actuation authority, and throughput.

Economic values are DERIVED SCENARIOS, never realized-savings claims. Only MATCHED
compiled episodes are assigned displaced-cognition capacity. FALLBACK_NOVELTY and
REFUSED_EVIDENCE carry zero replacement value.

Money semantics are pinned to ggen's vendored FIBO Currency Amount ontology:
https://spec.edmcouncil.org/fibo/ontology/FND/Accounting/CurrencyAmount/
ggen source snapshot: c37b46015b8e5ab40be771d61aafe3d7c7af084c
"""
from __future__ import annotations

import argparse
import csv
import json
import time
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Iterable

from autofde_lab.fabric.issue_reasoning import CompiledIssueReasoner, IssueRoute

FIBO_CURRENCY_AMOUNT = "https://spec.edmcouncil.org/fibo/ontology/FND/Accounting/CurrencyAmount/"
FIBO_MONETARY_AMOUNT = f"{FIBO_CURRENCY_AMOUNT}MonetaryAmount"
FIBO_HAS_CURRENCY = f"{FIBO_CURRENCY_AMOUNT}hasCurrency"
FIBO_USD = "https://spec.edmcouncil.org/fibo/ontology/FND/Accounting/ISO4217-CurrencyCodes/USDollar"
GGEN_FIBO_SOURCE_SHA = "c37b46015b8e5ab40be771d61aafe3d7c7af084c"
LOADED_ENGINEERING_USD_PER_HOUR = 100
SCENARIO_MINUTES = (5, 15, 30)


@dataclass(frozen=True)
class CaseStudy:
    id: str
    challenger_question: str
    episodes: tuple[tuple[str, ...], ...]


CASES: tuple[CaseStudy, ...] = (
    CaseStudy("global_platform_reliability", "Why purchase fresh cognition for recurring platform invariants?", (("workload_pending",), ("restarting",), ("no_endpoints",), ("dns_failure",), ("resource_exhausted",), ("storage_io_failure",), ("configuration_drift",), ("dependency_unreachable",))),
    CaseStudy("zero_trust_access", "Why escalate bounded policy-graph failures to open-ended reasoning?", (("authorization_denied",), ("policy_violation",), ("authorization_denied", "configuration_drift"), ("policy_violation", "authorization_denied"), ("authorization_denied",), ("policy_violation",), ("authorization_denied",), ("novel_or_metastable",))),
    CaseStudy("cloud_migration_factory", "Why reason manually about repeatable migration incompatibilities?", (("configuration_drift",), ("version_incompatible",), ("dependency_unreachable",), ("schema_validation_failure",), ("build_failure",), ("storage_io_failure",), ("dns_failure",), ("policy_violation",))),
    CaseStudy("data_platform", "Why send deterministic data-contract failures through expensive cognition?", (("schema_validation_failure",), ("queue_lag",), ("dependency_unreachable",), ("storage_io_failure",), ("version_incompatible",), ("configuration_drift",), ("resource_exhausted",), ("process_stuck",))),
    CaseStudy("software_delivery", "Why make engineers rediscover known delivery failure topology?", (("build_failure",), ("version_incompatible",), ("configuration_drift",), ("dependency_unreachable",), ("authorization_denied",), ("policy_violation",), ("resource_exhausted",), ("novel_or_metastable",))),
    CaseStudy("enterprise_integration", "Why treat bounded integration breakage as a language-generation problem?", (("dependency_unreachable",), ("schema_validation_failure",), ("version_incompatible",), ("dns_failure",), ("authorization_denied",), ("queue_lag",), ("configuration_drift",), ("process_stuck",))),
    CaseStudy("governance_controls", "Why debate controls whose conformance can be mechanically evaluated?", (("policy_violation",), ("authorization_denied",), ("configuration_drift",), ("schema_validation_failure",), ("version_incompatible",), ("process_stuck",), ("build_failure",), ("novel_or_metastable",))),
    CaseStudy("business_operations", "Why route recurring workflow-state failures through meetings and tickets?", (("process_stuck",), ("dependency_unreachable",), ("queue_lag",), ("authorization_denied",), ("configuration_drift",), ("schema_validation_failure",), ("resource_exhausted",), ("novel_or_metastable",))),
)


def scenario_usd(compiled_calls: int, minutes: int) -> float:
    """Derived displaced-cognition capacity for a declared economic envelope."""
    return compiled_calls * (minutes / 60) * LOADED_ENGINEERING_USD_PER_HOUR


def execute_case(reasoner: CompiledIssueReasoner, case: CaseStudy, repeats: int) -> dict[str, object]:
    started = time.perf_counter_ns()
    routes = {route.value: 0 for route in IssueRoute}
    eliminated = 0
    identities: set[str] = set()
    calls = 0
    for _ in range(repeats):
        for evidence in case.episodes:
            result = reasoner.reason(evidence)
            assert result.actuation == "REFUSED"
            routes[result.route.value] += 1
            eliminated += result.hypotheses_eliminated
            identities.add(result.candidate_identity_sha256)
            calls += 1
    elapsed_ns = time.perf_counter_ns() - started
    compiled_calls = routes[IssueRoute.MATCHED.value]
    return {
        "case": case.id,
        "tool_uses_per_portfolio": len(case.episodes),
        "repeats": repeats,
        "calls": calls,
        "compiled_calls": compiled_calls,
        "portfolio_compiled_coverage": compiled_calls / calls,
        "elapsed_ns": elapsed_ns,
        "calls_per_second": calls * 1_000_000_000 / elapsed_ns,
        "hypotheses_eliminated": eliminated,
        "hypotheses_eliminated_per_second": eliminated * 1_000_000_000 / elapsed_ns,
        "matched": compiled_calls,
        "refused_evidence": routes[IssueRoute.REFUSED_EVIDENCE.value],
        "fallback_novelty": routes[IssueRoute.FALLBACK_NOVELTY.value],
        "unique_candidate_identities": len(identities),
        "loaded_engineering_usd_per_hour": LOADED_ENGINEERING_USD_PER_HOUR,
        "derived_5m_usd": scenario_usd(compiled_calls, 5),
        "derived_15m_usd": scenario_usd(compiled_calls, 15),
        "derived_30m_usd": scenario_usd(compiled_calls, 30),
        "fibo_type": FIBO_MONETARY_AMOUNT,
        "fibo_currency_property": FIBO_HAS_CURRENCY,
        "fibo_currency": FIBO_USD,
        "ggen_fibo_source_sha": GGEN_FIBO_SOURCE_SHA,
        "economic_standing": "DERIVED_SCENARIO_NOT_REALIZED_SAVINGS",
        "actuation": "REFUSED",
        "challenger_question": case.challenger_question,
    }


def validate(rows: Iterable[dict[str, object]], repeats: int) -> None:
    rows = list(rows)
    assert len(rows) == 8
    expected = repeats * 8
    assert sum(int(row["calls"]) for row in rows) == 64 * repeats
    for row in rows:
        calls = int(row["calls"])
        compiled = int(row["compiled_calls"])
        assert row["tool_uses_per_portfolio"] == 8
        assert calls == expected
        assert 0 <= compiled <= calls
        assert abs(float(row["portfolio_compiled_coverage"]) - (compiled / calls)) < 1e-12
        assert row["elapsed_ns"] > 0
        assert row["calls_per_second"] > 0
        assert row["hypotheses_eliminated_per_second"] >= 0
        assert int(row["matched"]) + int(row["refused_evidence"]) + int(row["fallback_novelty"]) == expected
        for minutes in SCENARIO_MINUTES:
            observed = float(row[f"derived_{minutes}m_usd"])
            expected_usd = scenario_usd(compiled, minutes)
            assert abs(observed - expected_usd) < 1e-6
        assert row["fibo_type"] == FIBO_MONETARY_AMOUNT
        assert row["fibo_currency"] == FIBO_USD
        assert row["ggen_fibo_source_sha"] == GGEN_FIBO_SOURCE_SHA
        assert row["economic_standing"] == "DERIVED_SCENARIO_NOT_REALIZED_SAVINGS"
        assert row["actuation"] == "REFUSED"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeats", type=int, default=100_000)
    parser.add_argument("--output", type=Path, default=Path("challenger-issue-reasoning.csv"))
    args = parser.parse_args()
    reasoner = CompiledIssueReasoner()
    rows = [execute_case(reasoner, case, args.repeats) for case in CASES]
    validate(rows, args.repeats)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    direct_calls = sum(int(row["calls"]) for row in rows)
    compiled_calls = sum(int(row["compiled_calls"]) for row in rows)
    summary = {
        "case_studies": 8,
        "tool_uses_per_case_portfolio": 8,
        "direct_calls": direct_calls,
        "compiled_calls": compiled_calls,
        "portfolio_compiled_coverage": compiled_calls / direct_calls,
        "median_calls_per_second": median(float(row["calls_per_second"]) for row in rows),
        "total_hypotheses_eliminated": sum(int(row["hypotheses_eliminated"]) for row in rows),
        "fallback_calls": sum(int(row["fallback_novelty"]) for row in rows),
        "refused_calls": sum(int(row["refused_evidence"]) for row in rows),
        "loaded_engineering_usd_per_hour": LOADED_ENGINEERING_USD_PER_HOUR,
        "derived_5m_usd": scenario_usd(compiled_calls, 5),
        "derived_15m_usd": scenario_usd(compiled_calls, 15),
        "derived_30m_usd": scenario_usd(compiled_calls, 30),
        "fibo_type": FIBO_MONETARY_AMOUNT,
        "fibo_currency": FIBO_USD,
        "ggen_fibo_source_sha": GGEN_FIBO_SOURCE_SHA,
        "economic_standing": "DERIVED_SCENARIO_NOT_REALIZED_SAVINGS",
        "actuation": "REFUSED",
        "claim_boundary": "Dollar values apply only to MATCHED compiled episodes under declared loaded-rate/time assumptions; no realized savings or human/LLM displacement claim without an executed comparator and enterprise corpus.",
    }
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
