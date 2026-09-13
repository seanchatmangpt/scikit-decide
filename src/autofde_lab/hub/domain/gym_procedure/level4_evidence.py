# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Typed Level 4 evidence, constructible ONLY from durable OCEL 2.0 artifacts.

`crown_evidence.py` builds the same four *claims* from live runtime objects
(`gymact` `ConformanceResult`, `ReplayReport`, in-memory receipts). This
module is the durable-artifact counterpart: it constructs evidence from a
persisted trial directory alone, through
:func:`standalone_verifier.verify`, without importing the producing runtime.
The two are not parallel bookkeeping of the same fact -- they are the actor's
self-report and the third party's reconstruction, and only the latter can
make standing external to the actor
(`.claude/rules/no-dual-bookkeeping.md`).

The one law underneath every design decision here:

    Never manufacture semantics from absence, coincidence, prediction, or a
    secondary representation when the primary evidence can carry the relation
    itself.

Consequences that are structural, not stylistic:

* **No booleans.** No type here has a ``success``, ``passed``,
  ``goal_reached``, ``ok``, ``valid`` or ``is_alive`` field, and
  :class:`Level4AliveEvidence` cannot be built from any. Its constructor
  demands the two evidence *objects*, and rejects anything else at
  construction time -- ``Level4AliveEvidence(success=True)`` is a
  ``TypeError`` for an unknown keyword, and
  ``Level4AliveEvidence(True, True)`` is a ``TypeError`` for a wrong type.
* **No ``__bool__``.** Exactly as :class:`crown_factor.CrownFactor` denies
  ``if factor:`` a plausible verdict, ``if evidence:`` must never compile to
  a pass. Callers ``isinstance``/``match`` on the type.
* **Conformance and achievement are different claims.** A perfectly lawful
  execution that does not reach the admitted goal is
  :class:`ConformantButGoalUnmetEvidence`. There is no path, coercion, or
  helper that turns one into :class:`Level4AliveEvidence`.
* **UNKNOWN and NOT_ALIVE are both first class and never collapse.**
  :class:`UnknownRelationEvidence` means a required relation is *not
  established* -- neither a pass nor a failure -- and always names the exact
  relation. :class:`NotAliveEvidence` means the durable evidence establishes
  a *contradictory* condition (a self-certified postcondition, an explicitly
  refuted goal). Absence never becomes the latter.

The seven process relations are **not** re-derived here: they are consumed
verbatim from :data:`standalone_verifier.REQUIRED_CHAIN` and the
:class:`standalone_verifier.Edge` objects `verify()` returns, so the verifier
and these constructors cannot drift. The goal leg
(:data:`REQUIRED_GOAL_CHAIN`) is read from the *same* durable OCEL document
with the *same* explicit-typed-edge discipline, anchored to the identities
the verifier already carried forward -- never from timestamps, ordering, or
adjacency.

See `.claude/rules/level4-completion-law.md`,
`.claude/rules/absence-is-not-evidence.md`,
`.claude/rules/no-dual-bookkeeping.md`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

from autofde_lab.hub.domain.gym_procedure.standalone_verifier import (
    REQUIRED_CHAIN,
    Edge,
    IndependentStanding,
    verify,
)

#: The goal leg, in the same (relation, question) shape as
#: :data:`standalone_verifier.REQUIRED_CHAIN`. The admitted ``Goal`` is a
#: first-class durable object; runtime ``final_state`` may not establish
#: standing, so the independent ``PostconditionObservation`` must relate to
#: THAT exact goal identity by an explicit typed edge.
REQUIRED_GOAL_CHAIN: tuple[tuple[str, str], ...] = (
    ("task->goal", "is there an admitted Goal object bound to this exact Task?"),
    ("goal->plan_candidate", "was the plan candidate selected FOR that exact goal?"),
    (
        "postcondition->goal",
        "did the independent observation of THIS actuation relate to THAT exact goal?",
    ),
)

