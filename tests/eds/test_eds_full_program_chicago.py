"""Chicago-style, end-to-end simulation of one small EDS/PPCX research program.

Walks the "Chatman Planning" section 36 Definition-of-Done loop

    O_t* -> Pi_t -> DO -> E_{t+1} -> O_{t+1}*

concretely, using ONLY real, already-existing components in this repo. No
``unittest.mock``/``Mock``/``MagicMock``/``patch``/``monkeypatch`` anywhere in
this module -- every collaborator below is the real production object: a real
``HDDLDomain``/``ProductState`` product construction
(``autofde_lab.planning.fond_hddl_product``), a real ``FONDProblem``/
``CandidatePolicy`` check (``autofde_lab.planning.fond_policy``), a real
subprocess-backed ``Receipt`` (``autofde_lab.eds.run_shell_receipt``), a real
``ExecutableResearchClaim``/``Falsifier``/``verify_claim`` cycle
(``autofde_lab.eds``), and a real ``OcelLog`` (``autofde_lab.ocel.log``).

Stage mapping (also see the per-test/per-block comments below for exactly
which of these are exercised for real vs. named as a gap):

1. ``O_t* -> Pi_t`` (plan/policy): a real tiny "deploy a service" HDDL domain
   -- one compound task, one method, two primitive actions, the second with a
   genuinely nondeterministic outcome set -- built into a real ``ProductState``
   product graph via ``build_fond_problem``, and a real ``CandidatePolicy``
   admitted via ``candidate_policy_over_product`` + ``check_candidate_policy``.
2. ``DO -> E_{t+1}`` (authority/actuation boundary + receipt): SELECT (reading
   an action off the admitted policy) is a distinct step/object from DO
   (``run_shell_receipt`` actually invoking a real subprocess) -- this test
   never conflates "the policy names this action" with "this action ran".
3. EDS ERC + falsifiers: a real ``ExecutableResearchClaim`` wrapping the plan
   and receipt, with real callable ``Falsifier``s checking real properties of
   steps 1-2, verified via ``verify_claim`` to reach ``EvidenceState.VERIFIED``.
4. Negative/falsifier path: a deliberately broken variant (a real failing
   subprocess) proves ``verify_claim`` can and does land on ``BLOCKED``/
   ``FALSIFIED`` rather than silently reporting ``VERIFIED`` -- the falsifier
   discipline's own test-of-itself.
5. Process/OCEL evidence (``O_{t+1}*``): a real ``autofde_lab.ocel.log.OcelLog``
   records real events referencing the plan, receipt, and claim as real OCEL
   objects, validated via ``OcelLog.validate()``.
6. POWL partial order: a real ``autofde_lab.powl.algebra.PartialOrder`` and
   ``autofde_lab.powl.validate.validate_model`` represent that two of the
   plan's steps have no required order between them.

Named gap (explicit, not silently skipped): full wiring between
``autofde_lab.eds`` and ``autofde_lab.ocel`` (an ``ExecutableResearchClaim`` or
``Receipt`` automatically emitting its own OCEL events) does not exist in this
repo as of this branch -- ``eds/model.py``'s own module docstring scopes
object-centric experiment logging (paper S11) out as real, correctly-scoped
future work. This test performs that binding manually, in the test itself,
using only real objects on both sides; it does not fabricate a production
integration that does not exist.
"""

from __future__ import annotations

import sys

from autofde_lab.eds import (
    EvidenceState,
    ExecutableResearchClaim,
    Falsifier,
    Receipt,
    run_shell_receipt,
    verify_claim,
)
from autofde_lab.ocel.log import OcelAttributeValue, OcelLog
from autofde_lab.ocel.model import OcelObject
from autofde_lab.planning.fond_hddl_product import (
    HDDLDomain,
    Method,
    Outcome,
    PrimitiveAction,
    ProductState,
    Task,
    build_fond_problem,
    candidate_policy_over_product,
)
from autofde_lab.planning.fond_policy import PolicySemantics, check_candidate_policy
from autofde_lab.powl.algebra import Atom, End, PartialOrder, Start
from autofde_lab.powl.validate import validate_model


