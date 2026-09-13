# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from __future__ import annotations

from dataclasses import replace
from typing import Protocol, Sequence

from .domain import ChatmanCleanSessionDomain
from .model import (
    ActionKind,
    ActuationIntent,
    BrokerReceipt,
    ExecutionReceipt,
    Lane,
    SessionAction,
    SessionState,
    Stage,
    validate_standing,
)


class Broker(Protocol):
    """Exclusive BRCE-compatible DO boundary."""

    def actuate(self, intent: ActuationIntent) -> BrokerReceipt: ...


class ActuationRefused(RuntimeError):
    pass


def _admit_broker_standing(receipt: BrokerReceipt) -> tuple[str, str | None]:
    """Admit a broker observation into an execution standing.

    ``UNKNOWN`` remains observable on the broker receipt but cannot become an
    admitted terminal truth, so the enclosing execution remains
    ``PARTIAL_ALIVE``.
    """

    validate_standing(receipt.standing)
    if receipt.standing == "UNKNOWN":
        return "PARTIAL_ALIVE", receipt.reason or "broker standing was UNKNOWN"
    return receipt.standing, receipt.reason


def _invoke_broker(broker: Broker, intent: ActuationIntent) -> BrokerReceipt:
    """Invoke BRCE and manufacture a typed receipt for every observed attempt."""

    try:
        observed = broker.actuate(intent)
    except PermissionError as error:
        return BrokerReceipt.issue(
            intent,
            standing="REFUSED:AUTHORITY_DENIED",
            consequence={
                "exception_type": type(error).__name__,
                "message": str(error),
            },
            reason="AUTHORITY_DENIED",
        )
    except NotImplementedError as error:
        return BrokerReceipt.issue(
            intent,
            standing="UNSUPPORTED",
            consequence={
                "exception_type": type(error).__name__,
                "message": str(error),
            },
            reason="BROKER_CAPABILITY_UNSUPPORTED",
        )
    except TimeoutError as error:
        return BrokerReceipt.issue(
            intent,
            standing="PARTIAL_ALIVE",
            consequence={
                "exception_type": type(error).__name__,
                "message": str(error),
            },
            reason="BROKER_TIMEOUT",
        )
    except Exception as error:
        return BrokerReceipt.issue(
            intent,
            standing="PARTIAL_ALIVE",
            consequence={
                "exception_type": type(error).__name__,
                "message": str(error),
            },
            reason="BROKER_EXCEPTION",
        )

    if observed.intent_id != intent.intent_id:
        return BrokerReceipt.issue(
            intent,
            standing="REFUSED:BROKER_RECEIPT_IDENTITY_MISMATCH",
            consequence={
                "observed_receipt_id": observed.receipt_id,
                "observed_intent_id": observed.intent_id,
                "observed_standing": observed.standing,
            },
            reason="BROKER_RECEIPT_IDENTITY_MISMATCH",
        )
    return observed


def _refusal_state(
    state: SessionState, standing: str, reason: str
) -> SessionState:
    return replace(
        state,
        stage=Stage.STANDING,
        standing=standing,
        reason=reason,
    )


def execute_actions(
    domain: ChatmanCleanSessionDomain,
    actions: Sequence[SessionAction],
    broker: Broker | None,
) -> ExecutionReceipt:
    """Execute a plan while enforcing BRCE for every DO edge."""

    state = domain.initial_state()
    broker_receipts: list[BrokerReceipt] = []
    executed: list[SessionAction] = []

    for action in actions:
        if action not in domain.applicable_actions(state):
            raise ValueError(
                f"plan diverged at {state.stage.value}: "
                f"action {action} is not applicable"
            )
        if action.lane is Lane.DO:
            executed.append(action)
            if broker is None:
                state = _refusal_state(
                    state,
                    "REFUSED:MISSING_BRCE_BROKER",
                    "MISSING_BRCE_BROKER",
                )
                break
            intent = domain.make_actuation_intent(state)
            receipt = _invoke_broker(broker, intent)
            broker_receipts.append(receipt)
            standing, reason = _admit_broker_standing(receipt)
            if standing != "ALIVE":
                state = _refusal_state(
                    state, standing, reason or "BROKER_DID_NOT_ADMIT_ALIVE"
                )
                break
        state = domain.transition(state, action)
        if action.lane is not Lane.DO:
            executed.append(action)

    if state.stage is not Stage.STANDING:
        raise ValueError(
            f"plan ended before standing at stage {state.stage.value}"
        )

    return ExecutionReceipt.issue(
        task=domain.task,
        standing=state.standing,
        state=state,
        broker_receipts=broker_receipts,
        actions=executed,
    )


def replay_execution(
    domain: ChatmanCleanSessionDomain,
    prior: ExecutionReceipt,
    broker: Broker | None,
) -> ExecutionReceipt:
    """Replay the prior DO intent through BRCE, never by direct repetition."""

    if prior.task_identity != domain.task.identity:
        raise ActuationRefused("REFUSED:REPLAY_TASK_IDENTITY_MISMATCH")
    if not prior.broker_receipts:
        raise ActuationRefused("REFUSED:REPLAY_HAS_NO_BROKER_RECEIPT")

    plan = domain.canonical_completion_plan()
    state = domain.initial_state()
    broker_receipts: list[BrokerReceipt] = []
    executed: list[SessionAction] = []

    for action in plan:
        if action not in domain.applicable_actions(state):
            raise ValueError(
                f"replay plan diverged at {state.stage.value}: "
                f"action {action} is not applicable"
            )
        if action.kind is ActionKind.ACTUATE:
            executed.append(action)
            if broker is None:
                state = _refusal_state(
                    state,
                    "REFUSED:MISSING_BRCE_BROKER",
                    "MISSING_BRCE_BROKER",
                )
                break
            intent = domain.make_actuation_intent(
                state, replay_of=prior.receipt_id
            )
            receipt = _invoke_broker(broker, intent)
            broker_receipts.append(receipt)
            standing, reason = _admit_broker_standing(receipt)
            if standing != "ALIVE":
                state = _refusal_state(
                    state, standing, reason or "BROKER_DID_NOT_ADMIT_ALIVE"
                )
                break
        state = domain.transition(state, action)
        if action.kind is not ActionKind.ACTUATE:
            executed.append(action)

    if state.stage is not Stage.STANDING:
        raise ValueError(
            f"replay ended before standing at stage {state.stage.value}"
        )

    return ExecutionReceipt.issue(
        task=domain.task,
        standing=state.standing,
        state=state,
        broker_receipts=broker_receipts,
        actions=executed,
        replay_of=prior.receipt_id,
    )
