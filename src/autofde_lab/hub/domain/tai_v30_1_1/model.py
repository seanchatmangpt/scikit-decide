# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Pure transition model for the TAI v30.1.1 forward-deployment case study.

This module intentionally has no execution or network side effects.  It models
SELECT/CONSTRUCT/DO boundaries as planning states.  BRCE actions are intents in
this model; actual actuation remains outside the planner and must be performed
by an authorized broker that emits a receipt.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Iterable, NamedTuple

CASE_STUDY_VERSION = "30.1.1"
CASE_STUDY_SUBJECT = "Technology Applications, Inc. (TAI) forward deployment"

# User-supplied historical brochure observations admitted only as bounded case-study
# inputs.  They are not represented as independently audited corporate claims.
PUBLIC_EVIDENCE = (
    "TAI described an initial Navy engineering-services contract in 1977.",
    "TAI described capabilities in systems integration, telecommunications, "
    "software engineering, environmental services, and engineering services.",
    "TAI described lifecycle delivery spanning design, procurement, installation, "
    "testing, training, operations, maintenance, and customer-site support.",
    "TAI described a workforce of more than 500 serving customer installations.",
)

# These terms are bound to executable semantics in this case study rather than
# included as decorative vocabulary.
ONTOLOGY_BINDINGS = {
    "input_entity": "http://www.w3.org/ns/prov#Entity",
    "manufacture_activity": "http://www.w3.org/ns/prov#Activity",
    "authorized_agent": "http://www.w3.org/ns/prov#Agent",
    "permission": "http://www.w3.org/ns/odrl/2/Permission",
    "version": "http://purl.org/dc/terms/hasVersion",
    "receipt_event": "http://www.ocel-standard.org/ontology/Event",
}


class TaiState(NamedTuple):
    enterprise_compiled: bool = False
    public_model_admitted: bool = False
    keys_manufactured: bool = False
    local_conformance_validated: bool = False
    local_conformance_refused: bool = False
    private_parameters_bound: bool = False
    runtime_admitted: bool = False
    authority_granted: bool = False
    brce_actuated: bool = False
    consequence_verified: bool = False
    receipt_issued: bool = False
    replay_verified: bool = False
    standing: bool = False
    refusal_receipt_issued: bool = False


INITIAL_STATE = TaiState()


class TaiAction(Enum):
    compile_enterprise = 0
    admit_public_model = 1
    manufacture_keys = 2
    validate_local_conformance = 3
    refuse_local_conformance = 4
    bind_private_parameters = 5
    admit_runtime = 6
    grant_authority = 7
    brce_actuate = 8
    verify_consequence = 9
    issue_receipt = 10
    brce_replay = 11
    establish_standing = 12
    issue_refusal_receipt = 13


class RefusalReason(str, Enum):
    TERMINAL_STATE = "REFUSED:TERMINAL_STATE"
    ENTERPRISE_NOT_COMPILED = "REFUSED:ENTERPRISE_NOT_COMPILED"
    PUBLIC_MODEL_NOT_ADMITTED = "REFUSED:PUBLIC_MODEL_NOT_ADMITTED"
    KEYS_NOT_MANUFACTURED = "REFUSED:KEYS_NOT_MANUFACTURED"
    LOCAL_CONFORMANCE_FALSIFIED = "REFUSED:LOCAL_CONFORMANCE_FALSIFIED"
    LOCAL_CONFORMANCE_NOT_VALIDATED = "REFUSED:LOCAL_CONFORMANCE_NOT_VALIDATED"
    PRIVATE_PARAMETERS_NOT_BOUND = "REFUSED:PRIVATE_PARAMETERS_NOT_BOUND"
    RUNTIME_NOT_ADMITTED = "REFUSED:RUNTIME_NOT_ADMITTED"
    AUTHORITY_NOT_GRANTED = "REFUSED:AUTHORITY_NOT_GRANTED"
    CONSEQUENCE_NOT_OBSERVED = "REFUSED:CONSEQUENCE_NOT_OBSERVED"
    CONSEQUENCE_NOT_VERIFIED = "REFUSED:CONSEQUENCE_NOT_VERIFIED"
    RECEIPT_NOT_ISSUED = "REFUSED:RECEIPT_NOT_ISSUED"
    REPLAY_NOT_VERIFIED = "REFUSED:REPLAY_NOT_VERIFIED"
    ACTION_ALREADY_APPLIED = "REFUSED:ACTION_ALREADY_APPLIED"
    ACTION_NOT_APPLICABLE = "REFUSED:ACTION_NOT_APPLICABLE"