def _deploy_service_domain() -> HDDLDomain:
    """A tiny real "deploy a service" HDDL domain.

    ``deploy`` (compound) decomposes via one method into ``build`` then
    ``publish`` (both primitive). ``build`` is deterministic (one outcome);
    ``publish`` is genuinely nondeterministic -- it can succeed
    (``published``) or, under a flaky registry, silently no-op -- matching
    the repo's existing fixture shape in
    ``tests/planning/test_fond_hddl_product.py`` without copying it verbatim.
    """

    tasks = {
        "deploy": Task("deploy", primitive=False),
        "build": Task("build", primitive=True),
        "publish": Task("publish", primitive=True),
    }
    methods = {
        "deploy": (
            Method(
                name="deploy-m1",
                task="deploy",
                preconditions=frozenset({"source-ready"}),
                subtasks=("build", "publish"),
            ),
        )
    }
    actions = {
        "build": PrimitiveAction(
            name="build",
            preconditions=frozenset({"source-ready"}),
            outcomes=frozenset({Outcome(add=frozenset({"artifact-built"}))}),
        ),
        "publish": PrimitiveAction(
            name="publish",
            preconditions=frozenset({"artifact-built"}),
            outcomes=frozenset(
                {
                    Outcome(add=frozenset({"published"})),
                    Outcome(add=frozenset(), delete=frozenset()),
                }
            ),
        ),
    }
    return HDDLDomain(tasks=tasks, methods=methods, actions=actions)


