# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-school, JTBD-framed end-to-end tests for
autofde_lab.career.resume.generate_resume.

Each test states a Job To Be Done ("When I am <actor> and I need <job>, I
want <outcome>") and then exercises the real, real `CareerGraph` ->
`generate_resume` -> `Resume` pipeline with no mocks or stubs: every object
constructed here is a real dataclass instance, and every assertion checks
the real strings/structure `generate_resume` actually produced.
"""

import pytest

from autofde_lab.career import (
    Capability,
    CareerGraph,
    Evidence,
    Outcome,
    generate_resume,
)


def test_candidate_with_one_verified_outcome_gets_a_complete_resume():
    """JTBD: When I am a candidate with one verified outcome, I want a
    résumé so that every Appendix-G section is present and non-empty."""
    graph = CareerGraph(
        target_role="Agentic AI Architect",
        outcomes=[
            Outcome(
                statement="Reduced manual migration effort",
                beneficiary="platform engineering team",
                system="an agent-assisted migration workflow",
                evidence=Evidence(
                    label="fixture suite + build receipts", proof_level=3
                ),
            )
        ],
        capabilities=[Capability(name="MCP", category="Agent architecture")],
    )

    resume = generate_resume(graph)

    assert resume.headline
    assert resume.summary
    assert resume.capability_system
    assert resume.outcome_bullets
    assert resume.evidence_list
    # the headline is a real projection of the graph's own fields, not a
    # hardcoded template output
    assert "Agentic AI Architect" in resume.headline
    assert "platform engineering team" in resume.headline


def test_bare_assertion_evidence_is_never_surfaced_in_a_bullet():
    """JTBD: When my evidence is a bare assertion (proof_level 0), I want
    generate_resume to omit it from the outcome bullet and the evidence
    list, so recruiters are never shown a claim I can't defend."""
    unverified = Evidence(label="I am definitely the best candidate", proof_level=0)
    graph = CareerGraph(
        target_role="Principal Engineer",
        outcomes=[
            Outcome(
                statement="Improved system reliability",
                beneficiary="the org",
                evidence=unverified,
            )
        ],
    )

    resume = generate_resume(graph)

    assert unverified.label not in resume.outcome_bullets[0]
    assert unverified.label not in resume.evidence_list


def test_defensible_evidence_is_cited_in_its_bullet():
    """JTBD: When my evidence has proof_level >= 1 (an actual artifact),
    I want it cited in the bullet, so real proof isn't silently dropped
    alongside the unverifiable case above."""
    verified = Evidence(label="reproduced benchmark report", proof_level=5)
    graph = CareerGraph(
        target_role="Principal Engineer",
        outcomes=[
            Outcome(
                statement="Improved system reliability",
                beneficiary="the org",
                evidence=verified,
            )
        ],
    )

    resume = generate_resume(graph)

    assert verified.label in resume.outcome_bullets[0]
    assert verified.label in resume.evidence_list


def test_capabilities_across_categories_are_grouped_not_flattened():
    """JTBD: When I am a candidate with capabilities spanning multiple
    Appendix-G function groups, I want them grouped by category so the
    résumé communicates structure, not a flat keyword list."""
    graph = CareerGraph(
        target_role="Agentic AI Architect",
        outcomes=[
            Outcome(statement="Shipped a planning system", beneficiary="customers")
        ],
        capabilities=[
            Capability(name="MCP", category="Agent architecture"),
            Capability(name="A2A", category="Agent architecture"),
            Capability(name="Planning", category="Decision systems"),
            Capability(name="Evaluation", category="Reliability"),
        ],
    )

    resume = generate_resume(graph)

    assert set(resume.capability_system.keys()) == {
        "Agent architecture",
        "Decision systems",
        "Reliability",
    }
    assert resume.capability_system["Agent architecture"] == ["MCP", "A2A"]
    assert resume.capability_system["Decision systems"] == ["Planning"]
    assert resume.capability_system["Reliability"] == ["Evaluation"]


def test_zero_outcomes_is_refused_not_silently_projected():
    """JTBD: When my career graph has zero real outcomes, I want a clear
    refusal (ValueError) rather than a hollow, content-free résumé."""
    empty_graph = CareerGraph(target_role="Principal Engineer")

    with pytest.raises(ValueError):
        generate_resume(empty_graph)


def test_two_different_graphs_produce_actually_different_resumes():
    """JTBD: When I generate résumés from two distinct career graphs, I
    want the outputs to actually differ, confirming generate_resume
    reflects real input rather than leaking a fixed template."""
    graph_a = CareerGraph(
        target_role="Agentic AI Architect",
        outcomes=[
            Outcome(statement="Built a migration factory", beneficiary="engineering")
        ],
    )
    graph_b = CareerGraph(
        target_role="Decision Systems Lead",
        outcomes=[
            Outcome(statement="Built a scheduling optimizer", beneficiary="operations")
        ],
    )

    resume_a = generate_resume(graph_a)
    resume_b = generate_resume(graph_b)

    assert resume_a.headline != resume_b.headline
    assert resume_a.outcome_bullets != resume_b.outcome_bullets
    assert resume_a.summary != resume_b.summary