class TaiTransitionRefused(ValueError):
    """Raised when a transition violates the admitted planning boundary."""

    def __init__(self, action: TaiAction, reason: RefusalReason):
        self.action = action
        self.reason = reason
        super().__init__(f"{reason.value}: {action.name}")


@dataclass(frozen=True)
class TaiReceipt:
    receipt_id: str
    subject: str
    version: str
    standing: str
    intent: tuple[str, ...]
    final_state: TaiState
    ontology_bindings: tuple[tuple[str, str], ...]

    def to_json(self) -> str:
        payload = asdict(self)
        payload["final_state"] = self.final_state._asdict()
        payload["ontology_bindings"] = dict(self.ontology_bindings)
        return json.dumps(payload, indent=2, sort_keys=True)


POSITIVE_PLAN = (
    TaiAction.compile_enterprise,
    TaiAction.admit_public_model,
    TaiAction.manufacture_keys,
    TaiAction.validate_local_conformance,
    TaiAction.bind_private_parameters,
    TaiAction.admit_runtime,
    TaiAction.grant_authority,
    TaiAction.brce_actuate,
    TaiAction.verify_consequence,
    TaiAction.issue_receipt,
    TaiAction.brce_replay,
    TaiAction.establish_standing,
)

REFUSAL_PLAN = (
    TaiAction.compile_enterprise,
    TaiAction.admit_public_model,
    TaiAction.manufacture_keys,
    TaiAction.refuse_local_conformance,
    TaiAction.issue_refusal_receipt,
)


def is_terminal(state: TaiState) -> bool:
    return state.standing or state.refusal_receipt_issued


def applicable_actions(
    state: TaiState, *, local_conformance: bool = True
) -> tuple[TaiAction, ...]:
    """Return all lawful next actions for the admitted state."""
    if is_terminal(state):
        return ()
    if not state.enterprise_compiled:
        return (TaiAction.compile_enterprise,)
    if not state.public_model_admitted:
        return (TaiAction.admit_public_model,)
    if not state.keys_manufactured:
        return (TaiAction.manufacture_keys,)
    if not state.local_conformance_validated and not state.local_conformance_refused:
        return (
            (TaiAction.validate_local_conformance,)
            if local_conformance
            else (TaiAction.refuse_local_conformance,)
        )
    if state.local_conformance_refused:
        return (TaiAction.issue_refusal_receipt,)
    if not state.private_parameters_bound:
        return (TaiAction.bind_private_parameters,)
    if not state.runtime_admitted:
        return (TaiAction.admit_runtime,)
    if not state.authority_granted:
        return (TaiAction.grant_authority,)
    if not state.brce_actuated:
        return (TaiAction.brce_actuate,)
    if not state.consequence_verified:
        return (TaiAction.verify_consequence,)
    if not state.receipt_issued:
        return (TaiAction.issue_receipt,)
    if not state.replay_verified:
        return (TaiAction.brce_replay,)
    if not state.standing:
        return (TaiAction.establish_standing,)
    return ()


