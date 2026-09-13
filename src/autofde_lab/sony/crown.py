"""Executable three-round acceptance crown for the Sony Pictures EIP FDE role.

This is deliberately a bounded customer-like execution profile, not a claim of
Sony authority.  Fortune-5 construction stays inert (SELECT/CONSTRUCT with
``authority == NONE``).  The POWL orchestration rail may only produce physical
consequence through a BRCE-backed driver, and every successful activity must
carry a causal BRCE receipt that replays against the exact observed effect.

The three interview rounds are therefore projections of one exact subject:

    admitted role requirements
      -> Fortune-5 candidate identity
      -> POWL execution model
      -> BRCE-only filesystem consequence
      -> independent observation + verification
      -> receipt
      -> replay

The filesystem target is intentionally local and disposable.  It proves the
composition and authority topology without pretending this repository has Sony
cloud credentials or organizational approval.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping

from autofde_lab.fabric.brce import (
    ActuationIntent,
    ActuationResult,
    Authority,
    BrceStanding,
    execute_brce,
    replay_receipt,
)
from autofde_lab.fortune5.catalog import AXES
from autofde_lab.fortune5.space import StateSpace
from autofde_lab.powl.algebra import Atom, NodeId, OrderEdge, PartialOrder
from autofde_lab.powl.concurrent_runner import (
    ActivityIntent,
    ActivityOutcome,
    PowlV2Runner,
    RunStatus,
)
from autofde_lab.powl.executor import is_final, replay

__all__ = [
    "SONY_ARCHITECTURE_CHOICES",
    "SONY_ECOSYSTEM_PINS",
    "SONY_REQUIREMENTS",
    "SonyCrownEvidence",
    "run_sony_crown",
]

SUBJECT_ID = "sony-pictures-eip-principal-fde"
CLAIM_CEILING = "BOUNDED_LOCAL_SONY_ROLE_ACCEPTANCE_ONLY_NO_SONY_CLOUD_AUTHORITY"


@dataclass(frozen=True, slots=True)
class Requirement:
    requirement_id: str
    round_id: str
    capability: str
    acceptance: str
    proof_label: str


@dataclass(frozen=True, slots=True)
class EcosystemPin:
    repo: str
    ref: str
    sha: str
    visibility: str
    role: str


@dataclass(frozen=True, slots=True)
class SonyCrownEvidence:
    schema: str
    standing: str
    claim_ceiling: str
    subject_id: str
    scenario_id: str
    state_space_digest: str
    raw_upper_bound: int
    scenario_authority: str
    architecture: Mapping[str, str]
    requirement_ids: tuple[str, ...]
    activity_receipts: tuple[str, ...]
    activity_replays: tuple[str, ...]
    powl_status: str
    powl_model_sha256: str
    peak_concurrency: int
    worker_threads: tuple[str, ...]
    structural_replay: str
    ecosystem_pins: tuple[EcosystemPin, ...]

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["ecosystem_pins"] = [asdict(pin) for pin in self.ecosystem_pins]
        return value


SONY_REQUIREMENTS: tuple[Requirement, ...] = (
    Requirement(
        "R1-EIP-OUTCOME",
        "round-1-business",
        "forward-deployed outcome ownership",
        "translate an admitted business problem into a production-oriented AI outcome",
        "round-1-business-outcome",
    ),
    Requirement(
        "R1-AIDLC",
        "round-1-business",
        "AI Development Life Cycle",
        "show an execution path that compresses build work rather than adding a planning handoff",
        "round-1-business-outcome",
    ),
    Requirement(
        "R1-PARTNERSHIP",
        "round-1-business",
        "IT and business integration",
        "preserve one subject identity across business requirement and technical evidence",
        "round-1-business-outcome",
    ),
    Requirement(
        "R2-AZURE",
        "round-2-technical",
        "Azure-oriented enterprise architecture",
        "select an Azure production candidate from the admitted Fortune-5 state space",
        "round-2-technical-implementation",
    ),
    Requirement(
        "R2-DISTRIBUTED",
        "round-2-technical",
        "distributed systems and data flow",
        "execute a precedence-preserving concurrent process with independent worker evidence",
        "round-2-technical-implementation",
    ),
    Requirement(
        "R2-INTEGRATION",
        "round-2-technical",
        "API and integration design",
        "bind every consequential activity to an explicit driver and authority seam",
        "round-2-technical-implementation",
    ),
    Requirement(
        "R2-GENAI",
        "round-2-technical",
        "generative and agentic AI",
        "carry agentic runtime selection as inert architecture data until authority admits DO",
        "round-2-technical-implementation",
    ),
    Requirement(
        "R3-GOVERNANCE",
        "round-3-principal",
        "principal-scale governance",
        "refuse ambient authority and require policy plus principal/capability/resource authority",
        "round-3-principal-governance",
    ),
    Requirement(
        "R3-RECEIPT",
        "round-3-principal",
        "causal receipt and replay",
        "return no successful consequence without a BRCE receipt and exact replay match",
        "round-3-principal-governance",
    ),
    Requirement(
        "R3-OPTIONALITY",
        "round-3-principal",
        "combinatorial architecture optionality",
        "preserve the admitted state-space identity and selected scenario independently of actuation",
        "round-3-principal-governance",
    ),
)


SONY_ARCHITECTURE_CHOICES: Mapping[str, str] = {
    "enterprise": "enterprise-01",
    "cloud": "azure",
    "geography": "americas",
    "environment": "prod",
    "cluster_profile": "dedicated",
    "workload": "agent",
    "traffic": "event-driven",
    "data_class": "confidential",
    "availability": "mission-critical",
    "release": "canary",
    "identity": "workload-identity",
    "policy": "zero-trust",
    "runtime_ai": "agentic",
    "fault": "healthy",
}


SONY_ECOSYSTEM_PINS: tuple[EcosystemPin, ...] = (
    EcosystemPin(
        "seanchatmangpt/ggen",
        "main",
        "85b4ed191f76b427f7dc3df27e28a4e7881b4d4a",
        "public",
        "ontology-to-artifact manufacture",
    ),
    EcosystemPin(
        "seanchatmangpt/gymact",
        "main",
        "5a40c8f402aeb14699e216e17b2ef7aae9f0bc8f",
        "private",
        "bounded gym and capability execution",
    ),
    EcosystemPin(
        "seanchatmangpt/wasm4pm-compat",
        "main",
        "1d04337818d409160026b69c6917430267cf073a",
        "public",
        "process-model compatibility and receipt types",
    ),
)

_ACTIVITY_LABELS = (
    "admit-sony-o-star",
    "round-1-business-outcome",
    "round-2-technical-implementation",
    "round-3-principal-governance",
    "crown-replay",
)


def _order(source: int, target: int) -> OrderEdge:
    return OrderEdge(NodeId(source), NodeId(target))


def _model() -> PartialOrder:
    """One subject, three parallel round projections, one closing crown."""
    return PartialOrder(
        tuple(Atom(label) for label in _ACTIVITY_LABELS),
        frozenset(
            {
                _order(0, 1),
                _order(0, 2),
                _order(0, 3),
                _order(1, 4),
                _order(2, 4),
                _order(3, 4),
            }
        ),
    )


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


class _BrceFilesystemDriver:
    """Real bounded actuation target used only through ``execute_brce``."""

    def __init__(self, workspace: Path, *, scenario_id: str) -> None:
        self.workspace = workspace.resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.scenario_id = scenario_id
        self._resources = frozenset(
            str((self.workspace / f"{label}.json").resolve())
            for label in _ACTIVITY_LABELS
        )
        self._authority = Authority(
            principal_id="sony-crown-broker",
            capabilities=frozenset({"write-bounded-evidence"}),
            resources=self._resources,
        )

    def execute(self, intent: ActivityIntent) -> ActivityOutcome:
        path = (self.workspace / f"{intent.label}.json").resolve()
        resource = str(path)
        payload = {
            "schema": "autofde.sony-crown-activity/1",
            "subject_id": SUBJECT_ID,
            "scenario_id": self.scenario_id,
            "run_id": intent.run_id,
            "model_sha256": intent.model_sha256,
            "activity": intent.label,
            "occurrence": intent.occurrence,
            "attempt": intent.attempt,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        effect: dict[str, object] = {}
        observed: dict[str, object] = {}

        brce_intent = ActuationIntent(
            intent_id=f"{intent.run_id}:{intent.label}:{intent.occurrence}",
            subject_id=SUBJECT_ID,
            principal_id="sony-crown-broker",
            capability="write-bounded-evidence",
            resource=resource,
            intended_effect={"sha256": _digest(encoded), "activity": intent.label},
            idempotency_key=_digest(
                f"{intent.run_id}:{intent.label}:{intent.occurrence}".encode()
            ),
            planner_id="sony-three-round-crown",
            environment_id="bounded-local-filesystem",
            revision_id=self.scenario_id,
        )

        def actuator(_: ActuationIntent) -> ActuationResult:
            if resource not in self._resources:
                raise PermissionError("REFUSED:RESOURCE_OUTSIDE_CROWN_WORKSPACE")
            path.write_bytes(encoded)
            current = path.read_bytes()
            effect.update(
                {
                    "resource": resource,
                    "sha256": _digest(current),
                    "bytes": len(current),
                }
            )
            return ActuationResult(
                acknowledgement=f"filesystem:{_digest(current)}",
                effect_evidence=dict(effect),
                possibly_actuated=True,
            )

        def observer(_: ActuationIntent, __: ActuationResult) -> Mapping[str, object]:
            current = path.read_bytes()
            decoded = json.loads(current)
            observed.update(
                {
                    "resource": resource,
                    "sha256": _digest(current),
                    "subject_id": decoded.get("subject_id"),
                    "scenario_id": decoded.get("scenario_id"),
                    "activity": decoded.get("activity"),
                }
            )
            return dict(observed)

        def verifier(_: ActuationIntent, postcondition: Mapping[str, object]) -> bool:
            return (
                postcondition.get("sha256") == _digest(encoded)
                and postcondition.get("subject_id") == SUBJECT_ID
                and postcondition.get("scenario_id") == self.scenario_id
                and postcondition.get("activity") == intent.label
            )

        decision = execute_brce(
            brce_intent,
            authority=self._authority,
            policy_id="sony-crown-bounded-local-policy/v1",
            policy_admits=lambda candidate: (
                candidate.subject_id == SUBJECT_ID
                and candidate.resource in self._resources
                and candidate.capability == "write-bounded-evidence"
            ),
            actuator=actuator,
            observer=observer,
            verifier_id="sony-crown-independent-file-verifier/v1",
            verifier=verifier,
        )
        if decision.standing is not BrceStanding.ALIVE or decision.receipt is None:
            return ActivityOutcome(
                success=False,
                metadata={
                    "brce_standing": decision.standing.value,
                    "reason": decision.reason,
                },
            )

        replay_standing = replay_receipt(
            decision.receipt,
            brce_intent,
            authority=self._authority,
            policy_id="sony-crown-bounded-local-policy/v1",
            acknowledgement=decision.receipt.acknowledgement,
            effect_evidence=effect,
            postcondition=observed,
            verifier_id="sony-crown-independent-file-verifier/v1",
        )
        return ActivityOutcome(
            success=replay_standing is BrceStanding.REPLAY_MATCH,
            value=dict(observed),
            authority_receipt=decision.receipt.receipt_id,
            metadata={
                "brce_standing": decision.standing.value,
                "brce_replay": replay_standing.value,
                "resource": resource,
            },
        )


def run_sony_crown(workspace: Path) -> SonyCrownEvidence:
    """Execute the bounded Sony three-round crown against one exact subject."""
    space = StateSpace(AXES)
    scenario = space.scenario(SONY_ARCHITECTURE_CHOICES)
    if not space.is_lawful(scenario):
        raise RuntimeError("REFUSED:SONY_ARCHITECTURE_NOT_ADMITTED")
    if scenario.authority != "NONE" or scenario.standing != "CANDIDATE":
        raise RuntimeError("REFUSED:CONSTRUCT_ACQUIRED_AMBIENT_AUTHORITY")

    model = _model()
    driver = _BrceFilesystemDriver(workspace, scenario_id=scenario.scenario_id)
    with PowlV2Runner() as runner:
        run = runner.run(model, driver, run_id=f"sony-crown:{scenario.scenario_id}")

    if run.status is not RunStatus.COMPLETED:
        raise RuntimeError(f"SONY_CROWN_{run.status.value}:{run.detail}")
    if not is_final(model, run.final_marking):
        raise RuntimeError("REFUSED:SONY_CROWN_NON_FINAL_MARKING")
    if replay(model, run.structural_records) != run.final_marking:
        raise RuntimeError("REFUSED:SONY_CROWN_STRUCTURAL_REPLAY_DRIFT")
    if len(run.activity_records) != len(_ACTIVITY_LABELS):
        raise RuntimeError("REFUSED:SONY_CROWN_ACTIVITY_ACCOUNTING_DRIFT")

    receipts = tuple(record.authority_receipt or "" for record in run.activity_records)
    replays = tuple(
        str(record.metadata.get("brce_replay", "")) for record in run.activity_records
    )
    if not all(receipts):
        raise RuntimeError("REFUSED:UNRECEIPTED_SONY_CROWN_ACTIVITY")
    if any(value != BrceStanding.REPLAY_MATCH.value for value in replays):
        raise RuntimeError("REFUSED:SONY_CROWN_RECEIPT_REPLAY_DRIFT")

    proof_labels = {requirement.proof_label for requirement in SONY_REQUIREMENTS}
    executed = {record.label for record in run.activity_records if record.committed}
    if not proof_labels <= executed:
        missing = sorted(proof_labels - executed)
        raise RuntimeError(f"REFUSED:SONY_REQUIREMENT_WITHOUT_EXECUTED_PROOF:{missing}")

    return SonyCrownEvidence(
        schema="autofde.sony-three-round-crown/1",
        standing="ALIVE",
        claim_ceiling=CLAIM_CEILING,
        subject_id=SUBJECT_ID,
        scenario_id=scenario.scenario_id,
        state_space_digest=space.digest,
        raw_upper_bound=space.raw_upper_bound,
        scenario_authority=scenario.authority,
        architecture=scenario.names(),
        requirement_ids=tuple(
            requirement.requirement_id for requirement in SONY_REQUIREMENTS
        ),
        activity_receipts=receipts,
        activity_replays=replays,
        powl_status=run.status.value,
        powl_model_sha256=run.model_sha256,
        peak_concurrency=run.peak_concurrency,
        worker_threads=run.worker_threads,
        structural_replay=BrceStanding.REPLAY_MATCH.value,
        ecosystem_pins=SONY_ECOSYSTEM_PINS,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    evidence = run_sony_crown(args.workspace)
    encoded = json.dumps(evidence.to_dict(), indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
