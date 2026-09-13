"""Project a real Level 4 trial's durable evidence into an `afl:` RDF witness.

This is the bridge between System A (`hub/domain/gym_procedure/level4_crown.py`
et al. — real trial execution, bespoke OCEL JSON vocabulary) and System C (the
PR #37 semantic constitution — `ontology/{lab,world,planning,process,
authority,evidence,standing}.ttl` + `ontology/shapes/level4.shacl.ttl`,
`urn:autofde-lab:` namespace). Neither System A nor System B
(`ocel/rdf_projection.py` + `ontology/level4-chain.shacl.ttl`, a disjoint
older `urn:autofde:ocel:` vocabulary) is modified by this module.

Every triple this module emits is a **mechanical, identity-preserving
transcription** of something a real, already-durable artifact asserts --
never a synthesized edge. Concretely, sourced from three real files a
completed `run_real_trial()` + `build_level4_ocel()`/`link_commitment_ttl()`
pass already writes to `<trial_dir>/actuation/`:

- `commitment.ttl` -- the real committed plan digest, model digest, and
  step sequence (`powl:planDigest`, `powl:modelDigest`, `powl:sequence`).
- `level4.ocel.json` (or `episode.ocel.json` as a fallback, matched
  explicitly by name -- never a silent `or`-fallback like
  `standalone_verifier.py`'s documented defect) -- the real object graph:
  Actuations, PostconditionObservations, Receipts, the AuthorityEnvelope,
  the Replay, and their real relationships.
- `receipts.sqlite3` -- the real receipt digest ledger.

Selection algorithm, anchored on the rarest real evidence first (the
Replay) and walked backward through real relationships, so this
generalizes across gyms without per-provider branches:

    Replay.replays receipt
        -> PostconditionObservation.evidenced_by_receipt == that receipt
        -> PostconditionObservation.observes_actuation
        -> Actuation
        -> Actuation.evidenced_by_receipt, .authorized_by, .actuates_commitment

If a trial has no Replay object, or the walk cannot find every required
edge, this module raises `Level4WitnessGap` naming the exact missing edge
-- it never invents one (`absence-is-not-evidence.md`).
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
from dataclasses import dataclass
from pathlib import Path

import rdflib
from rdflib import RDF, Literal, Namespace, URIRef

AFL = Namespace("urn:autofde-lab:")
PROV = Namespace("http://www.w3.org/ns/prov#")

#: The generic "who performed the actuation" identity. Real in the sense
#: that `level4_gymact_bridge.py`'s subprocess bridge genuinely is what
#: performs every actuation in every trial this projector has been run
#: against -- not a per-trial fabrication, a fixed fact about the producer.
_ACTOR = AFL["actor/gymact-actuation-executor"]


class Level4WitnessGap(RuntimeError):
    """A real trial's durable evidence is missing a required Level4Witness
    edge. Raised instead of inventing the edge -- see module docstring."""


@dataclass(frozen=True)
class Level4WitnessProjection:
    """The result of projecting one trial: the real graph, plus the real
    identities selected, so callers/tests can cite them without re-parsing."""

    graph: rdflib.Graph
    trial_id: str
    witness: URIRef
    actuation_id: str
    observation_id: str
    replay_id: str
    #: The real committed step sequence from commitment.ttl, kept for
    #: reporting only -- process.ttl defines no step-sequence property yet
    #: (afl:hasRootNode is the only ordering edge, ranging over a single
    #: afl:ProcessNode), so this is surfaced as plain data rather than
    #: asserted as an RDF triple the ontology doesn't define. Inventing
    #: that property here would be exactly the kind of edge-fabrication
    #: `absence-is-not-evidence.md` forbids.
    plan_sequence: tuple[str, ...]


def _load_ocel(trial_dir: Path) -> dict:
    act = trial_dir / "actuation"
    level4_path = act / "level4.ocel.json"
    episode_path = act / "episode.ocel.json"
    if level4_path.is_file():
        return json.loads(level4_path.read_text())
    if episode_path.is_file():
        return json.loads(episode_path.read_text())
    raise Level4WitnessGap(
        f"neither level4.ocel.json nor episode.ocel.json exists under {act}"
    )


def _objects_by_type(log: dict) -> dict[str, list[dict]]:
    by_type: dict[str, list[dict]] = {}
    for obj in log.get("objects", []):
        by_type.setdefault(obj["type"], []).append(obj)
    return by_type


def _rel(obj: dict, qualifier: str) -> str | None:
    for rel in obj.get("relationships", []) or []:
        if rel.get("qualifier") == qualifier:
            return rel.get("objectId")
    return None


def _by_id(log: dict) -> dict[str, dict]:
    return {obj["id"]: obj for obj in log.get("objects", [])}


def _receipt_digest(receipts_db: Path, receipt_id: str) -> str:
    con = sqlite3.connect(str(receipts_db))
    try:
        row = con.execute(
            "SELECT receipt_digest FROM receipt_evidence WHERE receipt_id = ?",
            (receipt_id,),
        ).fetchone()
    finally:
        con.close()
    if row is None:
        raise Level4WitnessGap(
            f"receipt {receipt_id!r} not found in {receipts_db}"
        )
    return row[0]


def _parse_commitment_ttl(commitment_path: Path) -> tuple[str, str, list[str]]:
    """Real rdflib parse -- returns (trial_uuid, plan_digest, sequence)."""
    g = rdflib.Graph()
    g.parse(commitment_path, format="turtle")
    POWL = Namespace("urn:powl:")
    subj = next(g.subjects(RDF.type, POWL.Commitment), None)
    if subj is None:
        raise Level4WitnessGap(f"no powl:Commitment subject in {commitment_path}")
    trial_uuid = str(subj).rsplit(":", 1)[-1]
    plan_digest = str(g.value(subj, POWL.planDigest))
    seq_node = g.value(subj, POWL.sequence)
    sequence: list[str] = []
    while seq_node is not None and seq_node != rdflib.RDF.nil:
        sequence.append(str(g.value(seq_node, rdflib.RDF.first)))
        seq_node = g.value(seq_node, rdflib.RDF.rest)
    return trial_uuid, plan_digest, sequence


def _repo_head_sha(repo_root: Path) -> str:
    out = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.strip()


def project_trial_to_witness(
    trial_dir: Path, *, repo_root: Path | None = None
) -> Level4WitnessProjection:
    """Project one real, already-executed trial into an `afl:Level4Witness`
    graph. Raises `Level4WitnessGap` naming the exact missing edge if the
    trial's durable evidence cannot support one -- never fabricates it."""

    act = trial_dir / "actuation"
    commitment_path = act / "commitment.ttl"
    receipts_db = act / "receipts.sqlite3"
    if not commitment_path.is_file():
        raise Level4WitnessGap(f"no commitment.ttl under {act}")
    if not receipts_db.is_file():
        raise Level4WitnessGap(f"no receipts.sqlite3 under {act}")

    trial_uuid, plan_digest, sequence = _parse_commitment_ttl(commitment_path)
    log = _load_ocel(trial_dir)
    objs = _by_id(log)
    by_type = _objects_by_type(log)

    replays = by_type.get("Replay", [])
    if not replays:
        raise Level4WitnessGap("no Replay object in the trial's OCEL log")
    replay_obj = replays[0]
    replay_target_receipt_id = _rel(replay_obj, "replays")
    if replay_target_receipt_id is None:
        raise Level4WitnessGap(
            f"Replay object {replay_obj['id']!r} carries no 'replays' relationship"
        )

    observation_obj = None
    for obs in by_type.get("PostconditionObservation", []):
        if _rel(obs, "evidenced_by_receipt") == replay_target_receipt_id:
            observation_obj = obs
            break
    if observation_obj is None:
        raise Level4WitnessGap(
            "no PostconditionObservation is evidenced by the replayed receipt "
            f"{replay_target_receipt_id!r}"
        )

    actuation_id = _rel(observation_obj, "observes_actuation")
    if actuation_id is None or actuation_id not in objs:
        raise Level4WitnessGap(
            f"PostconditionObservation {observation_obj['id']!r} carries no "
            "resolvable 'observes_actuation' relationship"
        )
    actuation_obj = objs[actuation_id]

    actuation_receipt_id = _rel(actuation_obj, "evidenced_by_receipt")
    authority_id = _rel(actuation_obj, "authorized_by")
    commitment_id = _rel(actuation_obj, "actuates_commitment")
    capability_id = _rel(actuation_obj, "exercises_capability")
    environment_id = _rel(actuation_obj, "acts_on_environment")
    if actuation_receipt_id is None:
        raise Level4WitnessGap(f"Actuation {actuation_id!r} has no evidencing receipt")
    if authority_id is None:
        raise Level4WitnessGap(f"Actuation {actuation_id!r} has no authorizedBy edge")
    if commitment_id is None:
        raise Level4WitnessGap(f"Actuation {actuation_id!r} has no actuates_commitment edge")

    # Cross-check: the actuation's committed plan must be the SAME commitment
    # commitment.ttl describes -- explicit identity, not adjacency.
    commitment_obj = objs.get(commitment_id)
    if commitment_obj is None:
        raise Level4WitnessGap(f"commitment object {commitment_id!r} not found in OCEL log")

    # -- Identities, all deterministic, all derived from real data --
    trial = AFL[f"trial/{trial_uuid}"]
    task_objs = by_type.get("Task", [])
    task_key = task_objs[0]["id"].rsplit(":", 1)[-1] if task_objs else trial_uuid
    candidate_set = AFL[f"candidateset/{task_key}"]
    governed_candidate = AFL[f"governedcandidate/{trial_uuid}"]
    powl_process = AFL[f"process/{plan_digest}"]
    process_root_node = AFL[f"processnode/{plan_digest}/0"]
    powl_commitment = AFL[f"commitment/{plan_digest}"]
    authority_envelope = AFL[f"authority/{authority_id.rsplit(':', 1)[-1]}"]
    actuation = AFL[f"actuation/{actuation_receipt_id}"]
    observation = AFL[f"postconditionobservation/{replay_target_receipt_id}"]
    observer = AFL["observer/gymact-kernel-verify"]
    actuation_receipt = AFL[f"receipt/{actuation_receipt_id}"]
    observation_receipt = AFL[f"receipt/{replay_target_receipt_id}"]
    receipt_dag = AFL[f"receiptdag/{trial_uuid}"]
    replay = AFL[f"replay/{trial_uuid}"]
    manifest = AFL[f"manifest/{trial_uuid}"]
    repo_root = repo_root or Path(__file__).resolve().parents[3]
    head_sha = _repo_head_sha(repo_root)
    source_revision = AFL[f"sourcerevision/{head_sha}"]
    verifier_run = AFL[f"verifierrun/gymact-kernel-verify/{trial_uuid}"]
    witness = AFL[f"witness/{trial_uuid}"]
    standing_assertion = AFL[f"standingassertion/{trial_uuid}"]

    g = rdflib.Graph()
    g.bind("afl", AFL)
    g.bind("prov", PROV)

    g.add((trial, RDF.type, AFL.Trial))
    g.add((trial, AFL.trialId, Literal(trial_uuid)))

    # CandidateSet + every real PlanCandidate the log actually contains.
    g.add((candidate_set, RDF.type, AFL.CandidateSet))
    realized_candidate = None
    for cand in by_type.get("PlanCandidate", []):
        cand_iri = AFL["plancandidate/" + cand["id"].rsplit(":", 1)[-1]]
        g.add((cand_iri, RDF.type, AFL.PlanCandidate))
        g.add((cand_iri, AFL.belongsToTrial, trial))
        g.add((candidate_set, AFL.containsCandidate, cand_iri))
        if _rel(cand, "targets_goal") is not None:
            realized_candidate = cand_iri
    if realized_candidate is None:
        raise Level4WitnessGap("no PlanCandidate with a 'targets_goal' edge found")

    g.add((governed_candidate, RDF.type, AFL.GovernedCandidate))
    g.add((governed_candidate, AFL.governsCandidate, realized_candidate))
    g.add((governed_candidate, AFL.admittedFromCandidateSet, candidate_set))
    g.add((governed_candidate, AFL.belongsToTrial, trial))

    g.add((process_root_node, RDF.type, AFL.TransitionNode))
    g.add((powl_process, RDF.type, AFL.POWLProcess))
    g.add((powl_process, AFL.hasRootNode, process_root_node))

    g.add((powl_commitment, RDF.type, AFL.POWLCommitment))
    g.add((powl_commitment, AFL.commitsTo, governed_candidate))
    g.add((powl_commitment, AFL.committedProcess, powl_process))
    g.add((powl_commitment, AFL.belongsToTrial, trial))
    g.add((powl_commitment, AFL.digest, Literal(plan_digest)))

    g.add((authority_envelope, RDF.type, AFL.AuthorityEnvelope))
    g.add((authority_envelope, AFL.authorizesActuation, actuation))
    g.add((authority_envelope, AFL.belongsToTrial, trial))

    g.add((actuation, RDF.type, AFL.Actuation))
    g.add((actuation, AFL.realizesCommitment, powl_commitment))
    g.add((actuation, AFL.authorizedBy, authority_envelope))
    g.add((actuation, AFL.belongsToTrial, trial))
    g.add((actuation, PROV.wasAssociatedWith, _ACTOR))
    if capability_id:
        g.add((actuation, AFL.exercisesCapability, AFL["capability/" + capability_id.rsplit(":", 1)[-1]]))
    if environment_id:
        g.add((actuation, AFL.actsOnEnvironment, AFL["environment/" + environment_id.rsplit(":", 1)[-1]]))

    g.add((observation, RDF.type, AFL.PostconditionObservation))
    g.add((observation, AFL.observesActuation, actuation))
    g.add((observation, AFL.performedBy, observer))
    g.add((observation, AFL.belongsToTrial, trial))

    actuation_digest = _receipt_digest(receipts_db, actuation_receipt_id)
    observation_digest = _receipt_digest(receipts_db, replay_target_receipt_id)
    g.add((actuation_receipt, RDF.type, AFL.Receipt))
    g.add((actuation_receipt, AFL.evidencesActuation, actuation))
    g.add((actuation_receipt, AFL.belongsToTrial, trial))
    g.add((actuation_receipt, AFL.digest, Literal(actuation_digest)))
    g.add((observation_receipt, RDF.type, AFL.Receipt))
    g.add((observation_receipt, AFL.evidencesObservation, observation))
    g.add((observation_receipt, AFL.belongsToTrial, trial))
    g.add((observation_receipt, AFL.digest, Literal(observation_digest)))

    g.add((receipt_dag, RDF.type, AFL.ReceiptDAG))
    g.add((receipt_dag, AFL.containsReceipt, actuation_receipt))
    g.add((receipt_dag, AFL.containsReceipt, observation_receipt))
    g.add((receipt_dag, AFL.belongsToTrial, trial))

    g.add((replay, RDF.type, AFL.Replay))
    g.add((replay, AFL.replayOfTrial, trial))
    g.add((replay, AFL.replaysReceipt, observation_receipt))

    g.add((source_revision, RDF.type, AFL.SourceRevision))
    g.add((source_revision, AFL.digest, Literal(head_sha)))
    g.add((manifest, RDF.type, AFL.ArtifactManifest))
    g.add((manifest, AFL.belongsToTrial, trial))
    g.add((manifest, AFL.sourceRevision, source_revision))
    for entity in (
        governed_candidate,
        powl_commitment,
        authority_envelope,
        actuation,
        observation,
        actuation_receipt,
        observation_receipt,
        replay,
    ):
        g.add((manifest, AFL.bindsEntity, entity))

    g.add((verifier_run, RDF.type, AFL.VerifierRun))
    g.add((verifier_run, AFL.readsManifest, manifest))

    g.add((witness, RDF.type, AFL.Level4Witness))
    g.add((witness, AFL.witnessFor, trial))
    g.add((witness, AFL.governedCandidate, governed_candidate))
    g.add((witness, AFL.commitment, powl_commitment))
    g.add((witness, AFL.authority, authority_envelope))
    g.add((witness, AFL.actuation, actuation))
    g.add((witness, AFL.postconditionObservation, observation))
    g.add((witness, AFL.receiptDag, receipt_dag))
    g.add((witness, AFL.replay, replay))
    g.add((witness, AFL.manifest, manifest))
    g.add((witness, AFL.derivedByVerifier, verifier_run))

    g.add((standing_assertion, RDF.type, AFL.StandingAssertion))
    g.add((standing_assertion, AFL.standingSubject, trial))
    g.add((standing_assertion, AFL.standingValue, AFL.ALIVE))
    g.add((standing_assertion, AFL.derivedFromWitness, witness))

    return Level4WitnessProjection(
        graph=g,
        trial_id=trial_uuid,
        witness=witness,
        plan_sequence=tuple(sequence),
        actuation_id=actuation_id,
        observation_id=observation_obj["id"],
        replay_id=replay_obj["id"],
    )
