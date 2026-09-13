# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from enum import Enum
from hashlib import sha256
from typing import Any, Mapping, Sequence


PRIMARY_STANDINGS = frozenset(
    {
        "UNKNOWN",
        "PARTIAL_ALIVE",
        "ALIVE",
        "BLOCKED",
        "BUILD_BROKEN",
        "UNSUPPORTED",
    }
)


def validate_standing(value: str) -> str:
    if value in PRIMARY_STANDINGS or (
        value.startswith("REFUSED:") and len(value) > len("REFUSED:")
    ):
        return value
    raise ValueError(f"invalid Chatman standing: {value!r}")


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def digest(value: Any) -> str:
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()


class Lane(str, Enum):
    SELECT = "SELECT"
    CONSTRUCT = "CONSTRUCT"
    DO = "DO"


class Stage(str, Enum):
    PARSE = "parse"
    ROUTE = "route"
    ADMIT = "admit"
    DIAGNOSE = "diagnose_or_repair"
    CONSTRUCT = "construct"
    ACTUATE = "actuate"
    OBSERVE = "observe_consequence"
    VERIFY = "verify"
    RECEIPT = "receipt"
    REPLAY_OR_HOOK = "replay_or_hook"
    STANDING = "standing"


class RouteOutcome(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    BUILD_BROKEN = "BUILD_BROKEN"
    BLOCKED = "BLOCKED"
    UNSUPPORTED = "UNSUPPORTED"
    REFUSED = "REFUSED"


class ActionKind(str, Enum):
    PARSE = "parse"
    TRY_ROUTE = "try_route"
    CLASSIFY_EXHAUSTION = "classify_exhaustion"
    ADMIT = "admit"
    DIAGNOSE_OR_REPAIR = "diagnose_or_repair"
    CONSTRUCT = "construct"
    ACTUATE = "actuate"
    OBSERVE_CONSEQUENCE = "observe_consequence"
    VERIFY = "verify"
    RECEIPT = "receipt"
    REPLAY_OR_HOOK = "replay_or_hook"


ACTION_LANES: Mapping[ActionKind, Lane] = {
    ActionKind.PARSE: Lane.SELECT,
    ActionKind.TRY_ROUTE: Lane.SELECT,
    ActionKind.CLASSIFY_EXHAUSTION: Lane.SELECT,
    ActionKind.ADMIT: Lane.SELECT,
    ActionKind.DIAGNOSE_OR_REPAIR: Lane.SELECT,
    ActionKind.CONSTRUCT: Lane.CONSTRUCT,
    ActionKind.ACTUATE: Lane.DO,
    ActionKind.OBSERVE_CONSEQUENCE: Lane.SELECT,
    ActionKind.VERIFY: Lane.SELECT,
    ActionKind.RECEIPT: Lane.CONSTRUCT,
    ActionKind.REPLAY_OR_HOOK: Lane.CONSTRUCT,
}


@dataclass(frozen=True)
class RouteSpec:
    name: str
    cost: float = 1.0
    outcome: RouteOutcome = RouteOutcome.SUCCESS
    reason: str | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("route name must not be empty")
        if self.cost < 0:
            raise ValueError("route cost must be non-negative")
        if self.outcome is not RouteOutcome.SUCCESS and not self.reason:
            raise ValueError("non-success routes require an evidence reason")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "cost": self.cost,
            "outcome": self.outcome.value,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class TaskEnvelope:
    repo: str
    base: str
    task: str
    acceptance: str
    constraints: tuple[str, ...] = ()
    authority: str = ""

    def __post_init__(self) -> None:
        for field_name in ("repo", "base", "task", "acceptance"):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} must not be empty")

    @property
    def identity(self) -> str:
        return digest(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo": self.repo,
            "base": self.base,
            "task": self.task,
            "acceptance": self.acceptance,
            "constraints": list(self.constraints),
            "authority": self.authority,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> TaskEnvelope:
        return cls(
            repo=str(value["repo"]),
            base=str(value["base"]),
            task=str(value["task"]),
            acceptance=str(value["acceptance"]),
            constraints=tuple(str(item) for item in value.get("constraints", ())),
            authority=str(value.get("authority", "")),
        )


@dataclass(frozen=True)
class SessionAction:
    kind: ActionKind
    route: str | None = None

    @property
    def lane(self) -> Lane:
        return ACTION_LANES[self.kind]

    def __post_init__(self) -> None:
        if self.kind is ActionKind.TRY_ROUTE and not self.route:
            raise ValueError("TRY_ROUTE requires a route name")
        if self.kind is not ActionKind.TRY_ROUTE and self.route is not None:
            raise ValueError(f"{self.kind.value} must not carry a route")

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "lane": self.lane.value,
            "route": self.route,
        }


@dataclass(frozen=True)
class RouteEvidence:
    route: str
    outcome: RouteOutcome
    reason: str | None


@dataclass(frozen=True)
class SessionState:
    task_identity: str
    stage: Stage = Stage.PARSE
    attempted_routes: tuple[str, ...] = ()
    route_evidence: tuple[RouteEvidence, ...] = ()
    selected_route: str | None = None
    standing: str = "UNKNOWN"
    reason: str | None = None

    def __post_init__(self) -> None:
        validate_standing(self.standing)

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["stage"] = self.stage.value
        value["attempted_routes"] = list(self.attempted_routes)
        value["route_evidence"] = [
            {
                "route": evidence.route,
                "outcome": evidence.outcome.value,
                "reason": evidence.reason,
            }
            for evidence in self.route_evidence
        ]
        return value


