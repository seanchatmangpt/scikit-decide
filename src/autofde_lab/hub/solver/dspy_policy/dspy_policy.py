# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""An LLM-backed policy solver using DSPy.

Follows the same structure as `autofde_lab.hub.solver.simple_greedy.SimpleGreedy`:
a pure-Python `DeterministicPolicySolver` that computes its policy online
(no offline `_solve` computation), except each action is chosen by prompting
a language model through a `dspy.Predict` module instead of by evaluating
transition values.

The language model backend is any OpenAI-compatible chat-completions
endpoint via `dspy.LM` -- by default a local TurboFieldfare server
(https://github.com/drumih/turbo-fieldfare), started separately with
`TurboFieldfareServer --model <path> --port 8080`. No network call or API
key is required for that default.
"""

from __future__ import annotations

import json
import logging
from collections import OrderedDict
from typing import Any, Callable, Optional

import numpy  # noqa: F401 -- must be imported before dspy: dspy's lazy numpy
# loader (dspy.utils.lazy_import) recurses infinitely (RecursionError) if
# numpy is not already a real, fully-loaded module in sys.modules at the
# point dspy is first imported -- reproduced under pytest's import order,
# not present when dspy happens to be imported first in a fresh interpreter.
import dspy
import gymnasium as gym

from autofde_lab import Domain
from autofde_lab.builders.domain import (
    Actions,
    Environment,
    Initializable,
    Markovian,
    MultiAgent,
    Rewards,
    Sequential,
    TransformedObservable,
)
from autofde_lab.core import autocast
from autofde_lab.solvers import DeterministicPolicySolver

logger = logging.getLogger(__name__)

DEFAULT_LM_MODEL = "openai/gemma-4-26b-a4b-it"
DEFAULT_LM_API_BASE = "http://127.0.0.1:8080/v1"
DEFAULT_LM_API_KEY = "local"  # ignored by TurboFieldfare; required by the OpenAI client shape


def default_lm(
    model: str = DEFAULT_LM_MODEL,
    api_base: str = DEFAULT_LM_API_BASE,
    api_key: str = DEFAULT_LM_API_KEY,
) -> dspy.LM:
    """Build a dspy.LM pointed at a local, OpenAI-compatible TurboFieldfare server."""
    return dspy.LM(model, api_base=api_base, api_key=api_key)


class ChooseMove(dspy.Signature):
    """Choose the next move in a game given a short text description of the
    situation and the exact list of legal moves. Reply with exactly one of
    the legal moves, verbatim.
    """

    situation: str = dspy.InputField()
    legal_moves: str = dspy.InputField(desc="comma-separated exact legal move names")
    move: str = dspy.OutputField(desc="exactly one of legal_moves, verbatim")


class GenerateStructuredAction(dspy.Signature):
    """Generate a real action for a domain whose action space cannot be
    enumerated as a short list of legal moves (e.g. a combinatorial or
    continuous action space exposed as a gymnasium space). Reply with a
    single JSON object matching `action_schema` exactly: same keys, integer
    values within the stated bounds, no markdown code fences, no commentary.
    """

    situation: str = dspy.InputField()
    action_schema: str = dspy.InputField(
        desc="JSON-ish description of the required action fields and their allowed integer ranges"
    )
    action_json: str = dspy.OutputField(
        desc="a single real JSON object matching action_schema exactly -- no markdown fences, no prose"
    )


class D(
    Domain,
    MultiAgent,
    Sequential,
    Environment,
    Actions,
    Initializable,
    Markovian,
    TransformedObservable,
    Rewards,
):
    pass


def _describe_gym_dict_of_discrete_schema(gym_space: gym.Space) -> tuple[str, list[str]]:
    """Build a short textual schema description for a gymnasium action space,
    for use as the `action_schema` field fed to `GenerateStructuredAction`.

    Only `gym.spaces.Dict` of `gym.spaces.Discrete` sub-spaces is supported --
    the one real, empirically-verified shape (`RDDLDomain`'s per-boolean-fluent
    action space, e.g. TowerOfHanoi_arcade's `move___dX__rY` fields) DSPyPolicy
    can safely turn into a schema an LLM can fill in and that can be validated
    with `action_space.contains(...)` afterwards. Raises `NotImplementedError`
    for any other real gymnasium space shape rather than fabricating a schema
    for a shape never verified to round-trip through generation + validation.
    """
    if isinstance(gym_space, gym.spaces.Dict) and all(
        isinstance(sub, gym.spaces.Discrete) for sub in gym_space.spaces.values()
    ):
        keys = list(gym_space.spaces.keys())
        fields = ", ".join(
            f'"{k}": <integer in [0, {gym_space.spaces[k].n - 1}]>' for k in keys
        )
        return "{" + fields + "}", keys
    raise NotImplementedError(
        f"DSPyPolicy's generative action path only supports a gym.spaces.Dict "
        f"of gym.spaces.Discrete sub-spaces; got real gymnasium space "
        f"{gym_space!r}, which is not yet supported."
    )


class DSPyPolicy(DeterministicPolicySolver):
    """A DeterministicPolicySolver whose action at every step is chosen by a
    real call to a real language model through DSPy.

    Works with both SingleAgent domains (e.g. `Maze`, `SimpleGridWorld`,
    `MasterMind` -- where `D.T_agent[X]` collapses to plain `X`) and
    MultiAgent domains (e.g. `RockPaperScissors` -- where observations and
    action spaces are `{agent_name: ...}` dicts); the two shapes are detected
    at runtime rather than assumed.

    Three real action-resolution strategies are tried, in order, per agent
    (checked via `_check_domain_additional` and applied at each step by
    `_resolve_action`):

    1. **Static enumeration** -- `domain.get_action_space()` returns a space
       with a real `get_elements()` (e.g. `Maze`, `RockPaperScissors`): list
       the legal moves and ask the LLM to pick one verbatim.
    2. **Per-state enumeration** -- the static action space is not
       enumerable (e.g. `PDDLDomain`'s `ImplicitSpace`, or scheduling
       domains like `RCPSP`/`MRCPSP` whose `get_action_space()` returns
       `None`), but `domain.get_applicable_actions(observation)` returns a
       real, finite space at the current state: list *those* legal moves
       and ask the LLM to pick one verbatim.
    3. **Structured generation** -- neither of the above is enumerable
       (e.g. `RDDLDomain`'s combinatorial action space, exposed as a real
       gymnasium `Dict` of `Discrete` sub-spaces with no `get_elements()`):
       ask the LLM to generate a JSON object matching the action's real
       field schema, then validate it against the domain's real
       `action_space.contains(...)` before returning it -- retrying once
       with the real validation error fed back on an invalid generation,
       and raising a clear error (never a fabricated default action) if it
       still doesn't validate.
    """

    T_domain = D

    def __init__(
        self,
        domain_factory: Callable[[], Domain],
        lm: Optional[dspy.LM] = None,
        situation_formatter: Callable[[Any, str], str] = (
            lambda observation, agent: f"You are playing as '{agent}'. "
            f"Your last observation was: {observation!r}."
        ),
    ) -> None:
        """Construct a DSPyPolicy solver instance.

        # Parameters
        domain_factory: The lambda function to create a domain instance.
        lm: The dspy.LM to query for every action. Defaults to `default_lm()`
            (a local TurboFieldfare server on 127.0.0.1:8080).
        situation_formatter: Builds the natural-language `situation` field
            passed to the LLM for a given (observation, agent_name) pair.
            Override this to give the model richer context for other domains.
        """
        super().__init__(domain_factory=domain_factory)
        self._lm = lm or default_lm()
        self._predict = dspy.Predict(ChooseMove)
        self._generate_predict = dspy.Predict(GenerateStructuredAction)
        self._situation_formatter = situation_formatter
        self._domain = None

    @classmethod
    def _check_single_action_space_additional(cls, domain: D, action_space: Any) -> bool:
        """Real per-agent check for the three action-resolution strategies
        documented on the class: return True as soon as one of them is real
        and available for this `action_space`/`domain` pair.
        """
        if hasattr(action_space, "get_elements"):
            return True
        gym_space = getattr(action_space, "_gym_space", None)
        if gym_space is not None:
            try:
                _describe_gym_dict_of_discrete_schema(gym_space)
                return True
            except NotImplementedError:
                return False
        # Neither the static action space nor a recognized gymnasium
        # structure is enumerable/describable -- try the real, state-
        # dependent applicable-actions space (e.g. PDDLDomain, RCPSP/
        # MRCPSP), which is only meaningful once the domain has a real
        # current state.
        try:
            domain.reset()
            applicable = domain.get_applicable_actions()
            return hasattr(applicable, "get_elements")
        except Exception:
            return False

    @classmethod
    def _check_domain_additional(cls, domain: D) -> bool:
        get_action_space = autocast(domain.get_action_space, domain, cls.T_domain)
        action_space = get_action_space()
        # MultiAgent domains (e.g. RockPaperScissors): get_action_space()
        # returns a dict of {agent_name: space}. SingleAgent domains (e.g.
        # Maze, SimpleGridWorld, MasterMind): D.T_agent[X] collapses to plain
        # X, so get_action_space() returns a single space directly, not a
        # dict. Detect which shape we actually have by duck-typing on
        # `.items()` -- verified empirically against real instances of both
        # kinds above -- rather than assuming the multi-agent dict shape.
        if hasattr(action_space, "items"):
            return all(
                cls._check_single_action_space_additional(domain, space)
                for space in action_space.values()
            )
        else:
            return cls._check_single_action_space_additional(domain, action_space)

    def _solve(self) -> None:
        self._domain = self._domain_factory()

    def _choose_move(self, obs: Any, agent: str, legal: Any) -> Any:
        legal_by_name = {str(m): m for m in legal}
        with dspy.context(lm=self._lm):
            prediction = self._predict(
                situation=self._situation_formatter(obs, agent),
                legal_moves=", ".join(legal_by_name),
            )
        chosen_text = prediction.move.strip()
        move = legal_by_name.get(chosen_text)
        if move is None:
            # Real, observable LLM failure -- do not silently default to
            # an arbitrary move. Try a case-insensitive/substring match
            # before giving up, since models often add stray punctuation.
            lowered = chosen_text.lower()
            candidates = [m for name, m in legal_by_name.items() if name.lower() in lowered]
            if len(candidates) != 1:
                # Real observed failure mode (multi-line `Action` reprs,
                # e.g. RCPSP/MRCPSP's scheduling actions, or UPDomain's
                # multi-line `action <name> { ... }` block): the model
                # reproduces only a short, unambiguous fragment of the
                # real legal-move text (a truncated prefix, or just the
                # action's own short name embedded inside a longer repr),
                # so neither exact match nor `name in chosen_text` finds
                # it. Fall back to a whitespace-normalized, case-
                # insensitive substring match in either direction.
                normalized_chosen = " ".join(lowered.split())
                candidates = [
                    m
                    for name, m in legal_by_name.items()
                    if normalized_chosen in " ".join(name.lower().split())
                ]
            if len(candidates) == 1:
                move = candidates[0]
            else:
                raise ValueError(
                    f"DSPyPolicy: model returned {chosen_text!r} for agent "
                    f"{agent!r}, which does not match any legal move in "
                    f"{list(legal_by_name)}."
                )
        return move

    def _generate_action(self, obs: Any, agent: str, action_space: Any) -> Any:
        """Real structured-generation path (strategy 3 in the class
        docstring): ask the LLM to fill in a JSON object matching the real
        gymnasium action schema, then validate it against the domain's real
        `action_space.contains(...)`. Retries once with the real validation
        error fed back; raises a clear error on a second failure rather than
        silently substituting a fabricated default action.
        """
        gym_space = action_space._gym_space
        schema, keys = _describe_gym_dict_of_discrete_schema(gym_space)
        situation = self._situation_formatter(obs, agent)
        last_raw: Optional[str] = None
        error_feedback: Optional[str] = None
        for _attempt in range(2):
            prompt_situation = situation
            if error_feedback is not None:
                prompt_situation = (
                    f"{situation}\n\nYour previous answer {last_raw!r} was "
                    f"invalid: {error_feedback} Try again, and reply with "
                    f"only the corrected JSON object."
                )
            with dspy.context(lm=self._lm):
                prediction = self._generate_predict(
                    situation=prompt_situation, action_schema=schema
                )
            raw = prediction.action_json.strip()
            last_raw = raw
            text = raw
            if text.startswith("```"):
                text = text.strip("`")
                newline = text.find("\n")
                if newline != -1:
                    text = text[newline + 1 :]
            start, end = text.find("{"), text.rfind("}")
            if start != -1 and end != -1:
                text = text[start : end + 1]
            try:
                parsed = json.loads(text)
                candidate = OrderedDict((k, int(parsed[k])) for k in keys)
            except Exception as e:
                error_feedback = (
                    f"could not be parsed as a JSON object matching schema "
                    f"{schema}: {e!r}."
                )
                continue
            if action_space.contains(candidate):
                return candidate
            error_feedback = (
                f"parsed as {dict(candidate)!r}, but that is not contained "
                f"in the real action space (schema: {schema})."
            )
        raise ValueError(
            f"DSPyPolicy: model failed to generate a real action for agent "
            f"{agent!r} matching schema {schema} after 2 attempts; last raw "
            f"output was {last_raw!r}."
        )

    def _resolve_action(
        self, domain: D, obs: Any, agent: str, action_space: Any, is_cast: bool
    ) -> Any:
        """Dispatch to whichever of the three real action-resolution
        strategies documented on the class is actually available for this
        `action_space` -- checked in the same order, and against the same
        real predicates, as `_check_single_action_space_additional`.

        `is_cast` mirrors the identity check already done in
        `_get_next_action` for `get_action_space`: when `domain is
        self._domain`, `get_applicable_actions()` -- like `get_action_space`
        -- is called with no `memory` argument so it falls back to the
        domain's own real, already-current `_memory` (set by the most
        recent real `reset()`/`step()` on this exact domain instance,
        verified empirically), sidestepping the MultiAgent-dict-shape
        mismatch between a plain per-agent `obs` and what the mutated,
        cast-in-place method would otherwise expect as an explicit
        argument. A `domain` passed in explicitly by rollout machinery is
        the original, never-cast instance, so its own current `_memory` is
        the real per-agent state already and the same no-argument call
        works identically there too -- verified empirically, not assumed,
        against `PDDLDomain` and `RCPSP`/`MRCPSP`.
        """
        if hasattr(action_space, "get_elements"):
            return self._choose_move(obs, agent, action_space.get_elements())
        gym_space = getattr(action_space, "_gym_space", None)
        if gym_space is not None:
            return self._generate_action(obs, agent, action_space)
        if is_cast:
            applicable = domain.get_applicable_actions()
        else:
            get_applicable_actions = autocast(
                domain.get_applicable_actions, domain, self.T_domain
            )
            applicable = get_applicable_actions()
        if hasattr(applicable, "items"):
            applicable = applicable[agent]
        if hasattr(applicable, "get_elements"):
            return self._choose_move(obs, agent, applicable.get_elements())
        raise ValueError(
            f"DSPyPolicy: no real, enumerable, or generatable action space "
            f"available for agent {agent!r} (static action space "
            f"{action_space!r} has no get_elements() and is not a "
            f"recognized gymnasium structure, and "
            f"domain.get_applicable_actions(...) returned {applicable!r}, "
            f"which also has no get_elements())."
        )

    def _get_next_action(
        self, observation: D.T_agent[D.T_observation], domain: Optional[D] = None
    ) -> D.T_agent[D.T_concurrency[D.T_event]]:
        if domain is None:
            domain = self._domain
            logger.warning(
                "Rollout domain not given. Using domain seen during solve instead."
            )
        # `self._domain` (built by `_solve()` via `self._domain_factory()`) has
        # already had its own autocastable methods (including
        # `get_action_space`) mutated in place by `Solver.__init__`'s
        # `cast_domain_factory` to present T_domain's shape directly --
        # verified empirically: for a SingleAgent domain like Maze,
        # `self._domain.get_action_space()` already returns the
        # MultiAgent-dict shape `{"agent": space}` with no further casting.
        # Applying `autocast()` again on top of that already-cast bound
        # method double-wraps it into `{"agent": {"agent": space}}`. A
        # `domain` passed in explicitly by the rollout machinery (e.g.
        # `autofde_lab.utils.rollout`), by contrast, is the original, never-cast
        # domain instance and does need the explicit autocast here to reach
        # T_domain's shape. Distinguish the two by identity rather than
        # assuming either is always the case.
        if domain is self._domain:
            action_space = domain.get_action_space()
        else:
            get_action_space = autocast(domain.get_action_space, domain, self.T_domain)
            action_space = get_action_space()

        # Same MultiAgent-dict vs SingleAgent-collapsed detection as
        # `_check_domain_additional`, applied to both the observation and the
        # action space (they always agree in shape for a given domain,
        # verified empirically against Maze/SimpleGridWorld/MasterMind
        # (single) and RockPaperScissors (multi)).
        is_cast = domain is self._domain
        if hasattr(action_space, "items"):
            actions: dict[Any, Any] = {}
            for agent, obs in observation.items():
                actions[agent] = self._resolve_action(
                    domain, obs, agent, action_space[agent], is_cast
                )
            return actions
        else:
            return self._resolve_action(
                domain, observation, "agent", action_space, is_cast
            )

    def _is_policy_defined_for(self, observation: D.T_agent[D.T_observation]) -> bool:
        return True
