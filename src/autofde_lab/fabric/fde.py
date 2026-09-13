# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Forward-Deployed Architect (FDE) authority envelopes -- compile, check, advise.

The Chatman ecosystem closes a *technical* chain: blocked state -> planning ->
POWL -> brokered consequence -> manufacture -> verification -> receipts ->
replay -> standing. An enterprise transition needs a second chain layered on
it -- customer reality -> admitted customer model -> bounded organizational
authority -> technical consequence -> accountable acceptance -> adopted
organizational capability -- and the FDE owns the bridge between them.

What this module is allowed to do
---------------------------------
**COMPILE, STRUCTURE, and CHECK an authority envelope. Never MINT or ENFORCE
one.** Computing "would this grant permit this operation?" is a candidate /
advisory computation, which is exactly this repository's role
(`.claude/rules/ecosystem-boundary.md`: *a planner selects; the broker
authorizes; the executor performs; the verifier evaluates*). Actually
authorizing is `~/mfw`'s broker.

Concretely, and asserted by
``tests/ecosystem/test_fde_authority_chicago.py``:

* no function here returns a grant, a token, a capability handle, a
  signature, or a receipt;
* :class:`Permission` is an **advisory verdict object**. It carries
  ``advisory = True`` structurally, has no bearer value, and cannot be
  presented to anything as authorization;
* the seven act kinds below are modelled as *non-interchangeable* types, so a
  document cannot drift from one into another. In particular an
  ``fdet:FdeRecommendation`` -- the only kind this repository may author --
  is never an ``fdet:CustomerAuthorityGrant`` and never an
  ``fdet:BrokerAuthorization``.

Four things the FDE itself must never do, encoded as refusals rather than
prose: invent customer authority (:data:`REFUSED_FDE_SELF_AUTHORITY`),
self-admit its own compiled model (:data:`REFUSED_UNVALIDATED_MODEL`),
self-certify an artifact it caused to be manufactured
(:data:`REFUSED_SELF_CERTIFICATION`), and authorize sunset
(:data:`REFUSED_MISSING_SUNSET_AUTHORITY`).

Parsing
-------
Turtle is decoded with the subset tokenizer already committed in
:mod:`autofde_lab.fabric.powl` (``_parse_graph``). ``rdflib`` is deliberately not
introduced: it is not a dependency of this package, and the same
"a decoder that skips what it does not understand cannot be used to validate"
argument that governs the POWL decoder governs this one. Anything outside the
accepted subset is refused with a named reason.

A boolean ``approved = true`` appears nowhere in this vocabulary. Every
decision names its decider, the decision right it was taken under, and the
evidence it rests on.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from autofde_lab.fabric.powl import RDF_TYPE, PowlDecodeError, _parse_graph

FDE = "urn:skdecide:fde:"
FDET = "urn:skdecide:fde-term:"
XSD = "http://www.w3.org/2001/XMLSchema#"

# ---------------------------------------------------------------------------
# The seven non-interchangeable act kinds.
# ---------------------------------------------------------------------------
#
# These are the whole point of the vocabulary. Collapsing any two of them is
# how an enterprise transition quietly becomes self-attesting: an FDE
# recommendation read as a customer grant, a technical consequence read as an
# adoption decision, a verifier verdict read as acceptance.

KIND_FDE_RECOMMENDATION = FDET + "FdeRecommendation"
KIND_CUSTOMER_AUTHORITY_GRANT = FDET + "CustomerAuthorityGrant"
KIND_BROKER_AUTHORIZATION = FDET + "BrokerAuthorization"
KIND_TECHNICAL_CONSEQUENCE = FDET + "TechnicalConsequence"
KIND_VERIFIER_VERDICT = FDET + "VerifierVerdict"
KIND_ADOPTION_DECISION = FDET + "AdoptionDecision"
KIND_SUNSET_AUTHORIZATION = FDET + "SunsetAuthorization"

ACT_KINDS: Tuple[str, ...] = (
    KIND_FDE_RECOMMENDATION,
    KIND_CUSTOMER_AUTHORITY_GRANT,
    KIND_BROKER_AUTHORIZATION,
    KIND_TECHNICAL_CONSEQUENCE,
    KIND_VERIFIER_VERDICT,
    KIND_ADOPTION_DECISION,
    KIND_SUNSET_AUTHORIZATION,
)

#: The only act kind this repository may itself author. Everything else is
#: read, structured, and checked -- never produced.
AUTHORABLE_HERE: Tuple[str, ...] = (KIND_FDE_RECOMMENDATION,)


# ---------------------------------------------------------------------------
# Typed refusal reasons.
# ---------------------------------------------------------------------------

REFUSED_WRONG_CUSTOMER = "WRONG_CUSTOMER"
REFUSED_MISSING_DECISION_RIGHT = "MISSING_DECISION_RIGHT"
REFUSED_OUT_OF_RESOURCE_SCOPE = "OUT_OF_RESOURCE_SCOPE"
REFUSED_OUT_OF_ENVIRONMENT_SCOPE = "OUT_OF_ENVIRONMENT_SCOPE"
REFUSED_GRANT_EXPIRED = "GRANT_EXPIRED"
REFUSED_EXECUTABLE_DIGEST_MISMATCH = "EXECUTABLE_DIGEST_MISMATCH"
REFUSED_CONSEQUENCE_BOUNDS_EXCEEDED = "CONSEQUENCE_BOUNDS_EXCEEDED"
REFUSED_CAPABILITY_NOT_GRANTED = "CAPABILITY_NOT_GRANTED"
REFUSED_DELEGATION_NOT_ALLOWED = "DELEGATION_NOT_ALLOWED"
REFUSED_SELF_CERTIFICATION = "SELF_CERTIFICATION"
REFUSED_UNVALIDATED_MODEL = "UNVALIDATED_MODEL"
REFUSED_MISSING_ADOPTION_OWNER = "MISSING_ADOPTION_OWNER"
REFUSED_MISSING_SUNSET_AUTHORITY = "MISSING_SUNSET_AUTHORITY"

