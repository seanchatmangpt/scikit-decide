# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""The only coupling between the agent runtime and :func:`autofde_lab.utils.rollout`.

Why there is a proxy at all
---------------------------
``RolloutCallback.at_episode_step`` fires *after* the action has been applied and
hands back the **action**, not the node that produced it. Action -> node is not
injective: two enabled nodes may carry the same label, and then no amount of
post-hoc reasoning recovers which one advanced. Inferring it would fabricate the
one fact the ledger exists to record.

So the correspondence is established on the *other* side of the act. A thin
:class:`Policies` proxy wraps ``sample_action``: it asks the real policy for an
action, resolves that action against the epoch's enabled set **before** the
domain steps, and registers an intent. The callback then only ever *commits* an
outstanding intent — it never resolves anything.

When resolution is ambiguous (two enabled nodes match) or empty (none match),
this refuses with ``SKD-AGENT-007`` / ``BLOCKED:ACTION_NODE_UNRESOLVED``. There
is deliberately no inference-based fallback; a plausible guess here is worse
than a refusal, because it is indistinguishable from a correct answer downstream.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

from autofde_lab.agent.refusals import AgentRefusal, AgentRefusalCode
from autofde_lab.powl.algebra import Atom
from autofde_lab.powl.executor import NodePath, node_at
from autofde_lab.utils import RolloutCallback

if TYPE_CHECKING:  # pragma: no cover - typing only
    from autofde_lab.agent.epoch import DecisionEpoch
    from autofde_lab.agent.session import AgentSession

__all__ = [
    "action_labels",
    "resolve_enabled_node",
    "IntentRegisteringPolicies",
    "SessionRolloutCallback",
]


def action_labels(action: Any) -> frozenset[str]:
    """Candidate label strings for ``action``.

    Deliberately generous on the *label* side and strict on the *count* side:
    matching more names cannot create a wrong answer, only an ambiguity, and an
    ambiguity is refused.
    """
    out: set[str] = set()
    candidates = [action]
    if isinstance(action, dict):  # multi-agent: one action per agent
        candidates = list(action.values())
    for candidate in candidates:
        if isinstance(candidate, (list, tuple)):  # concurrency wrapper
            inner = list(candidate)
        else:
            inner = [candidate]
        for item in inner:
            name = getattr(item, "name", None)
            if isinstance(name, str):
                out.add(name)
            out.add(str(item))
    return frozenset(out)


def _matches(atom: Atom, action: Any, labels: frozenset[str]) -> bool:
    if atom.action is not None:
        try:
            return bool(atom.action == action)
        except Exception:  # pragma: no cover - exotic __eq__
            return False
    return atom.label in labels


def resolve_enabled_node(epoch: DecisionEpoch, action: Any) -> NodePath:
    """The single enabled node corresponding to ``action``.

    Refuses ``SKD-AGENT-007`` on zero matches *and* on more than one. The second
    case is the non-injectivity this module exists to refuse to paper over.
    """
    live = sorted(epoch.enabled())
    labels = action_labels(action)
    matches = [
        path
        for path in live
        if isinstance(node_at(epoch.model, path), Atom)
        and _matches(node_at(epoch.model, path), action, labels)
    ]
    if len(matches) == 1:
        return matches[0]
    reason = "no enabled node matches" if not matches else "action->node is not injective"
    raise AgentRefusal(
        AgentRefusalCode.ACTION_NODE_UNRESOLVED,
        f"{reason}; the node is never inferred from the action",
        details={
            "epoch_id": epoch.epoch_id,
            "action_labels": sorted(labels),
            "enabled": [list(p) for p in live],
            "matches": [list(p) for p in matches],
        },
    )


class IntentRegisteringPolicies:
    """A ``Policies``-shaped proxy that registers an intent before the act.

    Every attribute other than ``sample_action`` is delegated to the wrapped
    policy, so a real solver keeps behaving like itself.
    """

    def __init__(self, policy: Any, session: AgentSession) -> None:
        self._policy = policy
        self._session = session

    def sample_action(self, observation: Any, domain: Optional[Any] = None) -> Any:
        try:
            action = self._policy.sample_action(observation, domain=domain)
        except TypeError:
            action = self._policy.sample_action(observation)
        # Ordering is the whole point: the intent is written before the caller
        # gets the action back, therefore before the domain can step on it.
        self._session._register_intent(action)
        return action

    def is_policy_defined_for(self, observation: Any) -> bool:
        checker = getattr(self._policy, "is_policy_defined_for", None)
        return True if checker is None else bool(checker(observation))

    def __getattr__(self, name: str) -> Any:
        return getattr(self._policy, name)


class SessionRolloutCallback(RolloutCallback):
    """Commits outstanding intents. Resolves nothing, infers nothing."""

    def __init__(self, session: AgentSession) -> None:
        self._session = session
        self.steps = 0

    def at_episode_step(
        self,
        i_episode: int,
        step: int,
        domain: Any,
        solver: Any,
        action: Any,
        outcome: Any,
    ) -> bool:
        self._session._commit_intent(outcome=outcome, detail="AT_EPISODE_STEP")
        self.steps += 1
        return False

    def at_episode_end(self) -> None:
        # ``rollout`` breaks out of the step loop on termination *before* calling
        # ``at_episode_step``, so the final action of a terminating episode has an
        # intent that never reaches the per-step hook. Reaching here proves the
        # step body ran, so committing is observation, not assumption.
        if self._session._has_outstanding_intent():
            self._session._commit_intent(outcome=None, detail="AT_EPISODE_END_TERMINAL")
            self.steps += 1
