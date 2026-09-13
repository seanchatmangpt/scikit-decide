# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Run the frozen crown under the DESTRUCTIVE criterion and report typed missing edges.

The orchestration this module performs, per frozen identity:

    1. execute the real producer (`run_real_trial`) in THIS process
    2. persist the level4 OCEL + commitment link into the trial's evidence dir
    3. launch `standalone_verifier.py` as a FRESH SUBPROCESS over that dir

Step 3 is the whole point. The verifier process has never imported the
producing runtime, so anything it reconstructs is reconstructed from durable
artifacts alone. This module deliberately does NOT call `verify()` in-process:
an in-process call would carry `level4_crown` in `sys.modules` and could not
establish independence, which is the property `assert_no_runtime_imports`
checks and the reason the verifier refuses to be a library here.

## Never a bare failure string

A trial that does not reconstruct is reported as a TYPED missing-edge reason
drawn from the verifier's own output, e.g.
``UNKNOWN:AUTHORITY_ACTUATION_JOIN_ABSENT`` -- the graph says what to fix. A
verdict of "trial failed" would be exactly the manufactured-semantics-from-
absence this repo's laws forbid: it collapses "which identity is missing" into
a number, and a number cannot be repaired.

## UNKNOWN is not NOT_ALIVE

An unestablished edge is `UNKNOWN:<REASON>` -- the evidence relation was never
established. It is NOT a checked-and-failed condition. Nothing in this module
may promote an UNKNOWN into a NOT_ALIVE to simplify reporting.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

#: Verifier edge name -> typed reason emitted when that edge is unestablished.
#: The reason names the missing JOIN, never the trial.
EDGE_REASON: dict[str, str] = {
    "plan_candidate->commitment": "UNKNOWN:PLAN_CANDIDATE_COMMITMENT_JOIN_ABSENT",
    "commitment->actuation": "UNKNOWN:COMMITMENT_ACTUATION_JOIN_ABSENT",
    "authority->actuation": "UNKNOWN:AUTHORITY_ACTUATION_JOIN_ABSENT",
    "actuation->postcondition": "UNKNOWN:GOAL_CONSEQUENCE_ABSENT",
    "postcondition->independent": "UNKNOWN:INDEPENDENT_OBSERVER_ABSENT",
    "receipt->dag": "UNKNOWN:RECEIPT_DAG_INCOMPLETE",
    "replay->receipt": "UNKNOWN:REPLAY_SOURCE_RECEIPT_ABSENT",
}

_VERIFIER = Path(__file__).with_name("standalone_verifier.py")


@dataclass(frozen=True)
class TrialReconstruction:
    """One frozen identity's independent result. Identity, never position."""

    identity: int
    provider: str
    trial_dir: str
    producer_outcome: str
    verifier_verdict: str
    established_edges: tuple[str, ...]
    missing_reasons: tuple[str, ...]
    verifier_stdout: str
    verifier_stderr: str

    def reconstructed_alive(self) -> bool:
        return self.verifier_verdict == "ALIVE_EVIDENCE_RECONSTRUCTED"

    def to_dict(self) -> dict:
        return {
            "identity": self.identity,
            "provider": self.provider,
            "trial_dir": self.trial_dir,
            "producer_outcome": self.producer_outcome,
            "verifier_verdict": self.verifier_verdict,
            "established_edges": list(self.established_edges),
            "missing_reasons": list(self.missing_reasons),
        }


def run_verifier_subprocess(trial_dir: Path) -> subprocess.CompletedProcess:
    """The real verifier, in a real fresh process. Never imported here."""
    return subprocess.run(
        [sys.executable, str(_VERIFIER), str(trial_dir)],
        capture_output=True,
        text=True,
        check=False,
    )


def parse_verifier_output(stdout: str) -> tuple[tuple[str, ...], str, tuple[str, ...]]:
    """(established edge names, verdict, typed missing reasons) from real output.

    Parsed from the verifier's own stdout rather than recomputed here: a second
    computation of the same relation is dual bookkeeping, and this module has no
    authority to decide what the verifier established.
    """
    established: list[str] = []
    missing: list[str] = []
    verdict = "UNKNOWN:VERIFIER_PRODUCED_NO_VERDICT"
    for raw in stdout.splitlines():
        line = raw.strip()
        if line.startswith("OK "):
            established.append(line[3:].split(":", 1)[0].strip())
        elif line.startswith("-- "):
            name = line[3:].split(":", 1)[0].strip()
            missing.append(EDGE_REASON.get(name, f"UNKNOWN:UNMAPPED_EDGE:{name}"))
        elif line.startswith("VERDICT:"):
            verdict = line.split(":", 1)[1].strip()
    if verdict.startswith("UNKNOWN:ARTIFACTS_ABSENT") and not missing:
        # No edges were even evaluated: the artifacts the chain lives in are
        # not on disk. That is a distinct, nameable missing relation, not a
        # silent zero.
        missing.append(f"UNKNOWN:{verdict.split(':', 1)[1]}")
    return tuple(established), verdict, tuple(missing)