#: Qualifier of the explicit edge asserting that an independent observation
#: established the admitted goal.
GOAL_ESTABLISHED_QUALIFIER = "establishes_goal"
#: Qualifier of the explicit edge asserting the observation **refuted** it.
#: This is a real, checked, negative observation -- not an absence.
GOAL_REFUTED_QUALIFIER = "refutes_goal"

_GOAL_OF_TASK_QUALIFIER = "goal_of_task"
_CANDIDATE_TARGETS_GOAL_QUALIFIER = "targets_goal"


class EvidenceConstructionError(TypeError):
    """Raised when a typed evidence object is asked to exist without the
    evidence that defines it. Deliberately a ``TypeError``: constructing
    ``Level4AliveEvidence`` from booleans is a type error, not a value that
    happens to be wrong."""


# ── identity ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class EpisodeIdentity:
    """Where the durable evidence lives. Every evidence object carries this so
    two evidence objects from different episodes cannot be composed."""

    trial_dir: str
    ocel_path: str

    def __post_init__(self) -> None:
        if not self.trial_dir:
            raise EvidenceConstructionError("EPISODE_IDENTITY_REQUIRES_TRIAL_DIR")
        if not self.ocel_path:
            raise EvidenceConstructionError("EPISODE_IDENTITY_REQUIRES_OCEL_PATH")


# ── the two non-outcomes, both first class ────────────────────────────────


@dataclass(frozen=True)
class UnknownRelationEvidence:
    """A required relation is NOT ESTABLISHED. Never a pass, never a failure.

    ``relation`` is mandatory and must name one of the required relations (or
    a named absent artifact) -- "something is missing" is not a finding, "the
    `authority->actuation` relation is not established" is.
    """

    relation: str
    basis: str
    episode_ref: str

    def __post_init__(self) -> None:
        if not self.relation:
            raise EvidenceConstructionError("UNKNOWN_EVIDENCE_MUST_NAME_THE_RELATION")
        if not self.basis:
            raise EvidenceConstructionError(
                f"UNKNOWN_EVIDENCE_MUST_STATE_WHY: {self.relation!r} names no basis"
            )

    def describe(self) -> str:
        return f"UNKNOWN:{self.relation}: {self.basis} [{self.episode_ref}]"


@dataclass(frozen=True)
class NotAliveEvidence:
    """The durable evidence establishes a CONTRADICTORY / unlawful condition.

    Distinct from :class:`UnknownRelationEvidence` in kind, not degree: here
    something was observed and it refutes the claim (the observer identity is
    the actuator identity; the admitted goal was explicitly refuted). Never
    produced from a missing edge.
    """

    relation: str
    contradiction: str
    episode_ref: str
    witness: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.relation:
            raise EvidenceConstructionError("NOT_ALIVE_EVIDENCE_MUST_NAME_THE_RELATION")
        if not self.contradiction:
            raise EvidenceConstructionError(
                f"NOT_ALIVE_EVIDENCE_MUST_STATE_THE_CONTRADICTION: {self.relation!r}"
            )
        if not self.witness:
            # A contradiction with no witness edge is an assertion, not an
            # observation -- exactly the self-certification these types exist
            # to prevent.
            raise EvidenceConstructionError(
                f"NOT_ALIVE_EVIDENCE_REQUIRES_WITNESS: {self.relation!r} claims a "
                f"contradiction but names no durable edge establishing it"
            )

    def describe(self) -> str:
        return f"NOT_ALIVE:{self.relation}: {self.contradiction} [{self.episode_ref}]"


# ── the four evidence types ───────────────────────────────────────────────


