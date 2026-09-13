"""The Executable Research Claim (ERC) data model.

Implements paper sections 6-9 (``docs/2026-09-12-executable-design-science.md``):
the ERC tuple, the evidence-state vocabulary, receipt binding, and falsifiers
as first-class, actually-callable checks rather than prose.

Scope, named explicitly (per the paper's own falsifier F6 -- do not add
machinery whose cost exceeds its epistemic value): this module implements
ONLY the single-claim verification procedure. It does NOT implement:

- object-centric experiment logging (paper S11) -- no OCEL emission here;
- process-conformance checking against a declared protocol (paper S12) --
  ``ExecutableResearchClaim.protocol`` is stored but not conformance-checked;
- the comparative C_DSR vs C_EDS evaluation framework (paper S18);
- independent (cross-investigator) reproduction tracking (paper S7's
  REPRODUCED state is representable but nothing in this module can *set* it
  automatically -- that requires a second investigator's own run, which this
  module has no way to observe).

Those are real, correctly-scoped future work, not silently claimed done.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Callable

__all__ = [
    "EvidenceState",
    "Falsifier",
    "FalsifierResult",
    "Receipt",
    "ExecutableResearchClaim",
    "run_falsifiers",
    "verify_claim",
    "run_shell_receipt",
    "git_commit_identity",
]


class EvidenceState(Enum):
    """Paper section 7's evidence-state vocabulary. States are NOT a single
    linear maturity ladder -- see the paper for the orthogonality notes
    (e.g. EXECUTABLE and OBSERVED do not imply VERIFIED; VERIFIED does not
    imply REPRODUCED)."""

    PROPOSED = "PROPOSED"
    IMPLEMENTED = "IMPLEMENTED"
    EXECUTABLE = "EXECUTABLE"
    OBSERVED = "OBSERVED"
    VERIFIED = "VERIFIED"
    REPRODUCIBLE = "REPRODUCIBLE"
    REPRODUCED = "REPRODUCED"
    FALSIFIED = "FALSIFIED"
    BLOCKED = "BLOCKED"
    UNSUPPORTED = "UNSUPPORTED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class Falsifier:
    """Paper section 9: "a system incapable of producing output
    contradicting its own thesis is not a strong scientific instrument."

    `check` is a REAL, callable predicate -- not a prose description of a
    condition. It returns True iff the claim SURVIVES this falsifier (the
    contradicting condition did NOT occur). A falsifier with no real check
    is a description, not an executable falsifier, and this type refuses to
    represent one (see `__post_init__`)."""

    description: str
    check: Callable[[], bool]

    def __post_init__(self) -> None:
        if not callable(self.check):
            raise TypeError(
                "Falsifier.check must be a real callable -- a prose "
                "description of a falsifier is not an executable falsifier "
                "(paper S9: 'NoExecutableFalsifier => LimitedExecutableStanding')."
            )


@dataclass(frozen=True, slots=True)
class FalsifierResult:
    """The outcome of actually running one `Falsifier`. `ran` distinguishes
    "this falsifier was executed and returned a real boolean" from "this
    falsifier could not be evaluated" (e.g. raised) -- the latter is UNKNOWN
    survival, never silently coerced to True (per this repo's own
    `absence-is-not-evidence.md`, which the EDS paper's section 4.1 restates
    as "absence of falsification != verification")."""

    falsifier: Falsifier
    ran: bool
    survived: bool | None
    error: str | None = None


def run_falsifiers(
    falsifiers: tuple[Falsifier, ...],
) -> tuple[FalsifierResult, ...]:
    """Actually execute every falsifier's real `check()`. Never assumes
    survival for a falsifier that raised -- that becomes `ran=False,
    survived=None`, distinct from a falsifier that ran and returned False
    (genuinely falsified)."""

    results: list[FalsifierResult] = []
    for f in falsifiers:
        try:
            survived = bool(f.check())
            results.append(FalsifierResult(falsifier=f, ran=True, survived=survived))
        except Exception as exc:  # noqa: BLE001 - captured as explicit UNKNOWN, not swallowed
            results.append(
                FalsifierResult(falsifier=f, ran=False, survived=None, error=repr(exc))
            )
    return tuple(results)


@dataclass(frozen=True, slots=True)
class Receipt:
    """Paper section 8. Binds a claim to the exact execution that allegedly
    supports it. Every field is a real, observed value -- never a
    caller-asserted claim about what happened. Construct via
    `run_shell_receipt` for a real subprocess-backed receipt, or directly
    when wrapping an already-executed real command's real output."""

    command: str
    exit_code: int
    stdout_tail: str
    stderr_tail: str
    source_commit: str
    executed_at_utc: str
    duration_s: float

    @property
    def succeeded(self) -> bool:
        return self.exit_code == 0


