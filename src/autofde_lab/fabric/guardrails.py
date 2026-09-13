"""Provider-neutral candidate guardrails below the BRCE authority boundary."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Mapping, Protocol, Sequence


class CandidateProvider(Protocol):
    def propose(self, observation: Mapping[str, object]) -> Mapping[str, object]: ...


class GuardrailStanding(str, Enum):
    CANDIDATE = "CANDIDATE"
    REFUSED_INPUT = "REFUSED:INPUT_GUARDRAIL"
    REFUSED_OUTPUT = "REFUSED:OUTPUT_GUARDRAIL"
    REFUSED_TOOL = "REFUSED:TOOL_GUARDRAIL"


@dataclass(frozen=True, slots=True)
class CandidateDecision:
    standing: GuardrailStanding
    candidate: Mapping[str, object] | None
    reason: str


def guarded_candidate(
    provider: CandidateProvider,
    observation: Mapping[str, object],
    *,
    input_guards: Sequence[Callable[[Mapping[str, object]], bool]] = (),
    output_guards: Sequence[Callable[[Mapping[str, object]], bool]] = (),
    allowed_tools: frozenset[str] = frozenset(),
) -> CandidateDecision:
    if not all(guard(observation) for guard in input_guards):
        return CandidateDecision(GuardrailStanding.REFUSED_INPUT, None, "input refused")
    candidate = provider.propose(observation)
    if not all(guard(candidate) for guard in output_guards):
        return CandidateDecision(
            GuardrailStanding.REFUSED_OUTPUT, None, "output refused"
        )
    requested_tool = candidate.get("tool")
    if requested_tool is not None and str(requested_tool) not in allowed_tools:
        return CandidateDecision(GuardrailStanding.REFUSED_TOOL, None, "tool refused")
    return CandidateDecision(
        GuardrailStanding.CANDIDATE,
        dict(candidate),
        "candidate passed guardrails; no execution authority granted",
    )