@dataclass(frozen=True)
class ConformantExecutionEvidence:
    """THE PROCESS CONFORMED -- and nothing more.

    Every relation in :data:`standalone_verifier.REQUIRED_CHAIN` was
    established by an explicit typed edge in the durable OCEL, reconstructed
    by a verifier that did not import the producing runtime. Says NOTHING
    about whether the admitted goal was achieved; that is
    :class:`GoalConsequenceEvidence`'s separate claim.

    Constructed only from real :class:`standalone_verifier.Edge` objects. The
    constructor re-checks the full required set rather than trusting the
    caller to have filtered it, so an evidence object cannot exist while a
    relation it asserts does not.
    """

    episode: EpisodeIdentity
    chain: tuple[Edge, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.episode, EpisodeIdentity):
            raise EvidenceConstructionError(
                f"CONFORMANT_EVIDENCE_REQUIRES_EPISODE_IDENTITY: got "
                f"{type(self.episode).__name__}"
            )
        by_name = {}
        for edge in self.chain:
            if not isinstance(edge, Edge):
                raise EvidenceConstructionError(
                    f"CONFORMANT_EVIDENCE_REQUIRES_REAL_EDGES: got {type(edge).__name__}"
                )
            by_name[edge.name] = edge
        for name, _question in REQUIRED_CHAIN:
            if name not in by_name:
                raise EvidenceConstructionError(f"CONFORMANT_EVIDENCE_MISSING_RELATION:{name}")
            if not by_name[name].established:
                raise EvidenceConstructionError(
                    f"CONFORMANT_EVIDENCE_RELATION_NOT_ESTABLISHED:{name}: "
                    f"{by_name[name].basis}"
                )

    def edge(self, name: str) -> Edge:
        for e in self.chain:
            if e.name == name:
                return e
        raise KeyError(name)

    def describe(self) -> list[str]:
        return [f"OK {e.name}: {e.basis}" for e in self.chain]


@dataclass(frozen=True)
class GoalConsequenceEvidence:
    """THE ADMITTED GOAL WAS INDEPENDENTLY OBSERVED ACHIEVED.

    Carries the exact identities the relation ran through: the admitted
    ``Task``, the admitted ``Goal``, the ``Actuation`` that was committed AND
    authorized, and the ``PostconditionObservation`` -- distinct from that
    actuation -- whose explicit ``establishes_goal`` edge points at THAT
    goal. Never a ``final_state == target`` comparison, never a boolean read
    off a summary.
    """

    episode: EpisodeIdentity
    task_id: str
    goal_id: str
    actuation_id: str
    observation_id: str
    goal_edges: tuple[Edge, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.episode, EpisodeIdentity):
            raise EvidenceConstructionError(
                f"GOAL_EVIDENCE_REQUIRES_EPISODE_IDENTITY: got {type(self.episode).__name__}"
            )
        for field_name in ("task_id", "goal_id", "actuation_id", "observation_id"):
            if not getattr(self, field_name):
                raise EvidenceConstructionError(f"GOAL_EVIDENCE_REQUIRES_IDENTITY:{field_name}")
        if self.observation_id == self.actuation_id:
            raise EvidenceConstructionError(
                "SELF_CERTIFIED_POSTCONDITION: the observer identity is the actuation "
                "identity; that is not an independent observation"
            )
        by_name = {e.name: e for e in self.goal_edges}
        for name, _question in REQUIRED_GOAL_CHAIN:
            if name not in by_name:
                raise EvidenceConstructionError(f"GOAL_EVIDENCE_MISSING_RELATION:{name}")
            if not by_name[name].established:
                raise EvidenceConstructionError(
                    f"GOAL_EVIDENCE_RELATION_NOT_ESTABLISHED:{name}: {by_name[name].basis}"
                )


