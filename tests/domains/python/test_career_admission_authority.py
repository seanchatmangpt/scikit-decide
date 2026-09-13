# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""A genuinely reachable BLOCKED state, from a real generated authority file.

SCOPE WARNING -- read before citing this test as evidence of anything:

    This exercises reachability over a domain whose facts are loaded from
    ~/ggen-legacy/ontology/v26.8.1/legacy-capabilities.ttl, read in place.
    It manufactures nothing, admits nothing, receipts nothing, and verifies
    nothing independently. Reading a predicate out of another repository's
    generated file is not a standing determination made here.

What is verified: (a) the authority file really does assert UNKNOWN standing
with an UNASSIGNED equivalence verifier; (b) the domain built from it reaches
a state with an empty applicable-action set that is not a goal -- BLOCKED is
genuinely reachable; (c) `blocked_prerequisites` names the exact missing id;
(d) the curated DEFAULT_FACTS fixture has no such state, which is the defect
motivating this second fixture.

Skip discipline follows tests/ecosystem/test_chatman_chain_chicago.py: skip
ONLY on genuine absence of the authority file, never by substituting a
fixture.
"""

import os

import pytest

from autofde_lab.hub.domain.career_admission import CareerAdmission
from autofde_lab.hub.domain.career_admission.authority import (
    DEFAULT_AUTHORITY_PATH,
    UNASSIGNED_VERIFIER_ID,
    blocked_prerequisites,
    load_capability_facts,
    parse_legacy_turtle,
)
from autofde_lab.hub.domain.career_admission.career_admission import (
    DEFAULT_FACTS,
    DEFAULT_REQUIRED_CATEGORIES,
    State,
)


def _require_authority() -> str:
    if not os.path.isfile(DEFAULT_AUTHORITY_PATH):
        pytest.skip(
            f"BLOCKED:GGEN_LEGACY_ONTOLOGY_ABSENT: {DEFAULT_AUTHORITY_PATH}"
        )
    return DEFAULT_AUTHORITY_PATH


@pytest.fixture
def authority_graph():
    with open(_require_authority(), "r", encoding="utf-8") as handle:
        return parse_legacy_turtle(handle.read())


@pytest.fixture
def authority_domain():
    facts, required = load_capability_facts(_require_authority())
    return CareerAdmission(facts=facts, required_categories=required), facts


def _run_to_fixpoint(domain, limit: int = 500):
    """Greedily admit applicable facts until none remain or the goal is hit."""
    state = domain._get_initial_state_()
    for _ in range(limit):
        if domain._is_goal(state):
            return state, True
        applicable = domain._get_applicable_actions_from(state).get_elements()
        if not applicable:
            return state, False
        state = domain._get_next_state(state, sorted(applicable)[0])
    raise AssertionError("fixpoint not reached within limit")


def test_authority_file_asserts_unknown_standing_and_unassigned_verifier(
    authority_graph,
):
    """(a) The blocked-prerequisite source is asserted by the ontology."""
    unverifiable = [
        subject
        for subject, entry in authority_graph.items()
        if "ggen:LegacyCapability" in entry.get("a", [])
        and entry.get("ggen:hasStanding") == ["ggen:UNKNOWN"]
        and entry.get("ggen:equivalenceVerifier") == ["UNASSIGNED"]
    ]
    assert unverifiable, (
        "no capability in the authority file carries UNKNOWN standing with an "
        "UNASSIGNED equivalence verifier; the blocked-prerequisite premise "
        "does not hold for this file"
    )


def test_blocked_state_is_reachable_from_authority_facts(authority_domain):
    """(b) An empty applicable-action set at a non-goal state."""
    domain, facts = authority_domain
    assert facts, "authority file yielded no capability facts"

    state, reached_goal = _run_to_fixpoint(domain)

    assert not reached_goal, (
        "goal reached from the authority fixture; expected a blocked state "
        f"(admitted={len(state.admitted)} of {len(facts)})"
    )
    applicable = domain._get_applicable_actions_from(state).get_elements()
    assert applicable == [], (
        f"expected no applicable action at the blocked state, got {applicable}"
    )
    assert not domain._is_goal(state), "blocked state must not be a goal state"
    # The blocked state is genuinely reached, not the initial state.
    assert state.admitted, "no fact was admittable at all; fixture is degenerate"


def test_blocked_prerequisites_names_the_exact_missing_id(authority_domain):
    """(c) The dangling prerequisite id is named precisely."""
    _, facts = authority_domain
    missing = blocked_prerequisites(facts)

    assert missing, "no fact has a dangling prerequisite"
    for fact_id, dangling in missing.items():
        assert dangling == (UNASSIGNED_VERIFIER_ID,), (
            f"{fact_id} has unexpected dangling prerequisites {dangling}"
        )

    provided = {fact.id for fact in facts}
    assert UNASSIGNED_VERIFIER_ID not in provided, (
        "the missing prerequisite id is itself a loaded fact; it would be "
        "admittable and nothing would be blocked"
    )

    # The blocked facts are exactly those the domain can never admit.
    domain = CareerAdmission(
        facts=facts, required_categories=frozenset({"__unsatisfiable__"})
    )
    state, _ = _run_to_fixpoint(domain)
    assert set(missing) == {f.id for f in facts} - set(state.admitted), (
        "blocked_prerequisites disagrees with what the domain can admit"
    )


def test_default_facts_fixture_has_no_reachable_blocked_state():
    """(d) The curated fixture cannot reach a blocked state -- the defect."""
    domain = CareerAdmission()
    frontier = [State(admitted=frozenset())]
    seen = {frontier[0]}
    blocked = []
    while frontier:
        state = frontier.pop()
        if domain._is_goal(state):
            continue  # goal states are terminal, not blocked
        applicable = domain._get_applicable_actions_from(state).get_elements()
        if not applicable:
            blocked.append(state)
            continue
        for action in applicable:
            nxt = domain._get_next_state(state, action)
            if nxt not in seen:
                seen.add(nxt)
                frontier.append(nxt)

    assert not blocked, (
        f"DEFAULT_FACTS unexpectedly reaches blocked states: {blocked}"
    )
    assert blocked_prerequisites(DEFAULT_FACTS) == {}, (
        "DEFAULT_FACTS has a dangling prerequisite"
    )
    # And the two fixtures differ in exactly the claimed way.
    assert DEFAULT_REQUIRED_CATEGORIES == frozenset(
        {"ml_infra", "governance", "manufacturing"}
    )
