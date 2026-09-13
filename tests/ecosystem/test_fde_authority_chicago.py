# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""The 14 FDE falsifiers, one negative fixture each.

Scope, stated first so this file is not cited for more than it establishes:
these tests exercise :mod:`autofde_lab.fabric.fde` against **committed authority
artifacts**. They establish that the compiler/checker refuses each named
organizational failure with a typed code. They establish nothing about any
customer, any real grant, or any organizational standing -- no test here can
stand in for a customer operating owner's acceptance, and none tries to.

Two boundaries this file defends, both by assertion rather than by comment:

* :class:`TestModuleMintsNothing` -- ``fde.py`` exposes no function returning a
  grant, token, capability handle, signature, or receipt. Computing "would
  this grant permit this operation?" is advisory; authorizing is MFW's broker.
  ``tests/ecosystem/test_chatman_chain_chicago.py::TestPlannerOutputIsCandidateNotActuation``
  defends the technical half of the same line.
* :class:`TestActKindsAreNonInterchangeable` -- the seven kinds
  (`.claude/rules/fde-authority-boundary.md`) cannot collapse into one another.

Every assertion is on a typed ``.code`` / ``.reason``, never on message text.
Skips carry a ``BLOCKED:<TOKEN>:`` prefix and are used only for genuine absence
of a prerequisite, per ``tests/ecosystem/CLAUDE.md`` invariant 1.