@dataclass(frozen=True)
class ConformantButGoalUnmetEvidence:
    """LAWFUL EXECUTION, GOAL NOT ACHIEVED -- a REAL result, not a failure.

    Requires a real :class:`ConformantExecutionEvidence` (the process really
    did conform) plus a real :class:`NotAliveEvidence` witnessing the
    explicit ``refutes_goal`` edge. It refuses to be built from an absence:
    an episode whose goal relation is merely *missing* is
    :class:`UnknownRelationEvidence`, because "we did not observe the goal"
    and "we observed the goal was not reached" are different findings.

    There is deliberately no method, property, or helper on this type that
    yields :class:`Level4AliveEvidence`.
    """

    conformant: ConformantExecutionEvidence
    unmet: NotAliveEvidence

    def __post_init__(self) -> None:
        if not isinstance(self.conformant, ConformantExecutionEvidence):
            raise EvidenceConstructionError(
                f"GOAL_UNMET_EVIDENCE_REQUIRES_CONFORMANT_EXECUTION_EVIDENCE: got "
                f"{type(self.conformant).__name__}"
            )
        if not isinstance(self.unmet, NotAliveEvidence):
            raise EvidenceConstructionError(
                f"GOAL_UNMET_EVIDENCE_REQUIRES_OBSERVED_REFUTATION: got "
                f"{type(self.unmet).__name__}; an absent goal relation is UNKNOWN, "
                f"not an unmet goal"
            )


@dataclass(frozen=True)
class Level4AliveEvidence:
    """BOTH claims, composed -- the only green verdict.

    The constructor requires the two evidence OBJECTS. There is no
    ``success``, no ``goal_reached``, no flag, and no classmethod that
    accepts one; passing booleans raises
    :class:`EvidenceConstructionError`. Both objects must also name the SAME
    episode, so a conformant execution from one trial cannot be married to a
    goal observation from another.
    """

    conformant: ConformantExecutionEvidence
    goal: GoalConsequenceEvidence

    def __post_init__(self) -> None:
        if not isinstance(self.conformant, ConformantExecutionEvidence):
            raise EvidenceConstructionError(
                f"LEVEL4_ALIVE_REQUIRES_CONFORMANT_EXECUTION_EVIDENCE: got "
                f"{type(self.conformant).__name__}; a boolean is not evidence"
            )
        if not isinstance(self.goal, GoalConsequenceEvidence):
            raise EvidenceConstructionError(
                f"LEVEL4_ALIVE_REQUIRES_GOAL_CONSEQUENCE_EVIDENCE: got "
                f"{type(self.goal).__name__}; a boolean is not evidence"
            )
        if self.conformant.episode != self.goal.episode:
            raise EvidenceConstructionError(
                f"LEVEL4_ALIVE_EPISODE_IDENTITY_MISMATCH: process evidence from "
                f"{self.conformant.episode.trial_dir!r} composed with goal evidence from "
                f"{self.goal.episode.trial_dir!r}"
            )


#: Everything a durable episode can inhabit. Callers ``isinstance``/``match``;
#: no member is truthy-testable.
Level4Standing = Union[
    Level4AliveEvidence,
    ConformantButGoalUnmetEvidence,
    UnknownRelationEvidence,
    NotAliveEvidence,
]


# ── reconstruction from durable artifacts ─────────────────────────────────


def _parse_witness(witness: str) -> Optional[tuple[str, str, str]]:
    """Recover ``(source, qualifier, target)`` from the verifier's own witness
    string (``f"{s}-[{q}]->{t}"``, `standalone_verifier.verify`). Reading the
    verifier's output rather than re-deriving the edge is what keeps the two
    from drifting."""
    if "-[" not in witness or "]->" not in witness:
        return None
    source, rest = witness.split("-[", 1)
    qualifier, target = rest.split("]->", 1)
    return source, qualifier, target


def _o2o(ocel: dict) -> list[tuple[str, str, str]]:
    """Explicit object-to-object edges only, same discipline as the verifier:
    an event naming two objects asserts nothing about their relation."""
    out: list[tuple[str, str, str]] = []
    for obj in ocel.get("objects", []) or []:
        for rel in obj.get("relationships", []) or []:
            target = rel.get("objectId")
            if target:
                out.append((obj.get("id", ""), rel.get("qualifier", ""), target))
    return out


