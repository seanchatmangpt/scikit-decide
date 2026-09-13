from __future__ import annotations

from dataclasses import replace

import pytest

from autofde_lab.autofde.domain_pack import (
    DomainPack,
    ProjectionContract,
    SourceProvenance,
)


def projection(role: str) -> ProjectionContract:
    return ProjectionContract(
        projection_id=f"projection:{role}",
        role=role,
        schema_ref=f"schema:{role}",
        generator_ref=f"ggen:{role}",
    )


def pack(*, projections: tuple[ProjectionContract, ...] | None = None) -> DomainPack:
    return DomainPack(
        pack_id="domain:cloud-network",
        version="1.0.0",
        provenance=SourceProvenance(
            "https://example.invalid/spec",
            "rev:1",
            "Apache-2.0",
            "sha256:source",
        ),
        ontology_ref="ontology:cloud-network",
        ontology_digest="sha256:ontology",
        taxonomy_axes=("provider", "resource-kind"),
        state_model_ref="state:cloud-network",
        desired_state_laws=("reachable",),
        violation_modes=("route-blackhole",),
        observation_contracts=("observe:routes",),
        authority_contracts=("network.write",),
        planner_compatibility=("classical", "stochastic"),
        remediation_morphologies=("route-repair",),
        verification_rules=("verify:reachability",),
        projections=projections
        or tuple(
            projection(role)
            for role in ("world", "reasoning", "manufacture", "runtime")
        ),
    )


def test_domain_pack_requires_all_four_projection_roles_and_digest_binds_content() -> (
    None
):
    subject = pack()
    same_subject = pack()
    changed_subject = replace(subject, ontology_digest="sha256:different-ontology")

    assert subject.projection("world").generator_ref == "ggen:world"
    assert subject.projection("runtime").schema_ref == "schema:runtime"
    assert subject.digest == same_subject.digest
    assert subject.digest != changed_subject.digest


def test_missing_projection_role_is_refused() -> None:
    with pytest.raises(ValueError, match="DOMAIN_PACK_PROJECTION_CLOSURE_REFUSED"):
        pack(
            projections=(
                projection("world"),
                projection("reasoning"),
                projection("manufacture"),
            )
        )


def test_duplicate_projection_role_is_refused() -> None:
    with pytest.raises(ValueError, match="DOMAIN_PACK_PROJECTION_CLOSURE_REFUSED"):
        pack(
            projections=(
                projection("world"),
                projection("reasoning"),
                projection("manufacture"),
                projection("runtime"),
                ProjectionContract(
                    "projection:runtime:2", "runtime", "schema:r2", "ggen:r2"
                ),
            )
        )


def test_empty_semantic_dimension_is_refused() -> None:
    original = pack()
    with pytest.raises(ValueError, match="DOMAIN_PACK_SEMANTIC_CLOSURE_REFUSED"):
        DomainPack(
            pack_id=original.pack_id,
            version=original.version,
            provenance=original.provenance,
            ontology_ref=original.ontology_ref,
            ontology_digest=original.ontology_digest,
            taxonomy_axes=(),
            state_model_ref=original.state_model_ref,
            desired_state_laws=original.desired_state_laws,
            violation_modes=original.violation_modes,
            observation_contracts=original.observation_contracts,
            authority_contracts=original.authority_contracts,
            planner_compatibility=original.planner_compatibility,
            remediation_morphologies=original.remediation_morphologies,
            verification_rules=original.verification_rules,
            projections=original.projections,
        )