Nothing in the *positive* fixture asserts a customer decision: it declares a
sunset **authority** (who could decide) and no sunset **authorization** (a
decision taken). Writing ``customerAuthorizedRetirement true`` into a fixture
would manufacture the authority the gate exists to require -- invariant 7. The
only fixtures carrying that flag are negatives, exercised as refusals.
"""

from __future__ import annotations

import inspect
from datetime import datetime, timezone
from pathlib import Path

import pytest

from autofde_lab.fabric import fde
from autofde_lab.fabric.fde import (
    AuthorityError,
    ProposedOperation,
    load_authority,
    permits,
    validate_authority,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "fde"
BASE = FIXTURES / "customer-authority.ttl"
SHAPES = FIXTURES / "customer-authority.shacl.ttl"

FDE_NS = "urn:skdecide:fde:"
CUSTOMER = FDE_NS + "customer/acme"
CUSTOMER_EMEA = FDE_NS + "customer/acme-emea"
CAP_REBALANCE = FDE_NS + "capability/schedule-rebalance"
CAP_PAYROLL = FDE_NS + "capability/payroll-adjust"
OP_REBALANCE = FDE_NS + "operation/rebalance-north"
OP_PAYROLL = FDE_NS + "operation/payroll-adjust-north"
RS_NORTH = FDE_NS + "resource/plant-north"
RS_SOUTH = FDE_NS + "resource/plant-south"
ES_STAGING = FDE_NS + "environment/staging"
ES_PRODUCTION = FDE_NS + "environment/production"
FDE_PARTY = FDE_NS + "party/fde-architect"
VENDOR = FDE_NS + "party/vendor-manufacture"
VERIFIER = FDE_NS + "verifier/ggen-legacy-replay"

IN_WINDOW = datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc)
IN_PAST_WINDOW = datetime(2026, 2, 15, 12, 0, tzinfo=timezone.utc)
EXEC_DIGEST = "blake3:" + "9b2e4a70" * 8


def fixture(name: str):
    path = FIXTURES / name
    assert path.exists(), f"missing committed fixture {path}"
    return load_authority(str(path))


def proposal(**overrides) -> ProposedOperation:
    """A proposal that the base grant permits, unless a field is overridden."""
    kwargs = dict(
        customer=CUSTOMER,
        capability=CAP_REBALANCE,
        operation=OP_REBALANCE,
        resource_scope=RS_NORTH,
        environment_scope=ES_STAGING,
        at=IN_WINDOW,
        executable_digest=EXEC_DIGEST,
        affected_resources=4,
        irreversible_actions=0,
        duration_seconds=900,
        delegated=False,
        performed_by=VENDOR,
        manufactured_by=VENDOR,
        verified_by=VERIFIER,
    )
    kwargs.update(overrides)
    return ProposedOperation(**kwargs)


def refusal_code(name: str, **overrides) -> str:
    """Run ``permits`` against a fixture and return the typed refusal reason.

    A permitted proposal returns a sentinel rather than raising, so that a
    collapsed test naming several refusal axes reports *which* axis stopped
    refusing instead of aborting at the first one.
    """
    model = fixture(name)
    grant = model.the_grant()
    verdict = permits(model, grant, proposal(**overrides))
    if verdict.allowed:
        return f"NOT_REFUSED({name}: {verdict.verdict} -- {verdict.detail})"
    return verdict.reason


def validation_code(name: str) -> str:
    """Return the typed ``AuthorityError.code``, or a sentinel if none was raised."""
    model = fixture(name)
    try:
        validate_authority(model)
    except AuthorityError as error:
        return error.code
    return f"NOT_REFUSED({name}: validate_authority accepted the artifact)"


# ---------------------------------------------------------------------------
# The artifact itself
# ---------------------------------------------------------------------------


class TestTheAuthorityArtifact:
    def test_base_artifact_validates_and_permits_the_bounded_operation(self):
        """The positive baseline. If this goes red every refusal below is moot."""
        model = fixture("customer-authority.ttl")
        assert validate_authority(model) is not None
        verdict = permits(model, model.the_grant(), proposal())
        assert verdict.allowed, verdict.detail
        assert verdict.verdict == "ALLOW"

    def test_committed_artifacts_are_well_formed(self):
        """Four distinct artifact-corpus properties, each named on failure.

        Collapsed from four sibling tests; every check still runs and the
        report lists *all* offenders rather than stopping at the first.

        * SHAPES_FILE -- the SHACL shapes are committed with their 3 node
          shapes / 6 property blocks.
        * NAKED_APPROVAL -- `approved = true` records no decider, no right and
          no evidence, so no fixture statement line may carry it. Scanned over
          statement lines only; the prose comments deliberately discuss the
          banned shape in order to say why it is banned.
        * ENTITY_KINDS -- every entity kind the boundary requires is modelled.
        * NO_MANUFACTURED_DECISION -- invariant 7: the positive fixture must
          not manufacture customer authority.
        """
        failures: list[str] = []

        if not SHAPES.exists():
            failures.append(f"SHAPES_FILE: {SHAPES} missing")
        else:
            text = SHAPES.read_text()
            if text.count("a sh:NodeShape") < 3 or text.count("sh:property") < 6:
                failures.append(
                    "SHAPES_FILE: expected >=3 sh:NodeShape and >=6 sh:property, "
                    f"got {text.count('a sh:NodeShape')} / {text.count('sh:property')}"
                )

        for path in sorted(FIXTURES.glob("*.ttl")):
            for line in path.read_text().splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                lowered = stripped.lower()
                for banned in ("approved", "approval", "signoff", "sign_off", "ok "):
                    if banned in lowered:
                        failures.append(
                            f"NAKED_APPROVAL: {path.name}: {stripped!r} carries "
                            f"{banned!r}"
                        )

        turtle = BASE.read_text()
        for term in (
            "fdet:CustomerOrganization",
            "fdet:FdeIdentity",
            "fdet:CustomerAuthorityIdentity",
            "fdet:organizationalRole",
            "fdet:DecisionRight",
            "fdet:AuthorizedCapability",
            "fdet:AuthorizedOperation",
            "fdet:ResourceScope",
            "fdet:EnvironmentScope",
            "fdet:ValidityInterval",
            "fdet:ConsequenceBounds",
            "fdet:Verifier",
            "fdet:Postcondition",
            "fdet:AdoptionOwner",
            "fdet:SunsetAuthority",
            "fdet:grantIdentifier",
        ):
            if term not in turtle:
                failures.append(f"ENTITY_KINDS: artifact does not model {term}")

        for manufactured in (
            "customerAuthorizedRetirement",
            "fdet:SunsetAuthorization",
            "fdet:AdoptionDecision",
        ):
            if manufactured in turtle:
                failures.append(
                    f"NO_MANUFACTURED_DECISION: positive fixture carries "
                    f"{manufactured}"
                )

        assert not failures, "\n".join(failures)


# ---------------------------------------------------------------------------
# The boundary: compile and check, never mint or enforce
# ---------------------------------------------------------------------------


class TestModuleMintsNothing:
    """`.claude/rules/ecosystem-boundary.md` applied to organizational authority.

    Reads as pedantic until it isn't: the quiet failure mode is a helper named
    ``issue_grant`` appearing six months from now and being used as though the
    envelope it returns were authorization.
    """

    MINTING_VERBS = (
        "mint",
        "issue",
        "sign",
        "authorize",
        "authorise",
        "grant_",
        "receipt",
        "token",
        "certify",
        "admit",
        "actuate",
        "execute",
    )

    def test_module_mints_nothing(self):
        """Six ways the minting boundary could be crossed, all named on failure.

        Collapsed from six sibling tests, each of which redrew the single
        property "``fde.py`` compiles and checks authority, it never produces
        it". Every check still executes; the report lists all offenders.

        * MINTING_VERB -- scoped to functions. Dataclasses are the modelled
          vocabulary (``AuthorizedOperation``, ``SunsetAuthorization`` name
          customer acts this module *reads*); what must not exist is a verb
          you could call to obtain authority.
        * VERDICT_SHAPE -- the verdict carries no bearer value.
        * NOT_A_TRUTH_VALUE -- ``if permission:`` would swallow a refusal.
        * VALIDATE_CONFERS_NOTHING -- ``validate_authority`` returns its input.
        * RETURNS_A_GRANT -- no public callable is annotated as producing one.
        * AUTHORABLE_HERE -- this repo authors recommendations only.
        """
        failures: list[str] = []

        minting = [
            name
            for name, obj in vars(fde).items()
            if not name.startswith("_")
            and inspect.isfunction(obj)
            and obj.__module__ == fde.__name__
            and any(verb in name.lower() for verb in self.MINTING_VERBS)
        ]
        if minting:
            failures.append(
                f"MINTING_VERB: fde.py exposes minting-shaped callables {minting}; "
                "this module may compile, structure and check an authority "
                "envelope, never mint or enforce one"
            )

        for name, obj in vars(fde).items():
            if name.startswith("_") or not inspect.isfunction(obj):
                continue
            if obj.__module__ != fde.__name__:
                continue
            annotation = inspect.signature(obj).return_annotation
            if "AuthorityGrant" in str(annotation):
                failures.append(
                    f"RETURNS_A_GRANT: {name} is annotated to return "
                    f"{annotation}; grants are read and checked here, never "
                    "produced"
                )

        model = fixture("customer-authority.ttl")
        verdict = permits(model, model.the_grant(), proposal())
        fields = set(vars(verdict))
        if fields != {"allowed", "reason", "detail", "advisory"}:
            failures.append(f"VERDICT_SHAPE: unexpected verdict fields {fields}")
        for forbidden in ("token", "signature", "receipt", "capability", "grant"):
            if hasattr(verdict, forbidden):
                failures.append(f"VERDICT_SHAPE: verdict exposes {forbidden!r}")
        if verdict.advisory is not True:
            failures.append("VERDICT_SHAPE: verdict is not marked advisory")

        try:
            bool(verdict)
        except TypeError:
            pass
        else:
            failures.append(
                "NOT_A_TRUTH_VALUE: bool(verdict) succeeded; `if permission:` "
                "would swallow a refusal silently"
            )

        if validate_authority(model) is not model:
            failures.append(
                "VALIDATE_CONFERS_NOTHING: validate_authority did not return "
                "its input unchanged"
            )

        if fde.AUTHORABLE_HERE != (fde.KIND_FDE_RECOMMENDATION,):
            failures.append(
                f"AUTHORABLE_HERE: {fde.AUTHORABLE_HERE!r} is not exactly "
                "(KIND_FDE_RECOMMENDATION,)"
            )
        for kind in (fde.KIND_CUSTOMER_AUTHORITY_GRANT, fde.KIND_BROKER_AUTHORIZATION):
            if kind in fde.AUTHORABLE_HERE:
                failures.append(f"AUTHORABLE_HERE: this repo claims to author {kind}")

        assert not failures, "\n".join(failures)


class TestActKindsAreNonInterchangeable:
    def test_seven_kinds_stay_seven_and_may_not_collapse(self):
        """Cardinality and the typed collapse refusal, both named on failure."""
        failures: list[str] = []
        if len(fde.ACT_KINDS) != 7 or len(set(fde.ACT_KINDS)) != 7:
            failures.append(
                f"KIND_CARDINALITY: expected 7 distinct act kinds, got "
                f"{len(fde.ACT_KINDS)} ({len(set(fde.ACT_KINDS))} distinct)"
            )
        code = validation_code("neg-15-act-kind-collapse.ttl")
        if code != fde.REFUSED_ACT_KIND_COLLAPSE:
            failures.append(
                f"ACT_KIND_COLLAPSE: a node carrying two act kinds refused with "
                f"{code}, expected {fde.REFUSED_ACT_KIND_COLLAPSE}"
            )
        assert not failures, "\n".join(failures)


# ---------------------------------------------------------------------------
# The 14 falsifiers
# ---------------------------------------------------------------------------


def _check(failures: list[str], label: str, actual, expected) -> None:
    if actual != expected:
        failures.append(f"{label}: got {actual!r}, expected {expected!r}")


RECURSIVE_CONTROLLER = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "autofde_lab"
    / "fabric"
    / "recursive_controller.py"
)


class TestFalsifier01ModelUsedWithoutCustomerValidation:
    """A compiled customer model is a hypothesis until the customer says so."""

    def test_refused(self):
        failures: list[str] = []
        _check(
            failures,
            "VALIDATE",
            validation_code("neg-01-model-not-validated.ttl"),
            fde.REFUSED_UNVALIDATED_MODEL,
        )
        _check(
            failures,
            "PERMITS_PROPAGATES_SAME_CODE",
            refusal_code("neg-01-model-not-validated.ttl"),
            fde.REFUSED_UNVALIDATED_MODEL,
        )
        assert not failures, "\n".join(failures)


class TestFalsifier02FdeClaimsCustomerAuthority:
    """The FDE may not be the source of the authority it operates under."""

    def test_refused(self):
        failures: list[str] = []
        _check(
            failures,
            "VALIDATE",
            validation_code("neg-02-fde-claims-customer-authority.ttl"),
            fde.REFUSED_FDE_SELF_AUTHORITY,
        )
        # The refusal must be about who granted, not about a malformed file.
        model = fixture("neg-02-fde-claims-customer-authority.ttl")
        grant = model.the_grant()
        _check(failures, "FIXTURE_GRANTOR", grant.granted_by, FDE_PARTY)
        _check(failures, "FIXTURE_GRANTOR_IS_FDE", model.parties[grant.granted_by].is_fde, True)
        assert not failures, "\n".join(failures)


class TestFalsifier03CapabilityMismatch:
    """Granted capability A; the operation is capability B."""

    def test_refused(self):
        failures: list[str] = []
        _check(
            failures,
            "CAPABILITY_NOT_GRANTED",
            refusal_code(
                "neg-03-capability-not-granted.ttl",
                capability=CAP_PAYROLL,
                operation=OP_PAYROLL,
            ),
            fde.REFUSED_CAPABILITY_NOT_GRANTED,
        )
        # The refusal must be specific to the ungranted capability, not a
        # blanket refusal of the artifact.
        model = fixture("neg-03-capability-not-granted.ttl")
        verdict = permits(model, model.the_grant(), proposal())
        if not verdict.allowed:
            failures.append(
                f"NOT_A_BLANKET_REFUSAL: the granted capability was also "
                f"refused ({verdict.reason}: {verdict.detail})"
            )
        assert not failures, "\n".join(failures)


class TestFalsifier04ModelChangedAfterApproval:
    """Editing the admitted model after approval, without re-admission."""

    def test_refused(self):
        failures: list[str] = []
        _check(
            failures,
            "VALIDATE",
            validation_code("neg-04-model-changed-after-approval.ttl"),
            fde.REFUSED_MODEL_DIGEST_DRIFT,
        )
        # Drift is detectable only because validation pins bytes.
        model = fixture("neg-04-model-changed-after-approval.ttl")
        compiled = next(iter(model.models.values()))
        validation = model.validations[compiled.validation]
        if compiled.model_digest == validation.validated_model_digest:
            failures.append(
                "DIGEST_PINNED: fixture digests are equal, so the refusal "
                "above cannot have come from drift detection"
            )
        assert not failures, "\n".join(failures)


class TestFalsifier05VerifiedButNobodyAccepted:
    """Technical verification succeeded; no adoption owner accepted."""

    def test_refused(self):
        failures: list[str] = []
        _check(
            failures,
            "VALIDATE",
            validation_code("neg-05-verified-but-no-adoption-owner.ttl"),
            fde.REFUSED_MISSING_ADOPTION_OWNER,
        )
        # Otherwise the test would be passing for the wrong reason.
        model = fixture("neg-05-verified-but-no-adoption-owner.ttl")
        if not model.verdicts:
            failures.append(
                "TECHNICAL_CHAIN_CLOSED: fixture must contain a successful "
                "verifier verdict"
            )
        _check(failures, "NO_ADOPTION_OWNER", model.the_grant().adoption_owner, None)
        assert not failures, "\n".join(failures)


class TestFalsifier06FdeVerifiesItsOwnArtifact:
    """Self-certification: the producer's own check is not evidence."""

    def test_refused(self):
        failures: list[str] = []
        _check(
            failures,
            "VALIDATE",
            validation_code("neg-06-fde-verifies-own-artifact.ttl"),
            fde.REFUSED_SELF_CERTIFICATION,
        )
        model = fixture("neg-06-fde-verifies-own-artifact.ttl")
        verifier = model.verifiers[FDE_NS + "verifier/fde-inhouse"]
        consequence = next(iter(model.consequences.values()))
        if consequence.produced_by in verifier.independent_of:
            failures.append(
                "NOT_INDEPENDENT: fixture verifier is declared independent of "
                "the producer, so the refusal cannot be about self-certification"
            )
        assert not failures, "\n".join(failures)


