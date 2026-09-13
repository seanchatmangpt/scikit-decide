# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Frozen-crown execution harness.

Denominator-freezing discipline, enforced mechanically rather than by
convention:

* Seeds are drawn from an OS-entropy source **after** this process starts
  (`secrets.randbits`), so no concrete trial instance can have existed in
  any prior run, transcript, fixture, or training corpus.
* The frozen set is written to `crown_manifest.json` **before the first
  trial executes**, with a digest over the seed list. `verify_manifest`
  re-derives that digest afterwards -- a changed denominator, a dropped
  failing seed, or a swapped-in easier seed all fail the check.
* Every attempt is retained. `CrownRun.attempts` accumulates across
  repair-and-rerun cycles; nothing is overwritten, so an 8/10 followed by
  a 10/10 reports both, in order.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from autofde_lab.hub.domain.gym_procedure.crown_factor import (
    FactorConjunction,
    conjunction_from_row,
)


@dataclass(frozen=True)
class FrozenCrown:
    """An immutable, digest-bound trial set. Frozen before execution."""

    seeds: tuple[int, ...]
    provider_assignments: tuple[str, ...]  # provider key per seed, same order
    configs: tuple[dict, ...]
    manifest_digest: str
    frozen_at_step: str = "BEFORE_FIRST_TRIAL"

    def size(self) -> int:
        return len(self.seeds)


