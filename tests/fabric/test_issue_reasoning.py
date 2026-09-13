from autofde_lab.fabric.issue_reasoning import CompiledIssueReasoner, IssueRoute


def test_compiled_issue_matches_structured_evidence() -> None:
    result = CompiledIssueReasoner().reason({"no_endpoints": True})

    assert result.route is IssueRoute.MATCHED
    assert result.archetype == "service_routing"
    assert result.repair_intent is not None
    assert result.hypotheses_eliminated == 3
    assert result.actuation == "REFUSED"
    assert len(result.evidence_identity_sha256) == 64
    assert len(result.candidate_identity_sha256) == 64


def test_novel_causal_topology_falls_back_instead_of_guessing() -> None:
    result = CompiledIssueReasoner().reason(["novel_or_metastable"])

    assert result.route is IssueRoute.FALLBACK_NOVELTY
    assert result.archetype == "novel_causal_topology"
    assert result.hypotheses_eliminated == 0
    assert result.actuation == "REFUSED"


def test_contradictory_evidence_refuses_candidate() -> None:
    result = CompiledIssueReasoner().reason(["no_endpoints", "dns_failure"])

    assert result.route is IssueRoute.REFUSED_EVIDENCE
    assert result.repair_intent is None
    assert result.contradictory_evidence
    assert result.actuation == "REFUSED"


def test_catalog_spans_generalized_troubleshooting_domains() -> None:
    catalog = CompiledIssueReasoner().catalog()
    domains = {item["domain"] for item in catalog}

    assert len(catalog) == 16
    assert {
        "infrastructure",
        "distributed_system",
        "networking",
        "security",
        "capacity",
        "storage",
        "configuration",
        "dependencies",
        "data",
        "software",
        "messaging",
        "developer_tooling",
        "governance",
        "process",
        "unknown",
    } <= domains


def test_candidate_identity_is_deterministic_and_evidence_sensitive() -> None:
    reasoner = CompiledIssueReasoner()
    first = reasoner.reason(["build_failure"])
    replay = reasoner.reason(["build_failure"])
    changed = reasoner.reason(["configuration_drift"])

    assert first.candidate_identity_sha256 == replay.candidate_identity_sha256
    assert first.evidence_identity_sha256 == replay.evidence_identity_sha256
    assert first.candidate_identity_sha256 != changed.candidate_identity_sha256
    assert first.evidence_identity_sha256 != changed.evidence_identity_sha256