class TestFalsifier07AcceptedWithoutIndependentEvidence:
    """Acceptance resting on nothing is assent, not acceptance."""

    def test_refused(self):
        failures: list[str] = []
        _check(
            failures,
            "VALIDATE",
            validation_code("neg-07-accepted-without-independent-evidence.ttl"),
            fde.REFUSED_MISSING_INDEPENDENT_EVIDENCE,
        )
        model = fixture("neg-07-accepted-without-independent-evidence.ttl")
        adoption = next(iter(model.adoptions.values()))
        _check(failures, "FIXTURE_DECISION", adoption.adoption_decision, "ADOPTED")
        _check(failures, "FIXTURE_EVIDENCE", adoption.on_evidence, ())
        assert not failures, "\n".join(failures)


class TestFalsifier08GrantReusedForAnotherCustomerOrEnvironment:
    """One class, three axes of reuse -- each still refuses with its own code."""

    def test_refused(self):
        failures: list[str] = []
        _check(
            failures,
            "OTHER_CUSTOMER",
            refusal_code("neg-08-grant-reused-other-customer.ttl"),
            fde.REFUSED_WRONG_CUSTOMER,
        )
        _check(
            failures,
            "OTHER_ENVIRONMENT",
            refusal_code("customer-authority.ttl", environment_scope=ES_PRODUCTION),
            fde.REFUSED_OUT_OF_ENVIRONMENT_SCOPE,
        )
        _check(
            failures,
            "OTHER_RESOURCE",
            refusal_code("customer-authority.ttl", resource_scope=RS_SOUTH),
            fde.REFUSED_OUT_OF_RESOURCE_SCOPE,
        )
        # Reuse means the same grant pointed elsewhere, not a new grant.
        original = fixture("customer-authority.ttl").the_grant()
        reused = fixture("neg-08-grant-reused-other-customer.ttl").the_grant()
        _check(
            failures,
            "SAME_GRANT_IDENTIFIER",
            reused.grant_identifier,
            original.grant_identifier,
        )
        _check(failures, "REUSE_TARGET", reused.for_customer, CUSTOMER_EMEA)
        assert not failures, "\n".join(failures)