def _types(ocel: dict) -> dict[str, str]:
    return {o.get("id"): o.get("type") for o in ocel.get("objects", []) or []}


def _typed(
    edges: list[tuple[str, str, str]],
    types: dict[str, str],
    qualifier: str,
    src_type: str,
    tgt_type: str,
) -> list[tuple[str, str, str]]:
    return [
        (s, q, t)
        for s, q, t in edges
        if q == qualifier and types.get(s) == src_type and types.get(t) == tgt_type
    ]


def _edge(name: str, found: list[tuple[str, str, str]], ok: str, no: str) -> Edge:
    question = dict(REQUIRED_GOAL_CHAIN)[name]
    return Edge(
        name,
        question,
        bool(found),
        ok if found else no,
        tuple(f"{s}-[{q}]->{t}" for s, q, t in found[:3]),
    )


def _observation_and_actuation(standing: IndependentStanding) -> Optional[tuple[str, str]]:
    """The observation/actuation identities the verifier already carried
    forward through commitment AND authority. Anchoring the goal leg to these
    is what stops a goal edge hanging off some unrelated actuation."""
    for edge in standing.edges:
        if edge.name != "postcondition->independent":
            continue
        for witness in edge.witness:
            parsed = _parse_witness(witness)
            if parsed is not None:
                observation, _qualifier, actuation = parsed
                return observation, actuation
    return None


def goal_consequence_from_artifacts(
    episode: EpisodeIdentity,
    ocel: dict,
    standing: IndependentStanding,
) -> Union[GoalConsequenceEvidence, UnknownRelationEvidence, NotAliveEvidence]:
    """Reconstruct the goal leg from the durable OCEL, anchored to the exact
    actuation the verifier established as committed + authorized + observed.

    Three genuinely different outcomes, never collapsed: the goal was
    established (evidence), the goal relation is not present (UNKNOWN, naming
    the relation), or the observation explicitly refuted the goal
    (NOT_ALIVE, with the witness edge).
    """
    ref = episode.trial_dir
    anchored = _observation_and_actuation(standing)
    if anchored is None:
        return UnknownRelationEvidence(
            relation="postcondition->goal",
            basis=(
                "no independent PostconditionObservation identity was carried forward by the "
                "verifier, so no goal relation can be anchored to it"
            ),
            episode_ref=ref,
        )
    observation_id, actuation_id = anchored

    edges = _o2o(ocel)
    types = _types(ocel)

    goal_of_task = _typed(edges, types, _GOAL_OF_TASK_QUALIFIER, "Goal", "Task")
    task_edge = _edge(
        "task->goal",
        goal_of_task,
        f"{len(goal_of_task)} explicit Goal->Task edge(s)",
        "no explicit typed Goal->Task edge: no admitted Goal object in the durable evidence",
    )
    if not task_edge.established:
        return UnknownRelationEvidence("task->goal", task_edge.basis, ref)
    goal_ids = {s for s, _, _ in goal_of_task}

    to_goal = [
        (s, q, t)
        for s, q, t in _typed(
            edges, types, _CANDIDATE_TARGETS_GOAL_QUALIFIER, "PlanCandidate", "Goal"
        )
        if t in goal_ids
    ]
    candidate_edge = _edge(
        "goal->plan_candidate",
        to_goal,
        f"{len(to_goal)} explicit PlanCandidate->Goal edge(s)",
        "no explicit typed PlanCandidate->Goal edge: the selected plan is not bound to the "
        "admitted goal",
    )
    if not candidate_edge.established:
        return UnknownRelationEvidence("goal->plan_candidate", candidate_edge.basis, ref)
    targeted_goals = {t for _, _, t in to_goal}

    # The refutation is checked FIRST and on its own terms: an explicitly
    # refuted goal is a real observation, and must never be reported as the
    # same thing as a goal nobody looked at.
    refuted = [
        (s, q, t)
        for s, q, t in _typed(
            edges, types, GOAL_REFUTED_QUALIFIER, "PostconditionObservation", "Goal"
        )
        if s == observation_id and t in targeted_goals
    ]
    if refuted:
        return NotAliveEvidence(
            relation="postcondition->goal",
            contradiction=(
                "the independent observation of the committed+authorized actuation explicitly "
                "REFUTED the admitted goal; the execution was lawful and the goal was not reached"
            ),
            episode_ref=ref,
            witness=tuple(f"{s}-[{q}]->{t}" for s, q, t in refuted),
        )

    established = [
        (s, q, t)
        for s, q, t in _typed(
            edges, types, GOAL_ESTABLISHED_QUALIFIER, "PostconditionObservation", "Goal"
        )
        if s == observation_id and t in targeted_goals
    ]
    goal_edge = _edge(
        "postcondition->goal",
        established,
        f"{len(established)} explicit establishes_goal edge(s) from the independent observation "
        f"of the committed+authorized actuation to the admitted goal",
        "no explicit establishes_goal edge from THIS independent observation to the admitted "
        "goal (an edge from another observation does not observe this actuation's consequence)",
    )
    if not goal_edge.established:
        return UnknownRelationEvidence("postcondition->goal", goal_edge.basis, ref)

    goal_id = established[0][2]
    task_id = next(t for s, _, t in goal_of_task if s == goal_id)
    return GoalConsequenceEvidence(
        episode=episode,
        task_id=task_id,
        goal_id=goal_id,
        actuation_id=actuation_id,
        observation_id=observation_id,
        goal_edges=(task_edge, candidate_edge, goal_edge),
    )


