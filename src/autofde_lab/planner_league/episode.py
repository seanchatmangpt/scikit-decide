"""Episode-level identity binding: partition catalog + authority-grant join.

Capability 4 (V2030.1.1 PRD) requires the episode representation to carry
"world + roles + policies + information partitions + authority model". Prior
to this module, `LeagueMatch.information_partition_id` (core.py) was an
unvalidated free string and `LeagueMatch.authority_context_ref` was never
joined to a real `AuthorityModel` (fabric/fde.py) -- co-reference without an
explicit typed join, the exact defect
`.claude/rules/no-dual-bookkeeping.md` names.

This module adds that validation and that join. It does not admit, broker, or
actuate anything (see `CLAUDE.md`'s actuation law): `EpisodeSpec` only
answers "does this reference resolve against this real model", never "is this
authorized to run".
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from autofde_lab.fabric.fde import AuthorityModel

from .core import LeagueMatch

INFORMATION_PARTITIONS: tuple[str, ...] = (
    "shared",
    "left_private",
    "right_private",
    "mutual_private",
)


def validate_information_partition(information_partition_id: str) -> str:
    """Return the id unchanged if it is in the validated vocabulary.

    Raises ``ValueError`` with a typed refusal reason otherwise -- an unknown
    partition is refused, never silently accepted as free text.
    """
    if information_partition_id not in INFORMATION_PARTITIONS:
        raise ValueError(
            f"REFUSED:UNKNOWN_INFORMATION_PARTITION:{information_partition_id}"
        )
    return information_partition_id


class AuthorityStanding(str, Enum):
    """Standing of `LeagueMatch.authority_context_ref` against a real model.

    Never coerced from absence: `UNKNOWN` is the honest value when no ref was
    set, per `.claude/rules/absence-is-not-evidence.md` -- an unset reference
    is not evidence the match is authorized, nor evidence it is not.
    """

    BOUND = "BOUND"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class EpisodeSpec:
    """Binds a real `LeagueMatch` to a real, optionally-absent `AuthorityModel`.

    `authority` is the parsed model an `authority_context_ref` (if set) must
    resolve against. Resolution is by real dict key membership in
    `AuthorityModel.grants` -- no string-similarity or co-reference guessing,
    per the no-dual-bookkeeping identity rule.
    """

    match: LeagueMatch
    authority: AuthorityModel | None = None

    def __post_init__(self) -> None:
        validate_information_partition(self.match.information_partition_id)
        ref = self.match.authority_context_ref
        if ref is not None:
            model = self.authority
            if model is None or ref not in model.grants:
                raise ValueError(f"REFUSED:AUTHORITY_REF_NOT_IN_MODEL:{ref}")

    @property
    def authority_standing(self) -> AuthorityStanding:
        if self.match.authority_context_ref is None:
            return AuthorityStanding.UNKNOWN
        return AuthorityStanding.BOUND

    def as_gymact_candidate(self) -> dict[str, Any]:
        """Extend `LeagueMatch.as_gymact_candidate()` with validated identity.

        Still a transport-neutral candidate description, not an actuation
        request -- see module docstring.
        """
        candidate = self.match.as_gymact_candidate()
        candidate["information_partition_id"] = validate_information_partition(
            self.match.information_partition_id
        )
        candidate["authority"] = {
            "grant_id": self.match.authority_context_ref,
            "standing": self.authority_standing.value,
        }
        return candidate