# Additional codes beyond the required floor, each for a distinct FDE
# falsifier that would otherwise be forced into a code that misnames it.
REFUSED_FDE_SELF_AUTHORITY = "FDE_SELF_AUTHORITY"
REFUSED_MODEL_DIGEST_DRIFT = "MODEL_DIGEST_DRIFT"
REFUSED_MISSING_INDEPENDENT_EVIDENCE = "MISSING_INDEPENDENT_EVIDENCE"
REFUSED_MISSING_OPERATING_OBLIGATION = "MISSING_OPERATING_OBLIGATION"
REFUSED_RESUMED_BEFORE_ORGANIZATIONAL_ADMISSION = (
    "RESUMED_BEFORE_ORGANIZATIONAL_ADMISSION"
)
REFUSED_INFORMAL_ESCALATION_NOT_A_CHILD_WORKFLOW = (
    "INFORMAL_ESCALATION_NOT_A_CHILD_WORKFLOW"
)
REFUSED_REPLACEMENT_NOT_ORGANIZATIONALLY_ADMITTED = (
    "REPLACEMENT_NOT_ORGANIZATIONALLY_ADMITTED"
)
REFUSED_ACT_KIND_COLLAPSE = "ACT_KIND_COLLAPSE"
REFUSED_MALFORMED_ARTIFACT = "MALFORMED_ARTIFACT"

REFUSAL_REASONS: Tuple[str, ...] = (
    REFUSED_WRONG_CUSTOMER,
    REFUSED_MISSING_DECISION_RIGHT,
    REFUSED_OUT_OF_RESOURCE_SCOPE,
    REFUSED_OUT_OF_ENVIRONMENT_SCOPE,
    REFUSED_GRANT_EXPIRED,
    REFUSED_EXECUTABLE_DIGEST_MISMATCH,
    REFUSED_CONSEQUENCE_BOUNDS_EXCEEDED,
    REFUSED_CAPABILITY_NOT_GRANTED,
    REFUSED_DELEGATION_NOT_ALLOWED,
    REFUSED_SELF_CERTIFICATION,
    REFUSED_UNVALIDATED_MODEL,
    REFUSED_MISSING_ADOPTION_OWNER,
    REFUSED_MISSING_SUNSET_AUTHORITY,
    REFUSED_FDE_SELF_AUTHORITY,
    REFUSED_MODEL_DIGEST_DRIFT,
    REFUSED_MISSING_INDEPENDENT_EVIDENCE,
    REFUSED_MISSING_OPERATING_OBLIGATION,
    REFUSED_RESUMED_BEFORE_ORGANIZATIONAL_ADMISSION,
    REFUSED_INFORMAL_ESCALATION_NOT_A_CHILD_WORKFLOW,
    REFUSED_REPLACEMENT_NOT_ORGANIZATIONALLY_ADMITTED,
    REFUSED_ACT_KIND_COLLAPSE,
    REFUSED_MALFORMED_ARTIFACT,
)


class AuthorityError(ValueError):
    """A structural defect in an authority artifact, with a typed code.

    Carries ``.code`` (one of :data:`REFUSAL_REASONS`) so callers assert on
    the code, never on message text.
    """

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"REFUSED:{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class Permission:
    """An **advisory** verdict. Not authorization, and not convertible to it.

    There is deliberately no bearer value on this object -- no token, no
    signature, no expiry-bearing handle. It answers "would this grant permit
    this operation?" and nothing else; the broker in ``~/mfw`` answers "may
    this happen", which is a different question asked of a different system.
    """

    allowed: bool
    reason: Optional[str] = None
    detail: str = ""
    advisory: bool = True

    @property
    def verdict(self) -> str:
        return "ALLOW" if self.allowed else f"REFUSED:{self.reason}"

    def __bool__(self) -> bool:  # pragma: no cover - clarity guard
        raise TypeError(
            "Permission is advisory and must not be used as a truth value; "
            "read .allowed and .reason explicitly so a refusal cannot be "
            "silently swallowed by an `if permission:`"
        )


def allow(detail: str = "") -> Permission:
    return Permission(allowed=True, reason=None, detail=detail)


def refuse(reason: str, detail: str) -> Permission:
    if reason not in REFUSAL_REASONS:
        raise ValueError(f"untyped refusal reason {reason!r}")
    return Permission(allowed=False, reason=reason, detail=detail)


# ---------------------------------------------------------------------------
# Entities
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CustomerOrganization:
    iri: str
    identifier: str


@dataclass(frozen=True)
class Party:
    """An FDE identity or a customer authority identity. Never both."""

    iri: str
    identifier: str
    is_fde: bool
    role: Optional[str] = None
    acts_for: Optional[str] = None
    holds_decision_right: Tuple[str, ...] = ()


@dataclass(frozen=True)
class DecisionRight:
    iri: str
    identifier: str


@dataclass(frozen=True)
class AuthorizedCapability:
    iri: str
    identifier: str


@dataclass(frozen=True)
class Scope:
    """A resource scope or an environment scope."""

    iri: str
    identifier: str


@dataclass(frozen=True)
class AuthorizedOperation:
    iri: str
    identifier: str
    under_capability: str
    on_resource: str
    in_environment: str
    requires_decision_right: Tuple[str, ...] = ()


@dataclass(frozen=True)
class ValidityInterval:
    iri: str
    not_before: datetime
    not_after: datetime


@dataclass(frozen=True)
class ConsequenceBounds:
    iri: str
    max_affected_resources: int
    max_irreversible_actions: int
    max_duration_seconds: int


@dataclass(frozen=True)
class Verifier:
    iri: str
    identifier: str
    independent_of: Tuple[str, ...] = ()


@dataclass(frozen=True)
class Postcondition:
    iri: str
    identifier: str
    expression: str


@dataclass(frozen=True)
class AdoptionOwner:
    iri: str
    identifier: str
    role: Optional[str] = None
    operating_obligation: Tuple[str, ...] = ()


@dataclass(frozen=True)
class SunsetAuthority:
    iri: str
    identifier: str
    under_decision_right: Tuple[str, ...] = ()


@dataclass(frozen=True)
class ModelValidation:
    iri: str
    validated_by: str
    validation_decision: str
    validated_model_digest: str