# NOTE on self-certification, deliberately NOT re-checked here.
#
# `SELF_CERTIFIED_POSTCONDITION` cannot arise from
# `standalone_verifier.verify`'s output: its `observes_actuation` join is
# typed `PostconditionObservation -> Actuation`, so an observation whose
# observer id equals its target id would need one object carrying both types,
# which the OCEL object table cannot express. A branch here scanning for that
# case would be unreachable code asserting a guarantee it does not provide.
# The refusal lives where it IS reachable: `GoalConsequenceEvidence`
# rejects `observation_id == actuation_id` at construction, for callers
# composing evidence directly rather than through `standing_from_trial_dir`.


def standing_from_trial_dir(trial_dir: Path) -> Level4Standing:
    """Reconstruct Level 4 standing from a durable trial directory alone.

    Takes no boolean and returns no score. The process leg is
    :func:`standalone_verifier.verify`'s own result, consumed verbatim; the
    goal leg is read from the same durable OCEL under the same
    explicit-typed-edge rule.
    """
    standing = verify(trial_dir)
    ref = str(trial_dir)

    if standing.artifacts_absent:
        return UnknownRelationEvidence(
            relation=f"artifact:{','.join(standing.artifacts_absent)}",
            basis="durable artifact(s) absent; no relation can be reconstructed from them",
            episode_ref=ref,
        )

    unestablished = standing.unestablished()
    if unestablished:
        first = next(e for e in standing.edges if e.name == unestablished[0])
        return UnknownRelationEvidence(relation=first.name, basis=first.basis, episode_ref=ref)

    ocel_path = trial_dir / "actuation" / "level4.ocel.json"
    if not ocel_path.is_file():
        ocel_path = trial_dir / "actuation" / "episode.ocel.json"
    episode = EpisodeIdentity(trial_dir=ref, ocel_path=str(ocel_path))
    ocel = json.loads(ocel_path.read_text())

    conformant = ConformantExecutionEvidence(episode=episode, chain=standing.edges)

    goal = goal_consequence_from_artifacts(episode, ocel, standing)
    if isinstance(goal, GoalConsequenceEvidence):
        return Level4AliveEvidence(conformant=conformant, goal=goal)
    if isinstance(goal, NotAliveEvidence):
        return ConformantButGoalUnmetEvidence(conformant=conformant, unmet=goal)
    return goal
