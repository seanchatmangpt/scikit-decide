"""Generated projection of the Fortune-5 reference ontology; do not hand-edit."""

from __future__ import annotations

from .space import Axis, Option

ONTOLOGY_IRI = "urn:autofde-lab:fortune5:ontology"
MANUFACTURE = "ggen"
PUBLIC_ONTOLOGY_FOUNDATIONS = (
    "http://purl.org/dc/terms/",
    "http://www.w3.org/2004/02/skos/core#",
    "http://www.w3.org/ns/prov#",
)

CATALOG_ROWS: tuple[tuple[str, str], ...] = (
    ("enterprise", "enterprise-01"),
    ("enterprise", "enterprise-02"),
    ("enterprise", "enterprise-03"),
    ("enterprise", "enterprise-04"),
    ("enterprise", "enterprise-05"),
    ("cloud", "aws"),
    ("cloud", "azure"),
    ("cloud", "gcp"),
    ("geography", "americas"),
    ("geography", "emea"),
    ("geography", "apac"),
    ("geography", "regulated"),
    ("environment", "dev"),
    ("environment", "test"),
    ("environment", "stage"),
    ("environment", "prod"),
    ("environment", "dr"),
    ("cluster_profile", "shared"),
    ("cluster_profile", "dedicated"),
    ("cluster_profile", "regulated"),
    ("cluster_profile", "edge"),
    ("workload", "web"),
    ("workload", "api"),
    ("workload", "worker"),
    ("workload", "batch"),
    ("workload", "stream"),
    ("workload", "data"),
    ("workload", "ml"),
    ("workload", "agent"),
    ("traffic", "internal"),
    ("traffic", "internet"),
    ("traffic", "partner"),
    ("traffic", "event-driven"),
    ("data_class", "public"),
    ("data_class", "internal"),
    ("data_class", "confidential"),
    ("data_class", "restricted"),
    ("availability", "standard"),
    ("availability", "ha"),
    ("availability", "mission-critical"),
    ("release", "rolling"),
    ("release", "canary"),
    ("release", "blue-green"),
    ("release", "immutable"),
    ("identity", "workload-identity"),
    ("identity", "oidc"),
    ("identity", "service-account"),
    ("policy", "baseline"),
    ("policy", "restricted"),
    ("policy", "zero-trust"),
    ("runtime_ai", "none"),
    ("runtime_ai", "rag"),
    ("runtime_ai", "agentic"),
    ("runtime_ai", "inference"),
    ("fault", "healthy"),
    ("fault", "config-drift"),
    ("fault", "target-port"),
    ("fault", "dns"),
    ("fault", "rbac"),
    ("fault", "secret"),
    ("fault", "network-policy"),
    ("fault", "quota"),
    ("fault", "oom"),
    ("fault", "cpu-throttle"),
    ("fault", "pvc"),
    ("fault", "image-pull"),
    ("fault", "crash-loop"),
    ("fault", "cert"),
    ("fault", "ingress"),
    ("fault", "dependency"),
    ("fault", "schema"),
    ("fault", "backpressure"),
    ("fault", "node-pressure"),
    ("fault", "zone-loss"),
)


def _build_axes() -> tuple[Axis, ...]:
    grouped: dict[str, list[Option]] = {}
    for axis_name, option_name in CATALOG_ROWS:
        grouped.setdefault(axis_name, []).append(Option(option_name))
    return tuple(Axis(name, tuple(options)) for name, options in grouped.items())


AXES = _build_axes()
