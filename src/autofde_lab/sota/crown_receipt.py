# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""The required crown receipt -- the real, enforced type behind this repo's own
`docs/autofde/benchmarks/cloud-agent-crown/sregym.md` "Victory-claim gate":

    "The external release may say 'AutoFDE defeated the prior state of the art' only
    after the exact benchmark subject is pinned and executed, the strongest same-semantics
    comparator is established, hidden-task contamination is excluded, benchmark-native
    verifier output and repeated-run statistics are retained, model/toolchain/config/
    cost/latency/actions/refusals are disclosed, and the result replays from a clean
    environment or official submission path. Until then: UNKNOWN or PARTIAL_ALIVE, never
    a crown claim."

That doc's own "Required crown receipt" line specifies the schema:

    benchmark SHA/dataset hash -> comparator identity/score -> AutoFDE repo SHA +
    planner/world-factory/adapter/model/toolchain identities -> exact execution
    subject/repeats/native verifier -> score/cost/latency/tokens-actions/refusals ->
    replay command/exit/receipt -> scoped standing

Before this module existed, that schema was prose only -- nothing refused an incomplete
claim. `CrownReceipt.admit()` is that refusal, real and typed, mirroring
`gymact.sota.StandingEvidence.admit()`'s exact discipline (composed here, not
reimplemented -- `gymact` already solved subject/experiment/receipt/verifier/
replay-verified admission for one gymact episode; this module adds only the
SREGym-crown-specific fields the doc lists on top of that).

No dual-bookkeeping: `materialize_crown_receipt` reads real facts off a real gymact
episode (its OCEL log, its Receipt trail) and a real `DecisionBasis` point already built
in `materialize_sregym.py` -- it never invents or duplicates a fact those already own.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from gymact.evidence import digest
from gymact.models import Operation
from gymact.ocel import validate_ocel_log
from gymact.process import ConformanceChecker
from gymact.sota import StandingEvidence

from autofde_lab.sota.decision_basis import DecisionBasis

if TYPE_CHECKING:
    from gymact.runtime import GymAct


class CrownReceiptAdmissionError(ValueError):
    """Typed refusal for a crown-claim receipt missing required evidence.

    Raised, never silently defaulted -- an incomplete receipt is refused by
    construction. This is the literal enforcement of "we are not validating their
    SOTA until our architecture is complete."
    """