def refusal_reason(
    state: TaiState, action: TaiAction, *, local_conformance: bool = True
) -> RefusalReason:
    if is_terminal(state):
        return RefusalReason.TERMINAL_STATE
    if action == TaiAction.compile_enterprise and state.enterprise_compiled:
        return RefusalReason.ACTION_ALREADY_APPLIED
    if action == TaiAction.admit_public_model and not state.enterprise_compiled:
        return RefusalReason.ENTERPRISE_NOT_COMPILED
    if action == TaiAction.manufacture_keys and not state.public_model_admitted:
        return RefusalReason.PUBLIC_MODEL_NOT_ADMITTED
    if action in {
        TaiAction.validate_local_conformance,
        TaiAction.refuse_local_conformance,
    } and not state.keys_manufactured:
        return RefusalReason.KEYS_NOT_MANUFACTURED
    if action == TaiAction.validate_local_conformance and not local_conformance:
        return RefusalReason.LOCAL_CONFORMANCE_FALSIFIED
    if (
        action == TaiAction.bind_private_parameters
        and not state.local_conformance_validated
    ):
        return RefusalReason.LOCAL_CONFORMANCE_NOT_VALIDATED
    if action == TaiAction.admit_runtime and not state.private_parameters_bound:
        return RefusalReason.PRIVATE_PARAMETERS_NOT_BOUND
    if action == TaiAction.grant_authority and not state.runtime_admitted:
        return RefusalReason.RUNTIME_NOT_ADMITTED
    if action == TaiAction.brce_actuate:
        if not state.runtime_admitted:
            return RefusalReason.RUNTIME_NOT_ADMITTED
        if not state.authority_granted:
            return RefusalReason.AUTHORITY_NOT_GRANTED
    if action == TaiAction.verify_consequence and not state.brce_actuated:
        return RefusalReason.CONSEQUENCE_NOT_OBSERVED
    if action == TaiAction.issue_receipt and not state.consequence_verified:
        return RefusalReason.CONSEQUENCE_NOT_VERIFIED
    if action == TaiAction.brce_replay and not state.receipt_issued:
        return RefusalReason.RECEIPT_NOT_ISSUED
    if action == TaiAction.establish_standing and not state.replay_verified:
        return RefusalReason.REPLAY_NOT_VERIFIED
    return RefusalReason.ACTION_NOT_APPLICABLE


def transition(
    state: TaiState, action: TaiAction, *, local_conformance: bool = True
) -> TaiState:
    """Apply one admitted transition or emit a typed refusal."""
    if action not in applicable_actions(state, local_conformance=local_conformance):
        raise TaiTransitionRefused(
            action,
            refusal_reason(state, action, local_conformance=local_conformance),
        )

    field_by_action = {
        TaiAction.compile_enterprise: "enterprise_compiled",
        TaiAction.admit_public_model: "public_model_admitted",
        TaiAction.manufacture_keys: "keys_manufactured",
        TaiAction.validate_local_conformance: "local_conformance_validated",
        TaiAction.refuse_local_conformance: "local_conformance_refused",
        TaiAction.bind_private_parameters: "private_parameters_bound",
        TaiAction.admit_runtime: "runtime_admitted",
        TaiAction.grant_authority: "authority_granted",
        TaiAction.brce_actuate: "brce_actuated",
        TaiAction.verify_consequence: "consequence_verified",
        TaiAction.issue_receipt: "receipt_issued",
        TaiAction.brce_replay: "replay_verified",
        TaiAction.establish_standing: "standing",
        TaiAction.issue_refusal_receipt: "refusal_receipt_issued",
    }
    return state._replace(**{field_by_action[action]: True})


def replay_plan(
    actions: Iterable[TaiAction], *, local_conformance: bool = True
) -> TaiState:
    state = INITIAL_STATE
    for action in actions:
        state = transition(state, action, local_conformance=local_conformance)
    return state


def build_receipt(actions: Iterable[TaiAction], final_state: TaiState) -> TaiReceipt:
    intent = tuple(action.name for action in actions)
    if final_state.standing:
        standing = "ALIVE"
    elif final_state.refusal_receipt_issued:
        standing = RefusalReason.LOCAL_CONFORMANCE_FALSIFIED.value
    else:
        raise ValueError("A receipt requires standing or a receipted refusal")

    unsigned = {
        "subject": CASE_STUDY_SUBJECT,
        "version": CASE_STUDY_VERSION,
        "standing": standing,
        "intent": intent,
        "final_state": final_state._asdict(),
        "ontology_bindings": ONTOLOGY_BINDINGS,
    }
    canonical = json.dumps(unsigned, separators=(",", ":"), sort_keys=True)
    receipt_id = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return TaiReceipt(
        receipt_id=receipt_id,
        subject=CASE_STUDY_SUBJECT,
        version=CASE_STUDY_VERSION,
        standing=standing,
        intent=intent,
        final_state=final_state,
        ontology_bindings=tuple(sorted(ONTOLOGY_BINDINGS.items())),
    )


def verify_receipt_replay(receipt: TaiReceipt) -> bool:
    actions = tuple(TaiAction[name] for name in receipt.intent)
    local_conformance = receipt.standing == "ALIVE"
    replayed_state = replay_plan(actions, local_conformance=local_conformance)
    replayed_receipt = build_receipt(actions, replayed_state)
    return replayed_receipt == receipt
