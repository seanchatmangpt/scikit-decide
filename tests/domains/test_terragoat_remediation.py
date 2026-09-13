# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-school test for autofde_lab.hub.domain.terragoat.TerraGoatRemediation.

Exercises the real domain (parsed from the real vendored TerraGoat
``terraform/aws/s3.tf`` file, no mocked file contents or fabricated findings)
against the real, already-registered Astar solver's `solve()`. Assertions are
on real final state (all findings remediated) and the real returned plan
length/cost - no mocking of the domain or solver under test.
"""

from __future__ import annotations

from autofde_lab.hub.domain.terragoat import TerraGoatRemediation
from autofde_lab.hub.domain.terragoat.terragoat_remediation import (
    DEFAULT_TERRAFORM_FILE,
    parse_findings,
)
from autofde_lab.hub.solver.astar import Astar


def test_parse_findings_reads_real_terragoat_comments():
    """The parser must read real inline misconfiguration comments from the
    real vendored TerraGoat s3.tf file - not a fabricated fixture."""
    findings = parse_findings(DEFAULT_TERRAFORM_FILE, max_findings=8)

    assert len(findings) == 8
    assert findings[0].resource == "aws_s3_bucket.data"
    assert findings[0].description == "bucket is public"
    # ids are unique
    assert len({f.id for f in findings}) == 8


def test_astar_solves_terragoat_remediation_to_goal():
    """Real domain, real Astar C++ solver, real solve() call, real final state."""
    domain_factory = lambda: TerraGoatRemediation(max_findings=8)
    domain = domain_factory()

    initial_state = domain.get_initial_state()
    assert len(initial_state.open_findings) == 8

    with Astar(domain_factory=domain_factory) as solver:
        solver.solve()

        state = initial_state
        applied_actions = []
        for _ in range(len(initial_state.open_findings) + 1):
            if domain.is_goal(state):
                break
            action = solver.get_next_action(state)
            state = domain.get_next_state(state, action)
            applied_actions.append(action)

        # Real goal state reached: every parsed finding remediated.
        assert domain.is_goal(state)
        assert state.open_findings == frozenset()

        # Every finding was remediated exactly once (no repeats, no omissions).
        assert set(applied_actions) == {f.id for f in domain.findings}
        assert len(applied_actions) == 8

        plan = solver.get_plan(initial_state)
        assert len(plan) == 8
        total_cost = sum(value.cost for _, _, value in plan)
        assert total_cost == 8.0
