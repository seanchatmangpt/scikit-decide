"""Evidence-bound crown verifier for the delta-to-solution-code path.

The verifier cannot make a performance claim from partial stage timings. It admits
ALIVE only when every required stage was observed for the same run and the measured
total is within the configured budget.
"""

from __future__ import annotations

from dataclasses import dataclass

REQUIRED_STAGES = (
    "delta",
    "process_inference",
    "hypothesis_closure",
    "planner_ensemble",
    "desired_state",
    "manufacture",
    "verifier_generation",
    "recovery_generation",
)


@dataclass(frozen=True)
class StageObservation:
    stage: str
    elapsed_ms: float
    subject_digest: str
    observed: bool = True

    def __post_init__(self) -> None:
        if self.stage not in REQUIRED_STAGES:
            raise ValueError("UNKNOWN_CROWN_STAGE_REFUSED")
        if self.elapsed_ms < 0:
            raise ValueError("NEGATIVE_STAGE_TIME_REFUSED")
        if not self.subject_digest.strip():
            raise ValueError("UNBOUND_STAGE_OBSERVATION_REFUSED")


@dataclass(frozen=True)
class CrownResult:
    run_id: str
    standing: str
    elapsed_ms: float
    budget_ms: float
    missing_stages: tuple[str, ...]
    subject_digest: str | None


def verify_failure_to_fix_crown(
    run_id: str,
    observations: tuple[StageObservation, ...],
    *,
    budget_ms: float = 1000.0,
) -> CrownResult:
    if not run_id.strip():
        raise ValueError("MISSING_RUN_ID_REFUSED")
    if budget_ms <= 0:
        raise ValueError("INVALID_CROWN_BUDGET_REFUSED")

    by_stage: dict[str, StageObservation] = {}
    for observation in observations:
        if observation.stage in by_stage:
            raise ValueError("DUPLICATE_CROWN_STAGE_REFUSED")
        by_stage[observation.stage] = observation

    missing = tuple(stage for stage in REQUIRED_STAGES if stage not in by_stage or not by_stage[stage].observed)
    subjects = {o.subject_digest for o in observations if o.observed}
    subject_digest = next(iter(subjects)) if len(subjects) == 1 else None
    elapsed = sum(o.elapsed_ms for o in observations if o.observed)

    if missing:
        standing = "PARTIAL_ALIVE"
    elif subject_digest is None:
        standing = "REFUSED"
    elif elapsed <= budget_ms:
        standing = "ALIVE"
    else:
        standing = "BUILD_BROKEN"

    return CrownResult(run_id, standing, elapsed, budget_ms, missing, subject_digest)
