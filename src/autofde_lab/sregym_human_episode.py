# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Real, typed schema for one human-walked SREGym validation episode.

Schema only -- deliberately no automation logic here. The whole point of
`docs/sregym-human-validation-guide.md`'s canonical loop is that a human,
blinded to the injected fault, actually walks Observe -> Normalize ->
Hypothesize -> Discriminate -> Diagnose -> Construct -> Actuate -> Verify
-> Receipt in person; automating any of that would defeat the guide's
purpose (see the guide's own Phase 3: "The human should not know the
injected fault before troubleshooting... Otherwise we are testing
procedure replay, not diagnosis"). These models exist so a human's
filled-in episode is a real, checkable, schema-valid artifact -- not
free-form prose a later reader has to trust at face value.

Every field here maps to a real, already-existing gymact primitive where
one exists, rather than inventing a parallel vocabulary (see the guide's
own citation table):
- `HypothesisLedger.state` uses the guide's own explicit epistemic
  ontology (`SUPPORTED != PROVEN`, `UNKNOWN != FALSE`) -- a real,
  three-valued state, not a boolean.
- `HumanEpisodeReceipt.status_*` fields reuse `gymact.models.Standing`'s
  real vocabulary (`BLOCKED`, `UNKNOWN`, ...) rather than a bespoke
  pass/fail bit, matching the guide's Phase 1/2 distinction between
  `STATUS = BLOCKED:ENVIRONMENT` (the harness's own setup failed) and a
  genuine diagnostic failure -- these must never be conflated into one
  score.
- `HumanEpisodeReceipt.verification` deliberately separates "mutation
  accepted" from "desired state changed" from "service recovered" as
  distinct real booleans (the guide's Phase 14 recovery chain), matching
  gymact's own consequence law: `request accepted != world changed !=
  objective verified != benchmark scored`.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class HypothesisState(StrEnum):
    """Real, three-valued epistemic state for one candidate root-cause
    hypothesis -- per the guide's own explicit ontology: `UNKNOWN` is not
    the same claim as `REFUTED`, and `SUPPORTED` is not the same claim as
    `PROVEN`. A hypothesis starts `UNKNOWN` and only moves to `SUPPORTED`
    or `REFUTED` on real, cited evidence -- never defaulted."""

    UNKNOWN = "unknown"
    SUPPORTED = "supported"
    REFUTED = "refuted"


class HypothesisLedger(BaseModel):
    """One candidate root-cause hypothesis and the real evidence that
    moved it to its current state -- the guide's Phase 8-10 "hypothesis
    portfolio," kept explicit so premature convergence on the first
    plausible story is visible in the record, not hidden behind a single
    final answer."""

    hypothesis: str = Field(description="the real, specific candidate root cause")
    evidence: str = Field(
        default="",
        description="the real observation that supports or refutes this hypothesis -- "
        "empty string only while state is still UNKNOWN",
    )
    state: HypothesisState = HypothesisState.UNKNOWN


class BaselineHealth(BaseModel):
    """Phase 1: the real, pre-injection healthy control -- required before
    any failure can be confidently attributed to the injected scenario
    rather than pre-existing environment trouble."""

    deployments_ready: bool
    no_restart_storm: bool
    service_endpoints_populated: bool
    representative_request_succeeded: bool
    notes: str = ""


class ManifestationCheck(BaseModel):
    """Phase 3: did the injected fault actually produce a real, observable
    failure? A scenario whose injection never manifests is `SCENARIO =
    INVALID`, not a failed diagnosis -- these must never be conflated
    (`Injected != Manifested != Diagnosed`)."""

    manifested: bool
    observed_symptom: str = Field(
        description="the real, concrete symptom observed (e.g. 'Pod Pending', "
        "'CrashLoopBackOff'), or empty if manifested is False"
    )


class DiagnosisRecord(BaseModel):
    """Phase 11: the real diagnosis, stated BEFORE any mitigation is
    constructed -- keeps diagnosis and mitigation as two separately
    gradeable claims, per the guide's own Phase 11/12 split."""

    observed_symptom: str
    immediate_mechanism: str
    root_cause: str
    supporting_evidence: str
    confidence: str = Field(description="e.g. 'high'/'medium'/'low', the human's own real assessment")


class MitigationRecord(BaseModel):
    """Phase 12-13: the real, constructed fix and its real authorization --
    matching `.claude/rules/actuation-authority.md`'s own SELECT ->
    CONSTRUCT -> DO separation (a recommended fix is not the same event as
    the fix actually being applied)."""

    action: str = Field(description="the real, concrete remediation constructed")
    authorized: bool = Field(description="was this actuation admitted through a real authority boundary")
    applied: bool = Field(default=False, description="was this action actually executed, not just proposed")


class VerificationRecord(BaseModel):
    """Phase 14: the real recovery chain, kept as separate booleans on
    purpose -- `kubectl patch` returning exit code 0 does not mean the
    incident is fixed. Matches gymact's own consequence law: mutation
    accepted != desired state changed != controller reconciled != workload
    recovered != user-level behavior recovered."""

    mutation_accepted: bool
    rollout_complete: bool
    pods_ready: bool
    functional_check_passed: bool


class SafetyCheck(BaseModel):
    """Phase 15: bounded regression check -- did the mitigation avoid
    prohibited/destructive actions and avoid creating a new incident."""

    violations: int = 0
    regression_notes: str = ""


class OracleComparison(BaseModel):
    """Phase 16: revealed ONLY after the human commits their diagnosis and
    mitigation -- never available to the human beforehand (that would make
    this procedure replay, not diagnosis). Diagnosis, mitigation, and
    verification are graded as three separate claims, never collapsed
    into one pass/fail bit."""

    diagnosis_matched_oracle: bool | None = None
    mitigation_accepted: bool | None = None
    recovery_verified: bool | None = None


class HumanEpisodeReceipt(BaseModel):
    """One complete, real, schema-valid record of a human walking SREGym's
    canonical troubleshooting loop against one real, live, blinded
    scenario -- the reference process an agent's own trace (e.g.
    `gymact.dspy_ocel`'s real OCEL log of a DSPy run) can eventually be
    compared against. Every phase from the guide is represented as a real,
    typed field, not free prose."""

    episode_id: str
    scenario_namespace: str = Field(description="the real namespace investigated (known ahead of time)")
    started_at: datetime
    completed_at: datetime | None = None

    baseline: BaselineHealth
    manifestation: ManifestationCheck
    observations: list[str] = Field(
        default_factory=list, description="real, ordered raw observations collected (Phase 4-5)"
    )
    normalized_facts: list[str] = Field(
        default_factory=list,
        description="real observations converted into explicit semantic assertions (Phase 6)",
    )
    hypotheses: list[HypothesisLedger] = Field(default_factory=list)
    diagnosis: DiagnosisRecord | None = None
    mitigation: MitigationRecord | None = None
    verification: VerificationRecord | None = None
    safety: SafetyCheck = Field(default_factory=SafetyCheck)
    oracle: OracleComparison = Field(default_factory=OracleComparison)

    # Reuses `gymact.models.Standing`'s real vocabulary (as a plain string
    # here to avoid a hard runtime dependency on gymact's optional-extra
    # boundary from this schema module) -- `BLOCKED`/`UNKNOWN`/etc. keep
    # a harness-side failure (e.g. cluster unreachable) distinct from a
    # genuine diagnostic failure, per the guide's Phase 1/2 discipline.
    status: str = Field(
        default="UNKNOWN",
        description="a real gymact Standing value (BLOCKED/UNKNOWN/ALIVE/REFUSED/...) -- "
        "never a bespoke pass/fail bit",
    )
