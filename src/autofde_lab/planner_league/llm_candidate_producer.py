"""Cap 11: a high-concurrency LLM candidate-policy producer over the FOND x
HDDL product (`autofde_lab.planning.fond_hddl_product`).

Governing law (`V2030.1.1-PRD-ARD.md:42`): "LLMs are optional
compilers/oracles/candidate producers. They SHALL NOT be treated as proof or
production authority." This module is the first capability that uses an LLM
(GLM-5.3-flash via Z.ai) as a *bulk* candidate producer rather than a single
serial judge/agent call (contrast `sregym_sota/agent.py`'s one-shot
`dspy.configure` pattern, whose provider/model-string shape this module
reuses).

Everything an LLM produces here is quarantined as `LLMCandidateRawOutput`
until it passes through `admit_llm_candidate`, which is the *only* path to a
typed `CandidatePolicy` -- built exclusively via
`fond_hddl_product.candidate_policy_over_product`, the repo's existing "thin
constructor so callers never hand-build `fond_policy` types." No LLM output
ever reaches `BenchmarkVector` or `LabResultStanding` directly; those remain
strictly derived from real `gymact` episode receipts, unchanged by this
module.

Z.ai publishes no numeric RPM/TPM/concurrency ceiling for GLM-5.3-flash
(confirmed by this session's research pass), so `max_concurrency=50` is a
requested ceiling, not a guarantee -- `BackoffPolicy` retries 429/5xx with
exponential backoff + jitter, and any call that exhausts retries becomes an
explicit, counted `PoolRunFailure`. Failures are never dropped and never
coerced into a fake candidate or a fake benchmark score.

This module computes candidate plans only. It has no actuation authority and
does not call BRCE, an executor, or any `ExperimentExecutionPort`.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import random
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Mapping

from ..planning.fond_hddl_product import (
    ActionId,
    CandidatePolicy,
    StateId,
    candidate_policy_over_product,
)
from ..sota_factory.portfolio_autopilot import PortfolioAutopilotPolicy

DEFAULT_MODEL_ID = "zai/glm-5.3-flash"


@dataclass(frozen=True, slots=True)
class LLMCandidateRequest:
    """One unit of work: ask the model to propose actions for a set of
    ready `(state, applicable_action)` choices over a product frontier.

    `ready_choices` is the caller-supplied enumeration of legal options at
    this frontier (from `fond_hddl_product.ready_action_transitions` /
    `method_refinements`) -- this module never invents legal moves; it only
    asks the model to pick among ones the product construction already
    proved admissible.
    """

    ready_choices: Mapping[StateId, tuple[ActionId, ...]]
    prompt_seed: str
    temperature: float = 0.7
    request_id: str = ""

    def __post_init__(self) -> None:
        if not self.request_id:
            object.__setattr__(self, "request_id", _stable_request_id(self))


def _stable_request_id(request: "LLMCandidateRequest") -> str:
    payload = json.dumps(
        {
            "ready_choices": {
                state: list(actions)
                for state, actions in sorted(request.ready_choices.items())
            },
            "prompt_seed": request.prompt_seed,
            "temperature": request.temperature,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True, slots=True)
class LLMCandidateRawOutput:
    """Untrusted raw text from the model. NOT a `CandidatePolicy`. NOT a
    `BenchmarkVector` input. Quarantined until `admit_llm_candidate` parses
    and admits it."""

    request: LLMCandidateRequest
    raw_text: str
    model_id: str
    latency_s: float
    raw_response_sha256: str = ""

    def __post_init__(self) -> None:
        if not self.raw_response_sha256:
            digest = hashlib.sha256(self.raw_text.encode("utf-8")).hexdigest()
            object.__setattr__(self, "raw_response_sha256", digest)


class LLMCandidateParseError(Exception):
    """Raised when a model's raw output cannot be parsed into a legal
    `{state: action}` mapping restricted to the request's own
    `ready_choices`. Never silently coerced into a policy."""


def parse_llm_output_to_product_args(
    raw: LLMCandidateRawOutput,
) -> Mapping[StateId, ActionId]:
    """Parse `raw.raw_text` as a JSON object mapping state -> action, and
    validate every entry is one of the request's own admitted
    `ready_choices` for that state. Raises `LLMCandidateParseError` on any
    malformed, incomplete, or inadmissible entry -- never drops or
    silently fixes up a bad choice."""

    try:
        parsed = json.loads(raw.raw_text)
    except json.JSONDecodeError as exc:
        raise LLMCandidateParseError(f"not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise LLMCandidateParseError(f"expected a JSON object, got {type(parsed)!r}")

    ready = raw.request.ready_choices
    actions: dict[StateId, ActionId] = {}
    for state, action in parsed.items():
        if state not in ready:
            raise LLMCandidateParseError(f"state {state!r} not in ready_choices")
        if not isinstance(action, str) or action not in ready[state]:
            raise LLMCandidateParseError(
                f"action {action!r} for state {state!r} not in admitted choices "
                f"{ready[state]!r}"
            )
        actions[state] = action
    if not actions:
        raise LLMCandidateParseError("empty candidate policy")
    return actions


def admit_llm_candidate(raw: LLMCandidateRawOutput) -> CandidatePolicy:
    """The only path from raw LLM text to a typed `CandidatePolicy`.
    Internally: parse -> `candidate_policy_over_product`. Raises
    `LLMCandidateParseError` rather than admitting anything malformed."""

    actions = parse_llm_output_to_product_args(raw)
    return candidate_policy_over_product(actions)


@dataclass(frozen=True, slots=True)
class BackoffPolicy:
    """Exponential backoff + jitter for retryable HTTP statuses. Z.ai
    publishes no numeric rate/concurrency ceiling, so this is the real
    mechanism standing in for one."""

    max_retries: int = 5
    base_delay_s: float = 1.0
    max_delay_s: float = 30.0
    jitter: bool = True
    retry_status_codes: tuple[int, ...] = (429, 500, 502, 503, 529)

    def __post_init__(self) -> None:
        if self.max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        if self.base_delay_s <= 0 or self.max_delay_s <= 0:
            raise ValueError("base_delay_s and max_delay_s must be > 0")

    def delay_for_attempt(self, attempt: int) -> float:
        raw_delay = min(self.max_delay_s, self.base_delay_s * (2**attempt))
        if not self.jitter:
            return raw_delay
        return random.uniform(0.0, raw_delay)


def _status_code_of(exc: BaseException) -> int | None:
    """Best-effort extraction of an HTTP status code from a litellm/dspy
    call failure, without assuming a specific exception class -- provider
    SDK exception hierarchies vary and change across versions."""

    for attr in ("status_code", "code"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    response = getattr(exc, "response", None)
    value = getattr(response, "status_code", None)
    if isinstance(value, int):
        return value
    return None


LLMCallFn = Callable[[LLMCandidateRequest, str], Awaitable[str]]


class ConcurrencyProbe:
    """A real, in-process peak-concurrency counter -- used by tests to
    prove `max_concurrency` is respected without mocking the model call
    itself."""

    def __init__(self) -> None:
        self._current = 0
        self.peak = 0

    def enter(self) -> None:
        # Deliberately synchronous/non-awaiting: called from inside a
        # semaphore-guarded coroutine on the same event loop, so plain
        # increment/decrement is race-free here (single-threaded asyncio).
        self._current += 1
        self.peak = max(self.peak, self._current)

    def exit(self) -> None:
        self._current -= 1


async def call_glm_with_backoff(
    request: LLMCandidateRequest,
    *,
    backoff: BackoffPolicy,
    model_id: str = DEFAULT_MODEL_ID,
    concurrency_probe: ConcurrencyProbe | None = None,
    call_fn: LLMCallFn | None = None,
) -> LLMCandidateRawOutput:
    """Call the model with retry/backoff on `backoff.retry_status_codes`.
    Raises the last exception after exhausting retries -- a caller must
    distinguish "genuinely failed" (`PoolRunFailure`) from "no candidate
    produced" rather than have this silently return nothing.

    `call_fn` defaults to a real `dspy.LM(model_id, ...)` call against the
    real Z.ai API (`ZAI_API_KEY` required), matching the provider-string
    shape already used by `sregym_sota/agent.py`'s `dspy.LM(model, ...)`
    call for Groq. Injectable only so a test can wrap the same real call
    with an in-process concurrency counter (`concurrency_probe`) -- never
    to fake the model's response.
    """

    fn = call_fn or _real_glm_call
    last_exc: BaseException | None = None
    for attempt in range(backoff.max_retries + 1):
        if concurrency_probe is not None:
            concurrency_probe.enter()
        started = time.monotonic()
        try:
            raw_text = await fn(request, model_id)
        except Exception as exc:  # noqa: BLE001 - re-raised below if not retryable
            last_exc = exc
            status = _status_code_of(exc)
            if (
                status not in backoff.retry_status_codes
                or attempt == backoff.max_retries
            ):
                raise
            await asyncio.sleep(backoff.delay_for_attempt(attempt))
            continue
        finally:
            if concurrency_probe is not None:
                concurrency_probe.exit()
        latency_s = time.monotonic() - started
        return LLMCandidateRawOutput(
            request=request, raw_text=raw_text, model_id=model_id, latency_s=latency_s
        )
    assert last_exc is not None  # loop always returns or raises
    raise last_exc


async def _real_glm_call(request: LLMCandidateRequest, model_id: str) -> str:
    """A real, blocking `dspy.LM` call to Z.ai, run off the event loop via
    `asyncio.to_thread` so it composes with the semaphore-gated pool below.
    """

    import dspy  # local import: keep this module importable without dspy installed

    api_key = os.environ.get("ZAI_API_KEY")
    if not api_key:
        raise RuntimeError("ZAI_API_KEY is required for a real GLM-5.3-flash call")

    def _call() -> str:
        lm = dspy.LM(model_id, api_key=api_key, max_tokens=2000, cache=False)
        prompt = (
            "You are choosing one action per state for a partially-ordered "
            "planning frontier. Reply with ONLY a JSON object mapping each "
            "state name to exactly one of its listed admitted actions.\n\n"
            f"Ready choices (state -> admitted actions): "
            f"{dict(request.ready_choices)}\n"
            f"Seed: {request.prompt_seed}"
        )
        result = lm(prompt, temperature=request.temperature)
        return str(result[0]) if isinstance(result, list) else str(result)

    return await asyncio.to_thread(_call)


@dataclass(frozen=True, slots=True)
class LLMCandidatePoolPolicy(PortfolioAutopilotPolicy):
    """Same resource-envelope shape as `PortfolioAutopilotPolicy`, with a
    higher default concurrency for this bulk-candidate-producer use case.
    Does not change `PortfolioAutopilotPolicy`'s own default (8) for any
    other caller."""

    max_concurrency: int = 50
    backoff: BackoffPolicy = field(default_factory=BackoffPolicy)


@dataclass(frozen=True, slots=True)
class PoolRunFailure:
    """A retry-exhausted or fatal failure for one request. Explicit and
    counted -- never dropped, never coerced into a candidate or a fake
    benchmark score."""

    request: LLMCandidateRequest
    error: str
    attempts: int


@dataclass(frozen=True, slots=True)
class PoolRunResult:
    admitted: tuple[CandidatePolicy, ...]
    failures: tuple[PoolRunFailure, ...]
    identity_sha256: str


def _pool_identity_sha256(
    requests: tuple[LLMCandidateRequest, ...], model_id: str, backoff: BackoffPolicy
) -> str:
    payload = json.dumps(
        {
            "request_ids": [r.request_id for r in requests],
            "model_id": model_id,
            "backoff": {
                "max_retries": backoff.max_retries,
                "base_delay_s": backoff.base_delay_s,
                "max_delay_s": backoff.max_delay_s,
                "retry_status_codes": list(backoff.retry_status_codes),
            },
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def run_llm_candidate_pool(
    requests: tuple[LLMCandidateRequest, ...],
    *,
    policy: LLMCandidatePoolPolicy | None = None,
    model_id: str = DEFAULT_MODEL_ID,
    concurrency_probe: ConcurrencyProbe | None = None,
    call_fn: LLMCallFn | None = None,
) -> PoolRunResult:
    """Fan out `requests` to at most `policy.max_concurrency` concurrent
    `call_glm_with_backoff` calls (same bounded-concurrency idiom as
    `SOTAPortfolioAutopilot._execute_batch`: `asyncio.Semaphore` +
    `asyncio.gather`, preserving input order for stable evidence identity),
    then admit each successful raw output via `admit_llm_candidate`.

    Every request ends up in exactly one of `admitted` or `failures` --
    `len(admitted) + len(failures) == len(requests)` always."""

    resolved_policy = policy or LLMCandidatePoolPolicy()
    semaphore = asyncio.Semaphore(resolved_policy.max_concurrency)

    async def _one(request: LLMCandidateRequest):
        async with semaphore:
            try:
                raw = await call_glm_with_backoff(
                    request,
                    backoff=resolved_policy.backoff,
                    model_id=model_id,
                    concurrency_probe=concurrency_probe,
                    call_fn=call_fn,
                )
                return admit_llm_candidate(raw)
            except LLMCandidateParseError as exc:
                return PoolRunFailure(request=request, error=str(exc), attempts=1)
            except Exception as exc:  # noqa: BLE001 - captured as an explicit failure
                return PoolRunFailure(
                    request=request,
                    error=repr(exc),
                    attempts=resolved_policy.backoff.max_retries + 1,
                )

    results = await asyncio.gather(*(_one(request) for request in requests))
    admitted = tuple(r for r in results if isinstance(r, CandidatePolicy))
    failures = tuple(r for r in results if isinstance(r, PoolRunFailure))
    assert len(admitted) + len(failures) == len(requests)
    return PoolRunResult(
        admitted=admitted,
        failures=failures,
        identity_sha256=_pool_identity_sha256(
            requests, model_id, resolved_policy.backoff
        ),
    )