def reconstruct_identity(
    seed: int,
    provider: str,
    config: dict,
    evidence_root: Path,
) -> TrialReconstruction:
    """Execute one frozen identity, persist, then verify in a fresh subprocess."""
    # Imported here, not at module scope: the producer belongs to the
    # orchestrator's process only, and this keeps the import cost off any
    # consumer that only wants the parsing helpers.
    from autofde_lab.hub.domain.gym_procedure.level4_crown import run_real_trial

    report = run_real_trial(seed, provider, config, evidence_root)
    trial_dir = Path(report.evidence_dir)
    _persist_level4_ocel(trial_dir)

    proc = run_verifier_subprocess(trial_dir)
    established, verdict, missing = parse_verifier_output(proc.stdout)
    return TrialReconstruction(
        identity=seed,
        provider=provider,
        trial_dir=str(trial_dir),
        producer_outcome=report.outcome,
        verifier_verdict=verdict,
        established_edges=established,
        missing_reasons=missing,
        verifier_stdout=proc.stdout,
        verifier_stderr=proc.stderr,
    )


def _persist_level4_ocel(trial_dir: Path) -> None:
    """Build the level4 OCEL from the producer's own witness journal.

    This is a projection of what the producer already stated at each causal
    transition -- it never manufactures a relation the journal does not carry.
    A trial that never reached actuation has no actuation dir; that absence is
    reported by the verifier as ARTIFACTS_ABSENT rather than papered over.
    """
    from autofde_lab.hub.domain.gym_procedure.level4_ocel import (
        build_level4_ocel,
        link_commitment_ttl,
    )

    act = trial_dir / "actuation"
    if not (act / "commitment.ttl").is_file():
        return
    built = build_level4_ocel(trial_dir)
    if built.episode_id is not None and built.environment_id is not None:
        link_commitment_ttl(
            act / "commitment.ttl",
            episode_id=built.episode_id,
            environment_id=built.environment_id,
        )
        built = build_level4_ocel(trial_dir)
    (act / "level4.ocel.json").write_text(
        json.dumps(built.log.to_ocel2_json(), sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )


@dataclass(frozen=True)
class CrownReconstruction:
    """The identity-set comparison. Sets, never counts."""

    manifest_digest: str
    frozen_identities: frozenset[int]
    trials: tuple[TrialReconstruction, ...]

    def reconstructed_alive_set(self) -> frozenset[int]:
        return frozenset(t.identity for t in self.trials if t.reconstructed_alive())

    def unknown_set(self) -> frozenset[int]:
        witnessed = frozenset(t.identity for t in self.trials)
        return frozenset(
            t.identity
            for t in self.trials
            if not t.reconstructed_alive() and t.verifier_verdict.startswith("UNKNOWN")
        ) | (self.frozen_identities - witnessed)

    def not_alive_set(self) -> frozenset[int]:
        """Checked-and-contradicted identities only. Never an UNKNOWN."""
        return frozenset(
            t.identity
            for t in self.trials
            if not t.reconstructed_alive() and not t.verifier_verdict.startswith("UNKNOWN")
        )

    def missing_identities(self) -> frozenset[int]:
        return self.frozen_identities - self.reconstructed_alive_set()

    def foreign_identities(self) -> frozenset[int]:
        return frozenset(t.identity for t in self.trials) - self.frozen_identities

    def complete(self) -> bool:
        return (
            self.reconstructed_alive_set() == self.frozen_identities
            and not self.unknown_set()
            and not self.not_alive_set()
        )

    def to_dict(self) -> dict:
        return {
            "manifest_digest": self.manifest_digest,
            "denominator": len(self.frozen_identities),
            "frozen_identities": sorted(self.frozen_identities),
            "reconstructed_alive_set": sorted(self.reconstructed_alive_set()),
            "missing_identities": sorted(self.missing_identities()),
            "foreign_identities": sorted(self.foreign_identities()),
            "unknown_members": sorted(self.unknown_set()),
            "not_alive_members": sorted(self.not_alive_set()),
            "complete": self.complete(),
            "trials": [t.to_dict() for t in self.trials],
        }


def reconstruct_crown(manifest_path: Path, evidence_root: Path) -> CrownReconstruction:
    from autofde_lab.hub.domain.gym_procedure.level4_crown_runner import load_crown

    crown = load_crown(manifest_path)
    evidence_root.mkdir(parents=True, exist_ok=True)
    trials: list[TrialReconstruction] = []
    for seed, provider, config in zip(
        crown.seeds, crown.provider_assignments, crown.configs
    ):
        trials.append(reconstruct_identity(seed, provider, config, evidence_root))
    return CrownReconstruction(
        manifest_digest=crown.manifest_digest,
        frozen_identities=frozenset(crown.seeds),
        trials=tuple(trials),
    )


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: crown_reconstruct.py <crown_manifest.json> <evidence_root>", file=sys.stderr)
        return 2
    result = reconstruct_crown(Path(argv[1]), Path(argv[2]))
    out = Path(argv[2]) / "reconstruction.json"
    out.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
    for t in result.trials:
        print(
            f"{t.identity} {t.provider:24s} outcome={t.producer_outcome:12s} "
            f"{t.verifier_verdict if t.reconstructed_alive() else ','.join(t.missing_reasons) or t.verifier_verdict}"
        )
    print()
    print("manifest_digest:", result.manifest_digest)
    print("frozen        :", sorted(result.frozen_identities))
    print("alive_set     :", sorted(result.reconstructed_alive_set()))
    print("missing       :", sorted(result.missing_identities()))
    print("foreign       :", sorted(result.foreign_identities()))
    print("UNKNOWN       :", sorted(result.unknown_set()))
    print("NOT_ALIVE     :", sorted(result.not_alive_set()))
    print("COMPLETE      :", result.complete())
    return 0 if result.complete() else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