def git_commit_identity(repo_root: str | Path = ".") -> str:
    """The real exact-source identity for a receipt: `git rev-parse HEAD`
    against the real working tree, plus a `+dirty` suffix if the tree has
    real uncommitted changes -- so a receipt never silently claims a clean
    commit identity for a dirty tree (paper S4.3's "exact-subject standing").
    """

    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    dirty = (
        subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        != ""
    )
    return f"{sha}+dirty" if dirty else sha


def run_shell_receipt(
    command: list[str],
    *,
    repo_root: str | Path = ".",
    timeout_s: float = 600.0,
    tail_chars: int = 4000,
) -> Receipt:
    """Actually run `command` as a real subprocess and bind its real,
    observed exit code and output into a `Receipt`. This is the ONLY
    constructor this module provides for a receipt backed by a live
    execution -- there is no path here that lets a caller assert a receipt's
    contents without a real subprocess having produced them."""

    started = datetime.now(timezone.utc)
    proc = subprocess.run(
        command,
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=timeout_s,
    )
    finished = datetime.now(timezone.utc)
    return Receipt(
        command=" ".join(command),
        exit_code=proc.returncode,
        stdout_tail=proc.stdout[-tail_chars:],
        stderr_tail=proc.stderr[-tail_chars:],
        source_commit=git_commit_identity(repo_root),
        executed_at_utc=started.isoformat(),
        duration_s=(finished - started).total_seconds(),
    )


@dataclass(frozen=True, slots=True)
class ExecutableResearchClaim:
    """Paper section 6's `ERC+ = <H, A, F, P, I, E, V, R>`, adapted to what
    is directly representable in-repo:

    - `hypothesis` (H): the falsifiable proposition, in prose.
    - `artifact_ref` (A): a repo-relative path or module dotted-path naming
      the executable artifact operationalizing the hypothesis.
    - `falsifiers` (F): real, callable `Falsifier`s (see above).
    - `protocol` (P): optional prose description of the intended experiment
      protocol -- stored for human reference; NOT conformance-checked by
      this module (see module docstring's scope boundary).
    - `receipts`: zero or more `Receipt`s already produced by real
      execution. `verify_claim` reads only from this tuple -- it never
      executes anything itself, so a claim's evidence is exactly what was
      explicitly bound to it, matching this repo's own
      `no-dual-bookkeeping.md` law applied to research claims instead of
      software receipts.
    """

    hypothesis: str
    artifact_ref: str
    falsifiers: tuple[Falsifier, ...] = ()
    protocol: str | None = None
    receipts: tuple[Receipt, ...] = field(default_factory=tuple)

    def with_receipt(self, receipt: Receipt) -> "ExecutableResearchClaim":
        """Return a new claim with `receipt` appended. Frozen by design --
        a claim's receipt history is never mutated in place, only extended,
        so an earlier evidence state is never silently overwritten."""

        return ExecutableResearchClaim(
            hypothesis=self.hypothesis,
            artifact_ref=self.artifact_ref,
            falsifiers=self.falsifiers,
            protocol=self.protocol,
            receipts=self.receipts + (receipt,),
        )


def verify_claim(
    claim: ExecutableResearchClaim,
) -> tuple[EvidenceState, tuple[FalsifierResult, ...]]:
    """The single verification procedure enforcing the paper's central
    prohibition against state collapse. Returns both the resulting state
    AND the real falsifier results that justify it -- the state alone is
    never handed back without the evidence that produced it.

    Rules, applied in order (never inferred implicitly elsewhere):

    1. No artifact_ref and no receipts -> PROPOSED (a hypothesis with no
       executable artifact is legitimate research, but not yet an ERC).
    2. artifact_ref set, no receipts -> IMPLEMENTED (the artifact exists;
       nothing has been executed against it yet by this claim's own
       evidence -- code elsewhere existing is not evidence for THIS claim).
    3. Receipts exist but at least one has exit_code != 0 -> BLOCKED (a
       real execution was attempted and failed; never silently reported as
       IMPLEMENTED or VERIFIED).
    4. All receipts succeeded, but falsifiers cannot all be evaluated
       (any FalsifierResult.ran is False) -> UNKNOWN (never coerced to
       VERIFIED just because the receipts were clean).
    5. All receipts succeeded and every falsifier ran and survived ->
       VERIFIED.
    6. All receipts succeeded but at least one falsifier ran and did NOT
       survive -> FALSIFIED (this beats a clean receipt -- a green test
       suite does not overrule a real falsifier that fired).
    """

    falsifier_results = run_falsifiers(claim.falsifiers)

    if not claim.receipts:
        if not claim.artifact_ref:
            return EvidenceState.PROPOSED, falsifier_results
        return EvidenceState.IMPLEMENTED, falsifier_results

    if any(not r.succeeded for r in claim.receipts):
        return EvidenceState.BLOCKED, falsifier_results

    if claim.falsifiers:
        if any(r.ran and r.survived is False for r in falsifier_results):
            return EvidenceState.FALSIFIED, falsifier_results
        if any(not r.ran for r in falsifier_results):
            return EvidenceState.UNKNOWN, falsifier_results

    return EvidenceState.VERIFIED, falsifier_results
