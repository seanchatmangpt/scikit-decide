from pathlib import Path


def test_sota_factory_ontology_declares_core_basis_and_strict_standing_vocabulary() -> (
    None
):
    text = Path("ontology/sota-factory.ttl").read_text()
    for term in (
        "afl:BenchmarkPortfolio",
        "afl:BenchmarkTarget",
        "afl:DecisionBasis",
        "afl:ExperimentBasis",
        "afl:ArchitecturePoint",
        "afl:ExperimentPlan",
        "afl:TrialResult",
        "afl:BenchmarkScore",
        "afl:DefinitionOfDoneReport",
        "afl:ProofObligation",
        "afl:SOTA_SURPASSED",
    ):
        assert term in text


def test_sota_factory_shapes_require_all_decision_dimensions() -> None:
    text = Path("ontology/shapes/sota-factory.shacl.ttl").read_text()
    for prop in (
        "hasModelChoice",
        "hasPlannerChoice",
        "hasToolPolicyChoice",
        "hasRepairPolicyChoice",
        "hasReplanningPolicyChoice",
        "hasVerificationPolicyChoice",
        "hasProjectionPolicyChoice",
        "hasMemoryPolicyChoice",
        "hasBudgetPolicy",
    ):
        assert f"afl:{prop}" in text


def test_sota_factory_shapes_bind_portfolio_frontier_evaluator_and_done_proof() -> None:
    text = Path("ontology/shapes/sota-factory.shacl.ttl").read_text()
    for prop in (
        "hasPortfolioTarget",
        "evaluatorReference",
        "frontierSourceReference",
        "hasProofObligation",
        "obligationSatisfied",
    ):
        assert f"afl:{prop}" in text
