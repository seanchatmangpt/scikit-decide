"""A real LLM-driven optimization agent: calls the local TurboFieldfare
OpenAI-compatible server (Gemma 4 26B-A4B, see ``~/turbo-fieldfare/AGENTS.md`` and
``docs/OPENAI_SERVER.md``) with real OCEL-derived performance scores
(``optimization_agent.score_log``) and lets the model choose the winner via a real
forced tool call — not a mocked HTTP response, not a fabricated model reply.

Per turbo-fieldfare's own boundary ("the server ... never executes tool calls;
executing that call is always a downstream consumer's job"), this module is that
downstream consumer: it reads the model's ``select_winner`` tool-call arguments and
validates them itself (``winner_run_id`` must be one of the real candidates), it
does not let the model actuate anything.

Uses stdlib ``urllib`` only — no new HTTP client dependency for one local call.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from autofde_lab.standing import Blocked, Unsupported

from .optimization_agent import OcelPerformanceScore, OptimizationDecision, score_log
from .wasm4pm_types import OcelLog

DEFAULT_BASE_URL = "http://127.0.0.1:8080/v1"
DEFAULT_MODEL = "gemma-4-26b-a4b-it"

_SELECT_WINNER_TOOL = {
    "type": "function",
    "function": {
        "name": "select_winner",
        "description": (
            "Select the best candidate plan run from real OCEL-derived performance "
            "scores and state why."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "winner_run_id": {
                    "type": "string",
                    "description": "The run_id of the candidate you are selecting.",
                },
                "reason": {
                    "type": "string",
                    "description": "One sentence citing the actual numbers that justify the choice.",
                },
            },
            "required": ["winner_run_id", "reason"],
        },
    },
}


def is_server_available(base_url: str = DEFAULT_BASE_URL, timeout: float = 2.0) -> bool:
    """Real health check — GET /health against the real local server. Used so this
    module degrades to a named ``Blocked``/skip rather than hanging when no server
    is running on a given machine."""
    # base_url is "http://127.0.0.1:8080/v1" -> health at "http://127.0.0.1:8080/health"
    health_url = base_url.rsplit("/v1", 1)[0] + "/health"
    try:
        with urllib.request.urlopen(health_url, timeout=timeout) as resp:  # noqa: S310
            return resp.status == 200
    except (urllib.error.URLError, OSError):
        return False


def _post_chat_completion(base_url: str, model: str, scores: list[OcelPerformanceScore]) -> dict:
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You optimize plan-run selection using only the real OCEL-derived "
                    "performance scores given to you. Call select_winner exactly once."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Candidate plan-run performance scores (computed from real OCEL "
                    "event logs):\n"
                    + json.dumps(
                        [
                            {
                                "run_id": s.run_id,
                                "step_count": s.step_count,
                                "total_cost": s.total_cost,
                                "total_reward": s.total_reward,
                                "reached_goal": s.reached_goal,
                            }
                            for s in scores
                        ],
                        indent=2,
                    )
                    + "\n\nSelect the best candidate: prefer any run that reached the "
                    "goal, then the lowest total_cost among those."
                ),
            },
        ],
        "tools": [_SELECT_WINNER_TOOL],
        "tool_choice": "auto",
        "temperature": 0,
        "max_completion_tokens": 200,
    }
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as resp:  # noqa: S310
        return json.loads(resp.read())


class LLMOptimizationAgent:
    """The LLM-driven sibling of ``PlanPerformanceAgent``: same real OCEL-derived
    inputs (``score_log``), same ``OptimizationDecision`` output shape, but the
    winner and its stated reason come from a real local Gemma model's tool call
    instead of a hand-written comparison."""

    def __init__(self, base_url: str = DEFAULT_BASE_URL, model: str = DEFAULT_MODEL):
        self.base_url = base_url
        self.model = model

    def select_best(self, candidates: dict[str, OcelLog]) -> OptimizationDecision:
        if not candidates:
            raise Blocked("no candidate OCEL logs were supplied to optimize over")
        if not is_server_available(self.base_url):
            raise Unsupported(
                f"no TurboFieldfare server reachable at {self.base_url}; "
                "start it per ~/turbo-fieldfare/docs/OPENAI_SERVER.md"
            )

        scores = [score_log(run_id, log) for run_id, log in candidates.items()]
        response = _post_chat_completion(self.base_url, self.model, scores)

        message = response["choices"][0]["message"]
        tool_calls = message.get("tool_calls") or []
        if not tool_calls:
            raise Blocked(
                "LLM did not call select_winner; finish_reason="
                f"{response['choices'][0].get('finish_reason')!r}"
            )
        arguments = json.loads(tool_calls[0]["function"]["arguments"])
        winner_run_id = arguments["winner_run_id"]
        reason = arguments["reason"]

        if winner_run_id not in candidates:
            raise Blocked(
                f"LLM selected unknown run_id {winner_run_id!r}; "
                f"real candidates were {list(candidates)}"
            )

        return OptimizationDecision(
            winner_run_id=winner_run_id,
            scores=tuple(scores),
            reason=f"[{self.model}] {reason}",
        )


__all__ = ["LLMOptimizationAgent", "is_server_available", "DEFAULT_BASE_URL", "DEFAULT_MODEL"]
