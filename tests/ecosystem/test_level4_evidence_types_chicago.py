# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for the durable-artifact Level 4 evidence constructors.

Every collaborator is real: a real :class:`autofde_lab.ocel.log.OcelLog`
serialized through its real ``to_ocel2_json`` projection and written to a real
file on disk, a real ``commitment.ttl``, a real ``sqlite3`` receipt ledger, and
the real :func:`standalone_verifier.verify` reading them back off the
filesystem. No ``unittest.mock``, ``Mock``, ``MagicMock``, ``patch`` or
``monkeypatch`` appears anywhere in this file, and no assertion is on "was
something called" -- every assertion is on the final state of the real
reconstruction.

The episode is built once, completely and conformantly, and each test perturbs
exactly one relation, so the difference between "the goal was refuted",
"the relation is missing" and "the graph is self-certifying" is measured
against a common baseline rather than against three different fixtures.
"""

from __future__ import annotations

import dataclasses
import json
import sqlite3
from pathlib import Path

import pytest

from autofde_lab.hub.domain.gym_procedure.level4_evidence import (
    ConformantButGoalUnmetEvidence,
    ConformantExecutionEvidence,
    EpisodeIdentity,
    EvidenceConstructionError,
    GoalConsequenceEvidence,
    Level4AliveEvidence,
    NotAliveEvidence,
    UnknownRelationEvidence,
    standing_from_trial_dir,
)
from autofde_lab.ocel.log import OcelLog
from autofde_lab.ocel.model import (
    EventObjectLink,
    ObjectObjectLink,
    OcelEvent,
    OcelObject,
)

TASK = "urn:level4:task:t1"
GOAL = "urn:level4:goal:g1"
CANDIDATE = "urn:level4:plancandidate:pc1"
COMMITMENT = "urn:level4:commitment:c1"
ENVELOPE = "urn:level4:authority:a1"
ACTUATION = "urn:level4:actuation:r1"
OBSERVATION = "urn:level4:postcondition:v1"
RECEIPT = "urn:level4:receipt:r1"
RECEIPT_PARENT = "urn:level4:receipt:r0"
REPLAY = "urn:level4:replay:rp1"


def _objects() -> list[OcelObject]:
    return [
        OcelObject(TASK, "Task"),
        OcelObject(GOAL, "Goal"),
        OcelObject(CANDIDATE, "PlanCandidate"),
        OcelObject(COMMITMENT, "POWLCommitment"),
        OcelObject(ENVELOPE, "AuthorityEnvelope"),
        OcelObject(ACTUATION, "Actuation"),
        OcelObject(OBSERVATION, "PostconditionObservation"),
        OcelObject(RECEIPT_PARENT, "Receipt"),
        OcelObject(RECEIPT, "Receipt"),
        OcelObject(REPLAY, "Replay"),
    ]


def _o2o(*, goal_qualifier: str = "establishes_goal") -> list[ObjectObjectLink]:
    """The complete, conforming causal topology: seven process relations plus
    the three-edge goal leg. ``goal_qualifier`` is the single knob the
    goal-unmet fixture turns."""
    return [
        ObjectObjectLink(GOAL, TASK, "goal_of_task"),
        ObjectObjectLink(CANDIDATE, GOAL, "targets_goal"),
        ObjectObjectLink(CANDIDATE, TASK, "candidate_for_task"),
        ObjectObjectLink(COMMITMENT, CANDIDATE, "commits_candidate"),
        ObjectObjectLink(ACTUATION, COMMITMENT, "actuates_commitment"),
        ObjectObjectLink(ACTUATION, ENVELOPE, "authorized_by"),
        ObjectObjectLink(OBSERVATION, ACTUATION, "observes_actuation"),
        ObjectObjectLink(OBSERVATION, GOAL, goal_qualifier),
        ObjectObjectLink(RECEIPT, RECEIPT_PARENT, "caused_by"),
        ObjectObjectLink(REPLAY, RECEIPT, "replays_receipt"),
    ]


def _events() -> list[OcelEvent]:
    return [
        OcelEvent("ev:open", "ActuationOpened", 1_000_000_000),
        OcelEvent("ev:observed", "PostconditionObserved", 2_000_000_000),
    ]


def _e2o() -> list[EventObjectLink]:
    return [
        EventObjectLink("ev:open", TASK, "task"),
        EventObjectLink("ev:open", ACTUATION, "actuation"),
        EventObjectLink("ev:observed", TASK, "task"),
        EventObjectLink("ev:observed", OBSERVATION, "observation"),
    ]


def _write_trial(
    root: Path,
    *,
    objects: list[OcelObject] | None = None,
    o2o: list[ObjectObjectLink] | None = None,
) -> Path:
    """Persist a real durable trial directory: real OCEL 2.0 JSON produced by
    the real ``OcelLog.to_ocel2_json``, a real commitment TTL, a real sqlite
    receipt ledger. Nothing in-memory survives into the assertions."""
    act = root / "actuation"
    act.mkdir(parents=True, exist_ok=True)

    log = OcelLog.new(
        objects if objects is not None else _objects(),
        _events(),
        _e2o(),
        o2o if o2o is not None else _o2o(),
    )
    (act / "level4.ocel.json").write_text(json.dumps(log.to_ocel2_json(), indent=2))
    (act / "commitment.ttl").write_text(
        f"<{COMMITMENT}> <urn:level4:commits> <{CANDIDATE}> .\n"
    )

    ledger = act / "receipts.sqlite3"
    con = sqlite3.connect(ledger)
    try:
        con.execute(
            "CREATE TABLE receipt_evidence (sequence INTEGER PRIMARY KEY, receipt_json TEXT)"
        )
        con.execute(
            "INSERT INTO receipt_evidence VALUES (?, ?)",
            (1, json.dumps({"receipt_id": RECEIPT_PARENT, "parent_receipt_ids": []})),
        )
        con.execute(
            "INSERT INTO receipt_evidence VALUES (?, ?)",
            (2, json.dumps({"receipt_id": RECEIPT, "parent_receipt_ids": [RECEIPT_PARENT]})),
        )
        con.commit()
    finally:
        con.close()
    return root


ALL_EVIDENCE_TYPES = (
    ConformantExecutionEvidence,
    GoalConsequenceEvidence,
    ConformantButGoalUnmetEvidence,
    Level4AliveEvidence,
    UnknownRelationEvidence,
    NotAliveEvidence,
    EpisodeIdentity,
)


# ── 1. a complete conforming episode yields Level4AliveEvidence ───────────


def test_complete_conforming_episode_yields_level4_alive_evidence(tmp_path: Path) -> None:
    trial = _write_trial(tmp_path / "trial-alive")

    standing = standing_from_trial_dir(trial)

    assert isinstance(standing, Level4AliveEvidence), standing
    # State assertions on the real reconstructed identities, not on calls.
    assert standing.goal.goal_id == GOAL
    assert standing.goal.task_id == TASK
    assert standing.goal.actuation_id == ACTUATION
    assert standing.goal.observation_id == OBSERVATION
    assert standing.goal.observation_id != standing.goal.actuation_id
    assert standing.conformant.episode == standing.goal.episode
    assert all(edge.established for edge in standing.conformant.chain)
    assert standing.conformant.edge("authority->actuation").witness == (
        f"{ACTUATION}-[authorized_by]->{ENVELOPE}",
    )


# ── 2. conformant but goal-unmet, and it CANNOT become ALIVE ──────────────


def test_conformant_but_goal_unmet_is_a_real_result_and_cannot_be_coerced(
    tmp_path: Path,
) -> None:
    trial = _write_trial(
        tmp_path / "trial-unmet", o2o=_o2o(goal_qualifier="refutes_goal")
    )

    standing = standing_from_trial_dir(trial)

    assert isinstance(standing, ConformantButGoalUnmetEvidence), standing
    # The process really did conform -- this is not a degraded UNKNOWN.
    assert isinstance(standing.conformant, ConformantExecutionEvidence)
    assert all(edge.established for edge in standing.conformant.chain)
    assert standing.unmet.relation == "postcondition->goal"
    assert standing.unmet.witness == (f"{OBSERVATION}-[refutes_goal]->{GOAL}",)

    # No coercion path exists: no attribute yields the alive type, and
    # composing one by hand is refused because there is no goal evidence.
    assert not any(
        isinstance(getattr(standing, f.name), Level4AliveEvidence)
        for f in dataclasses.fields(standing)
    )
    with pytest.raises(EvidenceConstructionError, match="LEVEL4_ALIVE_REQUIRES_GOAL"):
        Level4AliveEvidence(conformant=standing.conformant, goal=standing.unmet)


# ── 3. Level4AliveEvidence is not constructible from booleans ─────────────


def test_level4_alive_evidence_cannot_be_constructed_from_booleans(tmp_path: Path) -> None:
    trial = _write_trial(tmp_path / "trial-bool")
    alive = standing_from_trial_dir(trial)
    assert isinstance(alive, Level4AliveEvidence)

    with pytest.raises(TypeError):
        Level4AliveEvidence(success=True)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        Level4AliveEvidence(goal_reached=True)  # type: ignore[call-arg]
    with pytest.raises(EvidenceConstructionError):
        Level4AliveEvidence(conformant=True, goal=True)  # type: ignore[arg-type]
    with pytest.raises(EvidenceConstructionError):
        Level4AliveEvidence(conformant=alive.conformant, goal=True)  # type: ignore[arg-type]

    # No boolean-ish field name exists anywhere on the evidence surface.
    banned = {"success", "passed", "goal_reached", "ok", "valid", "is_alive", "alive"}
    for evidence_type in ALL_EVIDENCE_TYPES:
        names = {f.name for f in dataclasses.fields(evidence_type)}
        assert not (names & banned), (evidence_type.__name__, names & banned)

    # Cross-episode composition is refused: identity, not adjacency.
    other = standing_from_trial_dir(_write_trial(tmp_path / "trial-other"))
    assert isinstance(other, Level4AliveEvidence)
    with pytest.raises(EvidenceConstructionError, match="EPISODE_IDENTITY_MISMATCH"):
        Level4AliveEvidence(conformant=alive.conformant, goal=other.goal)


# ── 4. no type defines __bool__ ───────────────────────────────────────────


def test_no_evidence_type_defines_bool(tmp_path: Path) -> None:
    for evidence_type in ALL_EVIDENCE_TYPES:
        # Nowhere in the MRO, not merely on the leaf class -- a base class
        # defining it would give `if evidence:` a verdict just as effectively.
        assert not any(
            "__bool__" in klass.__dict__ for klass in evidence_type.__mro__
        ), evidence_type.__name__
        assert not any(
            "__len__" in klass.__dict__ for klass in evidence_type.__mro__
        ), evidence_type.__name__

    # And on a real instance: `if evidence:` can never distinguish a verdict,
    # because every instance is uniformly truthy by object identity.
    trial = _write_trial(tmp_path / "trial-nobool")
    alive = standing_from_trial_dir(trial)
    unmet = standing_from_trial_dir(
        _write_trial(tmp_path / "trial-nobool-unmet", o2o=_o2o(goal_qualifier="refutes_goal"))
    )
    assert isinstance(alive, Level4AliveEvidence)
    assert isinstance(unmet, ConformantButGoalUnmetEvidence)
    assert bool(alive) is bool(unmet) is True


# ── 5. a missing relation is UNKNOWN, naming the relation ─────────────────


@pytest.mark.parametrize(
    "dropped_qualifier,expected_relation",
    [
        ("authorized_by", "authority->actuation"),
        ("caused_by", "receipt->dag"),
        ("replays_receipt", "replay->receipt"),
        ("goal_of_task", "task->goal"),
        ("targets_goal", "goal->plan_candidate"),
        ("establishes_goal", "postcondition->goal"),
    ],
)
def test_missing_relation_yields_unknown_naming_that_relation(
    tmp_path: Path, dropped_qualifier: str, expected_relation: str
) -> None:
    o2o = [link for link in _o2o() if link.qualifier != dropped_qualifier]
    trial = _write_trial(tmp_path / f"trial-missing-{dropped_qualifier}", o2o=o2o)

    standing = standing_from_trial_dir(trial)

    assert isinstance(standing, UnknownRelationEvidence), standing
    assert standing.relation == expected_relation
    assert standing.basis
    # Never a pass, never a failure.
    assert not isinstance(standing, (Level4AliveEvidence, NotAliveEvidence))
    assert not isinstance(standing, ConformantButGoalUnmetEvidence)


def test_absent_artifacts_yield_unknown_not_failure(tmp_path: Path) -> None:
    empty = tmp_path / "trial-empty"
    (empty / "actuation").mkdir(parents=True)

    standing = standing_from_trial_dir(empty)

    assert isinstance(standing, UnknownRelationEvidence), standing
    assert standing.relation.startswith("artifact:")
    assert "ocel" in standing.relation


def test_a_self_observing_object_cannot_reach_the_goal_leg_at_all(tmp_path: Path) -> None:
    """A durable graph in which the "observer" IS the actuation is refused
    upstream, and refused as UNKNOWN naming a relation -- never as a pass.

    Retyping the actuation so it can observe itself costs it its
    ``Actuation`` type, which breaks the typed ``commitment->actuation`` join
    first. This is the measured outcome, asserted exactly, rather than a
    weaker either/or: it is why ``level4_evidence`` carries no unreachable
    self-certification branch over the verifier's output, and instead refuses
    ``observation_id == actuation_id`` inside
    :class:`GoalConsequenceEvidence` (the test below).
    """
    o2o = [link for link in _o2o() if link.qualifier != "observes_actuation"]
    o2o.append(ObjectObjectLink(ACTUATION, ACTUATION, "observes_actuation"))
    objects = [o for o in _objects() if o.id != ACTUATION] + [
        OcelObject(ACTUATION, "PostconditionObservation")
    ]
    trial = _write_trial(tmp_path / "trial-selfcert", objects=objects, o2o=o2o)

    standing = standing_from_trial_dir(trial)

    assert isinstance(standing, UnknownRelationEvidence), standing
    assert standing.relation == "commitment->actuation"
    assert not isinstance(standing, Level4AliveEvidence)


# ── 6. the constructors refuse to exist without their evidence ────────────


def test_conformant_execution_evidence_requires_every_required_relation(
    tmp_path: Path,
) -> None:
    trial = _write_trial(tmp_path / "trial-partial")
    alive = standing_from_trial_dir(trial)
    assert isinstance(alive, Level4AliveEvidence)

    with pytest.raises(EvidenceConstructionError, match="MISSING_RELATION"):
        ConformantExecutionEvidence(
            episode=alive.conformant.episode, chain=alive.conformant.chain[:3]
        )
    with pytest.raises(EvidenceConstructionError, match="REQUIRES_REAL_EDGES"):
        ConformantExecutionEvidence(episode=alive.conformant.episode, chain=(True,))  # type: ignore[arg-type]


def test_goal_consequence_evidence_refuses_self_certified_identities(
    tmp_path: Path,
) -> None:
    trial = _write_trial(tmp_path / "trial-goalself")
    alive = standing_from_trial_dir(trial)
    assert isinstance(alive, Level4AliveEvidence)

    with pytest.raises(EvidenceConstructionError, match="SELF_CERTIFIED_POSTCONDITION"):
        GoalConsequenceEvidence(
            episode=alive.goal.episode,
            task_id=alive.goal.task_id,
            goal_id=alive.goal.goal_id,
            actuation_id=ACTUATION,
            observation_id=ACTUATION,
            goal_edges=alive.goal.goal_edges,
        )


def test_goal_unmet_evidence_refuses_to_be_built_from_an_absence(tmp_path: Path) -> None:
    """"We did not observe the goal" must not be expressible as "the goal was
    not reached"."""
    trial = _write_trial(tmp_path / "trial-absence")
    alive = standing_from_trial_dir(trial)
    assert isinstance(alive, Level4AliveEvidence)

    absent = UnknownRelationEvidence(
        relation="postcondition->goal", basis="no edge", episode_ref=str(trial)
    )
    with pytest.raises(EvidenceConstructionError, match="REQUIRES_OBSERVED_REFUTATION"):
        ConformantButGoalUnmetEvidence(conformant=alive.conformant, unmet=absent)  # type: ignore[arg-type]


def test_not_alive_evidence_requires_a_witness_edge() -> None:
    with pytest.raises(EvidenceConstructionError, match="REQUIRES_WITNESS"):
        NotAliveEvidence(
            relation="postcondition->goal", contradiction="asserted", episode_ref="x"
        )
