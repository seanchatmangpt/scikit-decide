from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

from autofde_lab.powl.algebra import Atom, NodeId, OrderEdge, PartialOrder, Silent
from autofde_lab.powl.runner import ActivityIntent, ActivityOutcome

from .models import Capability, MitigationProcessProposal, ObservationProcessProposal


class ProcessAdmissionError(ValueError):
    pass


_KUBECTL_READ_PREFIXES = (
    "kubectl api-resources",
    "kubectl api-versions",
    "kubectl auth can-i",
    "kubectl auth whoami",
    "kubectl cluster-info",
    "kubectl describe",
    "kubectl diff",
    "kubectl events",
    "kubectl explain",
    "kubectl get",
    "kubectl logs",
    "kubectl rollout status",
    "kubectl top",
    "kubectl version",
)


def kubectl_command_is_read_only(command: str) -> bool:
    normalized = " ".join(str(command).strip().split())
    return any(
        normalized == prefix or normalized.startswith(prefix + " ")
        for prefix in _KUBECTL_READ_PREFIXES
    )


def canonical_read_identity(capability_id: str, arguments: dict[str, Any]) -> str:
    return f"{capability_id}|{json.dumps(arguments, sort_keys=True, separators=(',', ':'), default=str)}"


def _capability_map(capabilities: list[Capability]) -> dict[str, Capability]:
    result: dict[str, Capability] = {}
    for capability in capabilities:
        if capability.id in result:
            raise ProcessAdmissionError(f"DUPLICATE_CAPABILITY_ID:{capability.id}")
        result[capability.id] = capability
    return result


def _validate_arguments(capability: Capability, arguments: dict[str, Any]) -> None:
    schema = capability.input_schema
    required = schema.get("required", []) if isinstance(schema, dict) else []
    missing = sorted(set(required) - set(arguments))
    if missing:
        raise ProcessAdmissionError(
            f"CAPABILITY_ARGUMENT_REQUIRED:{capability.id}:{','.join(missing)}"
        )
    properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
    if isinstance(properties, dict) and properties:
        unknown = sorted(set(arguments) - set(properties))
        if unknown:
            raise ProcessAdmissionError(
                f"CAPABILITY_ARGUMENT_UNKNOWN:{capability.id}:{','.join(unknown)}"
            )


def _authority_refusal(
    *,
    capability: Capability,
    arguments: dict[str, Any],
    consequence: str,
    allow_do: bool,
) -> str | None:
    surface = capability.surface
    tool = capability.tool
    if surface == "submit":
        return "CONTROL_SURFACE_RESERVED"
    if surface != "kubectl":
        return None if consequence != "DO" else "DO_SURFACE_NOT_ADMITTED"
    if tool == "get_previous_rollbackable_cmd":
        return None if consequence != "DO" else "DO_TOOL_IS_OBSERVATIONAL"
    if tool == "rollback_command":
        if consequence != "DO":
            return "MUTATION_MISLABELED_AS_OBSERVATION"
        return None if allow_do else "DO_NOT_ADMITTED"
    if tool != "exec_kubectl_cmd_safely":
        return "UNKNOWN_KUBECTL_TOOL_AUTHORITY"

    command = str(arguments.get("cmd", ""))
    read_only = kubectl_command_is_read_only(command)
    if consequence in {"READ", "VERIFY"} and not read_only:
        return "MUTATION_MISLABELED_AS_OBSERVATION"
    if consequence == "DO" and not allow_do:
        return "DO_NOT_ADMITTED"
    return None


def _validate_discrimination_contract(
    process: ObservationProcessProposal,
    *,
    hypothesis_ids: set[str],
    prior_read_identities: set[str],
) -> None:
    seen = set(prior_read_identities)
    for step in process.steps:
        declared = set(step.discriminates)
        if not declared:
            raise ProcessAdmissionError(f"DISCRIMINATION_TARGET_REQUIRED:{step.id}")
        unknown_targets = sorted(declared - hypothesis_ids)
        if unknown_targets:
            raise ProcessAdmissionError(
                f"DISCRIMINATION_TARGET_UNKNOWN:{step.id}:{','.join(unknown_targets)}"
            )
        if not step.outcomes:
            raise ProcessAdmissionError(f"DISCRIMINATION_OUTCOMES_REQUIRED:{step.id}")
        refutable: set[str] = set()
        for outcome in step.outcomes:
            refs = set(outcome.refutes)
            supports = set(outcome.supports)
            unknown = sorted((refs | supports) - hypothesis_ids)
            if unknown:
                raise ProcessAdmissionError(
                    f"DISCRIMINATION_OUTCOME_TARGET_UNKNOWN:{step.id}:{','.join(unknown)}"
                )
            refutable |= refs
        if not (refutable & declared):
            raise ProcessAdmissionError(
                f"DISCRIMINATION_MUST_REFUTE_COMPETITOR:{step.id}"
            )

        identity = canonical_read_identity(step.capability_id, dict(step.arguments))
        if identity in seen and not step.repeat_reason.strip():
            raise ProcessAdmissionError(
                f"DUPLICATE_READ_WITHOUT_TEMPORAL_REASON:{step.id}"
            )
        seen.add(identity)


