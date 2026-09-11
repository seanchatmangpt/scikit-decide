# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style falsifiers for continuous cache-aware planning.

Nothing here actuates.  The tests distinguish retrieval, admission, local repair,
and guarded promotion so none can be silently promoted into another.
"""

from autofde_lab.agent.continuous_planning import (
    AnchorVerdict,
    ContinuousPlanner,
    PlanApplicability,
    PlanArtifact,
    PlanCache,
    PlanDisposition,
    PlanningContext,
    PromotionPolicy,
    admit_plan,
    evaluate_promotion,
)
from autofde_lab.agent.replan import ReplanningMode
from autofde_lab.powl.algebra import Atom, OrderEdge, PartialOrder


def _plan(
    *,
    required_facts=frozenset({"healthy-control-plane"}),
    required_capabilities=frozenset({"kubectl"}),
) -> PlanArtifact:
    model = PartialOrder(
        (Atom("observe"), Atom("repair"), Atom("verify"), Atom("report")),
        frozenset(
            {
                OrderEdge(0, 1),
                OrderEdge(1, 2),
                OrderEdge(0, 3),
            }
        ),
    )
    return PlanArtifact(
        model=model,
        applicability=PlanApplicability(
            goal="restore-service",
            required_facts=required_facts,
            required_capabilities=required_capabilities,
            constraint_digest="policy-v1",
            semantic_revision="cloud-v1",
        ),
        planner="powl-repair",
        planner_parameters={"beam": 8},
        dependency_keys={
            (0,): frozenset({"fact:healthy-control-plane"}),
            (1,): frozenset({"fact:target-ready"}),
            (2,): frozenset({"fact:target-ready"}),
            (3,): frozenset({"fact:reporting-enabled"}),
        },
        downstream={
            (0,): frozenset({(1,), (3,)}),
            (1,): frozenset({(2,)}),
        },
        family_id="restore-service",
        version=3,
        required_authority_classes=("cloud-operator",),
    )


def _context(*, facts=frozenset({"healthy-control-plane", "target-ready"})):
    return PlanningContext(
        goal="restore-service",
        facts=facts,
        capabilities=frozenset({"kubectl"}),
        constraint_digest="policy-v1",
        semantic_revision="cloud-v1",
    )


def test_retrieval_is_not_admission() -> None:
    cache = PlanCache()
    plan = _plan(required_facts=frozenset({"healthy-control-plane", "secret-fact"}))
    cache.remember(plan)
    context = _context()

    candidates = cache.retrieve_candidates(context)
    assert candidates == (plan,)
    admission = admit_plan(candidates[0], context)
    assert admission.admitted is False

    decision = ContinuousPlanner(cache).decide(context)
    assert decision.disposition is PlanDisposition.FRESH_PLAN
    assert decision.mode is ReplanningMode.REPLAN


def test_exact_reuse_requires_fresh_admission() -> None:
    cache = PlanCache()
    plan = _plan()
    exact_key = cache.remember(plan)

    admitted = ContinuousPlanner(cache).decide(_context(), exact_key=exact_key)
    assert admitted.disposition is PlanDisposition.EXACT_REUSE
    assert admitted.plan is plan
    assert admitted.admission is not None and admitted.admission.admitted

    stale = _context(facts=frozenset({"target-ready"}))
    refused = ContinuousPlanner(cache).decide(stale, exact_key=exact_key)
    assert refused.disposition is PlanDisposition.FRESH_PLAN


def test_delta_driven_repair_only_marks_the_dependency_closure() -> None:
    plan = _plan(required_facts=frozenset())
    before = _context(
        facts=frozenset({"healthy-control-plane", "target-ready", "reporting-enabled"})
    )
    after = _context(facts=frozenset({"healthy-control-plane", "reporting-enabled"}))

    decision = ContinuousPlanner().decide(
        after,
        active_plan=plan,
        previous_context=before,
    )

    assert decision.disposition is PlanDisposition.REPAIR
    assert decision.mode is ReplanningMode.REPAIR
    assert decision.affected == frozenset({(1,), (2,)})
    assert (0,) not in decision.affected
    assert (3,) not in decision.affected


def test_irrelevant_delta_does_not_force_replanning() -> None:
    plan = _plan(required_facts=frozenset())
    before = _context(facts=frozenset({"target-ready"}))
    after = _context(facts=frozenset({"target-ready", "unrelated-observation"}))

    decision = ContinuousPlanner().decide(
        after,
        active_plan=plan,
        previous_context=before,
    )

    assert decision.disposition is PlanDisposition.CONTINUE
    assert decision.mode is ReplanningMode.CONTINUE
    assert decision.affected == frozenset()


def test_guarded_promotion_rejects_historical_regression() -> None:
    rejected = evaluate_promotion(
        current_score=0.70,
        candidate_score=0.91,
        validity_passed=True,
        anchors=(
            AnchorVerdict("aws", True, True),
            AnchorVerdict("azure", True, False),
            AnchorVerdict("gcp", True, True),
        ),
    )
    assert rejected.promoted is False
    assert rejected.reason == "RETENTION_BUDGET_EXCEEDED"
    assert rejected.regressions == ("azure",)

    promoted = evaluate_promotion(
        current_score=0.70,
        candidate_score=0.91,
        validity_passed=True,
        anchors=(
            AnchorVerdict("aws", True, True),
            AnchorVerdict("azure", True, False),
        ),
        policy=PromotionPolicy(max_retention_regressions=1),
    )
    assert promoted.promoted is True


def test_declared_authority_class_is_descriptive_only() -> None:
    plan = _plan(required_facts=frozenset())
    admission = admit_plan(plan, _context())
    assert admission.admitted is True
    assert plan.required_authority_classes == ("cloud-operator",)
    assert not hasattr(plan, "grant")
    assert not hasattr(plan, "execute")