@dataclass(frozen=True)
class ActuationIntent:
    task_identity: str
    route: str
    action: str
    payload: Mapping[str, Any]
    replay_of: str | None = None

    @property
    def intent_id(self) -> str:
        return digest(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_identity": self.task_identity,
            "route": self.route,
            "action": self.action,
            "payload": dict(self.payload),
            "replay_of": self.replay_of,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> ActuationIntent:
        return cls(
            task_identity=str(value["task_identity"]),
            route=str(value["route"]),
            action=str(value["action"]),
            payload=dict(value["payload"]),
            replay_of=(
                None if value.get("replay_of") is None else str(value["replay_of"])
            ),
        )


@dataclass(frozen=True)
class BrokerReceipt:
    receipt_id: str
    intent_id: str
    intent: Mapping[str, Any]
    standing: str
    consequence: Mapping[str, Any]
    reason: str | None = None

    def __post_init__(self) -> None:
        validate_standing(self.standing)
        if not self.receipt_id:
            raise ValueError("broker receipt_id must not be empty")
        if digest(dict(self.intent)) != self.intent_id:
            raise ValueError("broker intent document does not match intent_id")
        if digest(self._material()) != self.receipt_id:
            raise ValueError("broker receipt document does not match receipt_id")

    def _material(self) -> dict[str, Any]:
        return {
            "intent_id": self.intent_id,
            "intent": dict(self.intent),
            "standing": self.standing,
            "consequence": dict(self.consequence),
            "reason": self.reason,
        }

    @classmethod
    def issue(
        cls,
        intent: ActuationIntent,
        standing: str,
        consequence: Mapping[str, Any],
        reason: str | None = None,
    ) -> BrokerReceipt:
        validate_standing(standing)
        intent_document = intent.to_dict()
        material = {
            "intent_id": intent.intent_id,
            "intent": intent_document,
            "standing": standing,
            "consequence": dict(consequence),
            "reason": reason,
        }
        return cls(
            receipt_id=digest(material),
            intent_id=intent.intent_id,
            intent=intent_document,
            standing=standing,
            consequence=dict(consequence),
            reason=reason,
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> BrokerReceipt:
        return cls(
            receipt_id=str(value["receipt_id"]),
            intent_id=str(value["intent_id"]),
            intent=dict(value["intent"]),
            standing=str(value["standing"]),
            consequence=dict(value["consequence"]),
            reason=None if value.get("reason") is None else str(value["reason"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {"receipt_id": self.receipt_id, **self._material()}


@dataclass(frozen=True)
class ExecutionReceipt:
    receipt_id: str
    task_identity: str
    task: Mapping[str, Any]
    standing: str
    state_digest: str
    state: Mapping[str, Any]
    broker_receipts: tuple[BrokerReceipt, ...]
    actions: tuple[SessionAction, ...]
    replay_of: str | None = None

    def __post_init__(self) -> None:
        validate_standing(self.standing)
        if digest(dict(self.task)) != self.task_identity:
            raise ValueError("task document does not match task_identity")
        if digest(dict(self.state)) != self.state_digest:
            raise ValueError("state document does not match state_digest")
        if digest(self._material()) != self.receipt_id:
            raise ValueError("execution receipt document does not match receipt_id")

    def _material(self) -> dict[str, Any]:
        return {
            "task_identity": self.task_identity,
            "standing": self.standing,
            "state_digest": self.state_digest,
            "broker_receipts": [
                receipt.receipt_id for receipt in self.broker_receipts
            ],
            "actions": [action.to_dict() for action in self.actions],
            "replay_of": self.replay_of,
        }

    @classmethod
    def issue(
        cls,
        task: TaskEnvelope,
        standing: str,
        state: SessionState,
        broker_receipts: Sequence[BrokerReceipt],
        actions: Sequence[SessionAction],
        replay_of: str | None = None,
    ) -> ExecutionReceipt:
        validate_standing(standing)
        task_document = task.to_dict()
        state_document = state.to_dict()
        state_identity = digest(state_document)
        material = {
            "task_identity": task.identity,
            "standing": standing,
            "state_digest": state_identity,
            "broker_receipts": [receipt.receipt_id for receipt in broker_receipts],
            "actions": [action.to_dict() for action in actions],
            "replay_of": replay_of,
        }
        return cls(
            receipt_id=digest(material),
            task_identity=task.identity,
            task=task_document,
            standing=standing,
            state_digest=state_identity,
            state=state_document,
            broker_receipts=tuple(broker_receipts),
            actions=tuple(actions),
            replay_of=replay_of,
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> ExecutionReceipt:
        actions: list[SessionAction] = []
        for item in value["actions"]:
            action = SessionAction(
                ActionKind(str(item["kind"])),
                None if item.get("route") is None else str(item["route"]),
            )
            if item.get("lane") != action.lane.value:
                raise ValueError("action lane does not match action kind")
            actions.append(action)
        return cls(
            receipt_id=str(value["receipt_id"]),
            task_identity=str(value["task_identity"]),
            task=dict(value["task"]),
            standing=str(value["standing"]),
            state_digest=str(value["state_digest"]),
            state=dict(value["state"]),
            broker_receipts=tuple(
                BrokerReceipt.from_mapping(item)
                for item in value["broker_receipts"]
            ),
            actions=tuple(actions),
            replay_of=(
                None if value.get("replay_of") is None else str(value["replay_of"])
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "receipt_id": self.receipt_id,
            "task_identity": self.task_identity,
            "task": dict(self.task),
            "standing": self.standing,
            "state_digest": self.state_digest,
            "state": dict(self.state),
            "broker_receipts": [
                receipt.to_dict() for receipt in self.broker_receipts
            ],
            "actions": [action.to_dict() for action in self.actions],
            "replay_of": self.replay_of,
        }