class TestFalsifier09ExpiredOrOverBounds:
    """One class, four axes -- expiry plus the three consequence bounds."""

    def test_refused(self):
        failures: list[str] = []
        _check(
            failures,
            "EXPIRED",
            refusal_code("neg-09-expired-and-over-bounds.ttl"),
            fde.REFUSED_GRANT_EXPIRED,
        )
        _check(
            failures,
            "BOUNDS_IRREVERSIBLE",
            refusal_code(
                "neg-09-expired-and-over-bounds.ttl",
                at=IN_PAST_WINDOW,
                irreversible_actions=1,
            ),
            fde.REFUSED_CONSEQUENCE_BOUNDS_EXCEEDED,
        )
        _check(
            failures,
            "BOUNDS_RESOURCE_COUNT",
            refusal_code(
                "neg-09-expired-and-over-bounds.ttl",
                at=IN_PAST_WINDOW,
                affected_resources=3,
            ),
            fde.REFUSED_CONSEQUENCE_BOUNDS_EXCEEDED,
        )
        _check(
            failures,
            "BOUNDS_DURATION",
            refusal_code(
                "neg-09-expired-and-over-bounds.ttl",
                at=IN_PAST_WINDOW,
                affected_resources=1,
                duration_seconds=61,
            ),
            fde.REFUSED_CONSEQUENCE_BOUNDS_EXCEEDED,
        )
        assert not failures, "\n".join(failures)


class TestFalsifier10RetirementFlagWithoutAuthority:
    """`customer_authorized_retirement = true` with nobody behind it.

    This is the exact shape `.claude/rules/fde-authority-boundary.md` names:
    ``~/ggen-legacy/appliance/bin/decision-engine.py``'s last conjunct is a
    bare boolean in a manifest, and a true value there is unattributable
    unless it resolves to a record naming the authority and the decision
    right. The fixture writes the bare flag; the checker refuses it.
    """

    def test_refused(self):
        failures: list[str] = []
        _check(
            failures,
            "VALIDATE",
            validation_code("neg-10-retirement-without-authority.ttl"),
            fde.REFUSED_MISSING_SUNSET_AUTHORITY,
        )
        model = fixture("neg-10-retirement-without-authority.ttl")
        sunset = next(iter(model.sunsets.values()))
        _check(failures, "FLAG_IS_SET", sunset.customer_authorized_retirement, True)
        _check(failures, "NO_AUTHORITY_BEHIND_FLAG", sunset.authorized_by, None)
        assert not failures, "\n".join(failures)


class TestFalsifier11ResumedBeforeOrganizationalAdmission:
    """Parent resumes from technical completion, skipping adoption."""

    def test_artifact_level_refusal(self):
        assert validation_code(
            "neg-11-resumed-before-organizational-admission.ttl"
        ) == fde.REFUSED_RESUMED_BEFORE_ORGANIZATIONAL_ADMISSION

    def test_live_recursive_resume_cannot_be_exercised_yet(self):
        """BLOCKED: no component runs the blocked-parent resume loop.

        The artifact-level property above is checked. The *dynamic* property
        -- that a running parent workflow does not resume until an adoption
        decision exists -- needs a recursive bootstrap controller, which
        ``test_chatman_chain_chicago.py::
        test_recursive_bootstrap_controller_is_absent_across_ecosystem``
        asserts is absent across the whole portfolio. Skipping rather than
        faking: there is no loop to observe.
        """
        if not RECURSIVE_CONTROLLER.exists():
            pytest.skip(
                "BLOCKED:RECURSIVE_CONTROLLER_ABSENT: no component in the "
                "portfolio implements blocked -> child -> admit -> resume; "
                "only the artifact-level invariant is exercised"
            )
        pytest.fail(
            "a recursive controller now exists -- exercise the live resume "
            "ordering here instead of skipping"
        )


