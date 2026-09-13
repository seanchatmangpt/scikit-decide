from autofde_lab.fabric.handoff import (
    AuthorityScope,
    HandoffEnvelope,
    HandoffStanding,
    admit_handoff,
)


def scope(caps=("read", "write"), resources=("a", "b")):
    return AuthorityScope(frozenset(caps), frozenset(resources))


def envelope(**overrides):
    values = dict(
        handoff_id="h1",
        input_schema_id="schema:v1",
        payload_schema_id="schema:v1",
        parent_authority=scope(),
        delegated_authority=scope(("read",), ("a",)),
        evidence_lineage=("receipt:1",),
    )
    values.update(overrides)
    return HandoffEnvelope(**values)


def test_narrow_typed_handoff_is_admitted():
    assert admit_handoff(envelope()).standing is HandoffStanding.ADMITTED


def test_capability_broadening_is_refused():
    decision = admit_handoff(
        envelope(delegated_authority=scope(("read", "admin"), ("a",)))
    )
    assert decision.standing is HandoffStanding.REFUSED_AUTHORITY_BROADENING


def test_resource_broadening_is_refused():
    decision = admit_handoff(envelope(delegated_authority=scope(("read",), ("a", "c"))))
    assert decision.standing is HandoffStanding.REFUSED_AUTHORITY_BROADENING


def test_missing_lineage_is_refused_before_handoff():
    assert (
        admit_handoff(envelope(evidence_lineage=())).standing
        is HandoffStanding.REFUSED_MISSING_LINEAGE
    )


def test_schema_mismatch_is_refused():
    assert (
        admit_handoff(envelope(payload_schema_id="schema:v2")).standing
        is HandoffStanding.REFUSED_SCHEMA_MISMATCH
    )