@dataclass(frozen=True)
class CompiledCustomerModel:
    """The customer model the FDE compiled, as a falsifiable hypothesis."""

    iri: str
    identifier: str
    model_digest: str
    compiled_by: Optional[str] = None
    validation: Optional[str] = None


@dataclass(frozen=True)
class VerifierVerdict:
    iri: str
    verdict_by: str
    about_artifact: str
    verdict_decision: str


@dataclass(frozen=True)
class AdoptionDecision:
    iri: str
    decided_by: str
    on_evidence: Tuple[str, ...] = ()
    adoption_decision: str = ""
    ownership_assigned_to: Optional[str] = None
    operating_obligation: Tuple[str, ...] = ()


@dataclass(frozen=True)
class TechnicalConsequence:
    iri: str
    produced_by: Optional[str] = None
    consequence_digest: Optional[str] = None
    organizationally_admitted_by: Optional[str] = None
    parent_resumed: bool = False


@dataclass(frozen=True)
class SunsetAuthorization:
    iri: str
    authorized_by: Optional[str] = None
    under_decision_right: Tuple[str, ...] = ()
    replacement_adoption: Optional[str] = None
    customer_authorized_retirement: bool = False


@dataclass(frozen=True)
class OrganizationalBlocker:
    """A blocker in the enterprise chain and how it was discharged."""

    iri: str
    identifier: str
    resolution_mode: str
    child_workflow: Optional[str] = None


@dataclass(frozen=True)
class AuthorityGrant:
    iri: str
    grant_identifier: str
    granted_by: str
    granted_to: str
    for_customer: str
    based_on_model: str
    conveys_decision_right: Tuple[str, ...]
    authorizes_capability: Tuple[str, ...]
    authorizes_operation: Tuple[str, ...]
    resource_scope: Tuple[str, ...]
    environment_scope: Tuple[str, ...]
    validity: str
    consequence_bounds: str
    requires_verifier: Tuple[str, ...]
    requires_postcondition: Tuple[str, ...]
    adoption_owner: Optional[str]
    sunset_authority: Optional[str]
    delegation_allowed: bool
    executable_digest: Optional[str]


@dataclass(frozen=True)
class AuthorityModel:
    """Everything decoded from one authority artifact."""

    customers: Dict[str, CustomerOrganization] = field(default_factory=dict)
    parties: Dict[str, Party] = field(default_factory=dict)
    decision_rights: Dict[str, DecisionRight] = field(default_factory=dict)
    capabilities: Dict[str, AuthorizedCapability] = field(default_factory=dict)
    operations: Dict[str, AuthorizedOperation] = field(default_factory=dict)
    resource_scopes: Dict[str, Scope] = field(default_factory=dict)
    environment_scopes: Dict[str, Scope] = field(default_factory=dict)
    intervals: Dict[str, ValidityInterval] = field(default_factory=dict)
    bounds: Dict[str, ConsequenceBounds] = field(default_factory=dict)
    verifiers: Dict[str, Verifier] = field(default_factory=dict)
    postconditions: Dict[str, Postcondition] = field(default_factory=dict)
    adoption_owners: Dict[str, AdoptionOwner] = field(default_factory=dict)
    sunset_authorities: Dict[str, SunsetAuthority] = field(default_factory=dict)
    models: Dict[str, CompiledCustomerModel] = field(default_factory=dict)
    validations: Dict[str, ModelValidation] = field(default_factory=dict)
    grants: Dict[str, AuthorityGrant] = field(default_factory=dict)
    verdicts: Dict[str, VerifierVerdict] = field(default_factory=dict)
    adoptions: Dict[str, AdoptionDecision] = field(default_factory=dict)
    consequences: Dict[str, TechnicalConsequence] = field(default_factory=dict)
    sunsets: Dict[str, SunsetAuthorization] = field(default_factory=dict)
    blockers: Dict[str, OrganizationalBlocker] = field(default_factory=dict)
    kinds: Dict[str, Tuple[str, ...]] = field(default_factory=dict)

    def the_grant(self) -> AuthorityGrant:
        if len(self.grants) != 1:
            raise AuthorityError(
                REFUSED_MALFORMED_ARTIFACT,
                f"expected exactly 1 fdet:AuthorityGrant, found {len(self.grants)}",
            )
        return next(iter(self.grants.values()))


@dataclass(frozen=True)
class ProposedOperation:
    """An operation the FDE proposes. A recommendation, never an act."""

    customer: str
    capability: str
    operation: str
    resource_scope: str
    environment_scope: str
    at: datetime
    executable_digest: Optional[str] = None
    affected_resources: int = 0
    irreversible_actions: int = 0
    duration_seconds: int = 0
    delegated: bool = False
    performed_by: Optional[str] = None
    verified_by: Optional[str] = None
    manufactured_by: Optional[str] = None
    independent_evidence: Tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Decoding
# ---------------------------------------------------------------------------


def _iri_values(node, predicate: str) -> Tuple[str, ...]:
    out: List[str] = []
    for kind, value, _ in node.get(predicate, []):
        if kind != "iri":
            raise AuthorityError(
                REFUSED_MALFORMED_ARTIFACT,
                f"{predicate} expects an IRI object, got literal {value!r}",
            )
        out.append(value)
    return tuple(out)


def _one_iri(node, predicate: str, subject: str) -> str:
    values = _iri_values(node, predicate)
    if len(values) != 1:
        raise AuthorityError(
            REFUSED_MALFORMED_ARTIFACT,
            f"<{subject}> {predicate}: expected exactly 1 IRI, got {len(values)}",
        )
    return values[0]


def _opt_iri(node, predicate: str) -> Optional[str]:
    values = _iri_values(node, predicate)
    return values[0] if values else None


def _literals(node, predicate: str) -> Tuple[str, ...]:
    return tuple(
        value for kind, value, _ in node.get(predicate, []) if kind == "literal"
    )


def _one_literal(node, predicate: str, subject: str) -> str:
    values = _literals(node, predicate)
    if len(values) != 1:
        raise AuthorityError(
            REFUSED_MALFORMED_ARTIFACT,
            f"<{subject}> {predicate}: expected exactly 1 literal, got {len(values)}",
        )
    return values[0]