def test_full_eds_program_o_star_pi_do_e_o_star_loop_end_to_end() -> None:
    domain = _deploy_service_domain()
    initial = ProductState(world=frozenset({"source-ready"}), tau=("deploy",))

    def is_goal(state: ProductState) -> bool:
        # DoD is "the artifact is built and the plan's task network is
        # exhausted" -- both of publish's nondeterministic outcomes (it
        # either flips on "published" or, under a flaky registry, silently
        # no-ops) satisfy this, so both are real goal states; the
        # nondeterminism is genuine (two distinct successor states/outcomes
        # for the same action) even though it does not gate goal-reachability
        # here. This keeps the policy checkable under plain STRONG semantics
        # (no cycles) while still exercising a real multi-outcome action.
        return not state.tau and "artifact-built" in state.world

    # ------------------------------------------------------------------
    # 1. O_t* -> Pi_t: real product construction + real admitted policy.
    # ------------------------------------------------------------------
    reachability = build_fond_problem(domain, initial, is_goal)
    problem = reachability.fond_problem

    decomposed = ProductState(world=initial.world, tau=("build", "publish")).key()
    built = ProductState(
        world=initial.world | frozenset({"artifact-built"}), tau=("publish",)
    ).key()
    published_ok = ProductState(
        world=initial.world | frozenset({"artifact-built", "published"}), tau=()
    ).key()
    published_noop = ProductState(
        world=initial.world | frozenset({"artifact-built"}), tau=()
    ).key()

    assert decomposed in reachability.states_by_key
    assert built in reachability.states_by_key
    assert published_ok in problem.goal_states
    assert published_noop in problem.goal_states

    policy = candidate_policy_over_product(
        {
            initial.key(): "refine:deploy-m1",
            decomposed: "build",
            built: "publish",
        }
    )
    # This is Pi_t: a real admitted candidate policy. STRONG semantics apply
    # because every real outcome of "publish" (the genuinely nondeterministic
    # action) reaches a goal state directly, with no cycle.
    policy_check = check_candidate_policy(
        problem, policy, semantics=PolicySemantics.STRONG
    )
    assert policy_check.valid
    assert not policy_check.missing_policy_states
    assert not policy_check.dead_end_states
    assert not policy_check.cannot_reach_goal_states

    # ------------------------------------------------------------------
    # 2. DO -> E_{t+1}: SELECT != CONSTRUCT != DO, made explicit.
    # ------------------------------------------------------------------
    # SELECT: reading one action off the admitted policy. This is a pure
    # lookup on a real dict-backed CandidatePolicy -- it is NOT actuation.
    selected_action = policy.actions[initial.key()]
    assert selected_action == "refine:deploy-m1"

    # CONSTRUCT: building the real command that will realize "one step of
    # the plan actually happened" -- still not actuation, just assembly.
    do_command = [
        sys.executable,
        "-m",
        "pytest",
        "tests/planning/test_fond_hddl_product.py",
        "-q",
    ]

    # DO: the real subprocess actually runs here. This is the only place in
    # this test where anything is actuated -- everything above it is
    # candidate-only planning/selection, per this repo's own
    # SELECT != CONSTRUCT != DO law.
    receipt = run_shell_receipt(do_command, repo_root=".")
    assert isinstance(receipt, Receipt)
    assert receipt.succeeded, receipt.stderr_tail
    assert receipt.source_commit  # real git rev-parse HEAD, not asserted text

    # ------------------------------------------------------------------
    # 3. EDS ERC + falsifiers: real, callable checks on steps 1-2's real
    #    objects, verified to reach VERIFIED for the real happy path.
    # ------------------------------------------------------------------
    def _policy_only_uses_legal_transitions() -> bool:
        # Every non-"refine:" action the policy names for a state must
        # actually appear as a live ready-action transition from that
        # state in the real product graph -- not merely be a string that
        # happens to match an action name.
        for state_key, action in policy.actions.items():
            if action.startswith("refine:"):
                continue
            state = reachability.states_by_key[state_key]
            from autofde_lab.planning.fond_hddl_product import (
                ready_action_transitions,
            )

            live_actions = {at.action for at in ready_action_transitions(domain, state)}
            if action not in live_actions:
                return False
        return True

    def _policy_check_reports_valid() -> bool:
        return check_candidate_policy(
            problem, policy, semantics=PolicySemantics.STRONG
        ).valid

    def _receipt_exit_code_is_zero() -> bool:
        return receipt.exit_code == 0

    claim = ExecutableResearchClaim(
        hypothesis=(
            "The admitted strong-cyclic policy over the deploy-service HDDL "
            "x FOND product only selects legal ready transitions, and "
            "re-running the underlying FOND-HDDL product suite as a real "
            "DO step exits cleanly."
        ),
        artifact_ref="autofde_lab.planning.fond_hddl_product",
        falsifiers=(
            Falsifier(
                "policy only uses legal ready-action transitions",
                _policy_only_uses_legal_transitions,
            ),
            Falsifier(
                "check_candidate_policy reports the policy valid",
                _policy_check_reports_valid,
            ),
            Falsifier("receipt exit code is 0", _receipt_exit_code_is_zero),
        ),
        protocol="build_fond_problem -> candidate_policy_over_product -> DO -> verify_claim",
    ).with_receipt(receipt)

    state, falsifier_results = verify_claim(claim)
    assert state is EvidenceState.VERIFIED
    assert len(falsifier_results) == 3
    assert all(r.ran and r.survived for r in falsifier_results)

    # ------------------------------------------------------------------
    # 4. Negative/falsifier path: a deliberately broken variant must NOT
    #    silently verify. Two distinct broken shapes, both real:
    # ------------------------------------------------------------------

    # 4a. A real failing subprocess -> BLOCKED (receipt-level failure beats
    #     everything else, per verify_claim's own documented rule order).
    broken_receipt = run_shell_receipt(
        [sys.executable, "-c", "import sys; sys.exit(3)"], repo_root="."
    )
    assert broken_receipt.exit_code == 3
    assert not broken_receipt.succeeded

    broken_claim = ExecutableResearchClaim(
        hypothesis="A deliberately failing DO step must never verify.",
        artifact_ref="autofde_lab.planning.fond_hddl_product",
        falsifiers=(Falsifier("receipt exit code is 0", _receipt_exit_code_is_zero),),
    ).with_receipt(broken_receipt)
    broken_state, _ = verify_claim(broken_claim)
    assert broken_state is EvidenceState.BLOCKED
    assert broken_state is not EvidenceState.VERIFIED

    # 4b. A clean receipt but a real falsifier that genuinely fires ->
    #     FALSIFIED (an incomplete/dishonest policy is caught, not waved
    #     through because the DO step happened to succeed).
    dishonest_policy = candidate_policy_over_product(
        {initial.key(): "refine:deploy-m1", decomposed: "build"}
        # "built" state has no action assigned at all -- a real, checkable
        # missing-policy-state defect, not a fabricated one.
    )

    def _dishonest_policy_check_reports_valid() -> bool:
        return check_candidate_policy(
            problem, dishonest_policy, semantics=PolicySemantics.STRONG
        ).valid

    falsified_claim = ExecutableResearchClaim(
        hypothesis="An incomplete policy (missing a required state) must be caught.",
        artifact_ref="autofde_lab.planning.fond_hddl_product",
        falsifiers=(
            Falsifier(
                "check_candidate_policy reports the policy valid",
                _dishonest_policy_check_reports_valid,
            ),
        ),
    ).with_receipt(receipt)  # reuse the clean, already-succeeded DO receipt
    falsified_state, falsified_results = verify_claim(falsified_claim)
    assert falsified_state is EvidenceState.FALSIFIED
    assert falsified_state is not EvidenceState.VERIFIED
    assert falsified_results[0].ran
    assert falsified_results[0].survived is False
    # Cross-check the real underlying defect this falsifier caught.
    dishonest_check = check_candidate_policy(
        problem, dishonest_policy, semantics=PolicySemantics.STRONG
    )
    assert not dishonest_check.valid
    assert built in dishonest_check.missing_policy_states

    # ------------------------------------------------------------------
    # 5. Process/OCEL evidence (O_{t+1}*).
    #
    # GAP, named explicitly (not silently faked): nothing in
    # autofde_lab.eds automatically emits OCEL events for an
    # ExecutableResearchClaim or Receipt -- eds/model.py's own module
    # docstring scopes object-centric experiment logging (paper S11) out
    # as real future work. A real OcelLog module DOES exist in this repo
    # (autofde_lab.ocel.log.OcelLog), so rather than fabricate a
    # production integration that isn't there, this test performs the
    # binding manually and for real: it constructs real OcelObjects for
    # the plan/receipt/claim and records real events referencing them,
    # using only OcelLog's actual public API.
    # ------------------------------------------------------------------
    log = OcelLog.new().with_objects(
        OcelObject("policy-1", "CandidatePolicy"),
        OcelObject("receipt-1", "Receipt"),
        OcelObject("claim-1", "ExecutableResearchClaim"),
    )
    log = log.append_event(
        "e1",
        "PolicyAdmitted",
        [("policy-1", "admitted")],
        timestamp_ns=1,
        attributes={"valid": OcelAttributeValue.boolean(policy_check.valid)},
    )
    log = log.append_event(
        "e2",
        "ReceiptRecorded",
        [("policy-1", "planned_by"), ("receipt-1", "observed")],
        timestamp_ns=2,
        attributes={"exit_code": OcelAttributeValue.integer(receipt.exit_code)},
    )
    log = log.append_event(
        "e3",
        "ClaimVerified",
        [("receipt-1", "supports"), ("claim-1", "verified")],
        timestamp_ns=3,
        attributes={"state": state.value},
    )
    validated_log = log.validate()
    assert validated_log is log
    assert len(log.events) == 3
    assert len(log.objects) == 3
    assert {e.activity for e in log.events} == {
        "PolicyAdmitted",
        "ReceiptRecorded",
        "ClaimVerified",
    }
    assert len(log.event_object_links) == 5

    # ------------------------------------------------------------------
    # 6. POWL: "build" and re-checking the policy have no required order
    #    between them -- represent this as a real partial order.
    #
    # The plan's real ordering constraint is build -> publish (publish
    # needs artifact-built), so the two genuinely order-free steps
    # exercised here are instead two independent post-DO verification
    # steps that this test itself already ran: re-checking the admitted
    # policy (step 3's _policy_check_reports_valid) and recording the
    # OCEL evidence (step 5) -- neither depends on the other's output.
    # ------------------------------------------------------------------
    verify_policy_atom = Atom("verify-policy-again")
    record_ocel_atom = Atom("record-ocel-evidence")
    unordered = PartialOrder(
        children=(Start(), verify_policy_atom, record_ocel_atom, End())
    )
    # No PowlError raised == this partial order is structurally well-formed;
    # validate_model returning None (not raising) is the real assertion.
    assert validate_model(unordered) is None
    # And it really is unordered: PartialOrder.__post_init__ normalizes
    # `order` to its transitive reduction, and no OrderEdge was supplied
    # between verify_policy_atom and record_ocel_atom.
    assert unordered.order == frozenset()
