# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Lab-scoped result standing that refuses to become production standing
(`V2030.1.1-PRD-ARD.md` capability 9: keep research/lab result standing
distinct from production AutoFDE standing; falsifier: "if benchmark
success grants production actuation").

**The one law every type in this module obeys**: a laboratory result is
evidence *about an experiment*, never observed production evidence. A
candidate whose falsification standing is `SURVIVES` survived *this
repo's* attempt to kill it in a gym world -- that is not an observation
of the production consequence `autofde` would have to admit. So
`production_technical_claim` answers `UNKNOWN:...` for **every** lab
standing, including `SURVIVES` (`.claude/rules/absence-is-not-evidence.md`
applied to standing itself: not falsified in the lab != known alive in
production).

`GraduationPacket` carries exact identities only (candidate, world digest,
receipt/benchmark/falsifier refs, limits, and the *name* of the downstream
admitter). It deliberately has no `standing` field: standing is a query
over evidence the downstream admitter runs, never a field this repo stores
and hands forward (`.claude/rules/no-dual-bookkeeping.md`). Graduation
therefore transfers evidence, never lab authority.

This module selects nothing and actuates nothing. It carries no receipt,
admission, or actuation semantics -- it is a typed boundary that makes the
lab/production distinction a contract instead of an accident of two
vocabularies happening not to be wired together.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import TYPE_CHECKING, Literal

from autofde_lab.reasoning.dflss_solve_payoff_bridge import DflssSolvePayoffOutcome
from autofde_lab.reasoning.exploration_payoff_bridge import ExplorationPayoffOutcome
from autofde_lab.reasoning.laboratory import (
    ExperimentReceipt,
    FalsificationResult,
    FalsificationStanding,
)

if TYPE_CHECKING:
    # Deferred: `disturbance_episode.py` eagerly resolves
    # `world_admission.WORLD_DOMAIN_FACTORIES` at import time, which
    # transitively imports every registered domain (`maze`, `breach_clock`,
    # ...) and, through them, `hub.space.gym` -> `gymnasium`. That chain has
    # nothing to do with this module's actual job (refusing a category of
    # evidence from crossing a boundary), and a real, minimal-dependency CI
    # job (`payoff-bundle-qualification.yml`, which never installs
    # `gymnasium`) imports `fabric.cli`, which imports this module -- a
    # module-level import here would make merely importing `lab_standing`
    # require the entire domain registry. Deferred into
    # `disturbance_episode_production_claim()` below instead.
    from autofde_lab.planner_league.disturbance_episode import DisturbanceEpisodeResult

    # Same reason, same fix: `cross_play_world_schedule.py` also
    # module-level-imports `world_admission.WORLD_DOMAIN_FACTORIES`.
    # Deferred into `scheduled_match_payoff_production_claim()` below.
    from autofde_lab.reasoning.cross_play_schedule_payoff import (
        ScheduledMatchPayoffOutcome,
    )

__all__ = [
    "LAB_SCOPE",
    "PRODUCTION_CLAIM_REFUSAL",
    "REQUIRED_DOWNSTREAM_ADMISSION",
    "GraduationPacket",
    "LabResultStanding",
    "dflss_solve_payoff_production_claim",
    "disturbance_episode_production_claim",
    "experiment_receipt_production_claim",
    "exploration_payoff_production_claim",
    "graduation_packet",
    "production_technical_claim",
    "scheduled_match_payoff_production_claim",
]

LAB_SCOPE: Literal["LAB"] = "LAB"

# The typed refusal every lab standing maps to when asked for a production
# technical claim. Its base token is `UNKNOWN`, which is inside
# `fabric.enterprise_standing._STANDING_BASES`, so a caller that forwards it
# into `derive_enterprise_standing` fails closed (enterprise `UNKNOWN`)
# rather than raising -- the refusal is representable downstream, the lab
# vocabulary (`SURVIVES`, ...) intentionally is not.
PRODUCTION_CLAIM_REFUSAL = "UNKNOWN:LAB_RESULT_NOT_PRODUCTION_EVIDENCE"

# The only admitter that may turn a graduation packet into production
# standing (`V2030.1.1-PRD-ARD.md`, "Ecosystem contract": `autofde` must
# independently admit any graduated policy or architecture).
REQUIRED_DOWNSTREAM_ADMISSION: Literal["autofde"] = "autofde"


@dataclass(frozen=True, slots=True)
class LabResultStanding:
    """A real `FalsificationResult` tagged with the scope it was earned in.

    Constructible only from a real `FalsificationResult` -- there is no
    way to mint one from a bare string, so a lab standing always traces
    back to the `falsify_candidate` run that produced it.
    """

    candidate_id: str
    falsification: FalsificationResult
    world_ref_digest: str
    receipt_refs: tuple[str, ...] = ()
    scope: Literal["LAB"] = LAB_SCOPE

    def __post_init__(self) -> None:
        if not isinstance(self.falsification, FalsificationResult):
            raise TypeError("LAB_STANDING_REQUIRES_REAL_FALSIFICATION_RESULT")
        if self.falsification.candidate_id != self.candidate_id:
            raise ValueError(
                f"LAB_STANDING_CANDIDATE_MISMATCH:{self.candidate_id}!={self.falsification.candidate_id}"
            )
        if self.scope != LAB_SCOPE:
            raise ValueError(f"LAB_STANDING_SCOPE_NOT_LAB:{self.scope}")

    @property
    def lab_standing(self) -> FalsificationStanding:
        """The lab-scoped verdict, in the lab vocabulary only."""
        return self.falsification.standing


def production_technical_claim(lab: LabResultStanding) -> str:
    """What this lab result licenses as a production technical claim: nothing.

    Returns the typed refusal for every lab standing. The refusal is
    scope-based, not outcome-based -- `SURVIVES`, `FALSIFIED`, `PARTIAL`,
    `UNSUPPORTED`, `REFUSED` and `UNKNOWN` all answer the same way, because
    none of them is an observation of production consequence. Never `ALIVE`.
    """
    if lab.scope != LAB_SCOPE:
        raise ValueError(f"LAB_STANDING_SCOPE_NOT_LAB:{lab.scope}")
    return PRODUCTION_CLAIM_REFUSAL


def exploration_payoff_production_claim(outcome: ExplorationPayoffOutcome) -> str:
    """What a real `exploration_payoff_bridge.ExplorationPayoffOutcome`
    licenses as a production technical claim: nothing -- the same law
    `production_technical_claim` already states for `LabResultStanding`,
    applied to the second real producer of lab-scoped evidence in this repo.

    `ExplorationPayoffOutcome` is the second real producer of lab-scoped
    result standing (`laboratory.falsify_candidate` -> `LabResultStanding`
    is the first, boundary already closed above). It carries this repo's
    generic cross-module success token `'ALIVE'` in its own `standing` field
    when a payoff was admitted -- that token is correct and unchanged
    (`ALIVE:EXPLORATION_FALSIFICATION_PAYOFF_ADMITTED` means the payoff edge
    was constructed and added to the caller's `PayoffHypergraph`, nothing
    more) but it is still evidence about an experiment inside a
    `PlannerLeague`/`PayoffHypergraph` gym-scored league match, never
    observed production evidence. Per `.claude/rules/absence-is-not-evidence.md`
    applied to standing itself: a lab experiment not being falsified inside
    this repo is not the same fact as production having observed the
    candidate succeed.

    Returns the exact same typed refusal `production_technical_claim`
    returns, regardless of `outcome.standing` -- `'ALIVE'` (a payoff was
    admitted), `'REFUSED'` (identity mismatch, incompatible planner, or no
    receipt refs), or any real `FalsificationStanding` value forwarded
    unadmitted (`'UNKNOWN'`, `'UNSUPPORTED'`, `'REFUSED'`) all answer
    identically. There is no exploration payoff outcome -- admitted or
    not -- that could ever license a production claim, so the boundary does
    not branch on `outcome.observation` either: a `None` observation and a
    real `PayoffObservation` both refuse the same way.
    """
    if not isinstance(outcome, ExplorationPayoffOutcome):
        raise TypeError("EXPLORATION_PAYOFF_CLAIM_REQUIRES_REAL_OUTCOME")
    return PRODUCTION_CLAIM_REFUSAL


def dflss_solve_payoff_production_claim(outcome: DflssSolvePayoffOutcome) -> str:
    """What a real `dflss_solve_payoff_bridge.DflssSolvePayoffOutcome`
    licenses as a production technical claim: nothing -- the same law this
    module already states for `ExplorationPayoffOutcome`, applied to its
    real sibling type (`dflss_solve_payoff_bridge.py`'s own docstring:
    `DflssSolvePayoffOutcome` "mirrors `ExplorationPayoffOutcome`'s own
    `(observation/standing/reason)` shape").

    `DflssSolvePayoffOutcome` is the real, per-planner head-to-head
    admission outcome of two real planners each independently attempting
    `dflss_planner_solve.attempt_solve_dflss_curriculum`'s DMEDI-curriculum
    PDDL problem. It carries this repo's generic cross-module success token
    `'ALIVE'` in its own `standing` field when a payoff was admitted, and
    that field is now real, externally visible CLI output: `fabric.cli`'s
    `dmedi-solve-payoff` subcommand (added the same session `V2030.1.1`
    capability 9's boundary was generalized) emits `result.standing`
    directly as JSON, unwrapped. The token is correct and unchanged for
    what it is -- the payoff edge was constructed and added to the
    caller's `PayoffHypergraph` -- but it is still evidence about an
    experiment inside a `PlannerLeague`/`PayoffHypergraph` gym-scored
    league match, never observed production evidence. Per
    `.claude/rules/absence-is-not-evidence.md` applied to standing itself:
    two real planners both reaching the DMEDI-curriculum goal in the lab is
    not the same fact as production having observed either succeed.

    Returns the exact same typed refusal every other boundary function in
    this module returns, regardless of `outcome.standing` -- `'ALIVE'`
    (a payoff was admitted, including the honest tie both planners reach
    on this deterministic domain), `'REFUSED'` (identity mismatch or no
    receipt refs), or any other value a caller could construct all answer
    identically. The boundary does not branch on `outcome.left_outcome`,
    `outcome.right_outcome`, or `outcome.observation` either: this
    function's job is to refuse a *category* of evidence (lab head-to-head
    match consequence) from crossing into a production claim, not to grade
    either planner's own outcome.
    """
    if not isinstance(outcome, DflssSolvePayoffOutcome):
        raise TypeError("DFLSS_SOLVE_PAYOFF_CLAIM_REQUIRES_REAL_OUTCOME")
    return PRODUCTION_CLAIM_REFUSAL


def scheduled_match_payoff_production_claim(
    outcome: ScheduledMatchPayoffOutcome,
) -> str:
    """What a real `cross_play_schedule_payoff.ScheduledMatchPayoffOutcome`
    licenses as a production technical claim: nothing -- the same law this
    module already states for `DflssSolvePayoffOutcome`, applied to its
    real sibling producer (`cross_play_schedule_payoff.py`'s own docstring:
    reuses `dflss_solve_payoff_bridge`'s established `1.0 ALIVE / 0.0
    otherwise` score contract, never re-derived).

    `ScheduledMatchPayoffOutcome` is the real, per-match outcome of
    real-solving both planners of one real scheduled `LeagueMatch`
    produced by `cross_play_world_schedule.schedule_cross_play_for_world`,
    then admitting a real `PayoffObservation` into a `PayoffHypergraph` via
    `admit_cross_play_schedule_payoffs`. It carries this repo's generic
    cross-module success token `'ALIVE'` in its own `standing` field when a
    payoff was admitted -- correct and unchanged for what it is, but still
    evidence about an experiment inside a `PlannerLeague`/`PayoffHypergraph`
    gym-scored league match, never observed production evidence. Per
    `.claude/rules/absence-is-not-evidence.md` applied to standing itself:
    a real planner reaching a scheduled match's goal in the lab is not the
    same fact as production having observed it succeed.

    Returns the exact same typed refusal every other boundary function in
    this module returns, regardless of `outcome.standing` -- `'ALIVE'`
    (a payoff was admitted) or any other value a caller could construct
    all answer identically. The boundary does not branch on
    `outcome.match`, `outcome.left_outcome`, `outcome.right_outcome`, or
    `outcome.observation` either: this function's job is to refuse a
    *category* of evidence (scheduled-match consequence) from crossing
    into a production claim, not to grade either planner's own outcome.
    """
    # Deferred (see the `TYPE_CHECKING` import above): importing
    # `cross_play_schedule_payoff` at call time, not module load time,
    # keeps this module importable without the full domain registry (and
    # `gymnasium`) in a real, minimal-dependency CI job that never
    # installs either.
    from autofde_lab.reasoning.cross_play_schedule_payoff import (
        ScheduledMatchPayoffOutcome as _ScheduledMatchPayoffOutcome,
    )

    if not isinstance(outcome, _ScheduledMatchPayoffOutcome):
        raise TypeError("SCHEDULED_MATCH_PAYOFF_CLAIM_REQUIRES_REAL_OUTCOME")
    return PRODUCTION_CLAIM_REFUSAL


def experiment_receipt_production_claim(receipt: ExperimentReceipt) -> str:
    """What a real `laboratory.ExperimentReceipt` licenses as a production
    technical claim: nothing -- the same law `production_technical_claim`
    states for `LabResultStanding` and `exploration_payoff_production_claim`
    states for `ExplorationPayoffOutcome`, applied to the third real
    producer of lab-scoped evidence in this repo.

    `ExperimentReceipt` is real observed consequence evidence *inside a
    laboratory experiment* -- its own module docstring is explicit that it
    must "never [be] equated with 'candidate says it works'". Its bare
    `str` `standing` field can legitimately hold this repo's generic
    cross-module success token `'ALIVE'` (real fixtures in
    `tests/reasoning/test_laboratory_chicago.py` construct receipts with
    `standing='ALIVE'`), and its `authority_standing` field is likewise an
    unconstrained `str`. Neither field is typed to stop a future caller
    from feeding either one into
    `fabric.enterprise_standing.derive_enterprise_standing(technical_standing=...)`
    as though it were observed production evidence -- it would not be: a
    receipt's `standing='ALIVE'` records that the *lab's own* experiment
    apparatus considered the observation well-formed, never that
    `autofde` observed a production consequence. Per
    `.claude/rules/absence-is-not-evidence.md` applied to standing itself:
    a lab receipt not indicating a violation is not the same fact as
    production having observed success.

    Returns the exact same typed refusal `production_technical_claim` and
    `exploration_payoff_production_claim` return, regardless of the
    receipt's own `standing` or `authority_standing` values -- `'ALIVE'`
    (including the most dangerous-looking case, an `'ALIVE'`-standing
    receipt with `authority_standing='ALIVE'` and no violated
    postconditions), `'UNKNOWN'` (the dataclass default), `'UNSUPPORTED'`,
    or any other string a caller could construct all answer identically.
    The boundary does not branch on `postconditions_observed`,
    `postconditions_violated`, or `ocel_evidence_ref` either: this
    function's job is to refuse a *category* of evidence (lab-experiment
    consequence) from crossing into a production claim, not to grade the
    experiment's own outcome.
    """
    if not isinstance(receipt, ExperimentReceipt):
        raise TypeError("EXPERIMENT_RECEIPT_CLAIM_REQUIRES_REAL_RECEIPT")
    return PRODUCTION_CLAIM_REFUSAL


def disturbance_episode_production_claim(result: DisturbanceEpisodeResult) -> str:
    """What a real `planner_league.disturbance_episode.DisturbanceEpisodeResult`
    licenses as a production technical claim: nothing -- the same law this
    module states for `LabResultStanding`, `ExplorationPayoffOutcome`, and
    `ExperimentReceipt`, applied to the fourth real producer of lab-scoped
    evidence in this repo.

    `DisturbanceEpisodeResult` is the real outcome of replaying one
    constructor plan against one admitted adversarial `Disturbance`
    (`V2030.1.1-PRD-ARD.md` capability 6: adversarial/chaos/mutation
    scenarios). Its `standing` field is a `DisturbanceStanding` --
    `SURVIVES`, `FALSIFIED`, or `UNKNOWN` -- the same shape
    `FalsificationStanding` already carries, and
    `disturbance_episode.disturbance_result_to_payoff()` projects a
    `SURVIVES` standing into a `PayoffObservation` tagged
    `f"ALIVE:DISTURBANCE_PAYOFF:{result.standing.value}"`. That token
    records that this repo's own red-team apparatus failed to falsify the
    constructor plan against one disturbance in one gym world -- it is not
    an observation of a production consequence. Per
    `.claude/rules/absence-is-not-evidence.md` applied to standing itself:
    a disturbance not falsifying a plan in the lab is not the same fact as
    production having observed the plan survive.

    Returns the exact same typed refusal `production_technical_claim`,
    `exploration_payoff_production_claim`, and
    `experiment_receipt_production_claim` return, regardless of
    `result.standing` -- `SURVIVES`, `FALSIFIED`, and `UNKNOWN` all answer
    identically. The boundary does not branch on `reason`, `plan_length`,
    or `trajectory` either: this function's job is to refuse a *category*
    of evidence (adversarial-episode consequence) from crossing into a
    production claim, not to grade the episode's own outcome.
    """
    # Deferred (see the `TYPE_CHECKING` import above): importing
    # `disturbance_episode` at call time, not module load time, keeps this
    # module importable without the full domain registry (and `gymnasium`)
    # in a real, minimal-dependency CI job that never installs either.
    from autofde_lab.planner_league.disturbance_episode import (
        DisturbanceEpisodeResult as _DisturbanceEpisodeResult,
    )

    if not isinstance(result, _DisturbanceEpisodeResult):
        raise TypeError("DISTURBANCE_EPISODE_CLAIM_REQUIRES_REAL_RESULT")
    return PRODUCTION_CLAIM_REFUSAL


@dataclass(frozen=True, slots=True)
class GraduationPacket:
    """Exact identities handed to the downstream admitter -- no standing.

    Every field is a reference, a digest, or the primary evidence object
    itself; none is a verdict. The lab outcome travels as the real
    `FalsificationResult` it came from, not as a copied string: a copy would
    be a second bookkeeping location for the lab verdict that could drift
    from the result it claims to summarise (`no-dual-bookkeeping.md`). The
    scope-named `lab_falsification_standing` is a *query* over that object.
    """

    candidate_id: str
    falsification: FalsificationResult
    world_ref_digest: str
    receipt_refs: tuple[str, ...]
    benchmark_refs: tuple[str, ...]
    falsifier_refs: tuple[str, ...]
    limits: tuple[str, ...]
    required_downstream_admission: Literal["autofde"] = REQUIRED_DOWNSTREAM_ADMISSION

    def __post_init__(self) -> None:
        # Guard the no-dual-bookkeeping contract structurally, so a later
        # edit cannot quietly add a stored verdict to this packet.
        forbidden = {"standing", "alive", "is_alive", "technical_standing"}
        present = forbidden & {f.name for f in fields(self)}
        if present:
            raise ValueError(f"GRADUATION_PACKET_CARRIES_STANDING:{sorted(present)}")
        if not isinstance(self.falsification, FalsificationResult):
            raise TypeError("GRADUATION_PACKET_REQUIRES_REAL_FALSIFICATION_RESULT")
        if self.falsification.candidate_id != self.candidate_id:
            raise ValueError(
                f"GRADUATION_PACKET_CANDIDATE_MISMATCH:{self.candidate_id}!={self.falsification.candidate_id}"
            )
        if self.required_downstream_admission != REQUIRED_DOWNSTREAM_ADMISSION:
            raise ValueError(
                f"GRADUATION_REQUIRES_AUTOFDE_ADMISSION:{self.required_downstream_admission}"
            )

    @property
    def lab_falsification_standing(self) -> str:
        """The lab verdict, read from the result it belongs to -- never stored."""
        return self.falsification.standing.value


def graduation_packet(
    lab: LabResultStanding,
    *,
    benchmark_refs: tuple[str, ...] = (),
    falsifier_refs: tuple[str, ...] = (),
    limits: tuple[str, ...] = (),
) -> GraduationPacket:
    """Project a lab standing into the evidence packet `autofde` must admit.

    Nothing here decides whether the candidate graduates -- that decision is
    the downstream admitter's, made over these identities plus its own
    observations. This function only makes the lab evidence exact.
    """
    return GraduationPacket(
        candidate_id=lab.candidate_id,
        falsification=lab.falsification,
        world_ref_digest=lab.world_ref_digest,
        receipt_refs=tuple(lab.receipt_refs) + tuple(lab.falsification.receipt_refs),
        benchmark_refs=tuple(benchmark_refs),
        falsifier_refs=tuple(falsifier_refs)
        + tuple(lab.falsification.counterexample_refs),
        limits=tuple(limits),
    )
