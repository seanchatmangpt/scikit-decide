"""Deterministic baseline manifest definitions and synthesizers for Kubernetes resources."""

from __future__ import annotations

import json
from typing import Any

# Standard feature flag baseline for flagd in AstronomyShop
DEFAULT_FLAGD_CONFIG_JSON = json.dumps(
    {
        "flags": {
            "adFailure": {"state": "ENABLED", "defaultVariant": "off"},
            "adHighCpu": {"state": "ENABLED", "defaultVariant": "off"},
            "adManualGc": {"state": "ENABLED", "defaultVariant": "off"},
            "cartFailure": {"state": "ENABLED", "defaultVariant": "off"},
            "paymentFailure": {"state": "ENABLED", "defaultVariant": "off"},
            "paymentUnreachable": {"state": "ENABLED", "defaultVariant": "off"},
            "productCatalogFailure": {"state": "ENABLED", "defaultVariant": "off"},
            "kafkaQueueProblems": {"state": "ENABLED", "defaultVariant": "off"},
            "imageSlowLoad": {"state": "ENABLED", "defaultVariant": "off"},
            "loadGeneratorFloodHomepage": {"state": "ENABLED", "defaultVariant": "off"},
            "failedReadinessProbe": {"state": "ENABLED", "defaultVariant": "off"},
            "recommendationCacheFailure": {"state": "ENABLED", "defaultVariant": "off"},
            "emailMemoryLeak": {"state": "ENABLED", "defaultVariant": "off"},
            "llmInaccurateResponse": {"state": "ENABLED", "defaultVariant": "off"},
            "llmRateLimitError": {"state": "ENABLED", "defaultVariant": "off"},
        }
    },
    indent=2,
)

# Known baseline ConfigMap contents across SREGym benchmarks
KNOWN_CONFIGMAP_BASELINES: dict[str, dict[str, str]] = {
    "flagd-config": {"demo.flagd.json": DEFAULT_FLAGD_CONFIG_JSON},
    "geo-config": {
        "GeoMongoAddress": "mongodb-geo:27017",
        "GeoPort": "8083",
        "config.json": json.dumps(
            {
                "consulAddress": "consul:8500",
                "jaegerAddress": "jaeger:6831",
                "FrontendPort": "8080",
                "GeoPort": "8083",
                "GeoMongoAddress": "mongodb-geo:27017",
                "ProfilePort": "8081",
                "ProfileMongoAddress": "mongodb-profile:27017",
                "RatePort": "8084",
                "RateMongoAddress": "mongodb-rate:27017",
                "TraceAddr": "jaeger:6831",
            },
            indent=2,
        ),
    },
    "rate-config": {
        "RateMongoAddress": "mongodb-rate:27017",
        "RatePort": "8084",
        "config.json": json.dumps(
            {
                "RateMongoAddress": "mongodb-rate:27017",
                "RatePort": "8084",
            },
            indent=2,
        ),
    },
    "profile-config": {
        "ProfileMongoAddress": "mongodb-profile:27017",
        "ProfilePort": "8081",
        "config.json": json.dumps(
            {
                "ProfileMongoAddress": "mongodb-profile:27017",
                "ProfilePort": "8081",
            },
            indent=2,
        ),
    },
}

KNOWN_SECRET_BASELINES: dict[str, dict[str, str]] = {
    "jwt-secret": {"secret": "c2VjcmV0"},  # base64 encoded 'secret'
    "db-secret": {"password": "cGFzc3dvcmQ="},
}



def synthesize_service_manifest(service_name: str, namespace: str, target_port: int = 8080) -> dict[str, Any]:
    """Synthesizes a valid Kubernetes Service manifest for missing microservice endpoints."""
    return {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {
            "name": service_name,
            "namespace": namespace,
            "labels": {"app": service_name},
        },
        "spec": {
            "selector": {"app": service_name},
            "ports": [
                {
                    "name": "http",
                    "port": target_port,
                    "targetPort": target_port,
                    "protocol": "TCP",
                }
            ],
            "type": "ClusterIP",
        },
    }


def synthesize_configmap_manifest(
    configmap_name: str, namespace: str, data: dict[str, str] | None = None
) -> dict[str, Any]:
    """Synthesizes a valid Kubernetes ConfigMap manifest."""
    final_data = data or KNOWN_CONFIGMAP_BASELINES.get(configmap_name, {"default.key": "default.value"})
    return {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {
            "name": configmap_name,
            "namespace": namespace,
        },
        "data": final_data,
    }


def synthesize_secret_manifest(
    secret_name: str, namespace: str, data: dict[str, str] | None = None
) -> dict[str, Any]:
    """Synthesizes a valid Kubernetes Secret manifest."""
    final_data = data or KNOWN_SECRET_BASELINES.get(secret_name, {"password": "cGFzc3dvcmQ="})
    return {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {
            "name": secret_name,
            "namespace": namespace,
        },
        "type": "Opaque",
        "data": final_data,
    }


def get_baseline_manifest(kind: str, object_name: str, namespace: str) -> dict[str, Any]:
    """Returns baseline manifest dictionary for requested resource kind."""
    if kind == "Service":
        return synthesize_service_manifest(object_name, namespace)
    elif kind == "ConfigMap":
        return synthesize_configmap_manifest(object_name, namespace)
    elif kind == "Secret":
        return synthesize_secret_manifest(object_name, namespace)
    else:
        return {
            "apiVersion": "v1",
            "kind": kind,
            "metadata": {"name": object_name, "namespace": namespace},
        }