def _compile_steps(
    steps: list[Any],
    *,
    capabilities: list[Capability],
    allowed_consequences: set[str],
    allow_do: bool,
) -> PartialOrder:
    if not steps:
        raise ProcessAdmissionError("EMPTY_PROCESS")
    ids = [step.id for step in steps]
    if len(ids) != len(set(ids)):
        raise ProcessAdmissionError("DUPLICATE_STEP_ID")
    index = {step_id: i for i, step_id in enumerate(ids)}
    available = _capability_map(capabilities)
    children = []
    edges: set[OrderEdge] = set()
    for i, step in enumerate(steps):
        consequence = getattr(step, "consequence", "READ")
        if consequence not in allowed_consequences:
            raise ProcessAdmissionError(f"CONSEQUENCE_NOT_ADMITTED:{consequence}")
        capability = available.get(step.capability_id)
        if capability is None:
            raise ProcessAdmissionError(
                f"CAPABILITY_ID_NOT_DISCOVERED:{step.capability_id}"
            )
        _validate_arguments(capability, dict(step.arguments))
        refusal = _authority_refusal(
            capability=capability,
            arguments=dict(step.arguments),
            consequence=consequence,
            allow_do=allow_do,
        )
        if refusal:
            raise ProcessAdmissionError(
                f"CAPABILITY_AUTHORITY_REFUSED:{step.id}:{capability.id}:{refusal}"
            )
        children.append(
            Atom(
                label=step.id,
                action=f"mcp://{capability.surface}/{capability.tool}",
                bindings={
                    "capability_id": capability.id,
                    "surface": capability.surface,
                    "tool": capability.tool,
                    "arguments": dict(step.arguments),
                    "consequence": consequence,
                },
            )
        )
        for predecessor in step.after:
            if predecessor not in index:
                raise ProcessAdmissionError(f"UNKNOWN_PREDECESSOR:{predecessor}")
            edges.add(OrderEdge(NodeId(index[predecessor]), NodeId(i)))
    if len(children) == 1:
        children.append(Silent())
        edges.add(OrderEdge(NodeId(0), NodeId(1)))
    return PartialOrder(children=tuple(children), order=frozenset(edges))


def compile_observation_process(
    process: ObservationProcessProposal,
    capabilities: list[Capability],
    *,
    hypothesis_ids: set[str] | None = None,
    prior_read_identities: set[str] | None = None,
) -> PartialOrder:
    if hypothesis_ids is not None:
        _validate_discrimination_contract(
            process,
            hypothesis_ids=hypothesis_ids,
            prior_read_identities=prior_read_identities or set(),
        )
    return _compile_steps(
        process.steps,
        capabilities=capabilities,
        allowed_consequences={"READ"},
        allow_do=False,
    )


def compile_mitigation_process(
    process: MitigationProcessProposal, capabilities: list[Capability]
) -> PartialOrder:
    if (
        any(step.consequence == "DO" for step in process.steps)
        and not process.reversible
    ):
        raise ProcessAdmissionError("CONSEQUENTIAL_PROCESS_NOT_REVERSIBLE")
    if not any(step.consequence == "VERIFY" for step in process.steps):
        raise ProcessAdmissionError("MITIGATION_VERIFICATION_REQUIRED")
    return _compile_steps(
        process.steps,
        capabilities=capabilities,
        allowed_consequences={"DO", "VERIFY"},
        allow_do=True,
    )


@dataclass
class McpActivityDriver:
    broker: Any
    capabilities: list[Capability]
    allow_do: bool = False
    _by_id: dict[str, Capability] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._by_id = _capability_map(self.capabilities)

    def _authority_refusal(
        self,
        *,
        capability_id: str,
        surface: str,
        tool: str,
        arguments: dict[str, Any],
        consequence: str,
    ) -> str | None:
        capability = self._by_id.get(capability_id)
        if capability is None:
            return "CAPABILITY_ID_NOT_DISCOVERED"
        if capability.surface != surface or capability.tool != tool:
            return "CAPABILITY_BINDING_DRIFT"
        try:
            _validate_arguments(capability, arguments)
        except ProcessAdmissionError as exc:
            return str(exc)
        return _authority_refusal(
            capability=capability,
            arguments=arguments,
            consequence=consequence,
            allow_do=self.allow_do,
        )

    def execute(self, intent: ActivityIntent) -> ActivityOutcome:
        capability_id = str(intent.bindings.get("capability_id", ""))
        surface = str(intent.bindings["surface"])
        tool = str(intent.bindings["tool"])
        arguments = dict(intent.bindings.get("arguments", {}))
        consequence = str(intent.bindings.get("consequence", "READ"))

        refusal = self._authority_refusal(
            capability_id=capability_id,
            surface=surface,
            tool=tool,
            arguments=arguments,
            consequence=consequence,
        )
        if refusal:
            return ActivityOutcome(
                success=False,
                metadata={
                    "refusal": refusal,
                    "capability_id": capability_id,
                    "surface": surface,
                    "tool": tool,
                    "arguments": arguments,
                    "consequence": consequence,
                },
            )

        text = asyncio.run(self.broker.call(surface, tool, arguments))
        return ActivityOutcome(
            success=True,
            value=text,
            metadata={
                "capability_id": capability_id,
                "surface": surface,
                "tool": tool,
                "arguments": arguments,
                "consequence": consequence,
                "observation": text,
            },
        )