class TestFalsifier12AdoptedWithoutOwnershipObligations:
    def test_refused(self):
        failures: list[str] = []
        _check(
            failures,
            "VALIDATE",
            validation_code("neg-12-adopted-without-operating-obligations.ttl"),
            fde.REFUSED_MISSING_OPERATING_OBLIGATION,
        )
        # Two distinct places the obligation can go missing; both refuse.
        model = fixture("customer-authority.ttl")
        model.adoptions[FDE_NS + "adoption/x"] = fde.AdoptionDecision(
            iri=FDE_NS + "adoption/x",
            decided_by=FDE_NS + "owner/director-operations",
            on_evidence=(),
            adoption_decision="ADOPTED",
        )
        with pytest.raises(AuthorityError) as caught:
            validate_authority(model)
        _check(
            failures,
            "INJECTED_ADOPTION",
            caught.value.code,
            fde.REFUSED_MISSING_INDEPENDENT_EVIDENCE,
        )
        assert not failures, "\n".join(failures)


class TestFalsifier13InformalEscalationInsteadOfChildWorkflow:
    def test_artifact_level_refusal(self):
        assert validation_code("neg-13-informal-escalation.ttl") == (
            fde.REFUSED_INFORMAL_ESCALATION_NOT_A_CHILD_WORKFLOW
        )

    def test_live_child_workflow_spawn_cannot_be_exercised_yet(self):
        """BLOCKED: nothing spawns a child workflow for a blocker.

        The artifact-level property -- a blocker whose ``resolutionMode`` is
        not ``CHILD_WORKFLOW`` is refused -- is checked above. Observing that a
        *recursive organizational* blocker actually causes a child workflow to
        be manufactured and admitted requires the same absent controller, plus
        an organizational-blocker driver that no component implements.
        """
        if not RECURSIVE_CONTROLLER.exists():
            pytest.skip(
                "BLOCKED:CHILD_WORKFLOW_SPAWNER_ABSENT: no component spawns a "
                "child workflow from an organizational blocker; only the "
                "artifact-level invariant is exercised"
            )
        pytest.fail(
            "a controller now exists -- exercise the live spawn here instead"
        )


class TestFalsifier14SunsetAgainstAnUnadoptedReplacement:
    def test_refused(self):
        failures: list[str] = []
        _check(
            failures,
            "VALIDATE",
            validation_code("neg-14-sunset-replacement-not-adopted.ttl"),
            fde.REFUSED_REPLACEMENT_NOT_ORGANIZATIONALLY_ADMITTED,
        )
        # The point: technical completion is present, adoption is not.
        model = fixture("neg-14-sunset-replacement-not-adopted.ttl")
        adoption = model.adoptions[FDE_NS + "adoption/replacement"]
        _check(
            failures,
            "FIXTURE_TECHNICALLY_COMPLETE",
            adoption.adoption_decision,
            "TECHNICALLY_COMPLETE",
        )
        if not adoption.on_evidence:
            failures.append(
                "FIXTURE_HAS_VERIFIER_VERDICT: no evidence in the fixture, so "
                "the refusal is not about the adoption gap"
            )
        assert not failures, "\n".join(failures)


# ---------------------------------------------------------------------------
# Remaining typed refusals from the required floor
# ---------------------------------------------------------------------------


class TestRemainingTypedRefusals:
    def test_each_remaining_refusal_carries_its_own_code(self):
        """Three distinct typed refusals, each named on failure."""
        failures: list[str] = []
        _check(
            failures,
            "DELEGATION_NOT_ALLOWED",
            refusal_code("customer-authority.ttl", delegated=True),
            fde.REFUSED_DELEGATION_NOT_ALLOWED,
        )
        _check(
            failures,
            "EXECUTABLE_DIGEST_MISMATCH",
            refusal_code(
                "customer-authority.ttl", executable_digest="blake3:" + "00" * 32
            ),
            fde.REFUSED_EXECUTABLE_DIGEST_MISMATCH,
        )
        # An operation requiring a right the grant does not convey.
        model = fixture("customer-authority.ttl")
        grant = model.the_grant()
        model.operations[OP_REBALANCE] = fde.AuthorizedOperation(
            iri=OP_REBALANCE,
            identifier="OP-REBALANCE-NORTH",
            under_capability=CAP_REBALANCE,
            on_resource=RS_NORTH,
            in_environment=ES_STAGING,
            requires_decision_right=(FDE_NS + "right/retire-legacy",),
        )
        _check(
            failures,
            "MISSING_DECISION_RIGHT",
            permits(model, grant, proposal()).reason,
            fde.REFUSED_MISSING_DECISION_RIGHT,
        )
        assert not failures, "\n".join(failures)

    def test_the_refusal_vocabulary_is_closed(self):
        """The typed floor is declared, untyped reasons and bad bytes refuse."""
        failures: list[str] = []
        required = {
            "WRONG_CUSTOMER",
            "MISSING_DECISION_RIGHT",
            "OUT_OF_RESOURCE_SCOPE",
            "OUT_OF_ENVIRONMENT_SCOPE",
            "GRANT_EXPIRED",
            "EXECUTABLE_DIGEST_MISMATCH",
            "CONSEQUENCE_BOUNDS_EXCEEDED",
            "CAPABILITY_NOT_GRANTED",
            "DELEGATION_NOT_ALLOWED",
            "SELF_CERTIFICATION",
            "UNVALIDATED_MODEL",
            "MISSING_ADOPTION_OWNER",
            "MISSING_SUNSET_AUTHORITY",
        }
        undeclared = sorted(required - set(fde.REFUSAL_REASONS))
        if undeclared:
            failures.append(f"REQUIRED_FLOOR: undeclared refusal reasons {undeclared}")

        try:
            fde.refuse("BECAUSE_I_SAID_SO", "no")
        except ValueError:
            pass
        else:
            failures.append(
                "UNTYPED_REASON_ACCEPTED: fde.refuse admitted an undeclared reason"
            )

        try:
            fde.parse_authority_turtle("<urn:x> a fdet:AuthorityGrant ;")
        except AuthorityError as error:
            _check(
                failures, "MALFORMED_ARTIFACT", error.code, fde.REFUSED_MALFORMED_ARTIFACT
            )
        else:
            failures.append(
                "MALFORMED_ARTIFACT: malformed turtle was ignored, not refused"
            )

        assert not failures, "\n".join(failures)
