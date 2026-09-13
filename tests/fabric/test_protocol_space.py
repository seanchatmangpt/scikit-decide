from autofde_lab.fabric.protocol_space import (
    ProtocolCandidate,
    ProtocolConstraints,
    admit,
    maximal_admissible_space,
)


def constraints():
    return ProtocolConstraints(
        allowed_languages=("rust", "python"),
        allowed_transports=("stdio", "http"),
        allowed_digests=("sha-256", "blake3-256"),
        allowed_persistence=("sqlite", "append-log"),
        authority_providers=("external-a", "external-b"),
    )


def test_preserves_full_bounded_cartesian_space():
    space = maximal_admissible_space(constraints())
    assert len(space) == 32
    assert len({c.identity for c in space}) == len(space)


def test_planner_annotations_cannot_create_authority():
    bad = ProtocolCandidate(
        "rust", "stdio", "sha-256", "sqlite", "planner", True, ambient_authority=True
    )
    assert admit(bad, constraints()) == (False, "REFUSED:AMBIENT_AUTHORITY")


def test_unreceiptable_candidate_is_pruned_not_global_failure():
    bad = ProtocolCandidate("rust", "stdio", "sha-256", "sqlite", "external-a", False)
    space = maximal_admissible_space(constraints(), [bad])
    assert len(space) == 32
    assert bad not in space