@dataclass(frozen=True)
class CrownReceipt:
    """One candidate crown-claim record, per
    `docs/autofde/benchmarks/cloud-agent-crown/sregym.md`'s required schema.

    Every field is optional at construction time (a receipt is built up
    incrementally as real evidence becomes available) but `admit()` refuses unless
    every field the doc names is populated -- there is no partial-credit crown claim.
    """

    # benchmark SHA/dataset hash
    benchmark_sha: str | None = None

    # comparator identity/score -- the strongest same-semantics comparator being
    # compared against (e.g. the public leaderboard's current leader) and its score.
    comparator_identity: str | None = None
    comparator_score: float | None = None

    # AutoFDE repo SHA + planner/world-factory/adapter/model/toolchain identities
    autofde_repo_sha: str | None = None
    decision_basis: DecisionBasis | None = None

    # exact execution subject/repeats/native verifier
    execution_subject: str | None = None
    repeats: int | None = None
    native_verifier_name: str | None = None

    # score/cost/latency/tokens-actions/refusals
    score: float | None = None
    cost_usd: float | None = None
    latency_s: float | None = None
    tokens: int | None = None
    actions: int | None = None
    refusals: int | None = None

    # replay command/exit/receipt
    replay_command: tuple[str, ...] | None = None
    replay_exit_code: int | None = None

    # scoped standing -- composes gymact's own independent admission (subject/
    # experiment/receipt/verifier digests + replay_verified), the real, kernel-owned
    # evidence a single gymact episode produced.
    standing_evidence: StandingEvidence | None = None

    #: Free-form extra citations (doc paths, log paths) -- evidence, never load-bearing
    #: for admit()'s own required-field check.
    extra: dict[str, Any] = field(default_factory=dict)

    def admit(self) -> None:
        """Refuse unless every field the crown-receipt schema requires is present.

        Delegates to `self.standing_evidence.admit()` too (if set) -- a crown receipt
        with a present-but-incomplete `StandingEvidence` is refused with gymact's own
        real reason, not silently accepted here just because the outer fields are filled.
        """
        required: dict[str, object | None] = {
            "benchmark_sha": self.benchmark_sha,
            "comparator_identity": self.comparator_identity,
            "comparator_score": self.comparator_score,
            "autofde_repo_sha": self.autofde_repo_sha,
            "decision_basis": self.decision_basis,
            "execution_subject": self.execution_subject,
            "repeats": self.repeats,
            "native_verifier_name": self.native_verifier_name,
            "score": self.score,
            "cost_usd": self.cost_usd,
            "latency_s": self.latency_s,
            "tokens": self.tokens,
            "actions": self.actions,
            "refusals": self.refusals,
            "replay_command": self.replay_command,
            "replay_exit_code": self.replay_exit_code,
            "standing_evidence": self.standing_evidence,
        }
        missing = sorted(name for name, value in required.items() if value is None)
        if missing:
            raise CrownReceiptAdmissionError(
                f"REFUSED:CROWN_RECEIPT_MISSING_FIELD:{','.join(missing)}"
            )
        assert self.standing_evidence is not None  # narrowed by the check above
        self.standing_evidence.admit()


def standing_evidence_from_gymact_episode(
    gym: GymAct,
    episode_id: str,
    *,
    experiment_ref: object,
    verifier_ref: object,
) -> StandingEvidence:
    """Real, generic `StandingEvidence` for one already-run gymact episode.

    Not SREGym-specific -- this is the reusable composition point any gymact-backed
    benchmark crown receipt should build its `standing_evidence` from: reads the
    episode's real OCEL log (`gym.episode_ocel_log`), validates it against the real
    OCEL 2.0 schema, and replays its real extracted operation sequence in real
    recorded time order via `gymact.process.ConformanceChecker` -- exactly
    `.claude/rules/ocel-standing.md`'s own discipline, reused rather than
    reimplemented.

    Refuses (raises, never fabricates `replay_verified=True`) if the log is not
    schema-valid or the replay is not conformant -- `StandingEvidence.admit()` would
    refuse a `replay_verified=False` receipt anyway, but this function fails at the
    earliest real point rather than deferring to that later check.

    `experiment_ref`/`verifier_ref` are digested here (not required to already be
    strings) so a caller can pass the real `DecisionBasis` point and the real native
    verifier name directly, without a separate digesting step at each call site.
    """
    ocel_log = gym.episode_ocel_log(episode_id)
    validate_ocel_log(ocel_log)

    events_by_time = sorted(ocel_log["events"], key=lambda e: e["time"])
    operations = [Operation(e["type"]) for e in events_by_time]
    conformance = ConformanceChecker().check(operations)
    if not conformance.conformant:
        reasons = "; ".join(d.reason for d in conformance.deviations)
        raise CrownReceiptAdmissionError(f"REFUSED:NONCONFORMANT_REPLAY:{reasons}")

    receipts = gym.episode_receipts(episode_id)
    subject_refs = sorted({r.subject_ref for r in receipts if r.subject_ref})
    if not subject_refs:
        raise CrownReceiptAdmissionError("REFUSED:NO_SUBJECT_REF_IN_RECEIPT_TRAIL")

    return StandingEvidence(
        subject_digest=digest(subject_refs),
        experiment_digest=digest(experiment_ref),
        receipt_digest=digest([r.receipt_id for r in receipts]),
        verifier_digest=digest(verifier_ref),
        replay_verified=True,
    )