def _digest_manifest(
    seeds: tuple[int, ...], providers: tuple[str, ...], configs: tuple[dict, ...]
) -> str:
    payload = json.dumps(
        {"seeds": list(seeds), "providers": list(providers), "configs": list(configs)},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def freeze_crown(
    n_trials: int,
    provider_pool: list[str],
    config_for: Callable[[int, str], dict],
    manifest_path: Path,
) -> FrozenCrown:
    """Draw fresh seeds from OS entropy NOW (after process start), assign
    providers round-robin across the pool, write the manifest, return the
    frozen set. Refuses to overwrite an existing manifest -- re-freezing
    over a prior run is exactly the denominator-change this guards."""
    if manifest_path.exists():
        raise FileExistsError(
            f"CROWN_MANIFEST_EXISTS: {manifest_path} already holds a frozen denominator; "
            f"refusing to re-freeze (that would change the denominator after observing results)"
        )
    if n_trials < 10:
        raise ValueError(f"CROWN_DENOMINATOR_TOO_SMALL: {n_trials} < 10")
    if not provider_pool:
        raise ValueError("CROWN_PROVIDER_POOL_EMPTY")

    seeds = tuple(secrets.randbits(32) for _ in range(n_trials))
    providers = tuple(provider_pool[i % len(provider_pool)] for i in range(n_trials))
    configs = tuple(config_for(seed, prov) for seed, prov in zip(seeds, providers))
    digest = _digest_manifest(seeds, providers, configs)

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "seeds": list(seeds),
                "providers": list(providers),
                "configs": list(configs),
                "manifest_digest": digest,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return FrozenCrown(
        seeds=seeds,
        provider_assignments=providers,
        configs=configs,
        manifest_digest=digest,
    )


def load_crown(manifest_path: Path) -> FrozenCrown:
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    seeds = tuple(data["seeds"])
    providers = tuple(data["providers"])
    configs = tuple(data["configs"])
    recomputed = _digest_manifest(seeds, providers, configs)
    if recomputed != data["manifest_digest"]:
        raise ValueError(
            f"CROWN_MANIFEST_TAMPERED: recomputed digest {recomputed} != recorded {data['manifest_digest']}"
        )
    return FrozenCrown(
        seeds=seeds,
        provider_assignments=providers,
        configs=configs,
        manifest_digest=recomputed,
    )


def verify_manifest(crown: FrozenCrown, executed_seeds: list[int]) -> list[str]:
    """Return violations if what actually ran differs from what was frozen."""
    violations: list[str] = []
    frozen = list(crown.seeds)
    if sorted(executed_seeds) != sorted(frozen):
        missing = sorted(set(frozen) - set(executed_seeds))
        extra = sorted(set(executed_seeds) - set(frozen))
        if missing:
            violations.append(f"SUPPRESSED_TRIAL:seeds_not_executed={missing}")
        if extra:
            violations.append(f"POST_HOC_TRIAL_ADDED:seeds_not_in_manifest={extra}")
    if len(executed_seeds) != len(frozen):
        violations.append(
            f"DENOMINATOR_CHANGED:frozen={len(frozen)},executed={len(executed_seeds)}"
        )
    return violations


def _row_is_alive(row: dict) -> bool:
    """The scoreboard verdict, computed by the SAME typed conjunction
    `TrialReport.is_alive` uses, so the report and the scoreboard cannot
    drift apart.

    Previously this was a hand-maintained chain of `row.get(...)` tests that
    duplicated `TrialReport.is_alive` by convention -- and had already fallen
    out of step with it once (`real_goal_attained` was missing here while
    present there). It now delegates to `conjunction_from_row`, which
    reconstructs the seven `CrownFactor`s from the row: rows written before
    the typed equation existed reconstruct to `UNKNOWN` for every factor they
    never recorded, and `UNKNOWN` is not ALIVE.
    """
    return conjunction_from_row(row).is_alive()


def _row_verdict(row: dict) -> str:
    """`ALIVE` / `UNKNOWN` / `NOT_ALIVE` for one row.

    `UNKNOWN` is the honest verdict for the three pre-repair crown attempts:
    their rows carry no replay evidence at all, so they were never checked
    rather than checked and failed."""
    return conjunction_from_row(row).verdict()


class SetStanding(str, Enum):
    """Standing of a *collection* of trials. Three states, not a number.

    A count cannot express the distinction that sank crown attempts 1-3: a
    collection whose members were never checked and a collection whose members
    were checked and failed both produce a number below the denominator. Only
    ``UNKNOWN_SET`` vs ``NOT_ALIVE_SET`` says which happened.
    """

    ALIVE_SET = "ALIVE_SET"
    UNKNOWN_SET = "UNKNOWN_SET"
    NOT_ALIVE_SET = "NOT_ALIVE_SET"


@dataclass(frozen=True)
class StandingMember:
    """One frozen trial identity paired with the conjunction observed for it.

    Identity, not adjacency: a member is bound to the *seed* that was frozen,
    never to its position in a results list. A row landing under the wrong
    identity is a different member, not a reordering.
    """

    identity: int
    conjunction: FactorConjunction

    def __post_init__(self) -> None:
        if not self.conjunction.required:
            # A conjunction over zero required factors is vacuously alive --
            # a factor that cannot fail is a factor that is not being checked.
            raise ValueError(
                f"CROWN_STANDING_VACUOUS_CONJUNCTION: member {self.identity} carries a "
                f"conjunction with no required factors, which cannot fail"
            )

    def verdict(self) -> str:
        return self.conjunction.verdict()


@dataclass(frozen=True)
class CrownStanding:
    """The crown verdict as a typed collection standing, not an arithmetic one.

    Constructible only through :meth:`over`, which pairs each frozen identity
    with a conforming :class:`FactorConjunction`. There is no path from a count
    to this type: ``ALIVE_SET`` requires the *set* of alive identities to equal
    the *set* of frozen identities, so a run that scored ten alive trials none
    of which are the frozen ones is not alive, and neither is one that scored
    ten alive rows under nine distinct seeds.

    Deliberately no ``__bool__`` and no length: ``if standing:`` and
    ``len(standing) == 10`` must not compile to a verdict.
    """

    expected_identities: frozenset[int]
    members: tuple[StandingMember, ...]

    @classmethod
    def over(
        cls, expected_identities: Iterable[int], rows: Iterable[dict]
    ) -> "CrownStanding":
        """Build standing from the frozen identities and the recorded rows.

        Each row must name its own identity (``seed``); a row that does not is
        unattributable and is refused rather than being matched positionally.
        Two rows for one identity are refused as well -- a collection holding
        two records for one frozen trial is corrupt, not scoreable, and picking
        either one would be dual bookkeeping.
        """
        members: dict[int, StandingMember] = {}
        for row in rows:
            if "seed" not in row:
                raise ValueError(
                    "CROWN_STANDING_UNATTRIBUTED_ROW: a result row carries no seed; "
                    "membership is by identity, never by position"
                )
            identity = row["seed"]
            if identity in members:
                raise ValueError(
                    f"CROWN_STANDING_DUPLICATE_IDENTITY: two result rows claim seed "
                    f"{identity}; the collection is corrupt, not scoreable"
                )
            members[identity] = StandingMember(identity, conjunction_from_row(row))
        return cls(
            expected_identities=frozenset(expected_identities),
            members=tuple(members[k] for k in members),
        )

    # -- set queries; every one returns identities, never a count -----------

    def witnessed_identities(self) -> frozenset[int]:
        return frozenset(m.identity for m in self.members)

    def unwitnessed_identities(self) -> frozenset[int]:
        """Frozen identities with no record at all. UNKNOWN, never failed."""
        return self.expected_identities - self.witnessed_identities()

    def foreign_identities(self) -> frozenset[int]:
        """Recorded identities that were never frozen -- a post-hoc trial."""
        return self.witnessed_identities() - self.expected_identities

    def _by_verdict(self, verdict: str) -> frozenset[int]:
        return frozenset(
            m.identity
            for m in self.members
            if m.identity in self.expected_identities and m.verdict() == verdict
        )

    def alive_set(self) -> frozenset[int]:
        return self._by_verdict("ALIVE")

    def not_alive_set(self) -> frozenset[int]:
        return self._by_verdict("NOT_ALIVE")

    def unknown_set(self) -> frozenset[int]:
        """Members whose conjunction was never established, plus every frozen
        identity that produced no record at all."""
        return self._by_verdict("UNKNOWN") | self.unwitnessed_identities()

    def standing(self) -> SetStanding:
        """Set equality, not cardinality.

        Precedence mirrors :meth:`FactorConjunction.verdict` one level up: a
        positively observed integrity violation (a post-hoc identity) is
        evidence and reads ``NOT_ALIVE_SET``; otherwise anything unestablished
        keeps the whole collection ``UNKNOWN_SET``, because UNKNOWN survives
        projection and must not be summed away by the members around it.
        """
        if self.foreign_identities():
            return SetStanding.NOT_ALIVE_SET
        if not self.expected_identities:
            # Nothing was ever frozen, so nothing was ever checked. A vacuous
            # collection is UNKNOWN, and can never be the green one.
            return SetStanding.UNKNOWN_SET
        if self.alive_set() == self.expected_identities:
            return SetStanding.ALIVE_SET
        if self.unknown_set():
            return SetStanding.UNKNOWN_SET
        return SetStanding.NOT_ALIVE_SET

    def is_alive_set(self) -> bool:
        return self.standing() is SetStanding.ALIVE_SET

    def __bool__(self) -> bool:
        # No truthy shortcut, mirroring `CrownFactor`: `if standing:` must not
        # compile to a verdict on a non-empty collection of failures.
        raise TypeError(
            "CROWN_STANDING_HAS_NO_TRUTH_VALUE: call .standing() or .is_alive_set()"
        )

    def describe(self) -> str:
        return (
            f"{self.standing().value} "
            f"(ALIVE={sorted(self.alive_set())} "
            f"UNKNOWN={sorted(self.unknown_set())} "
            f"NOT_ALIVE={sorted(self.not_alive_set())}"
            + (f" FOREIGN={sorted(self.foreign_identities())}" if self.foreign_identities() else "")
            + ")"
        )

    def to_dict(self) -> dict:
        return {
            "standing": self.standing().value,
            "alive": sorted(self.alive_set()),
            "unknown": sorted(self.unknown_set()),
            "not_alive": sorted(self.not_alive_set()),
            "unwitnessed": sorted(self.unwitnessed_identities()),
            "foreign": sorted(self.foreign_identities()),
        }


@dataclass
class CrownAttempt:
    """One full pass over the frozen set. All attempts are retained."""

    attempt_index: int
    results: list[dict] = field(default_factory=list)
    repair_note: str = ""

    def standing(self, crown: "FrozenCrown") -> CrownStanding:
        """The attempt's verdict: a typed collection standing over the frozen
        identities. This is the only thing that ESTABLISHES anything here."""
        return CrownStanding.over(crown.seeds, self.results)

    def alive_count(self) -> int:
        """DESCRIPTIVE ONLY -- how many rows read alive, for reporting.

        Establishes nothing. The verdict is :meth:`standing`, which compares
        identity sets; this number cannot distinguish ten alive rows under the
        frozen seeds from ten alive rows under seeds nobody froze.
        """
        return sum(1 for r in self.results if _row_is_alive(r))

    def verdict_distribution(self) -> dict[str, int]:
        """How many rows are ALIVE / UNKNOWN / NOT_ALIVE. Reported alongside
        the score because `n/10 ALIVE` alone cannot distinguish a trial that
        failed a check from one whose check never ran."""
        dist = {"ALIVE": 0, "UNKNOWN": 0, "NOT_ALIVE": 0}
        for r in self.results:
            dist[_row_verdict(r)] += 1
        return dist

    def summary(self) -> str:
        dist = self.verdict_distribution()
        return (
            f"attempt {self.attempt_index}: {self.alive_count()}/{len(self.results)} ALIVE "
            f"(ALIVE={dist['ALIVE']} UNKNOWN={dist['UNKNOWN']} NOT_ALIVE={dist['NOT_ALIVE']})"
        )


@dataclass
class CrownRun:
    crown: FrozenCrown
    attempts: list[CrownAttempt] = field(default_factory=list)

    def record(self, attempt: CrownAttempt) -> None:
        self.attempts.append(attempt)

    def standing(self) -> CrownStanding:
        """Standing of the most recent full pass. With no attempts recorded,
        every frozen identity is unwitnessed -- UNKNOWN_SET, not a zero."""
        rows = self.attempts[-1].results if self.attempts else []
        return CrownStanding.over(self.crown.seeds, rows)

    def is_complete(self) -> bool:
        """`ALIVE_SET` on the most recent pass.

        Not an integer comparison. Formerly this was
        ``len(results) == size and alive_count() == size``; two counts agreeing
        with a denominator is not the same claim as *the alive identities being
        the frozen identities*, and the two diverge under exactly the
        substitutions the manifest freeze exists to catch.
        """
        return self.standing().is_alive_set()

    def failed_seeds(self) -> list[int]:
        """Frozen identities not established ALIVE -- in frozen order, and by
        set difference rather than by counting."""
        alive = self.standing().alive_set()
        return [s for s in self.crown.seeds if s not in alive]

    def full_history(self) -> list[str]:
        """Every attempt, in order -- an 8/10 then 10/10 reports BOTH."""
        return [
            a.summary() + (f" [{a.repair_note}]" if a.repair_note else "")
            for a in self.attempts
        ]

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "manifest_digest": self.crown.manifest_digest,
                    "denominator": self.crown.size(),
                    "attempts": [
                        {
                            "attempt_index": a.attempt_index,
                            "repair_note": a.repair_note,
                            # descriptive; the verdict is `standing` below
                            "alive": a.alive_count(),
                            "standing": a.standing(self.crown).to_dict(),
                            "results": a.results,
                        }
                        for a in self.attempts
                    ],
                    "history": self.full_history(),
                    "standing": self.standing().to_dict(),
                    "complete": self.is_complete(),
                },
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )
