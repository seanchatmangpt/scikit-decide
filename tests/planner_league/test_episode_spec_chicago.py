"""Chicago-style tests for `EpisodeSpec` (capability 4: information partitions
+ authority-model join).

Real collaborators throughout: a real `LeagueMatch`/`PolicySpec` pair built on
real catalog entries, and the real `AuthorityModel` parsed from the real fixture
`tests/ecosystem/fixtures/fde/customer-authority.ttl` via `load_authority`. No
mocking of any kind.
"""

from __future__ import annotations

import os

import pytest

from autofde_lab.fabric.fde import load_authority, validate_authority
from autofde_lab.planner_league.core import LeagueMatch, PolicySpec
from autofde_lab.planner_league.episode import (
    AuthorityStanding,
    EpisodeSpec,
    validate_information_partition,
)

FIXTURE = os.path.join(
    os.path.dirname(__file__),
    "..",
    "ecosystem",
    "fixtures",
    "fde",
    "customer-authority.ttl",
)

REAL_GRANT_REF = "urn:skdecide:fde:grant/AG-0001"


def _real_match(**overrides) -> LeagueMatch:
    kwargs = {
        "world_id": "identity_degradation",
        "left_role_id": "blue_defender",
        "left_policy": PolicySpec.for_role("Astar", "blue_defender"),
        "right_role_id": "red_disturbance",
        "right_policy": PolicySpec.for_role("MCTS", "red_disturbance"),
    }
    kwargs.update(overrides)
    return LeagueMatch(**kwargs)


@pytest.fixture(scope="module")
def real_authority_model():
    model = load_authority(FIXTURE)
    return validate_authority(model)


def test_real_grant_ref_binds_with_bound_standing(real_authority_model):
    assert (
        REAL_GRANT_REF in real_authority_model.grants
    )  # confirm real fixture grant id
    match = _real_match(authority_context_ref=REAL_GRANT_REF)
    spec = EpisodeSpec(match=match, authority=real_authority_model)
    assert spec.authority_standing is AuthorityStanding.BOUND
    candidate = spec.as_gymact_candidate()
    assert candidate["authority"] == {"grant_id": REAL_GRANT_REF, "standing": "BOUND"}


def test_nonexistent_ref_is_refused(real_authority_model):
    match = _real_match(authority_context_ref="urn:skdecide:fde:grant/NOPE")
    with pytest.raises(ValueError, match="REFUSED:AUTHORITY_REF_NOT_IN_MODEL"):
        EpisodeSpec(match=match, authority=real_authority_model)


def test_ref_set_but_no_model_supplied_is_refused():
    match = _real_match(authority_context_ref=REAL_GRANT_REF)
    with pytest.raises(ValueError, match="REFUSED:AUTHORITY_REF_NOT_IN_MODEL"):
        EpisodeSpec(match=match, authority=None)


def test_unknown_information_partition_is_refused():
    match = _real_match(information_partition_id="telepathic")
    with pytest.raises(
        ValueError, match="REFUSED:UNKNOWN_INFORMATION_PARTITION:telepathic"
    ):
        EpisodeSpec(match=match, authority=None)


def test_validate_information_partition_function_directly():
    assert validate_information_partition("shared") == "shared"
    with pytest.raises(ValueError, match="REFUSED:UNKNOWN_INFORMATION_PARTITION"):
        validate_information_partition("nope")


def test_unset_ref_yields_unknown_standing_never_bound(real_authority_model):
    match = _real_match()  # authority_context_ref defaults to None
    spec = EpisodeSpec(match=match, authority=real_authority_model)
    assert spec.authority_standing is AuthorityStanding.UNKNOWN
    assert spec.authority_standing is not AuthorityStanding.BOUND
    candidate = spec.as_gymact_candidate()
    assert candidate["authority"] == {"grant_id": None, "standing": "UNKNOWN"}


def test_identity_sha256_differs_by_information_partition():
    """core.py's `_canonical_json` includes `information_partition_id`
    (core.py:128) in the hashed payload, so two otherwise-identical matches
    that differ only in partition must have different `identity_sha256`.
    Verified empirically here rather than assumed.
    """
    shared = _real_match(information_partition_id="shared")
    private = _real_match(information_partition_id="left_private")
    assert shared.identity_sha256 != private.identity_sha256