def _opt_literal(node, predicate: str) -> Optional[str]:
    values = _literals(node, predicate)
    return values[0] if values else None


def _one_int(node, predicate: str, subject: str) -> int:
    terms = node.get(predicate, [])
    if len(terms) != 1:
        raise AuthorityError(
            REFUSED_MALFORMED_ARTIFACT,
            f"<{subject}> {predicate}: expected exactly 1 value, got {len(terms)}",
        )
    kind, value, datatype = terms[0]
    if kind != "literal" or datatype != XSD + "integer":
        raise AuthorityError(
            REFUSED_MALFORMED_ARTIFACT,
            f"<{subject}> {predicate}: must be an xsd:integer literal",
        )
    return int(value)


def _one_bool(node, predicate: str, subject: str, default: Optional[bool] = None) -> bool:
    terms = node.get(predicate, [])
    if not terms:
        if default is None:
            raise AuthorityError(
                REFUSED_MALFORMED_ARTIFACT,
                f"<{subject}> {predicate}: missing (minCount 1)",
            )
        return default
    kind, value, datatype = terms[0]
    if kind != "literal" or datatype != XSD + "boolean":
        raise AuthorityError(
            REFUSED_MALFORMED_ARTIFACT,
            f"<{subject}> {predicate}: must be an xsd:boolean literal",
        )
    return value == "true"


def _datetime(node, predicate: str, subject: str) -> datetime:
    terms = node.get(predicate, [])
    if len(terms) != 1:
        raise AuthorityError(
            REFUSED_MALFORMED_ARTIFACT,
            f"<{subject}> {predicate}: expected exactly 1 value, got {len(terms)}",
        )
    kind, value, datatype = terms[0]
    if kind != "literal" or datatype != XSD + "dateTime":
        raise AuthorityError(
            REFUSED_MALFORMED_ARTIFACT,
            f"<{subject}> {predicate}: must be an xsd:dateTime literal",
        )
    return parse_instant(value)


def parse_instant(text: str) -> datetime:
    """Parse an ISO-8601 instant, normalising to UTC-aware."""
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AuthorityError(
            REFUSED_MALFORMED_ARTIFACT, f"not an ISO-8601 instant: {text!r}"
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def parse_authority_turtle(text: str) -> AuthorityModel:
    """Decode an FDE authority artifact. Does **not** validate; see
    :func:`validate_authority`."""
    try:
        graph = _parse_graph(text)
    except PowlDecodeError as exc:
        raise AuthorityError(REFUSED_MALFORMED_ARTIFACT, str(exc)) from exc

    model = AuthorityModel()

    for subject, node in graph.items():
        types = tuple(value for _, value, _ in node.get(RDF_TYPE, []))
        model.kinds[subject] = types

        def has(local: str) -> bool:
            return FDET + local in types

        if has("CustomerOrganization"):
            model.customers[subject] = CustomerOrganization(
                iri=subject,
                identifier=_one_literal(node, FDET + "identifier", subject),
            )
        if has("FdeIdentity") or has("CustomerAuthorityIdentity"):
            model.parties[subject] = Party(
                iri=subject,
                identifier=_one_literal(node, FDET + "identifier", subject),
                is_fde=has("FdeIdentity"),
                role=_opt_literal(node, FDET + "organizationalRole"),
                acts_for=_opt_iri(node, FDET + "actsFor"),
                holds_decision_right=_iri_values(node, FDET + "holdsDecisionRight"),
            )
        if has("DecisionRight"):
            model.decision_rights[subject] = DecisionRight(
                iri=subject,
                identifier=_one_literal(node, FDET + "identifier", subject),
            )
        if has("AuthorizedCapability"):
            model.capabilities[subject] = AuthorizedCapability(
                iri=subject,
                identifier=_one_literal(node, FDET + "identifier", subject),
            )
        if has("AuthorizedOperation"):
            model.operations[subject] = AuthorizedOperation(
                iri=subject,
                identifier=_one_literal(node, FDET + "identifier", subject),
                under_capability=_one_iri(node, FDET + "underCapability", subject),
                on_resource=_one_iri(node, FDET + "onResource", subject),
                in_environment=_one_iri(node, FDET + "inEnvironment", subject),
                requires_decision_right=_iri_values(
                    node, FDET + "requiresDecisionRight"
                ),
            )
        if has("ResourceScope"):
            model.resource_scopes[subject] = Scope(
                iri=subject,
                identifier=_one_literal(node, FDET + "identifier", subject),
            )
        if has("EnvironmentScope"):
            model.environment_scopes[subject] = Scope(
                iri=subject,
                identifier=_one_literal(node, FDET + "identifier", subject),
            )
        if has("ValidityInterval"):
            model.intervals[subject] = ValidityInterval(
                iri=subject,
                not_before=_datetime(node, FDET + "notBefore", subject),
                not_after=_datetime(node, FDET + "notAfter", subject),
            )
        if has("ConsequenceBounds"):
            model.bounds[subject] = ConsequenceBounds(
                iri=subject,
                max_affected_resources=_one_int(
                    node, FDET + "maxAffectedResources", subject
                ),
                max_irreversible_actions=_one_int(
                    node, FDET + "maxIrreversibleActions", subject
                ),
                max_duration_seconds=_one_int(
                    node, FDET + "maxDurationSeconds", subject
                ),
            )
        if has("Verifier"):
            model.verifiers[subject] = Verifier(
                iri=subject,
                identifier=_one_literal(node, FDET + "identifier", subject),
                independent_of=_iri_values(node, FDET + "independentOf"),
            )
        if has("Postcondition"):
            model.postconditions[subject] = Postcondition(
                iri=subject,
                identifier=_one_literal(node, FDET + "identifier", subject),
                expression=_one_literal(node, FDET + "postconditionExpression", subject),
            )
        if has("AdoptionOwner"):
            model.adoption_owners[subject] = AdoptionOwner(
                iri=subject,
                identifier=_one_literal(node, FDET + "identifier", subject),
                role=_opt_literal(node, FDET + "organizationalRole"),
                operating_obligation=_literals(node, FDET + "operatingObligation"),
            )
        if has("SunsetAuthority"):
            model.sunset_authorities[subject] = SunsetAuthority(
                iri=subject,
                identifier=_one_literal(node, FDET + "identifier", subject),
                under_decision_right=_iri_values(node, FDET + "underDecisionRight"),
            )
        if has("ModelValidation"):
            model.validations[subject] = ModelValidation(
                iri=subject,
                validated_by=_one_iri(node, FDET + "validatedBy", subject),
                validation_decision=_one_literal(
                    node, FDET + "validationDecision", subject
                ),
                validated_model_digest=_one_literal(
                    node, FDET + "validatedModelDigest", subject
                ),
            )
        if has("CompiledCustomerModel"):
            model.models[subject] = CompiledCustomerModel(
                iri=subject,
                identifier=_one_literal(node, FDET + "identifier", subject),
                model_digest=_one_literal(node, FDET + "modelDigest", subject),
                compiled_by=_opt_iri(node, FDET + "compiledBy"),
                validation=_opt_iri(node, FDET + "validationState"),
            )
        if has("AuthorityGrant"):
            model.grants[subject] = AuthorityGrant(
                iri=subject,
                grant_identifier=_one_literal(node, FDET + "grantIdentifier", subject),
                granted_by=_one_iri(node, FDET + "grantedBy", subject),
                granted_to=_one_iri(node, FDET + "grantedTo", subject),
                for_customer=_one_iri(node, FDET + "forCustomer", subject),
                based_on_model=_one_iri(node, FDET + "basedOnModel", subject),
                conveys_decision_right=_iri_values(node, FDET + "conveysDecisionRight"),
                authorizes_capability=_iri_values(node, FDET + "authorizesCapability"),
                authorizes_operation=_iri_values(node, FDET + "authorizesOperation"),
                resource_scope=_iri_values(node, FDET + "resourceScope"),
                environment_scope=_iri_values(node, FDET + "environmentScope"),
                validity=_one_iri(node, FDET + "validity", subject),
                consequence_bounds=_one_iri(node, FDET + "consequenceBounds", subject),
                requires_verifier=_iri_values(node, FDET + "requiresVerifier"),
                requires_postcondition=_iri_values(node, FDET + "requiresPostcondition"),
                adoption_owner=_opt_iri(node, FDET + "adoptionOwner"),
                sunset_authority=_opt_iri(node, FDET + "sunsetAuthority"),
                delegation_allowed=_one_bool(
                    node, FDET + "delegationAllowed", subject, default=False
                ),
                executable_digest=_opt_literal(node, FDET + "executableDigest"),
            )
        if has("VerifierVerdict"):
            model.verdicts[subject] = VerifierVerdict(
                iri=subject,
                verdict_by=_one_iri(node, FDET + "verdictBy", subject),
                about_artifact=_one_iri(node, FDET + "aboutArtifact", subject),
                verdict_decision=_one_literal(node, FDET + "verdictDecision", subject),
            )
        if has("AdoptionDecision"):
            model.adoptions[subject] = AdoptionDecision(
                iri=subject,
                decided_by=_one_iri(node, FDET + "decidedBy", subject),
                on_evidence=_iri_values(node, FDET + "onEvidence"),
                adoption_decision=_one_literal(
                    node, FDET + "adoptionDecision", subject
                ),
                ownership_assigned_to=_opt_iri(node, FDET + "ownershipAssignedTo"),
                operating_obligation=_literals(node, FDET + "operatingObligation"),
            )
        if has("TechnicalConsequence"):
            model.consequences[subject] = TechnicalConsequence(
                iri=subject,
                produced_by=_opt_iri(node, FDET + "producedBy"),
                consequence_digest=_opt_literal(node, FDET + "consequenceDigest"),
                organizationally_admitted_by=_opt_iri(
                    node, FDET + "organizationallyAdmittedBy"
                ),
                parent_resumed=_one_bool(
                    node, FDET + "parentResumed", subject, default=False
                ),
            )
        if has("SunsetAuthorization"):
            model.sunsets[subject] = SunsetAuthorization(
                iri=subject,
                authorized_by=_opt_iri(node, FDET + "authorizedBy"),
                under_decision_right=_iri_values(node, FDET + "underDecisionRight"),
                replacement_adoption=_opt_iri(node, FDET + "replacementAdoption"),
                customer_authorized_retirement=_one_bool(
                    node,
                    FDET + "customerAuthorizedRetirement",
                    subject,
                    default=False,
                ),
            )
        if has("OrganizationalBlocker"):
            model.blockers[subject] = OrganizationalBlocker(
                iri=subject,
                identifier=_one_literal(node, FDET + "identifier", subject),
                resolution_mode=_one_literal(node, FDET + "resolutionMode", subject),
                child_workflow=_opt_iri(node, FDET + "resolvedByChildWorkflow"),
            )

    return model


def load_authority(path: str) -> AuthorityModel:
    with open(path, "r", encoding="utf-8") as handle:
        return parse_authority_turtle(handle.read())


# ---------------------------------------------------------------------------
# Validation -- the SHACL shapes plus the structural invariants SHACL cannot
# express.
# ---------------------------------------------------------------------------


def validate_authority(model: AuthorityModel) -> AuthorityModel:
    """Enforce ``customer-authority.shacl.ttl`` plus structural invariants.

    Raises :class:`AuthorityError` carrying a typed ``.code``. Returns the
    model unchanged on success -- returning the input, never a new authority
    object, is deliberate: this function checks, it does not confer.
    """
    _validate_act_kinds(model)

    grant = model.the_grant()

    # -- referential integrity -------------------------------------------
    for iri, table, what in (
        (grant.granted_by, model.parties, "fdet:grantedBy"),
        (grant.granted_to, model.parties, "fdet:grantedTo"),
        (grant.for_customer, model.customers, "fdet:forCustomer"),
        (grant.based_on_model, model.models, "fdet:basedOnModel"),
        (grant.validity, model.intervals, "fdet:validity"),
        (grant.consequence_bounds, model.bounds, "fdet:consequenceBounds"),
    ):
        if iri not in table:
            raise AuthorityError(
                REFUSED_MALFORMED_ARTIFACT,
                f"{what} <{iri}>: dangling reference",
            )

    for label, iris, table in (
        ("fdet:conveysDecisionRight", grant.conveys_decision_right, model.decision_rights),
        ("fdet:authorizesCapability", grant.authorizes_capability, model.capabilities),
        ("fdet:authorizesOperation", grant.authorizes_operation, model.operations),
        ("fdet:resourceScope", grant.resource_scope, model.resource_scopes),
        ("fdet:environmentScope", grant.environment_scope, model.environment_scopes),
        ("fdet:requiresVerifier", grant.requires_verifier, model.verifiers),
        ("fdet:requiresPostcondition", grant.requires_postcondition, model.postconditions),
    ):
        if not iris:
            raise AuthorityError(
                REFUSED_MALFORMED_ARTIFACT, f"{label}: minCount 1 violated"
            )
        for iri in iris:
            if iri not in table:
                raise AuthorityError(
                    REFUSED_MALFORMED_ARTIFACT, f"{label} <{iri}>: dangling reference"
                )

    # -- FDE may not be the source of customer authority (falsifier 2) ----
    granter = model.parties[grant.granted_by]
    if granter.is_fde:
        raise AuthorityError(
            REFUSED_FDE_SELF_AUTHORITY,
            f"<{grant.iri}> fdet:grantedBy <{granter.iri}> is an fdet:FdeIdentity; "
            "customer authority originates with a customer authority identity, "
            "never with the forward-deployed architect",
        )
    if granter.acts_for != grant.for_customer:
        raise AuthorityError(
            REFUSED_FDE_SELF_AUTHORITY,
            f"granting authority <{granter.iri}> acts for <{granter.acts_for}>, "
            f"not for the grant's customer <{grant.for_customer}>",
        )
    if granter.role is None:
        raise AuthorityError(
            REFUSED_FDE_SELF_AUTHORITY,
            f"granting authority <{granter.iri}> names no fdet:organizationalRole; "
            "an unnamed role cannot hold a decision right",
        )
    missing_rights = [
        right
        for right in grant.conveys_decision_right
        if right not in granter.holds_decision_right
    ]
    if missing_rights:
        raise AuthorityError(
            REFUSED_MISSING_DECISION_RIGHT,
            f"<{grant.iri}> conveys {missing_rights} which <{granter.iri}> does "
            "not hold; authority cannot be conveyed beyond what the granter has",
        )

    # -- the compiled model is a hypothesis until the customer validates --
    compiled = model.models[grant.based_on_model]
    if compiled.validation is None:
        raise AuthorityError(
            REFUSED_UNVALIDATED_MODEL,
            f"<{compiled.iri}> carries no fdet:validationState; a compiled "
            "customer model is a falsifiable hypothesis, not an admitted model",
        )
    if compiled.validation not in model.validations:
        raise AuthorityError(
            REFUSED_MALFORMED_ARTIFACT,
            f"fdet:validationState <{compiled.validation}>: dangling reference",
        )
    validation = model.validations[compiled.validation]
    validator = model.parties.get(validation.validated_by)
    if validator is None:
        raise AuthorityError(
            REFUSED_MALFORMED_ARTIFACT,
            f"fdet:validatedBy <{validation.validated_by}>: dangling reference",
        )
    if validator.is_fde:
        raise AuthorityError(
            REFUSED_UNVALIDATED_MODEL,
            f"<{compiled.iri}> was validated by the FDE <{validator.iri}>; "
            "self-admission of the compiled model is not validation",
        )
    if validation.validation_decision != "VALIDATED":
        raise AuthorityError(
            REFUSED_UNVALIDATED_MODEL,
            f"fdet:validationDecision is {validation.validation_decision!r}",
        )
    if validation.validated_model_digest != compiled.model_digest:
        raise AuthorityError(
            REFUSED_MODEL_DIGEST_DRIFT,
            f"<{compiled.iri}> fdet:modelDigest {compiled.model_digest!r} != "
            f"validated digest {validation.validated_model_digest!r}; the model "
            "changed after approval and was never re-admitted",
        )

    # -- accountable acceptance ------------------------------------------
    if grant.adoption_owner is None:
        raise AuthorityError(
            REFUSED_MISSING_ADOPTION_OWNER,
            f"<{grant.iri}> names no fdet:adoptionOwner; technical success "
            "without a named accepting owner is not adoption",
        )
    if grant.adoption_owner not in model.adoption_owners:
        raise AuthorityError(
            REFUSED_MALFORMED_ARTIFACT,
            f"fdet:adoptionOwner <{grant.adoption_owner}>: dangling reference",
        )
    owner = model.adoption_owners[grant.adoption_owner]
    if not owner.operating_obligation:
        raise AuthorityError(
            REFUSED_MISSING_OPERATING_OBLIGATION,
            f"<{owner.iri}> carries no fdet:operatingObligation; a capability "
            "adopted without operating obligations has no owner in practice",
        )

    if grant.sunset_authority is None:
        raise AuthorityError(
            REFUSED_MISSING_SUNSET_AUTHORITY,
            f"<{grant.iri}> names no fdet:sunsetAuthority",
        )
    if grant.sunset_authority not in model.sunset_authorities:
        raise AuthorityError(
            REFUSED_MALFORMED_ARTIFACT,
            f"fdet:sunsetAuthority <{grant.sunset_authority}>: dangling reference",
        )
    if not model.sunset_authorities[grant.sunset_authority].under_decision_right:
        raise AuthorityError(
            REFUSED_MISSING_SUNSET_AUTHORITY,
            f"<{grant.sunset_authority}> names no fdet:underDecisionRight",
        )

    # -- required verifiers must be independent of the FDE ----------------
    for verifier_iri in grant.requires_verifier:
        verifier = model.verifiers[verifier_iri]
        if grant.granted_to not in verifier.independent_of:
            raise AuthorityError(
                REFUSED_SELF_CERTIFICATION,
                f"<{verifier.iri}> is not declared fdet:independentOf the grantee "
                f"<{grant.granted_to}>; a verifier that is not independent of the "
                "manufacturing party certifies nothing",
            )

    _validate_adoption(model)
    _validate_consequences(model)
    _validate_sunsets(model)
    _validate_blockers(model)
    return model


def _validate_act_kinds(model: AuthorityModel) -> None:
    """No node may carry two of the seven act kinds."""
    for subject, types in model.kinds.items():
        carried = [kind for kind in ACT_KINDS if kind in types]
        if len(carried) > 1:
            raise AuthorityError(
                REFUSED_ACT_KIND_COLLAPSE,
                f"<{subject}> carries {len(carried)} act kinds "
                f"({[k.rsplit(':', 1)[-1] for k in carried]}); an FDE "
                "recommendation, a customer grant, a broker authorization, a "
                "technical consequence, a verifier verdict, an adoption "
                "decision and a sunset authorization are not interchangeable",
            )


def _validate_adoption(model: AuthorityModel) -> None:
    for adoption in model.adoptions.values():
        if adoption.decided_by not in model.adoption_owners:
            raise AuthorityError(
                REFUSED_MISSING_ADOPTION_OWNER,
                f"<{adoption.iri}> fdet:decidedBy <{adoption.decided_by}> is not "
                "an fdet:AdoptionOwner",
            )
        if adoption.adoption_decision != "ADOPTED":
            continue
        if not adoption.on_evidence:
            raise AuthorityError(
                REFUSED_MISSING_INDEPENDENT_EVIDENCE,
                f"<{adoption.iri}> is ADOPTED with no fdet:onEvidence; "
                "acceptance without independently produced evidence is assent, "
                "not acceptance",
            )
        for evidence in adoption.on_evidence:
            if evidence not in model.verdicts:
                raise AuthorityError(
                    REFUSED_MISSING_INDEPENDENT_EVIDENCE,
                    f"<{adoption.iri}> fdet:onEvidence <{evidence}> is not an "
                    "fdet:VerifierVerdict",
                )
            verdict = model.verdicts[evidence]
            verifier = model.verifiers.get(verdict.verdict_by)
            if verifier is None:
                raise AuthorityError(
                    REFUSED_MALFORMED_ARTIFACT,
                    f"fdet:verdictBy <{verdict.verdict_by}>: dangling reference",
                )
            consequence = model.consequences.get(verdict.about_artifact)
            if consequence is not None and consequence.produced_by is not None:
                if consequence.produced_by not in verifier.independent_of:
                    raise AuthorityError(
                        REFUSED_SELF_CERTIFICATION,
                        f"<{verifier.iri}> issued a verdict on <{consequence.iri}>, "
                        f"produced by <{consequence.produced_by}>, without being "
                        "declared fdet:independentOf it",
                    )
        if not (adoption.ownership_assigned_to and adoption.operating_obligation):
            raise AuthorityError(
                REFUSED_MISSING_OPERATING_OBLIGATION,
                f"<{adoption.iri}> is ADOPTED without both "
                "fdet:ownershipAssignedTo and fdet:operatingObligation",
            )


def _validate_consequences(model: AuthorityModel) -> None:
    for consequence in model.consequences.values():
        if not consequence.parent_resumed:
            continue
        admitted = consequence.organizationally_admitted_by
        if admitted is None or admitted not in model.adoptions:
            raise AuthorityError(
                REFUSED_RESUMED_BEFORE_ORGANIZATIONAL_ADMISSION,
                f"<{consequence.iri}> fdet:parentResumed true with no "
                "fdet:organizationallyAdmittedBy adoption decision; technical "
                "completion is not organizational admission",
            )
        if model.adoptions[admitted].adoption_decision != "ADOPTED":
            raise AuthorityError(
                REFUSED_RESUMED_BEFORE_ORGANIZATIONAL_ADMISSION,
                f"<{consequence.iri}> resumed on adoption <{admitted}> whose "
                "decision is not ADOPTED",
            )


def _validate_sunsets(model: AuthorityModel) -> None:
    for sunset in model.sunsets.values():
        if not sunset.customer_authorized_retirement:
            continue
        authority = model.sunset_authorities.get(sunset.authorized_by or "")
        if authority is None:
            raise AuthorityError(
                REFUSED_MISSING_SUNSET_AUTHORITY,
                f"<{sunset.iri}> asserts fdet:customerAuthorizedRetirement true "
                "with no named fdet:SunsetAuthority; the FDE does not authorize "
                "sunset",
            )
        if not (sunset.under_decision_right or authority.under_decision_right):
            raise AuthorityError(
                REFUSED_MISSING_SUNSET_AUTHORITY,
                f"<{sunset.iri}> names no fdet:underDecisionRight",
            )
        replacement = sunset.replacement_adoption
        if replacement is None or replacement not in model.adoptions:
            raise AuthorityError(
                REFUSED_REPLACEMENT_NOT_ORGANIZATIONALLY_ADMITTED,
                f"<{sunset.iri}> retires a capability without an "
                "fdet:replacementAdoption; a replacement that is only "
                "technically available is not organizationally admitted",
            )
        if model.adoptions[replacement].adoption_decision != "ADOPTED":
            raise AuthorityError(
                REFUSED_REPLACEMENT_NOT_ORGANIZATIONALLY_ADMITTED,
                f"<{sunset.iri}> replacement adoption <{replacement}> is "
                f"{model.adoptions[replacement].adoption_decision!r}, not ADOPTED",
            )


def _validate_blockers(model: AuthorityModel) -> None:
    for blocker in model.blockers.values():
        if blocker.resolution_mode == "CHILD_WORKFLOW":
            if blocker.child_workflow is None:
                raise AuthorityError(
                    REFUSED_MALFORMED_ARTIFACT,
                    f"<{blocker.iri}> claims CHILD_WORKFLOW resolution with no "
                    "fdet:resolvedByChildWorkflow",
                )
            continue
        raise AuthorityError(
            REFUSED_INFORMAL_ESCALATION_NOT_A_CHILD_WORKFLOW,
            f"<{blocker.iri}> resolves a recursive organizational blocker by "
            f"{blocker.resolution_mode!r}; an informal escalation leaves no "
            "admitted child workflow and therefore no auditable discharge",
        )


# ---------------------------------------------------------------------------
# The advisory computation
# ---------------------------------------------------------------------------


def permits(
    model: AuthorityModel,
    grant: AuthorityGrant,
    proposed: ProposedOperation,
) -> Permission:
    """Would this grant permit this operation? **Advisory only.**

    An ALLOW here is a statement about the shape of the envelope, not a
    decision that anything may happen. Nothing is minted, signed, or handed
    back that could be presented as authorization: the return value is a
    :class:`Permission`, which carries no bearer value at all.
    """
    try:
        validate_authority(model)
    except AuthorityError as exc:
        return refuse(exc.code, exc.detail)

    if proposed.customer != grant.for_customer:
        return refuse(
            REFUSED_WRONG_CUSTOMER,
            f"operation targets <{proposed.customer}>, grant is for "
            f"<{grant.for_customer}>",
        )

    if proposed.environment_scope not in grant.environment_scope:
        return refuse(
            REFUSED_OUT_OF_ENVIRONMENT_SCOPE,
            f"<{proposed.environment_scope}> not among {list(grant.environment_scope)}",
        )

    if proposed.capability not in grant.authorizes_capability:
        return refuse(
            REFUSED_CAPABILITY_NOT_GRANTED,
            f"capability <{proposed.capability}> is not among the granted "
            f"{list(grant.authorizes_capability)}",
        )

    operation = model.operations.get(proposed.operation)
    if operation is None or proposed.operation not in grant.authorizes_operation:
        return refuse(
            REFUSED_CAPABILITY_NOT_GRANTED,
            f"operation <{proposed.operation}> is not an authorized operation "
            "of this grant",
        )
    if operation.under_capability != proposed.capability:
        return refuse(
            REFUSED_CAPABILITY_NOT_GRANTED,
            f"operation <{operation.iri}> is under capability "
            f"<{operation.under_capability}>, not <{proposed.capability}>",
        )

    missing = [
        right
        for right in operation.requires_decision_right
        if right not in grant.conveys_decision_right
    ]
    if missing:
        return refuse(
            REFUSED_MISSING_DECISION_RIGHT,
            f"operation <{operation.iri}> requires {missing}, not conveyed",
        )

    if proposed.resource_scope not in grant.resource_scope:
        return refuse(
            REFUSED_OUT_OF_RESOURCE_SCOPE,
            f"<{proposed.resource_scope}> not among {list(grant.resource_scope)}",
        )
    if operation.on_resource != proposed.resource_scope:
        return refuse(
            REFUSED_OUT_OF_RESOURCE_SCOPE,
            f"operation <{operation.iri}> is scoped to <{operation.on_resource}>",
        )
    if operation.in_environment != proposed.environment_scope:
        return refuse(
            REFUSED_OUT_OF_ENVIRONMENT_SCOPE,
            f"operation <{operation.iri}> is scoped to <{operation.in_environment}>",
        )

    interval = model.intervals[grant.validity]
    at = proposed.at
    if at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    if not (interval.not_before <= at <= interval.not_after):
        return refuse(
            REFUSED_GRANT_EXPIRED,
            f"{at.isoformat()} outside [{interval.not_before.isoformat()}, "
            f"{interval.not_after.isoformat()}]",
        )

    if grant.executable_digest is not None:
        if proposed.executable_digest != grant.executable_digest:
            return refuse(
                REFUSED_EXECUTABLE_DIGEST_MISMATCH,
                f"proposed {proposed.executable_digest!r} != granted "
                f"{grant.executable_digest!r}",
            )

    bounds = model.bounds[grant.consequence_bounds]
    for actual, limit, what in (
        (proposed.affected_resources, bounds.max_affected_resources, "affected resources"),
        (
            proposed.irreversible_actions,
            bounds.max_irreversible_actions,
            "irreversible actions",
        ),
        (proposed.duration_seconds, bounds.max_duration_seconds, "duration seconds"),
    ):
        if actual > limit:
            return refuse(
                REFUSED_CONSEQUENCE_BOUNDS_EXCEEDED,
                f"{what}: {actual} > {limit}",
            )

    if proposed.delegated and not grant.delegation_allowed:
        return refuse(
            REFUSED_DELEGATION_NOT_ALLOWED,
            f"<{grant.iri}> fdet:delegationAllowed false",
        )

    if proposed.verified_by is not None:
        verifier = model.verifiers.get(proposed.verified_by)
        if verifier is None:
            return refuse(
                REFUSED_MISSING_INDEPENDENT_EVIDENCE,
                f"<{proposed.verified_by}> is not a declared fdet:Verifier",
            )
        if proposed.verified_by not in grant.requires_verifier:
            return refuse(
                REFUSED_MISSING_INDEPENDENT_EVIDENCE,
                f"<{proposed.verified_by}> is not a required verifier of this grant",
            )
        manufacturer = proposed.manufactured_by or proposed.performed_by
        if manufacturer is not None and manufacturer not in verifier.independent_of:
            return refuse(
                REFUSED_SELF_CERTIFICATION,
                f"verifier <{verifier.iri}> is not fdet:independentOf the "
                f"manufacturing party <{manufacturer}>",
            )

    return allow(
        f"advisory: <{grant.iri}> would permit <{operation.iri}>; authorization "
        "remains the broker's act"
    )


def permits_from_file(path: str, proposed: ProposedOperation) -> Permission:
    """Convenience wrapper: load, then :func:`permits`. Still advisory."""
    try:
        model = load_authority(path)
    except AuthorityError as exc:
        return refuse(exc.code, exc.detail)
    try:
        grant = model.the_grant()
    except AuthorityError as exc:
        return refuse(exc.code, exc.detail)
    return permits(model, grant, proposed)


__all__ = [
    "ACT_KINDS",
    "AUTHORABLE_HERE",
    "AuthorityError",
    "AuthorityGrant",
    "AuthorityModel",
    "Permission",
    "ProposedOperation",
    "REFUSAL_REASONS",
    "load_authority",
    "parse_authority_turtle",
    "permits",
    "permits_from_file",
    "validate_authority",
]
