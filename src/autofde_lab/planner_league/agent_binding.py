"""Agent identity, kept distinct from Planner, Policy, and Role.

Capability 2 of V2030.1.1 requires preserving the distinction
``Planner != Policy != Role != Agent``. ``core.py`` already keeps Planner
(``PolicySpec.planner_id``), Policy (``PolicySpec`` as a whole), and Role
(``role_id`` / ``ROLE_SPECS``) as three independently-varying identities, but
no typed Agent object exists anywhere in this package: two distinct agents
playing the same role with the same policy were previously indistinguishable.

This module adds the fourth identity as a standalone, frozen representation
that rides *beside* a ``LeagueMatch``, never inside it — ``core.py`` is not
modified. This module manufactures candidate identity only; it confers no
authority and carries no receipt or admission semantics (see
``src/autofde_lab/planner_league/core.py`` module docstring and this repo's
actuation boundary).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from .catalog import ROLE_SPECS
from .core import LeagueMatch, PolicySpec


@dataclass(frozen=True, slots=True)
class AgentBinding:
    """A stable agent identity bound to one role and one policy.

    ``agent_id``, ``role_id``, and ``policy`` are three independently-varying
    axes; ``information_partition_id`` mirrors ``LeagueMatch``'s own field of
    the same name so a binding can be checked for consistency against a match
    it participates in.
    """

    agent_id: str
    role_id: str
    policy: PolicySpec
    information_partition_id: str = "shared"

    def __post_init__(self) -> None:
        if self.role_id not in ROLE_SPECS:
            raise ValueError(f"REFUSED:UNKNOWN_ROLE:{self.role_id}")

    def _canonical_json(self) -> str:
        return json.dumps(
            {
                "agent_id": self.agent_id,
                "role_id": self.role_id,
                "policy": {
                    "planner_id": self.policy.planner_id,
                    "parameters": self.policy.parameters,
                    "objective_id": self.policy.objective_id,
                    "observation_projection_id": self.policy.observation_projection_id,
                    "action_projection_id": self.policy.action_projection_id,
                    "budget_id": self.policy.budget_id,
                },
                "information_partition_id": self.information_partition_id,
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    @property
    def identity_sha256(self) -> str:
        """Stable agent-binding identity; explicitly not an execution receipt."""
        return hashlib.sha256(self._canonical_json().encode("utf-8")).hexdigest()

    @property
    def policy_identity_sha256(self) -> str:
        """Identity of the policy axis alone, independent of agent_id/role_id."""
        return hashlib.sha256(
            json.dumps(
                {
                    "planner_id": self.policy.planner_id,
                    "parameters": self.policy.parameters,
                    "objective_id": self.policy.objective_id,
                    "observation_projection_id": self.policy.observation_projection_id,
                    "action_projection_id": self.policy.action_projection_id,
                    "budget_id": self.policy.budget_id,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()


def identity_quadruple(binding: AgentBinding) -> tuple[str, str, str, str]:
    """Return the four independently-varying identity components of a binding.

    ``(agent_id, role_id, planner_id, policy_identity_sha256)`` — Agent, Role,
    Planner, and Policy respectively, so callers can assert that varying one
    axis leaves the other three unchanged.
    """
    return (
        binding.agent_id,
        binding.role_id,
        binding.policy.planner_id,
        binding.policy_identity_sha256,
    )


def match_from_bindings(
    world_id: str,
    left: AgentBinding,
    right: AgentBinding,
    *,
    authority_context_ref: str | None = None,
) -> LeagueMatch:
    """Build a real ``LeagueMatch`` from two ``AgentBinding``s.

    A free function rather than a ``LeagueMatch`` classmethod, so ``core.py``
    stays untouched. Agent identity (``left.agent_id`` / ``right.agent_id``)
    is not passed into ``LeagueMatch`` at all: it rides beside the resulting
    match, never inside its experiment identity or
    ``as_gymact_candidate()`` payload.
    """
    information_partition_id = left.information_partition_id
    if right.information_partition_id != information_partition_id:
        raise ValueError(
            "REFUSED:INFORMATION_PARTITION_MISMATCH:"
            f"{left.information_partition_id}!={right.information_partition_id}"
        )
    return LeagueMatch(
        world_id=world_id,
        left_role_id=left.role_id,
        left_policy=left.policy,
        right_role_id=right.role_id,
        right_policy=right.policy,
        information_partition_id=information_partition_id,
        authority_context_ref=authority_context_ref,
    )
